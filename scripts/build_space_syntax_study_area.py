#!/usr/bin/env python3
"""Clip the user-supplied PlanX space-syntax layer to the selected study area."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd

from ahmedabad_scanner.space_syntax import clip_space_syntax_to_boundary

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SYNTAX = ROOT / "data/external/space-syntax/space-syntax.gpkg"
DEFAULT_BOUNDARY = ROOT / "data/external/boundary/ahmedabad-gandhinagar-black-line.gpkg"
DEFAULT_OUTPUT = ROOT / "data/derived/space_syntax/ahmedabad-gandhinagar-space-syntax-clipped.gpkg"
DEFAULT_REPORT = ROOT / "reports/ahmedabad_gandhinagar_space_syntax_clip.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--syntax", type=Path, default=DEFAULT_SYNTAX)
    parser.add_argument("--boundary", type=Path, default=DEFAULT_BOUNDARY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    syntax = gpd.read_file(args.syntax, layer="segment_analysis")
    boundary = gpd.read_file(args.boundary, layer="study_area")
    clipped = clip_space_syntax_to_boundary(syntax, boundary)
    clipped["clipped_length_m"] = clipped.geometry.length
    if clipped.crs is None:
        raise ValueError("Clipped space-syntax layer lost its CRS")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        args.output.unlink()
    clipped.to_file(args.output, layer="segment_analysis_clipped", driver="GPKG")

    report = {
        "source": str(args.syntax),
        "source_layer": "segment_analysis",
        "boundary": str(args.boundary),
        "boundary_layer": "study_area",
        "output": str(args.output),
        "output_layer": "segment_analysis_clipped",
        "crs": clipped.crs.to_string(),
        "source_rows": int(len(syntax)),
        "clipped_rows": int(len(clipped)),
        "source_rows_removed": int(len(syntax) - len(clipped)),
        "clipped_geometry_types": {str(k): int(v) for k, v in clipped.geom_type.value_counts().items()},
        "clipped_bounds": [float(value) for value in clipped.to_crs(4326).total_bounds],
        "boundary_assignment_rule": "retain segments whose geometry intersects the study polygon; clip geometry to the polygon boundary",
        "source_metrics_preserved": True,
        "clipped_length_field": "clipped_length_m",
        "source_length_field": "length_m",
        "space_syntax_rerun": False,
    }
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
