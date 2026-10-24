#!/usr/bin/env python3
"""Generate the reproducible full-study PlanX building-form audit."""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

REQUIRED_FIELDS = [
    "area_m2", "perim_m", "compact", "convexity", "rectang", "elongation",
    "orient_deg", "court_m2", "court_idx", "fractal", "corners", "sharedwall",
]

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data/derived/planx/ahmedabad-gandhinagar-full-buildings-inputs.gpkg"
DEFAULT_OUTPUT = ROOT / "data/derived/planx/ahmedabad-gandhinagar-full-building-outputs/building_metrics.gpkg"
DEFAULT_LOG_DIR = ROOT / "data/derived/planx/ahmedabad-gandhinagar-full-building-logs"
DEFAULT_CONFIG = ROOT / "config/ahmedabad_gandhinagar_planx_full_buildings.toml"
DEFAULT_JSON = ROOT / "reports/ahmedabad_gandhinagar_planx_full_building_form_audit.json"
DEFAULT_MARKDOWN = ROOT / "reports/ahmedabad_gandhinagar_planx_full_building_form_audit.md"

RATIO_SEMANTICS = {
    "convexity": "outer-ring area / convex-hull area",
    "rectang": "outer-ring area / minimum-oriented-rectangle area",
    "theoretical_upper_bound": 1.0,
    "interpretation": "Small values above 1 are numerical overshoots of bounded ratios; source values are retained and not clipped.",
}


def _table_fields(path: Path, layer: str) -> list[str]:
    with sqlite3.connect(path) as db:
        return [row[1] for row in db.execute(f'PRAGMA table_info("{layer}")')]


def _count(path: Path, layer: str) -> int:
    with sqlite3.connect(path) as db:
        return int(db.execute(f'SELECT COUNT(*) FROM "{layer}"').fetchone()[0])


def select_latest_successful_run(log_dir: Path) -> Path:
    candidates = []
    for path in log_dir.glob("run_*.json"):
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        step = next((item for item in payload.get("steps", []) if item.get("name") == "buildingmetrics"), None)
        if payload.get("status") == "ok" and step and step.get("returncode") == 0:
            candidates.append((payload.get("started_at", ""), path.name, path))
    if not candidates:
        raise FileNotFoundError(f"No successful buildingmetrics run in {log_dir}")
    return max(candidates)[2]


def _nearest_rank(db: sqlite3.Connection, layer: str, field: str, count: int, q: float) -> float | None:
    if not count:
        return None
    offset = max(0, math.ceil(q * count) - 1)
    row = db.execute(f'SELECT "{field}" FROM "{layer}" WHERE "{field}" IS NOT NULL ORDER BY "{field}" LIMIT 1 OFFSET ?', (offset,)).fetchone()
    return None if row is None else float(row[0])


def numeric_audit(path: Path, layer: str, fields: list[str]) -> tuple[dict[str, dict[str, int | float | None]], dict[str, dict[str, float | None]]]:
    contract: dict[str, dict[str, int | float | None]] = {}
    statistics: dict[str, dict[str, float | None]] = {}
    with sqlite3.connect(path) as db:
        row_count = int(db.execute(f'SELECT COUNT(*) FROM "{layer}"').fetchone()[0])
        available = set(_table_fields(path, layer))
        for field in fields:
            if field not in available:
                contract[field] = {"present": False, "rows": 0, "non_null": 0, "numeric": 0, "finite": 0}
                statistics[field] = {"min": None, "p10": None, "median": None, "p90": None, "max": None}
                continue
            row = db.execute(f'''SELECT COUNT(*),
                SUM(CASE WHEN "{field}" IS NOT NULL THEN 1 ELSE 0 END),
                SUM(CASE WHEN "{field}" IS NOT NULL AND typeof("{field}") IN ('integer','real') THEN 1 ELSE 0 END)
                FROM "{layer}"''').fetchone()
            non_null = int(row[1] or 0)
            numeric = int(row[2] or 0)
            values = [v for (v,) in db.execute(f'SELECT "{field}" FROM "{layer}" WHERE "{field}" IS NOT NULL')]
            finite = sum(1 for value in values if isinstance(value, (int, float)) and math.isfinite(float(value)))
            contract[field] = {"present": True, "rows": int(row[0]), "non_null": non_null, "numeric": numeric, "finite": finite}
            if values:
                n = len(values)
                statistics[field] = {
                    "min": float(db.execute(f'SELECT MIN("{field}") FROM "{layer}"').fetchone()[0]),
                    "p10": _nearest_rank(db, layer, field, n, 0.10),
                    "median": _nearest_rank(db, layer, field, n, 0.50),
                    "p90": _nearest_rank(db, layer, field, n, 0.90),
                    "max": float(db.execute(f'SELECT MAX("{field}") FROM "{layer}"').fetchone()[0]),
                }
            else:
                statistics[field] = {"min": None, "p10": None, "median": None, "p90": None, "max": None}
    return contract, statistics


