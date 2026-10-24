#!/usr/bin/env python3
"""Acquire reproducible public NDVI and Landsat LST composites for a boundary."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import warnings
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import numpy as np
import planetary_computer as pc
import rasterio
import requests
from affine import Affine
from pystac import Item
from pystac_client import Client
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.vrt import WarpedVRT

from ahmedabad_scanner.environment import (
    landsat_clear_mask,
    landsat_surface_temperature_c,
    normalized_difference_vegetation_index,
    sentinel_clear_mask,
    sentinel_surface_reflectance,
)

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boundary", type=Path, default=Path("data/external/boundary/ahmedabad-gandhinagar-black-line.gpkg"))
    parser.add_argument("--date-range", default="2026-04-01/2026-05-31")
    parser.add_argument("--analysis-crs", default="EPSG:32643")
    parser.add_argument("--landsat-max-cloud-pct", type=float, default=20.0)
    parser.add_argument("--sentinel-max-cloud-pct", type=float, default=20.0)
    parser.add_argument("--max-scenes", type=int, default=12)
    parser.add_argument("--sentinel-mgrs-tile", default="43QBF")
    parser.add_argument("--output-dir", type=Path, default=Path("data/derived/environment-ahmedabad-gandhinagar"))
    parser.add_argument("--report", type=Path, default=Path("reports/ahmedabad_gandhinagar_remote_sensing_audit.json"))
    return parser.parse_args()


def aligned_grid(bounds: tuple[float, float, float, float], resolution: float) -> tuple[Affine, int, int]:
    min_x, min_y, max_x, max_y = bounds
    left = math.floor(min_x / resolution) * resolution
    bottom = math.floor(min_y / resolution) * resolution
    right = math.ceil(max_x / resolution) * resolution
    top = math.ceil(max_y / resolution) * resolution
    return from_origin(left, top, resolution, resolution), int(round((right - left) / resolution)), int(round((top - bottom) / resolution))


def select_evenly(items: list[Item], maximum: int) -> list[Item]:
    ordered = sorted(items, key=lambda item: item.datetime or datetime.min.replace(tzinfo=UTC))
    if len(ordered) <= maximum:
        return ordered
    indices = np.linspace(0, len(ordered) - 1, maximum).round().astype(int)
    return [ordered[index] for index in dict.fromkeys(indices)]


def read_asset(item: Item, key: str, *, crs: str, transform: Affine, width: int, height: int, resampling: Resampling) -> np.ndarray:
    signed = pc.sign(item.assets[key])
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".TIF,.tif"):
        with rasterio.open(signed.href) as source, WarpedVRT(source, crs=crs, transform=transform, width=width, height=height, resampling=resampling) as vrt:
            return vrt.read(1)


def sentinel_scaling(item: Item) -> tuple[float, float]:
    signed = pc.sign(item.assets["product-metadata"])
    response = requests.get(signed.href, timeout=120)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    quantification = None
    offsets = []
    for element in root.iter():
        name = element.tag.rsplit("}", 1)[-1]
        if name == "BOA_QUANTIFICATION_VALUE" and element.text:
            quantification = float(element.text)
        elif name == "BOA_ADD_OFFSET" and element.text:
            offsets.append(float(element.text))
    if quantification is None or not offsets or len(set(offsets)) != 1:
        raise ValueError(f"Could not resolve Sentinel-2 scaling metadata for {item.id}")
    return offsets[0], quantification


def nanmedian(arrays: list[np.ndarray]) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmedian(np.stack(arrays).astype("float32"), axis=0).astype("float32")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_raster(path: Path, data: np.ndarray, *, crs: str, transform: Affine, nodata: float | int, tags: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    output = np.where(np.isfinite(data), data, nodata).astype("float32")
    with rasterio.open(path, "w", driver="GTiff", height=output.shape[0], width=output.shape[1], count=1, dtype="float32", crs=crs, transform=transform, nodata=nodata, compress="deflate", tiled=True) as dst:
        dst.write(output, 1)
        dst.update_tags(**tags)


def main() -> int:
    args = parse_args()
    boundary = gpd.read_file(args.boundary).to_crs("EPSG:4326")
    bbox = tuple(float(value) for value in boundary.total_bounds)
    metric_boundary = boundary.to_crs(args.analysis_crs)
    bounds = tuple(float(value) for value in metric_boundary.total_bounds)
    catalog = Client.open(STAC_URL)
    landsat_candidates = list(catalog.search(collections=["landsat-c2-l2"], bbox=bbox, datetime=args.date_range, query={"eo:cloud_cover": {"lt": args.landsat_max_cloud_pct}}).items())
    sentinel_candidates = [item for item in catalog.search(collections=["sentinel-2-l2a"], bbox=bbox, datetime=args.date_range, query={"eo:cloud_cover": {"lt": args.sentinel_max_cloud_pct}}).items() if item.properties.get("s2:mgrs_tile") == args.sentinel_mgrs_tile]
    landsat_items = select_evenly(landsat_candidates, args.max_scenes)
    sentinel_items = select_evenly(sentinel_candidates, args.max_scenes)
    if not landsat_items or not sentinel_items:
        raise RuntimeError(f"Matched no usable scenes: Landsat={len(landsat_items)}, Sentinel-2={len(sentinel_items)}")
    lst_transform, lst_width, lst_height = aligned_grid(bounds, 30.0)
    lst_scenes = []
    for item in landsat_items:
        raw = read_asset(item, "lwir11", crs=args.analysis_crs, transform=lst_transform, width=lst_width, height=lst_height, resampling=Resampling.bilinear)
        qa = read_asset(item, "qa_pixel", crs=args.analysis_crs, transform=lst_transform, width=lst_width, height=lst_height, resampling=Resampling.nearest)
        data = landsat_surface_temperature_c(raw)
        data[~landsat_clear_mask(qa)] = np.nan
        data[(data < 10) | (data > 75)] = np.nan
        lst_scenes.append(data)
    ndvi_transform, ndvi_width, ndvi_height = aligned_grid(bounds, 10.0)
    ndvi_scenes = []
    for item in sentinel_items:
        red_raw = read_asset(item, "B04", crs=args.analysis_crs, transform=ndvi_transform, width=ndvi_width, height=ndvi_height, resampling=Resampling.bilinear)
        nir_raw = read_asset(item, "B08", crs=args.analysis_crs, transform=ndvi_transform, width=ndvi_width, height=ndvi_height, resampling=Resampling.bilinear)
        scl = read_asset(item, "SCL", crs=args.analysis_crs, transform=ndvi_transform, width=ndvi_width, height=ndvi_height, resampling=Resampling.nearest)
        offset, quantification = sentinel_scaling(item)
        ndvi = normalized_difference_vegetation_index(sentinel_surface_reflectance(nir_raw, additive_offset=offset, quantification_value=quantification), sentinel_surface_reflectance(red_raw, additive_offset=offset, quantification_value=quantification))
        ndvi[~sentinel_clear_mask(scl)] = np.nan
        ndvi[(ndvi < -1) | (ndvi > 1)] = np.nan
        ndvi_scenes.append(ndvi)
    lst = nanmedian(lst_scenes)
    ndvi = nanmedian(ndvi_scenes)
    lst_count = np.sum(np.isfinite(np.stack(lst_scenes)), axis=0).astype("uint16")
    ndvi_count = np.sum(np.isfinite(np.stack(ndvi_scenes)), axis=0).astype("uint16")
    common = {"source_catalog": STAC_URL, "date_range": args.date_range, "analysis_crs": args.analysis_crs, "generated_utc": datetime.now(UTC).isoformat()}
    lst_path = args.output_dir / "landsat-lst-celsius.tif"
    lst_count_path = args.output_dir / "landsat-lst-valid-scene-count.tif"
    ndvi_path = args.output_dir / "sentinel-2-ndvi.tif"
    ndvi_count_path = args.output_dir / "sentinel-2-ndvi-valid-scene-count.tif"
    write_raster(lst_path, lst, crs=args.analysis_crs, transform=lst_transform, nodata=-9999, tags={**common, "source": "USGS Landsat Collection 2 Level-2", "band": "ST_B10/lwir11", "units": "degrees Celsius", "resolution_m": "30", "cloud_mask": "QA_PIXEL bits 0-5 removed; 10-75 C physical filter"})
    write_raster(lst_count_path, lst_count, crs=args.analysis_crs, transform=lst_transform, nodata=0, tags={**common, "units": "valid scenes per pixel"})
    write_raster(ndvi_path, ndvi, crs=args.analysis_crs, transform=ndvi_transform, nodata=-9999, tags={**common, "source": "Copernicus Sentinel-2 Level-2A", "bands": "B08,B04", "units": "unitless NDVI", "resolution_m": "10", "cloud_mask": "SCL classes 2,4,5,6 retained; baseline offset read from product metadata"})
    write_raster(ndvi_count_path, ndvi_count, crs=args.analysis_crs, transform=ndvi_transform, nodata=0, tags={**common, "units": "valid scenes per pixel"})
    manifest_path = args.output_dir / "scene_manifest.json"
    manifest_path.write_text(json.dumps({"stac_api": STAC_URL, "landsat": [item.to_dict() for item in landsat_items], "sentinel_2": [item.to_dict() for item in sentinel_items]}, indent=2) + "\n")
    with rasterio.open(lst_path) as src:
        lst_meta = {"crs": src.crs.to_string(), "resolution_m": abs(src.transform.a), "shape": [src.height, src.width], "bounds": list(src.bounds), "nodata": src.nodata, "valid_pixels": int(np.isfinite(lst).sum()), "min": float(np.nanmin(lst)), "max": float(np.nanmax(lst))}
    with rasterio.open(ndvi_path) as src:
        ndvi_meta = {"crs": src.crs.to_string(), "resolution_m": abs(src.transform.a), "shape": [src.height, src.width], "bounds": list(src.bounds), "nodata": src.nodata, "valid_pixels": int(np.isfinite(ndvi).sum()), "min": float(np.nanmin(ndvi)), "max": float(np.nanmax(ndvi))}
    report = {"generated_utc": datetime.now(UTC).isoformat(), "status": "complete", "study_boundary": {"path": str(args.boundary), "bbox_wgs84": list(bbox), "crs": "EPSG:4326"}, "processing": {"date_range": args.date_range, "analysis_crs": args.analysis_crs, "landsat_cloud_threshold_pct": args.landsat_max_cloud_pct, "sentinel_cloud_threshold_pct": args.sentinel_max_cloud_pct, "sentinel_mgrs_tile": args.sentinel_mgrs_tile, "max_scenes": args.max_scenes, "composite": "per-pixel median after masking", "buffer_m": 0}, "landsat": {"collection": "landsat-c2-l2", "scene_count": len(landsat_items), "scene_ids": [item.id for item in landsat_items], "product": "ST_B10/lwir11", "metadata": lst_meta}, "sentinel_2": {"collection": "sentinel-2-l2a", "scene_count": len(sentinel_items), "scene_ids": [item.id for item in sentinel_items], "mgrs_tile": args.sentinel_mgrs_tile, "metadata": ndvi_meta}, "outputs": {"lst": {"path": str(lst_path), "sha256": sha256(lst_path)}, "lst_valid_scene_count": {"path": str(lst_count_path), "sha256": sha256(lst_count_path)}, "ndvi": {"path": str(ndvi_path), "sha256": sha256(ndvi_path)}, "ndvi_valid_scene_count": {"path": str(ndvi_count_path), "sha256": sha256(ndvi_count_path)}, "scene_manifest": {"path": str(manifest_path), "sha256": sha256(manifest_path)}}, "limitations": ["LST is satellite-observed surface skin temperature near the Landsat overpass, not air temperature or human thermal exposure.", "The median composites combine multiple dates in the configured window and do not represent a single day or heatwave; with max-scenes=1 this is a single scene, not a temporal composite.", "NDVI is a vegetation greenness index, not tree canopy, shade, vegetation quality, or accessibility.", "Cloud masks and scene-level cloud thresholds reduce but do not eliminate residual cloud, haze, shadow, mixed-pixel, and atmospheric/reprojection effects.", "Only Sentinel-2 MGRS tile 43QBF is included; areas outside that tile are not represented in the NDVI composite.", "The boundary is user-supplied and is not asserted to be an official administrative boundary."]}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    args.report.with_suffix(".md").write_text("# Ahmedabad–Gandhinagar remote-sensing audit\n\n" + "\n".join([f"- Status: `{report['status']}`", f"- Date window: `{args.date_range}`", f"- Landsat scenes: `{len(landsat_items)}`; 30 m `ST_B10/lwir11`, Celsius", f"- Sentinel-2 scenes: `{len(sentinel_items)}`; 10 m `B08/B04`, unitless NDVI", f"- CRS: `{args.analysis_crs}`", f"- Outputs: `{args.output_dir}`", "- Public source: Microsoft Planetary Computer STAC; no credentials used.", "- No address or geocoder enrichment is part of this workflow."]) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
