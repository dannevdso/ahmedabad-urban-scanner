from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString, Point, Polygon, box

from ahmedabad_scanner.web_export import (
    join_planx_building_metrics,
    prepare_web_buildings,

    prepare_web_space_syntax,
    prepare_web_space_syntax_points,
    prepare_web_raw_buildings,
    prepare_web_streets,
    prepare_web_vector_layer,
    quantile_breaks,
    natural_breaks,
    classification_metadata,
)


def test_classification_metadata_uses_deterministic_quantiles_and_removes_duplicate_breaks():
    result = classification_metadata(pd.Series([0, 0, 1, 2, 2, 3, 4]), property_name="betweenness", palette="viridis")
    assert result["method"] == "quantile"
    assert result["breaks"] == sorted(set(result["breaks"]))
    assert result["breaks"][0] > result["min"]
    assert result["class_count"] == len(result["palette"])


def test_heat_risk_classification_uses_published_values_and_sequential_heat_palette():
    result = classification_metadata(
        pd.Series([38.54, 50.0, 75.0, 100.0, None]),
        property_name="heat_risk",
        palette="heat",
    )
    assert result["method"] == "quantile"
    assert result["min"] == 38.54
    assert result["max"] == 100.0
    assert result["non_null_count"] == 4
    assert result["palette"][0] == "#ffffcc"
    assert result["palette"][-1] == "#800026"


def test_classification_metadata_marks_constant_values_without_fake_ramp():
    result = classification_metadata(pd.Series([4.0, 4.0, 4.0]), property_name="connectivity", palette="viridis")
    assert result["method"] == "constant"
    assert result["class_count"] == 1
    assert "no variation" in result["note"].lower()


def test_space_syntax_classification_covers_every_selector_field():
    fields = {"connectivity": [0, 1, 2], "betweenness": [0.000000001, 0.000000002], "closeness": [0.000000001, 0.000000003]}
    result = {field: classification_metadata(pd.Series(values), property_name=field, palette="viridis") for field, values in fields.items()}
    assert set(result) == {"connectivity", "betweenness", "closeness"}


def test_space_syntax_closeness_precision_survives_export_and_matches_breaks():
    source = gpd.GeoDataFrame({"seg_id": [1, 2], "clo_mean": [0.000000001234, 0.000000003456], "connectivity": [1, 2], "betw_edge": [1, 2], "str_mean": [1, 2], "NC_400": [1, 2], "NC_2500": [1, 2], "TD_400": [1, 2], "MD_400": [1, 2], "NAIN_400": [1, 2], "CH_400": [1, 2], "NACH_400": [1, 2], "TD_2500": [1, 2], "MD_2500": [1, 2], "NAIN_2500": [1, 2], "CH_2500": [1, 2], "NACH_2500": [1, 2], "clipped_length_m": [1, 2]}, geometry=[LineString([(0, 0), (1, 0)]), LineString([(1, 0), (2, 0)])], crs="EPSG:32643")
    result = prepare_web_space_syntax(source)
    assert result["closeness"].tolist() == [0.000000001234, 0.000000003456]
    metadata = classification_metadata(result["closeness"], property_name="closeness", palette="viridis")
    assert metadata["max"] == max(result["closeness"])


def test_classification_metadata_exposes_clean_display_precision_and_labels():
    result = classification_metadata(pd.Series([0, 12858.8, 17240.125, 75723658.45]), property_name="betweenness")
    labels = result["legend_entries"]
    assert result["display_precision"] >= 1
    assert all("999999" not in entry["label"] for entry in labels)
    assert labels[0]["label"].startswith("0")
    assert labels[-1]["label"].endswith("75723658.45")
    assert len({entry["label"] for entry in labels}) == len(labels)


def test_removed_green_access_has_no_legend_metadata():
    from scripts.build_web_data import build_overlay_legends

    legends = build_overlay_legends({})
    assert "greenAccess" not in legends


