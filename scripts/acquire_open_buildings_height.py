#!/usr/bin/env python3
"""Prepare/start a bounded Earth Engine export of Open Buildings height.

The Earth Engine Python client and an authenticated EE session are required.
This intentionally exports only the latest published annual band (2023), not
historical rasters. The export is started as a Drive task; it is not silently
replaced by a local fake or thumbnail.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

COLLECTION = "GOOGLE/Research/open-buildings-temporal/v1"
LATEST_PUBLISHED_YEAR = 2023
INFERENCE_TIME_EPOCH_S = 1688108400  # 2023-06-30 00:00 America/Los_Angeles
BOUNDARY_DEFAULT = Path("config/study_areas/ahmedabad-gandhinagar-black-line.gpkg")
CONFIG_DEFAULT = Path("data/external/open-buildings-height/export_config.json")


def load_boundary(path: Path):
    import geopandas as gpd

    frame = gpd.read_file(path)
    if frame.empty or frame.crs is None:
        raise ValueError(f"Boundary is empty or has no CRS: {path}")
    return json.loads(frame.to_crs("EPSG:4326").to_json())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--boundary", type=Path, default=BOUNDARY_DEFAULT)
    parser.add_argument("--config", type=Path, default=CONFIG_DEFAULT)
    parser.add_argument("--scale", type=int, default=30)
    parser.add_argument("--drive-folder", default="open-buildings-height")
    parser.add_argument("--description", default="ahmedabad_open_buildings_height_2023")
    args = parser.parse_args()

    config = json.loads(args.config.read_text())
    try:
        import importlib
        ee = importlib.import_module("ee")
    except ImportError as error:
        result = {
            "status": "blocked",
            "blocker": "Earth Engine Python client is not installed in the active environment.",
            "error": repr(error),
            "reproducible_command": "uv run python scripts/acquire_open_buildings_height.py",
            "next_step": "Install the Earth Engine client, run `earthengine authenticate` interactively, then rerun this command.",
        }
        print(json.dumps(result, indent=2))
        return 2

    try:
        ee.Initialize()
    except Exception as error:
        result = {
            "status": "blocked",
            "blocker": "Earth Engine initialization/authentication failed; no export task was started.",
            "error": repr(error),
            "reproducible_command": "uv run python scripts/acquire_open_buildings_height.py",
            "next_step": "Run `earthengine authenticate` interactively (or configure an approved service account), then rerun.",
        }
        print(json.dumps(result, indent=2))
        return 3

    boundary_geojson = load_boundary(args.boundary)
    geometry = ee.Geometry(boundary_geojson["features"][0]["geometry"])
    image = (
        ee.ImageCollection(COLLECTION)
        .filter(ee.Filter.eq("inference_time_epoch_s", INFERENCE_TIME_EPOCH_S))
        .mosaic()
    )
    height = image.select("building_height").updateMask(
        image.select("building_presence").gte(config["presence_mask_threshold"])
    )
    task = ee.batch.Export.image.toDrive(
        image=height,
        description=args.description,
        folder=args.drive_folder,
        fileNamePrefix=args.description,
        region=geometry,
        scale=args.scale,
        crs=config["export_crs"],
        maxPixels=config["max_pixels"],
        fileFormat="GeoTIFF",
        formatOptions={"cloudOptimized": True},
    )
    task.start()
    result = {
        "status": "started",
        "task_id": task.id,
        "description": args.description,
        "collection": COLLECTION,
        "year": LATEST_PUBLISHED_YEAR,
        "band": "building_height",
        "units": "metres",
        "scale_m": args.scale,
        "crs": config["export_crs"],
        "boundary": str(args.boundary.resolve()),
        "started_at_local": datetime.now().astimezone().isoformat(),
        "note": "Download from Google Drive after task completion, then run the audit/metadata command documented in README.md.",
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
