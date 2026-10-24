from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path


SPEC = importlib.util.spec_from_file_location(
    "audit_planx_building_form", Path(__file__).parents[1] / "scripts/audit_planx_building_form.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_range_audit_flags_out_of_range_values(tmp_path: Path) -> None:
    path = tmp_path / "metrics.gpkg"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE metrics (compact REAL)")
        db.executemany("INSERT INTO metrics VALUES (?)", [(0.2,), (1.00001,), (None,)])
        db.commit()
    result = MODULE.range_audit(path, "metrics", {"compact": (0.0, 1.0)})
    assert result["compact"]["rows_checked"] == 2
    assert result["compact"]["above_max"] == 1


def test_id_join_audit_reports_exact_coverage(tmp_path: Path) -> None:
    input_path = tmp_path / "input.gpkg"
    output_path = tmp_path / "output.gpkg"
    with sqlite3.connect(input_path) as db:
        db.execute("CREATE TABLE buildings (building_id TEXT)")
        db.executemany("INSERT INTO buildings VALUES (?)", [("a",), ("b",), ("c",)])
        db.commit()
    with sqlite3.connect(output_path) as db:
        db.execute("CREATE TABLE metrics (building_id TEXT)")
        db.executemany("INSERT INTO metrics VALUES (?)", [("a",), ("b",), ("c",)])
        db.commit()
    result = MODULE.id_join_audit(input_path, output_path, "buildings", "metrics")
    assert result == {
        "input_unique_building_ids": 3,
        "output_unique_building_ids": 3,
        "output_ids_in_input": 3,
        "output_ids_missing_from_input": 0,
        "input_ids_missing_from_output": 0,
    }
