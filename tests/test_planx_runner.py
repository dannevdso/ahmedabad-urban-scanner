from __future__ import annotations

import json
from pathlib import Path

import pytest

from ahmedabad_scanner.planx_runner import (
    EXPECTED_PLANX_COMMIT,
    MANIFEST,
    PlanXRunner,
    build_qgis_command,
    layer_uri,
)


@pytest.fixture
def runner(tmp_path: Path) -> PlanXRunner:
    return PlanXRunner(tmp_path, qgis_process=tmp_path / "qgis_process")


def test_manifest_covers_all_high_readiness_algorithms() -> None:
    expected = {
        "preparenetwork", "networkcentrality", "spacesyntax", "streetmorphology",
        "deadends", "linkcriticality", "odmatrix", "odroutes", "serviceareas",
        "nearestfacility", "accessscore", "buildingmetrics", "tessellation",
        "greenaccess", "greenconnectivity", "heatriskgrid", "facilitylocation",
        "scenariosnapshot", "scenariocompare", "scenariorank", "performancereport",
    }
    actual = {
        entry.algorithm.removeprefix("planx:")
        for entry in MANIFEST
        if entry.algorithm.startswith("planx:")
    }
    assert actual == expected
    assert EXPECTED_PLANX_COMMIT == "d24233790b0b93af25a5a9024c078f1ec04089fc"


def test_space_syntax_is_deferred_by_default_but_can_be_selected(tmp_path: Path) -> None:
    entries = {entry.name: entry for entry in MANIFEST}
    assert entries["spacesyntax"].enabled_by_default is False

    input_path = tmp_path / "inputs.gpkg"
    input_path.write_bytes(b"not a gpkg")
    runner = PlanXRunner(tmp_path)
    runner.check_plugin = lambda: EXPECTED_PLANX_COMMIT
    runner.validate_qgis = lambda: None
    runner._available_layers = lambda _: {
        "raw_network", "buildings", "building_centroids", "destinations", "categories",
        "green_spaces", "study_area", "representative_origins", "criticality_origins",
        "candidate_sites", "civic_facilities",
    }

    default_result = runner.run(input_path=input_path, dry_run=True)
    assert all(command[2] != "planx:spacesyntax" for command in default_result.commands)

    prepared = tmp_path / "data/derived/planx/outputs/prepared_network.gpkg"
    prepared.parent.mkdir(parents=True, exist_ok=True)
    prepared.write_bytes(b"existing")
    explicit_result = runner.run(input_path=input_path, only={"spacesyntax"}, dry_run=True)
    assert [command[2] for command in explicit_result.commands] == ["planx:spacesyntax"]


def test_native_scenario_dependencies_keep_native_provider_prefix() -> None:
    entries = {entry.name: entry for entry in MANIFEST}
    assert entries["extractinterventionsites"].algorithm == "native:extractbyattribute"
    assert entries["mergeinterventioncivic"].algorithm == "native:mergevectorlayers"


def test_layer_uri_is_explicit_gpkg_layer() -> None:
    assert layer_uri(Path("inputs.gpkg"), "raw_network") == "inputs.gpkg|layername=raw_network"


def test_command_is_an_argument_array_and_preserves_values(tmp_path: Path) -> None:
    command = build_qgis_command(
        tmp_path / "qgis process",
        "planx:preparenetwork",
        {"INPUT": "a path/input.gpkg|layername=raw_network", "OUTPUT": "out.gpkg|layername=prepared"},
    )
    assert isinstance(command, list)
    assert command[:3] == [str(tmp_path / "qgis process"), "run", "planx:preparenetwork"]
    assert "--INPUT=a path/input.gpkg|layername=raw_network" in command
    assert all(not isinstance(value, str) or " && " not in value for value in command)


def test_command_repeats_multiple_layer_parameters(tmp_path: Path) -> None:
    command = build_qgis_command(
        tmp_path / "qgis_process",
        "planx:accessscore",
        {"AMENITIES": ["health.gpkg", "education.gpkg"]},
    )
    assert command.count("--AMENITIES=health.gpkg") == 1
    assert command.count("--AMENITIES=education.gpkg") == 1


