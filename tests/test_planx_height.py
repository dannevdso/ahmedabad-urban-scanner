from __future__ import annotations

from ahmedabad_scanner.planx_height import HEIGHT_REQUIREMENTS, requirements_as_dicts


def test_height_requirement_matrix_has_height_and_non_height_visibility_stages() -> None:
    stages = {item.stage: item for item in HEIGHT_REQUIREMENTS}
    assert stages["sunhours"].input_schema.startswith("DSM:")
    assert "metres" in stages["sunhours"].units
    assert stages["isovistfield"].current_status == "available"
    assert "none" in stages["isovistfield"].height_dependency


def test_requirement_serialization_is_json_ready() -> None:
    rows = requirements_as_dicts()
    assert len(rows) == len(HEIGHT_REQUIREMENTS)
    assert {row["stage"] for row in rows} >= {"heatriskgrid", "frontalarea", "sunhours", "isovistfield"}
    assert all(set(row) == {"stage", "height_dependency", "input_schema", "units", "current_status", "safe_action"} for row in rows)