def test_flood_risk_publication_preserves_source_bytes_and_validates_risk_classes(tmp_path):
    import json

    from scripts.build_web_data import publish_flood_risk_zones

    source = tmp_path / "source.geojson"
    source.write_text(json.dumps({
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"uf_risk": label}, "geometry": {"type": "Polygon", "coordinates": [[[72, 23], [73, 23], [73, 24], [72, 23]]]}}
            for label in ["Very High Risk Areas", "High Risk Areas", "Moderate Risk Areas"]
        ],
    }))
    output_dir = tmp_path / "public"

    publication = publish_flood_risk_zones(output_dir, source_path=source)

    target = output_dir / "ahm-urban-flood-risk-zones.geojson"
    assert target.read_bytes() == source.read_bytes()
    assert publication["feature_count"] == 3
    assert publication["risk_field"] == "uf_risk"
    assert publication["risk_class_counts"] == {
        "Very High Risk Areas": 1,
        "High Risk Areas": 1,
        "Moderate Risk Areas": 1,
    }


def test_public_poi_export_keeps_only_parks_and_schools():
    from scripts.build_web_data import select_published_pois

    source = gpd.GeoDataFrame(
        {"poi_type": ["parks", "schools", "hospitals", "markets"]},
        geometry=[Point(0, 0), Point(1, 1), Point(2, 2), Point(3, 3)],
        crs="EPSG:4326",
    )

    result = select_published_pois(source)

    assert result["poi_type"].tolist() == ["parks", "schools"]


def test_service_intensity_legends_cover_whole_day_peaks_and_hourly_average():
    from scripts.build_web_data import build_overlay_legends

    classification = {
        "method": "quantile",
        "property": "daily_departures",
        "min": 0,
        "max": 20,
        "breaks": [2, 5, 10],
        "palette": ["#eff3ff", "#bdd7e7", "#6baed6", "#08519c"],
    }
    classifications = {
        "gtfsServiceDay": {"daily_departures": classification},
        "gtfsMorningPeak": {"morning_peak_departures": {**classification, "property": "morning_peak_departures"}},
        "gtfsEveningPeak": {"evening_peak_departures": {**classification, "property": "evening_peak_departures"}},
        "gtfsDeparturesPerHour": {"departures_per_hour": {**classification, "property": "departures_per_hour"}},
    }
    legends = build_overlay_legends(classifications)

    assert legends["gtfsServiceDay"]["renderer_property"] == "daily_departures"
    assert legends["gtfsMorningPeak"]["unit"] == "departures, 08:00–10:00"
    assert legends["gtfsEveningPeak"]["unit"] == "departures, 17:00–19:00"
    assert legends["gtfsDeparturesPerHour"]["unit"] == "average departures/hour"
    assert all("route count" in legends[key]["caveat"].lower() for key in classifications)


def test_space_syntax_legend_uses_readable_selector_titles():
    from scripts.build_web_data import build_overlay_legends

    legends = build_overlay_legends({})["spaceSyntax"]
    assert legends["closeness"]["title"] == "Mean closeness"
    assert legends["betweenness"]["title"] == "Edge betweenness"
    assert legends["nc_2500"]["title"] == "NC 2,500 m"


def test_raster_legend_requires_explicit_verified_palette_stops():
    from scripts.build_web_data import build_overlay_legends

    legends = build_overlay_legends({}, raster_manifests={"surface-temperature": {"display_range": [35, 55], "colormap": "inferno", "palette_stops": [{"value": 0, "color": "#000004"}, {"value": 1, "color": "#fcffa4"}]}})
    assert legends["environmentSurfaceTemperature"]["source"]["palette_stops"]
    assert legends["environmentSurfaceTemperature"]["entries"][0]["palette_stops"]


def test_building_height_legend_declares_modelled_2023_raster_provenance():
    from scripts.build_web_data import build_overlay_legends

    legends = build_overlay_legends({}, raster_manifests={"building-height": {
        "display_range": [0.023, 92.319],
        "colormap": "viridis",
        "palette_stops": [{"value": 0, "color": "#440154"}, {"value": 1, "color": "#fde725"}],
        "unit": "metres",
        "validation_status": "verified",
        "source": "Google Research Open Buildings Temporal",
        "source_year": 2023,
        "resolution_m": 30,
        "presence_threshold": 0.2,
    }})

    legend = legends["buildingHeight"]
    assert legend["unit"] == "metres"
    assert legend["entries"][0]["palette_stops"]
    assert "modelled" in legend["caveat"].lower()
    assert "surveyed" in legend["caveat"].lower()


