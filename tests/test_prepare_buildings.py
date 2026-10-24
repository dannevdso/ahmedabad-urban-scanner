from __future__ import annotations

import geopandas as gpd
from shapely.geometry import box

from ahmedabad_scanner.buildings import (
    prepare_building_frame,
    prepare_open_buildings_frame,
)


def test_prepare_building_frame_selects_and_measures_pilot_buildings() -> None:
    source = gpd.GeoDataFrame(
        {
            "id": ["inside", "outside", "tiny"],
            "subtype": ["residential", "commercial", None],
            "num_floors": [3.0, 2.0, None],
        },
        geometry=[
            box(72.55, 23.02, 72.5502, 23.0202),
            box(72.59, 23.02, 72.5902, 23.0202),
            box(72.56, 23.03, 72.560005, 23.030005),
        ],
        crs="EPSG:4326",
    )

    result = prepare_building_frame(
        source,
        study_bbox=(72.5443429, 23.0159998, 72.5843429, 23.0559998),
        analysis_crs="EPSG:32643",
        min_area_m2=10.0,
    )

    assert result["building_id"].tolist() == ["inside"]
    assert result.crs.to_string() == "EPSG:32643"
    assert result.iloc[0]["footprint_area_m2"] > 100
    assert result.iloc[0]["perimeter_m"] > 40
    assert 0 < result.iloc[0]["compactness"] <= 1


def test_prepare_building_frame_reports_elongation_and_orientation() -> None:
    source = gpd.GeoDataFrame(
        {"id": ["rectangle"]},
        geometry=[box(72.55, 23.02, 72.5504, 23.0202)],
        crs="EPSG:4326",
    )

    result = prepare_building_frame(
        source,
        study_bbox=(72.5443429, 23.0159998, 72.5843429, 23.0559998),
        analysis_crs="EPSG:32643",
        min_area_m2=10.0,
    )

    assert 1.8 < result.iloc[0]["elongation"] < 2.2
    assert min(
        abs(result.iloc[0]["orientation_deg"]),
        abs(180 - result.iloc[0]["orientation_deg"]),
    ) < 2


def test_prepare_open_buildings_frame_uses_plus_code_and_confidence() -> None:
    source = gpd.GeoDataFrame(
        {
            "full_plus_code": ["7JMM2H92+22", "7JMM2H93+33"],
            "confidence": [0.91, 0.70],
            "area_in_meters": [400.0, 400.0],
        },
        geometry=[
            box(72.55, 23.02, 72.5502, 23.0202),
            box(72.56, 23.03, 72.5602, 23.0302),
        ],
        crs="EPSG:4326",
    )

    result = prepare_open_buildings_frame(
        source,
        study_bbox=(72.5443429, 23.0159998, 72.5843429, 23.0559998),
        analysis_crs="EPSG:32643",
        min_area_m2=10.0,
        confidence_min=0.802,
    )

    assert result["building_id"].tolist() == ["7JMM2H92+22"]
    assert result["source"].tolist() == ["google_open_buildings_v3"]
    assert result["confidence"].tolist() == [0.91]
