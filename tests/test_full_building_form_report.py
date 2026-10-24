from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).parents[1]

def load_module(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REPORT = load_module("scripts/audit_planx_full_building_form.py", "full_report")
WEB = load_module("scripts/build_web_data.py", "build_web_data")


def make_db(path: Path, table: str, columns: str, rows: list[tuple]) -> None:
    with sqlite3.connect(path) as db:
        db.execute(f"CREATE TABLE {table} ({columns})")
        placeholders = ",".join("?" for _ in rows[0])
        db.executemany(f"INSERT INTO {table} VALUES ({placeholders})", rows)


def test_latest_successful_run_selection_ignores_failed_and_older_runs(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "run_20261018T005947Z.json").write_text(json.dumps({"status": "ok", "started_at": "20261018T005947Z", "steps": [{"name": "buildingmetrics", "returncode": 0}]}))
    (logs / "run_20261019T005947Z.json").write_text(json.dumps({"status": "error", "started_at": "20261019T005947Z", "steps": [{"name": "buildingmetrics", "returncode": 1}]}))
    (logs / "run_20261017T225355Z.json").write_text(json.dumps({"status": "ok", "started_at": "20261017T225355Z", "steps": [{"name": "buildingmetrics", "returncode": 0}]}))
    selected = REPORT.select_latest_successful_run(logs)
    assert selected.name == "run_20261018T005947Z.json"


def test_full_report_contract_covers_ids_fields_quantiles_anomalies_and_truthful_stages(tmp_path: Path) -> None:
    input_path = tmp_path / "input.gpkg"
    output_path = tmp_path / "output.gpkg"
    make_db(input_path, "buildings", "building_id TEXT, source_building_id TEXT", [("a", "s1"), ("b", "s2"), ("c", "s2")])
    make_db(output_path, "building_metrics", "building_id TEXT, source_building_id TEXT, area_m2 REAL, convexity REAL, rectang REAL, compact REAL", [("a", "s1", 1.0, 0.5, 1.2, 0.2), ("b", "s2", 2.0, 1.1, 0.8, 0.4), ("c", "s2", 3.0, 1.2, 1.3, 0.6)])
    report = REPORT.build_report(input_path, output_path, tmp_path / "missing-config.toml", tmp_path / "missing-log.json")
    assert report["status"] == "ok"
    assert report["counts"] == {"input_buildings": 3, "output_building_metrics": 3}
    assert report["id_audit"]["input_unique_building_ids"] == 3
    assert report["id_audit"]["source_building_id_duplicates_excess"] == 1
    assert report["required_fields"]["area_m2"]["numeric"] == 3
    assert report["statistics"]["area_m2"] == {"min": 1.0, "p10": 1.0, "median": 2.0, "p90": 3.0, "max": 3.0}
    assert report["observed_anomalies"]["convexity_gt_1"] == 2
    assert report["observed_anomalies"]["rectang_gt_1"] == 2
    assert report["observed_anomalies"]["convexity_max_excess"] == 0.2
    assert report["observed_anomalies"]["rectang_max_excess"] == 0.3


def test_ratio_exceedances_are_reported_as_formula_overshoots_without_clipping(tmp_path: Path) -> None:
    input_path = tmp_path / "input.gpkg"
    output_path = tmp_path / "output.gpkg"
    make_db(input_path, "buildings", "building_id TEXT", [("a",)])
    make_db(
        output_path,
        "building_metrics",
        "building_id TEXT, source_building_id TEXT, convexity REAL, rectang REAL",
        [("a", "s1", 1.00001, 1.0002)],
    )

    report = REPORT.build_report(input_path, output_path, tmp_path / "config.toml", tmp_path / "run.json")

    assert report["ratio_semantics"] == {
        "convexity": "outer-ring area / convex-hull area",
        "rectang": "outer-ring area / minimum-oriented-rectangle area",
        "theoretical_upper_bound": 1.0,
        "interpretation": "Small values above 1 are numerical overshoots of bounded ratios; source values are retained and not clipped.",
    }
    assert report["observed_anomalies"] == {
        "convexity_gt_1": 1,
        "rectang_gt_1": 1,
        "convexity_max_excess": 0.00001,
        "rectang_max_excess": 0.0002,
    }
    assert report["stages"]["tessellation"]["status"] == "not_run"
    assert report["stages"]["spacematrix"]["status"] == "blocked"


def test_json_and_markdown_share_report_facts_and_exclude_stale_claims() -> None:
    path = ROOT / "reports/ahmedabad_gandhinagar_planx_full_building_form_audit.json"
    markdown_path = ROOT / "reports/ahmedabad_gandhinagar_planx_full_building_form_audit.md"
    payload = json.loads(path.read_text())
    rendered = REPORT.markdown(payload)
    assert str(payload["counts"]["input_buildings"]) in rendered
    assert "30,000" not in rendered
    assert "17,847" not in rendered
    assert "run_20261018T005947Z.json" in rendered
    assert rendered == markdown_path.read_text()


def test_web_metadata_publishes_planx_stats_provenance_without_cell_area() -> None:
    metadata = WEB.planx_building_statistics()
    assert set(metadata) == {"footprint_area_m2", "planx_compactness", "planx_convexity", "planx_elongation"}
    for item in metadata.values():
        assert item["source_field"]
        assert item["scope"] == "full-study"
        assert item["report_path"].endswith("ahmedabad_gandhinagar_planx_full_building_form_audit.json")
    assert "planx_cell_m2" not in metadata


def test_current_handbook_scope_uses_full_study_claims() -> None:
    text = (ROOT / "HANDBOOK.md").read_text()
    assert "1,077,523" in text
    assert "run_20261018T005947Z.json" in text
    assert "30,000 selected" not in text
