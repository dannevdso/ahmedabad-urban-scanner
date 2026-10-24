from __future__ import annotations

import geopandas as gpd
from shapely.geometry import Point, Polygon

from scripts.download_clean_osm import clean_osm_features, geometry_quality, source_metadata


def test_clean_osm_features_keeps_inside_valid_features_and_adds_stable_ids() -> None:
    features = gpd.GeoDataFrame(
        {
            "element": ["node", "way", "way"],
            "osmid": [1, 2, 3],
            "amenity": ["school", None, "hospital"],
            "name": ["A", "B", "C"],
        },
        geometry=[Point(0.5, 0.5), Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]), Point(5, 5)],
        crs="EPSG:4326",
    )
    boundary = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])

    cleaned = clean_osm_features(features, boundary)

    assert cleaned["osm_id"].tolist() == ["node/1", "way/2"]
    assert cleaned["geometry"].is_valid.all()
    assert len(cleaned) == 2


def test_geometry_quality_reports_empty_invalid_and_valid_rows() -> None:
    features = gpd.GeoDataFrame(
        geometry=[Point(0, 0), None, Polygon([(0, 0), (1, 1), (0, 1), (1, 0), (0, 0)])],
        crs="EPSG:4326",
    )
    quality = geometry_quality(features)
    assert quality == {"rows": 3, "nonempty": 2, "valid": 1, "invalid": 1, "empty": 0}


def test_source_metadata_is_explicit_and_reproducible() -> None:
    metadata = source_metadata("2026-10-18T00:00:00Z", "https://overpass-api.de/api/interpreter")
    assert metadata["source"] == "OpenStreetMap via Overpass API"
    assert metadata["retrieved_utc"] == "2026-10-18T00:00:00Z"
    assert metadata["endpoint"] == "https://overpass-api.de/api/interpreter"
    assert metadata["license"] == "ODbL 1.0"
