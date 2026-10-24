from __future__ import annotations

import math
import numpy as np
import geopandas as gpd
from numpy.ma import masked_array
from shapely.geometry import LineString, Point, box

from ahmedabad_scanner.local_area_profile import (
    FIXED_CLASS_METADATA,
    build_local_area_profile,
    build_local_area_profiles,
    summarize_length_weighted,
    summarize_raster,
    summarize_flood_risk_area,
)


def test_single_selection_contract_has_frontend_sections_and_top_level_selection():
    result = build_local_area_profile(Point(10, 20), radius_m=400)
    assert result["contractVersion"] == "local-area-profile.v1"
    assert result["center"] == [10.0, 20.0]
    assert result["radiusM"] == 400
    assert list(result["sections"]) == [
        "overview", "buildings", "streetsConnectivity", "spaceSyntaxCentrality",
        "environment", "publicTransport", "parksEducation", "availability", "methods",
    ]
    assert result["sections"]["overview"]["data"] == {
        "buildingCount": None,
        "buildingFootprintCoveragePct": None,
        "intersectionDensityPerKm2": None,
        "vegetationFractionMean": None,
        "publicTransportStops": None,
        "directlyServingRoutes": None,
    }
    assert set(result) >= {"sources", "provenance", "warnings"}


def test_optional_multi_radius_wrapper_is_separately_named():
    result = build_local_area_profiles(Point(0, 0), radii_m=[800, 400])
    assert result["contractVersion"] == "local-area-profiles.v1"
    assert [item["radiusM"] for item in result["profiles"]] == [400, 800]


def test_buildings_prefer_footprint_area_and_report_coverage_and_histogram():
    buildings = gpd.GeoDataFrame(
        {"footprint_area_m2": [100, 999], "area_m2": [1, 1], "compact": [0.8, 0.6]},
        geometry=[box(-5, -5, 5, 5), box(395, -2, 405, 2)], crs="EPSG:3857",
    )
    result = build_local_area_profile(Point(0, 0), buildings=buildings, radius_m=400)
    data = result["sections"]["buildings"]["data"]
    assert data["buildingCount"] == 1
    assert data["footprintAreaM2"]["median"] == 100.0
    assert data["footprintCoverageM2"] > 0
    assert 0 < data["footprintCoveragePct"] < 1
    assert sum(data["footprintAreaM2"]["histogram"]["counts"]) == 1
    assert data["buildingMetrics"]["compactness"]["summary"]["mean"] == 0.8


def test_summary_has_required_stats_and_fixed_bins():
    buildings = gpd.GeoDataFrame({"footprint_area_m2": [1, 2, 3]}, geometry=[box(0, 0, 1, 1)] * 3, crs="EPSG:3857")
    result = build_local_area_profile(Point(0, 0), buildings=buildings, radius_m=400)
    summary = result["sections"]["buildings"]["data"]["footprintAreaM2"]
    assert set(summary) >= {"mean", "median", "min", "max", "std", "histogram"}
    assert summary["histogram"]["bins"] == FIXED_CLASS_METADATA["footprint_area_m2"]["bins"]


def test_street_metrics_use_authoritative_topology_and_exclude_clip_points():
    edges = gpd.GeoDataFrame(
        {"u": [1, 2, 3, 10], "v": [2, 3, 4, 11]},
        geometry=[LineString([(0, 0), (5, 0)]), LineString([(5, 0), (10, 0)]), LineString([(10, 0), (20, 0)]), LineString([(-5, 5), (-5, 6)])],
        crs="EPSG:3857",
    )
    result = build_local_area_profile(Point(0, 0), street_edges=edges, radius_m=10)
    data = result["sections"]["streetsConnectivity"]["data"]
    assert data["clippedLengthM"] == 11.0
    assert data["linkNodeRatio"] == 0.75
    assert data["intersectionDensityPerKm2"] == 0.0
    assert data["connectedNodeRatio"] == 0.5
    assert data["nodeRule"] == "authoritative_u_v_only; clip-created boundary points excluded"


def test_length_weighting_clips_to_circle_before_weighting():
    edges = gpd.GeoDataFrame({"length_m": [100, 10], "value": [1, 3]}, geometry=[LineString([(-50, 0), (50, 0)]), LineString([(0, 0), (10, 0)])], crs="EPSG:3857")
    circle = Point(0, 0).buffer(10)
    summary = summarize_length_weighted(edges, ["value"], circle=circle)
    assert summary["value"]["weight_field"] == "clipped_geometry_length_m"
    assert summary["value"]["weighted_mean"] == 1.666667


