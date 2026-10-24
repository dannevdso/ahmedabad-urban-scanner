#!/usr/bin/env python3
"""Download intersecting Copernicus DEM GLO-30 tiles and clip to the study area."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import ssl
import urllib.request
from datetime import datetime, timezone

import certifi
from pathlib import Path
from xml.etree import ElementTree as ET

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.mask import mask
from rasterio.merge import merge
from shapely.geometry import box, mapping

BUCKET = "https://copernicus-dem-30m.s3.amazonaws.com"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def tile_name(lat: int, lon: int) -> str:
    ns = f"N{lat:02d}" if lat >= 0 else f"S{abs(lat):02d}"
    ew = f"E{lon:03d}" if lon >= 0 else f"W{abs(lon):03d}"
    return f"Copernicus_DSM_COG_10_{ns}_00_{ew}_00_DEM"


def download(url: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 0:
        return
    tmp = path.with_suffix(path.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "ahmedabad-urban-scanner/DEM-acquisition"})
    context = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(req, timeout=120, context=context) as src, tmp.open("wb") as dst:
        shutil.copyfileobj(src, dst, length=1024 * 1024)
    tmp.replace(path)


def xml_metadata(path: Path) -> dict[str, str]:
    root = ET.parse(path).getroot()
    result: dict[str, str] = {}
    for el in root.iter():
        text = (el.text or "").strip()
        if not text:
            continue
        tag = el.tag.rsplit("}", 1)[-1]
        if tag in {"CharacterString", "Decimal", "Integer", "Date", "DateTime"}:
            result.setdefault(tag, text)
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--boundary", default="data/external/boundary/ahmedabad-gandhinagar-black-line.gpkg")
    ap.add_argument("--output-dir", default="data/external/copernicus-dem")
    ap.add_argument("--output", default="data/external/copernicus-dem/ahmedabad-gandhinagar-copernicus-dem-glo30.tif")
    ap.add_argument("--report", default="reports/copernicus_dem_audit.json")
    args = ap.parse_args()

    boundary_path = Path(args.boundary)
    out_dir = Path(args.output_dir)
    raw_dir = out_dir / "raw"
    output = Path(args.output)
    report_path = Path(args.report)
    boundary = gpd.read_file(boundary_path)
    if boundary.crs is None:
        raise ValueError("Boundary CRS is missing")
    boundary_wgs84 = boundary.to_crs("EPSG:4326")
    geom = boundary_wgs84.geometry.union_all()
    minx, miny, maxx, maxy = geom.bounds
    # Tiles are 1-degree cells; include every cell touched by the polygon.
    lats = range(math.floor(miny), math.floor(maxy) + 1)
    lons = range(math.floor(minx), math.floor(maxx) + 1)
    selected = []
    for lat in lats:
        for lon in lons:
            cell = box(lon, lat, lon + 1, lat + 1)
            if geom.intersects(cell):
                selected.append((lat, lon, tile_name(lat, lon)))
    if not selected:
        raise ValueError("No intersecting Copernicus tiles found")

    tiles = []
    for lat, lon, name in selected:
        tile_dir = raw_dir / name
        tif_url = f"{BUCKET}/{name}/{name}.tif".replace("COG_10", "COG_10")
        xml_name = name.replace("Copernicus_DSM_COG_10_", "Copernicus_DSM_10_").removesuffix("_DEM") + ".xml"
        xml_url = f"{BUCKET}/{name}/{xml_name}"
        tif_path = tile_dir / f"{name}.tif"
        xml_path = tile_dir / xml_name
        download(tif_url, tif_path)
        download(xml_url, xml_path)
        with rasterio.open(tif_path) as src:
            schema = {
                "crs": src.crs.to_string(), "width": src.width, "height": src.height,
                "count": src.count, "dtype": src.dtypes[0], "nodata": src.nodata,
                "resolution": list(src.res), "bounds": list(src.bounds),
                "transform": list(src.transform)[:6], "area_or_point": src.tags().get("AREA_OR_POINT"),
            }
            arr = src.read(1, masked=True)
            arr = np.ma.masked_where(np.asarray(arr) >= 1e19, arr)
            schema["source_sentinel_threshold"] = 1e19
            schema["valid_min"] = float(arr.min())
            schema["valid_max"] = float(arr.max())
        tiles.append({
            "tile": name, "lat": lat, "lon": lon, "url": tif_url, "metadata_url": xml_url,
            "local_path": str(tif_path), "metadata_path": str(xml_path),
            "bytes": tif_path.stat().st_size, "sha256": sha256(tif_path), "schema": schema,
            "xml_metadata": xml_metadata(xml_path),
        })

    output.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(tiles[0]["local_path"]) as first:
        srcs = [rasterio.open(t["local_path"]) for t in tiles]
        try:
            mosaic, transform = merge(srcs, nodata=1e20)
            mosaic = np.where(mosaic >= 1e19, -9999.0, mosaic).astype("float32")
            profile = first.profile.copy()
            profile.update(height=mosaic.shape[1], width=mosaic.shape[2], transform=transform, nodata=-9999.0, compress="deflate", tiled=True, BIGTIFF="IF_SAFER")
            tmp = output.with_suffix(".tmp.tif")
            with rasterio.open(tmp, "w", **profile) as dst:
                dst.write(mosaic)
            with rasterio.open(tmp) as src:
                clipped, clipped_transform = mask(src, [mapping(geom)], crop=True, filled=False)
                profile = src.profile.copy()
                profile.update(height=clipped.shape[1], width=clipped.shape[2], transform=clipped_transform, compress="deflate", tiled=True, BIGTIFF="IF_SAFER")
                with rasterio.open(output, "w", **profile) as dst:
                    dst.write(clipped)
            tmp.unlink(missing_ok=True)
        finally:
            for src in srcs:
                src.close()

    with rasterio.open(output) as src:
        vals = src.read(1, masked=True)
        output_info = {
            "path": str(output), "bytes": output.stat().st_size, "sha256": sha256(output),
            "crs": src.crs.to_string(), "width": src.width, "height": src.height,
            "count": src.count, "dtype": src.dtypes[0], "nodata": src.nodata,
            "resolution": list(src.res), "bounds": list(src.bounds), "transform": list(src.transform)[:6],
            "valid_pixel_count": int(vals.count()), "total_pixel_count": int(vals.size),
            "valid_fraction": float(vals.count() / vals.size),
            "valid_min": float(vals.min()), "valid_max": float(vals.max()), "valid_mean": float(vals.mean()),
            "masked_pixel_count": int(np.ma.count_masked(vals)),
        }
    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source": {"provider": "Copernicus DEM", "product": "GLO-30", "bucket": BUCKET, "license_note": "Copernicus DEM data access and use are subject to the published Copernicus DEM licence/EULA."},
        "boundary": {"path": str(boundary_path), "source_crs": boundary.crs.to_string(), "wgs84_bounds": list(boundary_wgs84.total_bounds), "geometry_type": boundary.geometry.geom_type.tolist()},
        "selection_rule": "All 1-degree tiles whose cells intersect the supplied boundary polygon; no bbox-only tiles were downloaded.",
        "tiles": tiles, "output": output_info,
        "processing": {"mosaic": "rasterio.merge.merge", "clip": "rasterio.mask.mask", "nodata_preserved": True, "resampling": "none"},
        "fallback": "If direct Copernicus object access becomes unavailable, use the exact tile IDs and metadata URLs in this report, or the public Copernicus DEM registry/COG catalog, then rerun this script.",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    md = report_path.with_suffix(".md")
    md.write_text("# Copernicus DEM audit\n\n" + json.dumps(report, indent=2) + "\n")
    print(json.dumps({"output": str(output), "report": str(report_path), "tiles": len(tiles), "sha256": output_info["sha256"]}, indent=2))


if __name__ == "__main__":
    main()