def test_prepare_web_buildings_selects_rounds_and_preserves_missing_values():
    source = gpd.GeoDataFrame(
        {
            "building_id": ["a", "b"],
            "footprint_area_m2": [123.456, 80.0],
            "essential_categories_15min": [7, 5],
            "walk_health_min": [4.444, np.nan],
            "lst_c_100m_median": [45.6789, 43.0],
            "ndvi_50m_median": [0.12345, 0.4],
            "environment_data_ok": [True, False],
        },
        geometry=[box(0, 0, 10, 10), box(20, 20, 30, 30)],
        crs="EPSG:32643",
    )

    result = prepare_web_buildings(source)

    assert result.crs.to_epsg() == 4326
    assert result.loc[0, "area_m2"] == 123.5
    assert result.loc[0, "health_min"] == 4.4
    assert result.loc[1, "health_min"] is None
    assert result.loc[0, "lst_c"] == 45.68
    assert result.loc[0, "ndvi"] == 0.123
    assert result.loc[1, "environment_ok"] is False


def test_prepare_web_streets_deduplicates_directed_edges_and_projects_to_wgs84():
    source = gpd.GeoDataFrame(
        {
            "u": [1, 2, 2],
            "v": [2, 1, 3],
            "key": [0, 0, 0],
        },
        geometry=[
            LineString([(500000, 2545000), (500100, 2545000)]),
            LineString([(500100, 2545000), (500000, 2545000)]),
            LineString([(500100, 2545000), (500200, 2545100)]),
        ],
        crs="EPSG:32643",
    )

    result = prepare_web_streets(source)

    assert result.crs.to_epsg() == 4326
    assert len(result) == 2
    assert list(result.columns) == ["geometry"]


def test_join_planx_building_metrics_preserves_buildings_and_adds_tessellation():
    buildings = gpd.GeoDataFrame(
        {"building_id": ["a", "b"], "footprint_area_m2": [100.0, 80.0]},
        geometry=[box(0, 0, 10, 10), box(20, 20, 30, 28)],
        crs="EPSG:32643",
    )
    metrics = gpd.GeoDataFrame(
        {"building_id": ["a", "b"], "compact": [0.8, 0.6], "convexity": [0.9, 0.7], "elongation": [1.0, 1.5]},
        geometry=buildings.geometry,
        crs=buildings.crs,
    )
    tessellation = gpd.GeoDataFrame(
        {"building_id": ["a", "b"], "cell_m2": [320.0, 450.0]},
        geometry=[box(-5, -5, 15, 15), box(15, 15, 35, 35)],
        crs=buildings.crs,
    )

    result = join_planx_building_metrics(buildings, metrics, tessellation)

    assert len(result) == 2
    assert result["planx_compactness"].tolist() == [0.8, 0.6]
    assert result["planx_convexity"].tolist() == [0.9, 0.7]
    assert result["planx_elongation"].tolist() == [1.0, 1.5]
    assert result["planx_cell_m2"].tolist() == [320.0, 450.0]


def test_join_planx_building_metrics_uses_preserved_source_ids():
    buildings = gpd.GeoDataFrame(
        {"building_id": ["source-a"]}, geometry=[box(0, 0, 10, 10)], crs="EPSG:32643"
    )
    metrics = gpd.GeoDataFrame(
        {
            "building_id": ["planx-a"],
            "source_building_id": ["source-a"],
            "compact": [0.8],
            "convexity": [0.9],
            "elongation": [1.1],
        },
        geometry=buildings.geometry,
        crs=buildings.crs,
    )
    tessellation = gpd.GeoDataFrame(
        {"building_id": ["planx-a"], "source_building_id": ["source-a"], "cell_m2": [320.0]},
        geometry=[box(-5, -5, 15, 15)],
        crs=buildings.crs,
    )

    result = join_planx_building_metrics(buildings, metrics, tessellation)

    assert result.loc[0, "planx_compactness"] == 0.8
    assert result.loc[0, "planx_cell_m2"] == 320.0



