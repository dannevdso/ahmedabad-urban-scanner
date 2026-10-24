#!/usr/bin/env python3
"""Audit and locally enrich Open Buildings with decoded Plus Code locations.

This intentionally stops at a decoded WGS84 location. It does not produce a
street address and never calls a geocoder or requires credentials.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

from ahmedabad_scanner.open_buildings import OPEN_BUILDINGS_COLUMNS
from ahmedabad_scanner.plus_codes import decode_full_plus_code


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boundary", type=Path, default=Path("data/external/boundary/ahmedabad-gandhinagar-black-line.gpkg"))
    parser.add_argument("--raw", type=Path, nargs="+", default=[Path("data/google-open-buildings-v3/raw/395d_buildings.csv.gz"), Path("data/google-open-buildings-v3/raw/395f_buildings.csv.gz")])
    parser.add_argument("--output", type=Path, default=Path("data/derived/ahmedabad-gandhinagar-open-buildings-pluscode.parquet"))
    parser.add_argument("--report", type=Path, default=Path("reports/open_buildings_plus_code_audit.json"))
    parser.add_argument("--chunk-size", type=int, default=250_000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    boundary = gpd.read_file(args.boundary).to_crs("EPSG:4326")
    region = boundary.geometry.union_all()
    min_lon, min_lat, max_lon, max_lat = region.bounds
    selected: list[gpd.GeoDataFrame] = []
    source_stats = []
    invalid_codes = 0
    total_rows = 0
    bbox_rows = 0
    boundary_rows = 0
    for path in args.raw:
        source_total = 0
        source_bbox = 0
        with gzip.open(path, "rt", newline="") as handle:
            for chunk in pd.read_csv(handle, header=None, names=OPEN_BUILDINGS_COLUMNS, chunksize=args.chunk_size):
                total_rows += len(chunk)
                source_total += len(chunk)
                candidate = chunk[chunk["longitude"].between(min_lon, max_lon) & chunk["latitude"].between(min_lat, max_lat)].copy()
                bbox_rows += len(candidate)
                source_bbox += len(candidate)
                if candidate.empty:
                    continue
                geometries = gpd.GeoSeries.from_wkt(candidate.pop("geometry_wkt"), crs="EPSG:4326")
                candidate = gpd.GeoDataFrame(candidate, geometry=geometries)
                candidate = candidate[candidate.geometry.intersects(region)].copy()
                boundary_rows += len(candidate)
                if candidate.empty:
                    continue
                decoded_lat = []
                decoded_lon = []
                code_valid = []
                for code in candidate["full_plus_code"].astype(str):
                    try:
                        area = decode_full_plus_code(code)
                    except ValueError:
                        invalid_codes += 1
                        decoded_lat.append(None)
                        decoded_lon.append(None)
                        code_valid.append(False)
                    else:
                        decoded_lat.append(area.latitude)
                        decoded_lon.append(area.longitude)
                        code_valid.append(True)
                candidate["plus_code_valid"] = code_valid
                candidate["plus_code_latitude"] = decoded_lat
                candidate["plus_code_longitude"] = decoded_lon
                candidate["building_id"] = candidate["full_plus_code"].astype(str)
                selected.append(candidate)
        source_stats.append({"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path), "rows": source_total, "bbox_rows": source_bbox})

    if selected:
        output = gpd.GeoDataFrame(pd.concat(selected, ignore_index=True), geometry="geometry", crs="EPSG:4326")
        output = output.drop_duplicates(subset=["building_id"], keep="first")
    else:
        output = gpd.GeoDataFrame(columns=[*OPEN_BUILDINGS_COLUMNS[:4], "full_plus_code", "plus_code_valid", "plus_code_latitude", "plus_code_longitude", "building_id", "geometry"], geometry="geometry", crs="EPSG:4326")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output.to_parquet(args.output, index=False)
    report = {
        "generated_utc": datetime.now(UTC).isoformat(),
        "status": "complete",
        "boundary": {"path": str(args.boundary), "crs": "EPSG:4326", "bounds": [min_lon, min_lat, max_lon, max_lat], "feature_count": len(boundary)},
        "source": {"provider": "Google Research Open Buildings V3", "raw_files": source_stats, "columns": OPEN_BUILDINGS_COLUMNS},
        "audit": {"raw_rows_scanned": total_rows, "bbox_candidate_rows": bbox_rows, "boundary_intersecting_rows": boundary_rows, "output_rows": len(output), "valid_full_plus_codes": int(output["plus_code_valid"].sum()) if len(output) else 0, "invalid_full_plus_codes": invalid_codes, "duplicate_ids_removed": boundary_rows - len(output)},
        "enrichment": {"decoded_fields": ["plus_code_latitude", "plus_code_longitude"], "decoded_location_crs": "EPSG:4326", "street_addresses_added": 0, "geocoder": None, "credentials_required": False},
        "limitations": ["A decoded Plus Code is a location area, not a street address.", "Street names, locality names, postal addresses, and reverse-geocoded labels require a separate geocoder/API source and are intentionally not added.", "The output is restricted to building polygons intersecting the supplied boundary; raw Open Buildings rows outside it are audited only by scan counts."],
        "output": {"path": str(args.output), "rows": len(output), "sha256": sha256(args.output)},
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    md = args.report.with_suffix(".md")
    md.write_text("# Open Buildings Plus Code audit\n\n" + "\n".join([
        f"- Status: `{report['status']}`",
        f"- Raw rows scanned: `{total_rows:,}`",
        f"- Boundary-intersecting buildings: `{len(output):,}`",
        f"- Valid full Plus Codes: `{int(output['plus_code_valid'].sum()) if len(output) else 0:,}`",
        "- Local enrichment: decoded latitude/longitude only; no geocoder, API, address claim, or credentials.",
        f"- Output: `{args.output}`",
    ]) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
