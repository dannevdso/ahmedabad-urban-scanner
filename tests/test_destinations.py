from __future__ import annotations

import pytest

from ahmedabad_scanner.destinations import classify_osm_feature, osm_feature_identifier


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        ({"amenity": "clinic"}, "health"),
        ({"amenity": "school"}, "education"),
        ({"shop": "supermarket"}, "food"),
        ({"highway": "bus_stop"}, "transport"),
        ({"leisure": "park"}, "green"),
        ({"amenity": "community_centre"}, "civic"),
        ({"amenity": "library"}, "culture"),
        ({"leisure": "sports_centre"}, "sport"),
        ({"shop": "clothes"}, None),
    ],
)
def test_classify_osm_feature_uses_documented_destination_rules(
    tags: dict[str, str], expected: str | None
) -> None:
    assert classify_osm_feature(tags) == expected


def test_osm_feature_identifier_accepts_geopackage_column_names() -> None:
    assert osm_feature_identifier({"element": "node", "id": 123}) == "node/123"
