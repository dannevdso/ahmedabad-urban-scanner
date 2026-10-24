from __future__ import annotations

import geopandas as gpd
from shapely.geometry import LineString, Point, Polygon

from ahmedabad_scanner.planx_inputs import (
    add_stable_building_ids,
    deduplicate_undirected_network,
    extract_green_spaces,
    thin_points_on_grid,
    validate_planx_layers,
)



def test_deduplicate_undirected_network_keeps_lowest_cost_direction() -> None:
    edges = gpd.GeoDataFrame(
        {
            "u": [2, 1, 1],
            "v": [1, 2, 2],
            "key": [0, 0, 1],
            "length": [12.0, 12.0, 10.0],
            "walk_time_min": [1.2, 1.2, 1.0],
        },
        geometry=[LineString([(1, 0), (2, 0)])] * 3,
        crs="EPSG:32643",
    )

    result = deduplicate_undirected_network(edges)

    assert len(result) == 1
    assert result.loc[0, "u"] == 1
    assert result.loc[0, "v"] == 2
    assert result.loc[0, "length"] == 10.0
    assert result.loc[0, "walk_time_min"] == 1.0



def test_stable_building_ids_do_not_depend_on_input_order() -> None:
    geometries = [Polygon([(0, 0), (1, 0), (1, 1), (0, 0)]), Polygon([(3, 0), (4, 0), (4, 1), (3, 0)])]
    first = gpd.GeoDataFrame({"source": ["a", "b"]}, geometry=geometries, crs="EPSG:32643")
    second = first.iloc[::-1].reset_index(drop=True)

    first_ids = set(add_stable_building_ids(first)["building_id"])
    second_ids = set(add_stable_building_ids(second)["building_id"])

    assert first_ids == second_ids
    assert all(value.startswith("bldg_") for value in first_ids)



def test_grid_thinning_is_deterministic_and_keeps_source_id() -> None:
    points = gpd.GeoDataFrame(
        {"source_id": ["b", "a", "c"]},
        geometry=[Point(1, 1), Point(2, 2), Point(251, 1)],
        crs="EPSG:32643",
    )

    result = thin_points_on_grid(points, spacing_m=250, source_id="source_id", output_id="candidate_id", prefix="site")

    assert result["source_id"].tolist() == ["a", "c"]
    assert result["candidate_id"].tolist() == ["site_000001", "site_000002"]



def test_extract_green_spaces_returns_only_polygonal_green_features() -> None:
    raw = gpd.GeoDataFrame(
        {"element": ["way", "node", "way"], "id": [1, 2, 3], "leisure": ["park", "park", None], "landuse": [None, None, "residential"]},
        geometry=[Polygon([(0, 0), (2, 0), (2, 2), (0, 0)]), Point(1, 1), Polygon([(4, 0), (5, 0), (5, 1), (4, 0)])],
        crs="EPSG:4326",
    )

    result = extract_green_spaces(raw, metric_crs="EPSG:32643")

    assert len(result) == 1
    assert result.geometry.iloc[0].geom_type == "Polygon"
    assert result.loc[0, "category"] == "green"



def test_validate_planx_layers_rejects_wrong_crs_and_duplicate_ids() -> None:
    layer = gpd.GeoDataFrame({"building_id": ["bldg_1", "bldg_1"]}, geometry=[Point(0, 0), Point(1, 1)], crs="EPSG:4326")

    try:
        validate_planx_layers({"buildings": layer}, expected_crs="EPSG:32643")
    except ValueError as exc:
        assert "CRS" in str(exc)
    else:
        raise AssertionError("wrong CRS should fail validation")

    layer = layer.to_crs("EPSG:32643")
    try:
        validate_planx_layers({"buildings": layer}, expected_crs="EPSG:32643", id_columns={"buildings": "building_id"})
    except ValueError as exc:
        assert "duplicate" in str(exc).lower()
    else:
        raise AssertionError("duplicate IDs should fail validation")