def test_transit_is_unavailable_without_provable_route_cell_relationship():
    stops = gpd.GeoDataFrame({"route_ids": [["r1"]]}, geometry=[Point(0, 0)], crs="EPSG:3857")
    cells = gpd.GeoDataFrame({"cell_id": [1]}, geometry=[box(-1, -1, 1, 1)], crs="EPSG:3857")
    result = build_local_area_profile(Point(0, 0), transit_stops=stops, route_reach_cells=cells, radius_m=400)
    transit = result["sections"]["publicTransport"]
    assert transit["status"] == "unavailable"
    assert "route-serving-stop" in transit["reason"]


def test_raster_summary_supports_masked_values_and_valid_coverage():
    values = masked_array(np.array([[1, 2], [3, 99]]), mask=[[False, False], [False, True]])
    result = summarize_raster(values, expected_cell_count=4, bins=[0, 2, 4])
    assert result["status"] == "available"
    assert result["mean"] == 2.0
    assert result["median"] == 2.0
    assert result["max"] == 3.0
    assert result["validCoveragePct"] == 75.0
    assert result["distribution"]["counts"] == [1, 2]


def test_flood_risk_area_uses_union_area_per_class_and_marks_low_unavailable():
    flood = gpd.GeoDataFrame(
        {"uf_risk": ["Very High Risk Areas", "Very High Risk Areas", "High Risk Areas", "Moderate Risk Areas"]},
        geometry=[box(-20, -10, 0, 10), box(-10, -10, 10, 10), box(0, -10, 20, 10), box(10, -10, 30, 10)],
        crs="EPSG:3857",
    )
    result = summarize_flood_risk_area(flood, box(-10, -10, 10, 10))
    assert result["status"] == "available"
    assert result["unit"] == "m²"
    assert [category["label"] for category in result["categories"]] == ["Very high", "High", "Moderate", "Low"]
    assert result["categories"][0]["areaM2"] == 400.0
    assert result["categories"][1]["areaM2"] == 200.0
    assert result["categories"][2]["areaM2"] == 0.0
    assert result["categories"][3] == {"key": "low", "label": "Low", "sourceClass": None, "areaM2": None, "status": "unavailable"}
    assert result["totalClassifiedAreaM2"] == 600.0
    assert "no Low" in result["caveat"]


def test_flood_risk_area_is_unavailable_without_source():
    result = summarize_flood_risk_area(None, Point(0, 0).buffer(10))
    assert result == {"status": "unavailable", "unit": "m²", "categories": [], "totalClassifiedAreaM2": None, "reason": "flood-risk source unavailable"}


def test_profile_uses_flood_source_metric_crs_when_it_is_the_only_vector_source():
    center = Point(240_000, 2_538_000)
    flood = gpd.GeoDataFrame(
        {"uf_risk": ["High Risk Areas"]},
        geometry=[box(center.x - 10, center.y - 10, center.x + 10, center.y + 10)],
        crs="EPSG:32643",
    )

    result = build_local_area_profile(
        center,
        center_crs="EPSG:32643",
        radius_m=50,
        flood_risk_zones=flood,
    )

    high = result["sections"]["environment"]["data"]["floodRiskArea"]["categories"][1]
    assert high["areaM2"] == 400.0


def test_flood_risk_area_is_present_for_each_standard_profile_radius():
    flood = gpd.GeoDataFrame(
        {"uf_risk": ["Very High Risk Areas"]},
        geometry=[box(-2000, -2000, 2000, 2000)],
        crs="EPSG:3857",
    )
    result = build_local_area_profiles(Point(0, 0), radii_m=[400, 800, 1200], flood_risk_zones=flood)
    assert [profile["radiusM"] for profile in result["profiles"]] == [400, 800, 1200]
    assert [profile["sections"]["environment"]["data"]["floodRiskArea"]["status"] for profile in result["profiles"]] == ["available"] * 3
    assert all(profile["sections"]["environment"]["data"]["floodRiskArea"]["categories"][3]["areaM2"] is None for profile in result["profiles"])


