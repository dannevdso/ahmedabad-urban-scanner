#!/usr/bin/env python3
"""Build versioned FlatGeobuf/raster Local Area Profile assets."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ahmedabad_scanner.local_profile_assets import build_assets, build_building_location_asset


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--audit-center", nargs=2, type=float, metavar=("EASTING", "NORTHING"), default=(251800.0, 2556000.0))
    parser.add_argument("--build-building-locations", action="store_true")
    parser.add_argument("--buildings-source", type=Path, default=Path.home() / ".hermes/attachments/buildings.gpkg")
    parser.add_argument("--zones-source", type=Path, default=Path.home() / ".hermes/attachments/amc_zones.geojson")
    args = parser.parse_args()
    output = args.output or args.root / "web/public/data/local-profile"
    if args.build_building_locations:
        manifest = build_building_location_asset(args.buildings_source, args.zones_source, output)
        print(json.dumps({"output": str(output), "asset": manifest["asset"], "audit": manifest["audit"]}, indent=2))
        return 0
    manifest = build_assets(args.root, output, audit_center=tuple(args.audit_center))
    print(json.dumps({"output": str(output), "runtime_seconds": manifest["build_runtime_seconds"], "assets": sorted(manifest["assets"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
