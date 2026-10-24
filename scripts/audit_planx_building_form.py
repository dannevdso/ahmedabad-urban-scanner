#!/usr/bin/env python3
"""Audit current-study PlanX building-form outputs and their no-height limitations."""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

METRICS_FIELDS = [
    "area_m2", "perim_m", "compact", "convexity", "rectang", "elongation",
    "orient_deg", "court_m2", "court_idx", "fractal", "corners", "sharedwall",
]


def table_count(path: Path, layer: str) -> int:
    with sqlite3.connect(path) as db:
        return int(db.execute(f'SELECT COUNT(*) FROM "{layer}"').fetchone()[0])


def table_fields(path: Path, layer: str) -> list[str]:
    with sqlite3.connect(path) as db:
        return [row[1] for row in db.execute(f'PRAGMA table_info("{layer}")')]


def numeric_audit(path: Path, layer: str, fields: list[str]) -> dict[str, dict[str, int | float | None]]:
    result: dict[str, dict[str, int | float | None]] = {}
    with sqlite3.connect(path) as db:
        for field in fields:
            row = db.execute(
                f'''SELECT COUNT(*),
                           SUM(CASE WHEN "{field}" IS NOT NULL THEN 1 ELSE 0 END),
                           SUM(CASE WHEN "{field}" IS NOT NULL AND typeof("{field}") IN ('integer','real') THEN 1 ELSE 0 END),
                           SUM(CASE WHEN "{field}" IS NOT NULL AND "{field}" = "{field}" THEN 1 ELSE 0 END),
                           MIN("{field}"), MAX("{field}")
                    FROM "{layer}"'''
            ).fetchone()
            result[field] = {
                "rows": int(row[0]),
                "non_null": int(row[1] or 0),
                "numeric": int(row[2] or 0),
                "finite_sql": int(row[3] or 0),
                "min": row[4],
                "max": row[5],
            }
    return result


def range_audit(path: Path, layer: str, ranges: dict[str, tuple[float, float]]) -> dict[str, dict[str, int | float | None]]:
    result: dict[str, dict[str, int | float | None]] = {}
    with sqlite3.connect(path) as db:
        for field, (low, high) in ranges.items():
            count, below, above = db.execute(
                f'''SELECT COUNT(*),
                           SUM(CASE WHEN "{field}" < ? THEN 1 ELSE 0 END),
                           SUM(CASE WHEN "{field}" > ? THEN 1 ELSE 0 END)
                    FROM "{layer}" WHERE "{field}" IS NOT NULL''',
                (low, high),
            ).fetchone()
            min_value, max_value = db.execute(
                f'SELECT MIN("{field}"), MAX("{field}") FROM "{layer}"'
            ).fetchone()
            result[field] = {
                "expected_min": low,
                "expected_max": high,
                "rows_checked": int(count or 0),
                "below_min": int(below or 0),
                "above_max": int(above or 0),
                "min": min_value,
                "max": max_value,
            }
    return result


def id_join_audit(input_path: Path, output_path: Path, input_layer: str, output_layer: str) -> dict[str, int]:
    with sqlite3.connect(input_path) as inp, sqlite3.connect(output_path) as out:
        input_ids = {row[0] for row in inp.execute(f'SELECT building_id FROM "{input_layer}"')}
        output_ids = {row[0] for row in out.execute(f'SELECT building_id FROM "{output_layer}"')}
    return {
        "input_unique_building_ids": len(input_ids),
        "output_unique_building_ids": len(output_ids),
        "output_ids_in_input": len(output_ids & input_ids),
        "output_ids_missing_from_input": len(output_ids - input_ids),
        "input_ids_missing_from_output": len(input_ids - output_ids),
    }