def test_manifest_uses_real_output_files_and_required_id_fields(tmp_path: Path) -> None:
    entries = {entry.name: entry for entry in MANIFEST}
    output_root = tmp_path / "outputs"
    input_path = tmp_path / "inputs.gpkg"

    building_output = entries["buildingmetrics"].parameters(input_path, output_root)["OUTPUT"]
    assert building_output == str(output_root / "building_metrics.gpkg")
    assert "|layername=" not in building_output

    nearest = entries["nearestfacility"].parameters(input_path, output_root)
    assert nearest["FACILITY_ID"] == "destination_id"
    facility = entries["facilitylocation"].parameters(input_path, output_root)
    assert facility["CANDIDATE_ID"] == "candidate_id"

    criticality = entries["linkcriticality"].parameters(input_path, output_root)
    assert str(criticality["ORIGINS"]).endswith("|layername=criticality_origins")
    assert str(criticality["DESTINATIONS"]).endswith("|layername=civic_facilities")

    service_areas = entries["serviceareas"].parameters(input_path, output_root)
    assert service_areas["COST_FIELD"] == "length_m"
    assert service_areas["BREAKS"] == "400,800,1200"

    amenities = entries["accessscore"].parameters(input_path, output_root)["AMENITIES"]
    assert isinstance(amenities, list)
    assert len(amenities) == 8
    assert all("destination_" in value for value in amenities)


def test_manifest_output_layers_match_plain_geopackage_filenames() -> None:
    for entry in MANIFEST:
        for filename, layer in entry.outputs:
            if filename.endswith(".gpkg"):
                assert layer == Path(filename).stem, (entry.name, filename, layer)
            else:
                assert layer == "", (entry.name, filename, layer)


def test_declared_outputs_are_actual_parameter_destinations(tmp_path: Path) -> None:
    input_path = tmp_path / "inputs.gpkg"
    output_root = tmp_path / "outputs"
    for entry in MANIFEST:
        parameter_values = {
            str(value)
            for value in entry.parameters(input_path, output_root).values()
            if not isinstance(value, (list, tuple))
        }
        for filename, _ in entry.outputs:
            assert str(output_root / filename) in parameter_values, (entry.name, filename)


def test_missing_layers_stop_honestly(tmp_path: Path) -> None:
    input_path = tmp_path / "missing.gpkg"
    runner = PlanXRunner(tmp_path)
    runner.check_plugin = lambda: EXPECTED_PLANX_COMMIT
    runner.validate_qgis = lambda: None
    result = runner.run(input_path=input_path, dry_run=True)
    assert result.status == "blocked"
    assert "raw_network" in result.missing_layers
    assert result.logs_path.exists()
    payload = json.loads(result.logs_path.read_text())
    assert payload["status"] == "blocked"


def test_dry_run_orders_prepare_before_downstream(tmp_path: Path) -> None:
    input_path = tmp_path / "inputs.gpkg"
    input_path.write_bytes(b"not a gpkg")
    runner = PlanXRunner(tmp_path)
    runner.check_plugin = lambda: EXPECTED_PLANX_COMMIT
    runner.validate_qgis = lambda: None
    runner._available_layers = lambda _: {
        "raw_network", "buildings", "building_centroids", "destinations", "categories",
        "green_spaces", "study_area", "representative_origins", "criticality_origins",
        "candidate_sites", "civic_facilities",
    }
    result = runner.run(input_path=input_path, dry_run=True)
    assert result.status == "dry-run"
    assert result.commands[0][2] == "planx:preparenetwork"
    assert result.commands.index(next(c for c in result.commands if c[2] == "planx:accessscore")) > 0


def test_reuse_skips_existing_outputs(tmp_path: Path) -> None:
    input_path = tmp_path / "inputs.gpkg"
    input_path.write_bytes(b"not a gpkg")
    runner = PlanXRunner(tmp_path)
    runner.check_plugin = lambda: EXPECTED_PLANX_COMMIT
    runner.validate_qgis = lambda: None
    runner._available_layers = lambda _: {
        "raw_network", "buildings", "building_centroids", "destinations", "categories",
        "green_spaces", "study_area", "representative_origins", "candidate_sites", "civic_facilities",
    }
    output = tmp_path / "data/derived/planx/outputs/prepared_network.gpkg"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"existing")
    result = runner.run(input_path=input_path, only={"preparenetwork"}, reuse=True, dry_run=True)
    assert result.status == "dry-run"
    assert result.skipped == ["preparenetwork"]