def test_prepare_web_space_syntax_preserves_raw_planx_fields_and_projects():
    source = gpd.GeoDataFrame(
        {
            "seg_id": [1],
            "NC_400": [29.1234],
            "NC_2500": [553.9876],
            "connectivity": [4],
            "clo_mean": [0.1234],
            "str_mean": [0.2345],
            "TD_400": [12.3456],
            "MD_400": [1.2345],
            "NAIN_400": [0.9876],
            "CH_400": [45.6789],
            "NACH_400": [1.4567],
            "TD_2500": [23.4567],
            "MD_2500": [2.3456],
            "NAIN_2500": [1.1234],
            "CH_2500": [67.8901],
            "NACH_2500": [2.5678],
            "betw_edge": [112.4567],
            "clipped_length_m": [75.4321],
        },
        geometry=[LineString([(500000, 2545000), (500100, 2545000)])],
        crs="EPSG:32643",
    )

    result = prepare_web_space_syntax(source)

    assert result.crs.to_epsg() == 4326
    assert list(result.columns) == [
        "segment_id", "connectivity", "betweenness", "closeness", "straightness", "nc_400", "nc_2500", "td_400", "md_400",
        "nain_400", "ch_400", "nach_400", "td_2500", "md_2500", "nain_2500",
        "ch_2500", "nach_2500", "clipped_length_m", "geometry"
    ]
    assert result.loc[0, "nc_400"] == 29.123
    assert result.loc[0, "nc_2500"] == 553.988
    assert result.loc[0, "nain_400"] == 0.988


def test_prepare_web_space_syntax_points_uses_segment_midpoints():
    source = gpd.GeoDataFrame(
        {"seg_id": [1], "connectivity": [4], "betw_edge": [10], "clo_mean": [0], "str_mean": [0.5],
         "NC_400": [1], "NC_2500": [2], "TD_400": [3], "MD_400": [4], "NAIN_400": [5],
         "CH_400": [6], "NACH_400": [7], "TD_2500": [8], "MD_2500": [9], "NAIN_2500": [10],
         "CH_2500": [11], "NACH_2500": [12], "clipped_length_m": [100]},
        geometry=[LineString([(500000, 2545000), (500100, 2545000)])],
        crs="EPSG:32643",
    )

    result = prepare_web_space_syntax_points(source)

    assert result.geometry.iloc[0].geom_type == "Point"


def test_prepare_web_raw_buildings_preserves_source_fields():
    source = gpd.GeoDataFrame(
        {
            "area_in_meters": [12.34],
            "confidence": [0.87654],
            "full_plus_code": ["abc123"],
        },
        geometry=[Polygon([(72.5, 23.0), (72.5001, 23.0), (72.5001, 23.0001), (72.5, 23.0)])],
        crs="EPSG:4326",
    )
    result = prepare_web_raw_buildings(source)
    assert result[["building_id", "full_plus_code", "footprint_area_m2", "confidence"]].iloc[0].to_dict() == {
        "building_id": "abc123",
        "full_plus_code": "abc123",
        "footprint_area_m2": 12.3,
        "confidence": 0.877,
    }


def test_prepare_web_vector_layer_keeps_public_fields_only():
    source = gpd.GeoDataFrame(
        {"selected": [1], "gain": [12.345], "private": ["drop"]},
        geometry=[Point(500000, 2545000)],
        crs="EPSG:32643",
    )

    result = prepare_web_vector_layer(source, {"selected": ("selected", None), "gain": ("gain", 1)})

    assert result.crs.to_epsg() == 4326
    assert list(result.columns) == ["selected", "gain", "geometry"]
    assert result.loc[0, "gain"] == 12.3


def test_quantile_breaks_returns_unique_ordered_breaks_for_graduated_symbology():
    result = quantile_breaks(pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9]), classes=5)

    assert result == [2.6, 4.2, 5.8, 7.4]


def test_quantile_breaks_uses_only_interior_i_over_n_thresholds():
    assert quantile_breaks(pd.Series(range(7)), classes=3) == [2.0, 4.0]


def test_classification_metadata_reports_effective_class_count_after_duplicate_breaks():
    result = classification_metadata(pd.Series([0, 1, 1, 1, 2, 2, 3]), property_name="betweenness")

    assert result["class_count"] == len(result["breaks"]) + 1
    assert "up to seven" in result["note"].lower()


def test_natural_breaks_separates_a_clear_value_gap():
    result = natural_breaks(pd.Series([1, 2, 3, 10, 11, 12]), classes=2)

    assert result == [1.0, 10.0]