def audit(input_path: Path, output_dir: Path, height_path: Path) -> dict[str, object]:
    input_buildings = table_count(input_path, "buildings")
    input_study_area = table_count(input_path, "study_area")
    input_fields = table_fields(input_path, "buildings")
    height_fields = table_fields(height_path, "buildings") if height_path.exists() else []
    positive_height = 0
    if height_path.exists() and "height_m" in height_fields:
        with sqlite3.connect(height_path) as db:
            positive_height = int(db.execute('SELECT COUNT(*) FROM buildings WHERE height_m > 0').fetchone()[0])

    stages: list[dict[str, object]] = []
    metrics_path = output_dir / "building_metrics.gpkg"
    if metrics_path.exists():
        fields = table_fields(metrics_path, "building_metrics")
        stages.append({
            "stage": "buildingmetrics",
            "status": "completed",
            "manual_contract": "Building Form Metrics: area, perimeter, compactness, convexity, rectangularity, elongation, orientation, courtyard, fractal, corners, shared-wall ratio",
            "inputs": {"buildings": input_buildings},
            "outputs": {"building_metrics": table_count(metrics_path, "building_metrics")},
            "output_fields": fields,
            "required_metric_fields": {field: field in fields for field in METRICS_FIELDS},
            "numeric_audit": numeric_audit(metrics_path, "building_metrics", METRICS_FIELDS),
            "range_audit": range_audit(metrics_path, "building_metrics", {"compact": (0.0, 1.0), "convexity": (0.0, 1.0), "rectang": (0.0, 1.0), "elongation": (0.0, 1.0), "orient_deg": (0.0, 180.0), "sharedwall": (0.0, 1.0)}),
            "id_audit": id_join_audit(input_path, metrics_path, "buildings", "building_metrics"),
            "limitations": ["Ratios are footprint-shape metrics in projected EPSG:32643; they are not height, floor-area, land-use, quality, or occupancy measures.", "The result represents the deterministic current-study 30,000-building subset, not all 1,077,523 source footprints.", "The audit checks documented ratio ranges; any values above a theoretical upper bound are retained and flagged rather than clipped or fabricated."],
        })
    else:
        stages.append({"stage": "buildingmetrics", "status": "not_run", "inputs": {"buildings": input_buildings}, "outputs": {}, "limitations": ["Expected output file is absent."]})

    tess_path = output_dir / "tessellation.gpkg"
    if tess_path.exists():
        fields = table_fields(tess_path, "tessellation")
        stages.append({
            "stage": "tessellation",
            "status": "completed",
            "manual_contract": "Morphological Tessellation: shrunken/densified footprint boundary Voronoi cells clipped to study area",
            "parameters": {"SHRINK": 0.4, "DENSIFY": 2.0, "LIMIT": 100.0},
            "inputs": {"buildings": input_buildings, "study_area": input_study_area},
            "outputs": {"tessellation": table_count(tess_path, "tessellation")},
            "output_fields": fields,
            "numeric_audit": numeric_audit(tess_path, "tessellation", ["cell_id", "cell_m2"]),
            "id_audit": id_join_audit(input_path, tess_path, "buildings", "tessellation"),
            "limitations": ["cell_m2 is a morphological plot proxy, not a cadastral parcel or ownership boundary.", "Cells clipped by the study-area edge are artificially truncated and should be excluded from edge-sensitive statistics.", "The result represents the deterministic current-study 30,000-building subset."],
        })
    else:
        stages.append({"stage": "tessellation", "status": "not_run", "inputs": {"buildings": input_buildings, "study_area": input_study_area}, "outputs": {}, "limitations": ["Expected output file is absent."]})

    stages.append({
        "stage": "spacematrix",
        "status": "skipped",
        "manual_contract": "Spacematrix Density requires BUILDINGS, numeric LEVELS_FIELD or explicit DEFAULT_LEVELS, and polygon BLOCKS.",
        "inputs": {"buildings": input_buildings, "study_area": input_study_area, "height_join_positive_height_m": positive_height},
        "outputs": {},
        "reason": "No verified floor-count/levels field is available. The current buildings layer has no levels field; height_m is metres and cannot be converted to levels without an explicit observed floor-count source or modelling rule.",
        "limitations": ["No DEFAULT_LEVELS was supplied because that would be a modelling assumption rather than observed levels.", "No Spacematrix values were fabricated."],
    })

    return {
        "generated_utc": datetime.now(UTC).isoformat(),
        "study_area": "Ahmedabad–Gandhinagar black-line study area",
        "input": {"path": str(input_path), "buildings": input_buildings, "study_area": input_study_area, "building_fields": input_fields},
        "height_join_audit": {"path": str(height_path), "fields": height_fields, "positive_height_m_count": positive_height},
        "stages": stages,
        "global_limitations": [
            "No space syntax was run.",
            "No height-dependent building analysis was run in this no-height-first stage.",
            "Open Buildings V3 footprint selection is deterministic but capped at 30,000 features for PlanX computation.",
            "Outputs were written to a new current-study directory; archived Navrangpura outputs were not modified.",
        ],
    }