def test_tps_polygon_selection_uses_boundary_inclusive_points_exact_clipping_and_explicit_metadata():
    points = gpd.GeoDataFrame(
        {"zone_group": ["central", "enriched", "enriched"], "height_m": [None, 5, None], "area_m2": [None, 10, 20], "volume_m3": [None, 50, None], "suhi": [None, " High SUHI ", "low SUHI"]},
        geometry=[Point(0, 0), Point(5, 5), Point(20, 20)], crs="EPSG:3857",
    )
    streets = gpd.GeoDataFrame({"u": [1], "v": [2]}, geometry=[LineString([(-5, 5), (15, 5)])], crs="EPSG:3857")
    selection = box(0, 0, 10, 10)
    result = build_local_area_profile(
        Point(5, 5),
        selection_geometry=selection,
        selection_crs="EPSG:3857",
        selection_metadata={"source_id": "x-1", "tps_name": "Duplicate", "tps_no": "7", "tps_status": "provisional"},
        buildings=points,
        street_edges=streets,
    )
    assert result["selection"] == {"type": "tps", "source_id": "x-1", "tps_name": "Duplicate", "tps_no": "7", "tps_status": "provisional", "areaM2": 100.0}
    data = result["sections"]["buildings"]["data"]
    assert data["totalLocationCount"] == 2
    assert data["centralLocationCount"] == 1
    assert data["enrichedLocationCount"] == 1
    assert data["provisionalHeightM"]["availability"] == {"available": 1, "denominator": 1}
    assert data["provisionalAreaM2"]["availability"] == {"available": 1, "denominator": 1}
    assert data["derivedVolumeM3"]["availability"] == {"available": 1, "denominator": 1}
    assert data["suhi"]["availability"] == {"available": 1, "denominator": 1}
    assert data["suhi"]["summary"] == {"dominantClass": "High"}
    assert data["suhi"]["distribution"]["categories"] == [
        {"key": "low", "label": "Low", "count": 0},
        {"key": "moderate", "label": "Moderate", "count": 0},
        {"key": "high", "label": "High", "count": 1},
        {"key": "veryHigh", "label": "Very High", "count": 0},
        {"key": "extremeHigh", "label": "Extreme High", "count": 0},
    ]
    assert result["sections"]["streetsConnectivity"]["data"]["clippedLengthM"] == 10.0


def test_circle_building_locations_keep_central_count_only_and_reconcile_distributions_and_stored_area():
    points = gpd.GeoDataFrame(
        {
            "zone_group": ["central", "enriched", "enriched", "enriched", "enriched"],
            "height_m": [999, 2, 12, 125, None],
            "area_m2": [99999, 10, 100, 6000, None],
            "volume_m3": [999999, 20, 1200, 750000, None],
            "suhi": ["Extreme High SUHI", "low SUHI", "High SUHI", "mystery class", None],
        },
        geometry=[Point(0, 0), Point(1, 0), Point(2, 0), Point(3, 0), Point(4, 0)],
        crs="EPSG:3857",
    )

    data = build_local_area_profile(Point(0, 0), buildings=points, radius_m=400)["sections"]["buildings"]["data"]

    assert data["totalLocationCount"] == 5
    assert data["enrichedLocationCount"] == 4
    assert data["suhi"]["availability"] == {"available": 3, "denominator": 4}
    assert data["suhi"]["summary"] == {"dominantClass": "Low"}
    assert data["suhi"]["distribution"] == {
        "categories": [
            {"key": "low", "label": "Low", "count": 1},
            {"key": "moderate", "label": "Moderate", "count": 0},
            {"key": "high", "label": "High", "count": 1},
            {"key": "veryHigh", "label": "Very High", "count": 0},
            {"key": "extremeHigh", "label": "Extreme High", "count": 0},
            {"key": "otherUnknown", "label": "Other/unknown", "count": 1},
        ],
        "totalCount": 3,
    }
    for key in ("provisionalHeightM", "provisionalAreaM2", "derivedVolumeM3"):
        distribution = data[key]["distribution"]
        assert distribution["totalCount"] == data[key]["availability"]["available"]
        assert sum(distribution["counts"]) + distribution["underflowCount"] + distribution["overflowCount"] == distribution["totalCount"]
    assert data["provisionalHeightM"]["distribution"]["overflowCount"] == 1
    assert data["provisionalAreaM2"]["distribution"]["overflowCount"] == 1
    assert data["derivedVolumeM3"]["distribution"]["overflowCount"] == 1

    assert data["summedStoredAreaM2"] == 6110.0
    assert data["storedAreaSharePct"] == round(6110 / (math.pi * 400 * 400) * 100, 6)
    assert "point-selected stored area" in data["storedAreaSelectionBasis"]


def test_tps_polygon_selection_clips_polygon_building_coverage_to_exact_boundary():
    buildings = gpd.GeoDataFrame(
        {"footprint_area_m2": [200]}, geometry=[box(8, 0, 28, 10)], crs="EPSG:3857"
    )
    result = build_local_area_profile(
        Point(5, 5), selection_geometry=box(0, 0, 10, 10), selection_crs="EPSG:3857",
        selection_metadata={"source_id": "x", "tps_name": None, "tps_no": None, "tps_status": None}, buildings=buildings,
    )
    data = result["sections"]["buildings"]["data"]
    assert data["buildingCount"] == 1
    assert data["footprintCoverageM2"] == 20.0
    assert data["buildingInclusionRule"] == "exact_polygon_intersection"