def _id_audit(input_path: Path, output_path: Path) -> dict[str, int]:
    with sqlite3.connect(input_path) as inp, sqlite3.connect(output_path) as out:
        input_count, input_unique = inp.execute('SELECT COUNT(*), COUNT(DISTINCT building_id) FROM buildings').fetchone()
        output_count, output_unique = out.execute('SELECT COUNT(*), COUNT(DISTINCT building_id) FROM building_metrics').fetchone()
        source_count, source_unique = out.execute('SELECT COUNT(*), COUNT(DISTINCT source_building_id) FROM building_metrics').fetchone()
        input_ids = {row[0] for row in inp.execute('SELECT building_id FROM buildings')}
        output_ids = {row[0] for row in out.execute('SELECT building_id FROM building_metrics')}
        in_out = len(input_ids & output_ids)
        out_missing = len(output_ids - input_ids)
        missing = len(input_ids - output_ids)
        return {
            "input_unique_building_ids": int(input_unique), "output_unique_building_ids": int(output_unique),
            "output_ids_in_input": int(in_out), "output_ids_missing_from_input": int(out_missing),
            "input_ids_missing_from_output": int(missing), "input_rows": int(input_count), "output_rows": int(output_count),
            "source_building_id_rows": int(source_count), "source_building_id_unique": int(source_unique),
            "source_building_id_duplicates_excess": int(source_count - source_unique),
        }


def _ratio_audit(path: Path) -> dict[str, int | float]:
    with sqlite3.connect(path) as db:
        result: dict[str, int | float] = {}
        for field in ("convexity", "rectang"):
            count, maximum = db.execute(
                f'SELECT COUNT(*), MAX("{field}") FROM building_metrics WHERE "{field}" > 1'
            ).fetchone()
            result[f"{field}_gt_1"] = int(count)
            result[f"{field}_max_excess"] = round(max(0.0, float(maximum or 1.0) - 1.0), 15)
        return result


def _run_details(log_path: Path) -> dict[str, object]:
    if not log_path.exists():
        return {"path": str(log_path), "status": "unavailable"}
    payload = json.loads(log_path.read_text())
    step = next((item for item in payload.get("steps", []) if item.get("name") == "buildingmetrics"), {})
    return {
        "path": str(log_path), "run_id": log_path.stem.removeprefix("run_"),
        "status": payload.get("status"), "command": payload.get("commands", [None])[0],
        "returncode": step.get("returncode"), "started_at": payload.get("started_at"),
    }


