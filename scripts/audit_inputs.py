"""Audit Ahmedabad pilot vector inputs before analysis.

The audit records source parity, schema, spatial coverage, and geometry quality.
It does not modify source data.
"""

from __future__ import annotations

import argparse
import json
import tomllib
from pathlib import Path
from typing import Any

import geopandas as gpd
from shapely.geometry import box


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/ahmedabad_pilot.toml"),
        help="Study configuration TOML",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/ahmedabad_pilot_input_audit.json"),
        help="JSON report path",
    )
    return parser.parse_args()


def rounded_bounds(values: Any) -> list[float] | None:
    bounds = [float(value) for value in values]
    if any(value != value for value in bounds):
        return None
    return [round(value, 7) for value in bounds]


def audit_layer(path: Path, study_bbox: tuple[float, float, float, float]) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False}

    layer = gpd.read_parquet(path) if path.suffix == ".parquet" else gpd.read_file(path)
    if layer.crs is None:
        in_wgs84 = layer
    else:
        in_wgs84 = layer.to_crs("EPSG:4326")

    bbox_geometry = box(*study_bbox)
    nonempty = in_wgs84.geometry.notna() & ~in_wgs84.geometry.is_empty
    valid = nonempty & in_wgs84.geometry.is_valid
    intersects = nonempty & in_wgs84.geometry.intersects(bbox_geometry)
    fully_inside = nonempty & in_wgs84.geometry.within(bbox_geometry)

    return {
        "path": str(path),
        "exists": True,
        "size_bytes": path.stat().st_size,
        "rows": int(len(layer)),
        "crs": str(layer.crs) if layer.crs else None,
        "geometry_types": {
            str(key): int(value)
            for key, value in layer.geometry.geom_type.value_counts(dropna=False).items()
        },
        "bounds_wgs84": rounded_bounds(in_wgs84.total_bounds),
        "nonempty_geometry_rows": int(nonempty.sum()),
        "valid_geometry_rows": int(valid.sum()),
        "intersects_study_bbox_rows": int(intersects.sum()),
        "fully_inside_study_bbox_rows": int(fully_inside.sum()),
        "outside_study_bbox_rows": int((nonempty & ~intersects).sum()),
        "columns": [str(column) for column in layer.columns],
    }


def main() -> None:
    args = parse_args()
    config_path = args.config.resolve()
    project_root = config_path.parent.parent
    with config_path.open("rb") as file:
        config = tomllib.load(file)

    study_bbox = tuple(float(value) for value in config["boundary"]["bbox"])
    if len(study_bbox) != 4:
        raise ValueError("boundary.bbox must be [min_lon, min_lat, max_lon, max_lat]")
    min_lon, min_lat, max_lon, max_lat = study_bbox
    if not (min_lon < max_lon and min_lat < max_lat):
        raise ValueError("boundary.bbox has invalid coordinate ordering")

    layers = {
        name: audit_layer(project_root / relative_path, study_bbox)
        for name, relative_path in config["inputs"].items()
    }
    report = {
        "project": config["project"],
        "study_bbox_wgs84": list(study_bbox),
        "analysis_crs": config["project"]["analysis_crs"],
        "layers": layers,
        "warnings": [],
    }

    for name, layer in layers.items():
        if not layer.get("exists"):
            report["warnings"].append(f"{name}: source file is missing")
            continue
        if layer["outside_study_bbox_rows"]:
            report["warnings"].append(
                f"{name}: {layer['outside_study_bbox_rows']:,} geometries do not intersect the configured bbox"
            )
        invalid_count = layer["nonempty_geometry_rows"] - layer["valid_geometry_rows"]
        if invalid_count:
            report["warnings"].append(f"{name}: {invalid_count:,} geometries are invalid")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    print(f"Saved audit: {args.output.resolve()}")


if __name__ == "__main__":
    main()
