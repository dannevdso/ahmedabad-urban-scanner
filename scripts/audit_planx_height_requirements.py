#!/usr/bin/env python3
"""Audit PlanX height-dependent stages and current source coverage without modifying inputs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ahmedabad_scanner.planx_height import audit_sources, requirements_as_dicts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--osm", type=Path, default=Path("data/external/osm/ahmedabad-gandhinagar-osm.gpkg"))
    parser.add_argument("--inputs", type=Path, default=Path("data/derived/planx/ahmedabad-gandhinagar-planx-inputs.gpkg"))
    parser.add_argument("--output", type=Path, default=Path("reports/ahmedabad_gandhinagar_planx_height_audit.json"))
    args = parser.parse_args()
    report = {
        "requirements": requirements_as_dicts(),
        "source_audit": audit_sources(args.osm, args.inputs),
        "commands_after_prerequisite": {
            "isovist_field_no_height": "uv run python scripts/run_planx_height_ready.py --stage isovistfield --input <projected_buildings.gpkg> --output <isovist_points.gpkg>",
            "height_field_heat": "qgis_process run planx:heatriskgrid --BUILDINGS=<height-bearing.gpkg>|layername=buildings --HEIGHT_FIELD=height_m --GREEN=<green.gpkg>|layername=green --CELL_SIZE=100 --H_REF=20 --OUTPUT=<output.gpkg>",
            "sun_hours": "qgis_process run planx:sunhours --DSM=<terrain_plus_buildings_dsm.tif> --DATE=2026-12-21T12:00:00 --UTC_OFFSET=5.5 --INTERVAL=30 --OUTPUT=<sunhours.tif>",
        },
        "preservation": "No existing outputs are overwritten; new audit artifacts use a new report path.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Saved audit: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