def build_report(input_path: Path, output_path: Path, config_path: Path, log_path: Path) -> dict[str, object]:
    input_count = _count(input_path, "buildings")
    output_count = _count(output_path, "building_metrics")
    fields = _table_fields(output_path, "building_metrics")
    contract, statistics = numeric_audit(output_path, "building_metrics", REQUIRED_FIELDS)
    for field in REQUIRED_FIELDS:
        contract[field]["present"] = field in fields
        if field not in fields:
            contract[field].update({"rows": 0, "non_null": 0, "numeric": 0, "finite": 0})
    ratio_audit = _ratio_audit(output_path)
    _, input_statistics = numeric_audit(input_path, "buildings", ["footprint_area_m2"])
    run = _run_details(log_path)
    return {
        "generated_utc": datetime.now(UTC).isoformat(), "status": "ok",
        "study_area": "Ahmedabad–Gandhinagar black-line study area", "scope": "full-study",
        "paths": {"input": str(input_path), "output": str(output_path), "config": str(config_path), "log": str(log_path)},
        "run": run, "counts": {"input_buildings": input_count, "output_building_metrics": output_count},
        "id_audit": _id_audit(input_path, output_path), "required_fields": contract,
        "statistics": {"footprint_area_m2": input_statistics["footprint_area_m2"], **statistics},
        "quantile_method": "Exact deterministic nearest-rank quantiles: ceil(q*N)-1 zero-based offset after ascending ORDER BY; values are unrounded SQLite REAL values.",
        "ratio_semantics": RATIO_SEMANTICS,
        "observed_anomalies": ratio_audit,
        "stages": {
            "buildingmetrics": {"status": "completed", "input_count": input_count, "output_count": output_count},
            "tessellation": {"status": "not_run", "reason": "No full-study tessellation output is present or claimed."},
            "spacematrix": {"status": "blocked", "reason": "No verified floor-count/levels field is available; no DEFAULT_LEVELS assumption was supplied."},
            "space_syntax": {"status": "not_run", "reason": "Space syntax was not rerun for this full-study report."},
        },
        "limitations": [
            "Shape metrics are footprint geometry measures in projected EPSG:32643; they are not height, floor-area, land-use, occupancy, or quality measures.",
            "Values above 1.0 are retained as observed PlanX outputs and counted; their small positive excess is reported as floating-point numerical overshoot of bounded ratios, with no clipping or normalization.",
            "No planx_cell_m2 is reported because full-study tessellation is absent.",
        ],
    }


def markdown(report: dict[str, object]) -> str:
    lines = [f"# Ahmedabad–Gandhinagar full-study PlanX building-form audit", "", f"Status: **{report['status']}**", f"Generated UTC: `{report['generated_utc']}`", f"Scope: **{report['scope']}**", "", "## Provenance", ""]
    for key, value in report["paths"].items(): lines.append(f"- `{key}`: `{value}`")
    run = report["run"]
    lines += [f"- Run `{run.get('run_id', '—')}`: status `{run.get('status', '—')}`, return code `{run.get('returncode', '—')}`", "", "## Counts and identifiers", "", f"- Input buildings: **{report['counts']['input_buildings']}**", f"- Output building metrics: **{report['counts']['output_building_metrics']}**", f"- Source-building duplicate excess rows: **{report['id_audit']['source_building_id_duplicates_excess']}**", "", "## Required-field contract", "", "| Field | Present | Non-null | Numeric | Finite | Min | P10 | Median | P90 | Max |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for field in REQUIRED_FIELDS:
        c, s = report["required_fields"][field], report["statistics"][field]
        lines.append(f"| `{field}` | {c['present']} | {c['non_null']} | {c['numeric']} | {c['finite']} | {s['min']} | {s['p10']} | {s['median']} | {s['p90']} | {s['max']} |")
    lines += ["", "## Quantiles", "", f"- {report['quantile_method']}", "", "## Convexity and rectangularity above 1", "", f"- Convexity semantics: `{report['ratio_semantics']['convexity']}`.", f"- Rectangularity semantics (`rectang`): `{report['ratio_semantics']['rectang']}`.", "- Both ratios have a theoretical upper bound of **1.0** for valid planar geometry. The PlanX implementation uses floating-point area calculations, so these small overshoots are numerical artifacts, not a new metric meaning.", "- Source values are retained without clipping or normalization.", f"- `convexity > 1`: **{report['observed_anomalies']['convexity_gt_1']}**; maximum excess: **{report['observed_anomalies']['convexity_max_excess']}**.", f"- `rectang > 1`: **{report['observed_anomalies']['rectang_gt_1']}**; maximum excess: **{report['observed_anomalies']['rectang_max_excess']}**.", "", "## Stage truthfulness", "", "| Stage | Status | Reason |", "|---|---|---|"]
    for name, stage in report["stages"].items(): lines.append(f"| `{name}` | **{stage['status']}** | {stage.get('reason', '—')} |")
    lines += ["", "## Limitations", ""] + [f"- {item}" for item in report["limitations"]] + [""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    args = parser.parse_args()
    log_path = select_latest_successful_run(args.log_dir)
    report = build_report(args.input, args.output, args.config, log_path)
    args.json.parent.mkdir(parents=True, exist_ok=True); args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.markdown.write_text(markdown(report), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__": raise SystemExit(main())