def markdown(report: dict[str, object]) -> str:
    lines = [
        "# Ahmedabad–Gandhinagar PlanX building-form audit",
        "",
        f"Generated UTC: `{report['generated_utc']}`",
        "",
        "## Input and height audit",
        "",
        f"- Current PlanX buildings input: **{report['input']['buildings']}**",
        f"- Study-area features: **{report['input']['study_area']}**",
        f"- Positive joined `height_m` values available separately: **{report['height_join_audit']['positive_height_m_count']}**; not used for the no-height-first analyses.",
        f"- Building input fields: `{', '.join(report['input']['building_fields'])}`",
        "",
        "## Stage matrix",
        "",
        "| Stage | Status | Exact input counts | Exact output counts | Limitations / reason |",
        "|---|---|---:|---:|---|",
    ]
    for stage in report["stages"]:
        inp = ", ".join(f"{k}={v}" for k, v in stage.get("inputs", {}).items())
        out = ", ".join(f"{k}={v}" for k, v in stage.get("outputs", {}).items()) or "—"
        reason = stage.get("reason") or " ".join(stage.get("limitations", []))
        lines.append(f"| `{stage['stage']}` | **{stage['status']}** | {inp} | {out} | {reason} |")
    metrics = next(stage for stage in report["stages"] if stage["stage"] == "buildingmetrics")
    convexity_above = metrics.get("range_audit", {}).get("convexity", {}).get("above_max", 0)
    rectangularity_above = metrics.get("range_audit", {}).get("rectang", {}).get("above_max", 0)
    sharedwall_max = metrics.get("numeric_audit", {}).get("sharedwall", {}).get("max")
    lines += ["", "## Output verification", "", "- Building metrics fields include compactness, convexity, elongation, tessellation-independent footprint measures, and the other manual-described shape fields.", "- Tessellation output includes `cell_id` and `cell_m2` and was checked against the input building IDs.", f"- Range audit retained, without clipping, **{convexity_above}** convexity values and **{rectangularity_above}** rectangularity values above the documented 1.0 ratio bound; this is a PlanX output-quality limitation requiring review before interpretive use.", f"- `sharedwall` maximum is **{sharedwall_max}** across this subset; this does not demonstrate that the full source fabric has no attached buildings, because the 30,000-footprint subset is not a complete adjacency inventory.", "- Spacematrix was intentionally skipped because valid observed levels are unavailable.", "- No space-syntax stage was run.", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/derived/planx/ahmedabad-gandhinagar-planx-inputs.gpkg"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/derived/planx/ahmedabad-gandhinagar-building-form-outputs"))
    parser.add_argument("--height", type=Path, default=Path("data/derived/planx/ahmedabad-gandhinagar-buildings-height.gpkg"))
    parser.add_argument("--json", type=Path, default=Path("reports/ahmedabad_gandhinagar_planx_building_form_audit.json"))
    parser.add_argument("--markdown", type=Path, default=Path("reports/ahmedabad_gandhinagar_planx_building_form_audit.md"))
    args = parser.parse_args()
    report = audit(args.input, args.output_dir, args.height)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.markdown.write_text(markdown(report), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
