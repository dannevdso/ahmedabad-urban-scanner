#!/usr/bin/env python3
"""Validate downloaded 2023 Open Buildings Temporal tiles and clip building height."""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.io import MemoryFile
from rasterio.mask import mask
from rasterio.merge import merge
from rasterio.transform import array_bounds


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def md5_base64(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return base64.b64encode(digest.digest()).decode()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tiles-csv", type=Path, default=Path("reports/open_buildings_temporal_tiles.csv"))
    parser.add_argument("--tile-dir", type=Path, default=Path("data/external/open-buildings-height/temporal-2023"))
    parser.add_argument("--boundary", type=Path, default=Path("data/external/boundary/ahmedabad-gandhinagar-black-line.gpkg"))
    parser.add_argument("--output", type=Path, default=Path("data/external/open-buildings-height/ahmedabad-gandhinagar-building-height-2023.tif"))
    parser.add_argument("--audit", type=Path, default=Path("reports/open_buildings_height_audit.json"))
    args = parser.parse_args()

    rows = [row for row in csv.DictReader(args.tiles_csv.open()) if row["year"] == "2023"]
    checks = []
    datasets = []
    for row in rows:
        path = args.tile_dir / Path(row["url"]).name
        if not path.exists():
            raise FileNotFoundError(path)
        actual_size = path.stat().st_size
        expected_size = int(row["content_length"])
        actual_md5 = md5_base64(path)
        expected_md5 = row["remote_md5_base64"]
        if actual_size != expected_size:
            raise ValueError(f"size mismatch for {path}: {actual_size} != {expected_size}")
        if actual_md5 != expected_md5:
            raise ValueError(f"MD5 mismatch for {path}: {actual_md5} != {expected_md5}")
        source = rasterio.open(path)
        if source.count < 3 or source.descriptions[1] != "building_height":
            source.close()
            raise ValueError(f"unexpected bands in {path}: {source.descriptions}")
        datasets.append(source)
        checks.append({"path": str(path), "bytes": actual_size, "sha256": sha256(path), "md5_base64": actual_md5})

    boundary = gpd.read_file(args.boundary).to_crs("EPSG:32643")
    geometry = [boundary.geometry.unary_union.__geo_interface__]
    bounds = boundary.total_bounds.tolist()
    height, transform = merge(
        datasets,
        indexes=[2, 3],
        bounds=tuple(bounds),
        res=(30, 30),
        nodata=-99.0,
        dtype="float32",
    )
    height_band = height[0]
    presence_band = height[1]
    height_band[(presence_band < 0.2) | (height_band < 0)] = -99.0
    mosaic_profile = datasets[0].profile.copy()
    mosaic_profile.update(
        driver="GTiff",
        height=height_band.shape[0],
        width=height_band.shape[1],
        count=1,
        dtype="float32",
        crs="EPSG:32643",
        transform=transform,
        nodata=-99.0,
    )
    with MemoryFile() as memory_file:
        with memory_file.open(**mosaic_profile) as mosaic:
            mosaic.write(height_band.astype("float32"), 1)
            clipped, clipped_transform = mask(mosaic, geometry, crop=True, nodata=-99.0)
    clipped = clipped[0]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    profile = datasets[0].profile.copy()
    profile.update(
        driver="GTiff",
        height=clipped.shape[0],
        width=clipped.shape[1],
        count=1,
        dtype="float32",
        crs="EPSG:32643",
        transform=clipped_transform,
        nodata=-99.0,
        compress="deflate",
        predictor=3,
        tiled=True,
        BIGTIFF="IF_SAFER",
    )
    with rasterio.open(args.output, "w", **profile) as dst:
        dst.write(clipped.astype("float32"), 1)
        dst.set_band_description(1, "building_height")
        dst.update_tags(1, units="metres", source_year="2023", presence_threshold="0.2")
    for dataset in datasets:
        dataset.close()

    valid = clipped[clipped != -99.0]
    with rasterio.open(args.output) as output:
        audit = {
            "status": "complete",
            "source_app": "https://mmeka-ee.projects.earthengine.app/view/open-buildings-temporal-dataset",
            "collection": "GOOGLE/Research/open-buildings-temporal/v1",
            "source_year": 2023,
            "band": "building_height",
            "units": "metres",
            "presence_threshold": 0.2,
            "source_tiles": checks,
            "output": {
                "path": str(args.output),
                "bytes": args.output.stat().st_size,
                "sha256": sha256(args.output),
                "crs": output.crs.to_string(),
                "width": output.width,
                "height": output.height,
                "bounds": list(output.bounds),
                "nodata": output.nodata,
                "valid_pixels": int(valid.size),
                "valid_min_m": float(valid.min()) if valid.size else None,
                "valid_max_m": float(valid.max()) if valid.size else None,
                "valid_mean_m": float(valid.mean()) if valid.size else None,
            },
            "historical_years_downloaded": [],
        }
    args.audit.parent.mkdir(parents=True, exist_ok=True)
    args.audit.write_text(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(audit["output"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
