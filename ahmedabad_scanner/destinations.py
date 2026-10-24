"""OpenStreetMap destination categories for everyday access."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

OSM_DESTINATION_TAGS: dict[str, list[str]] = {
    "amenity": [
        "arts_centre",
        "cinema",
        "clinic",
        "college",
        "community_centre",
        "doctors",
        "hospital",
        "kindergarten",
        "library",
        "marketplace",
        "pharmacy",
        "school",
        "social_facility",
        "theatre",
        "townhall",
        "university",
    ],
    "shop": [
        "bakery",
        "butcher",
        "convenience",
        "greengrocer",
        "grocery",
        "seafood",
        "supermarket",
    ],
    "highway": ["bus_stop"],
    "public_transport": ["platform", "station", "stop_position"],
    "railway": ["halt", "station", "subway_entrance", "tram_stop"],
    "leisure": [
        "fitness_centre",
        "garden",
        "park",
        "pitch",
        "playground",
        "sports_centre",
        "stadium",
        "swimming_pool",
    ],
    "landuse": ["recreation_ground"],
    "tourism": ["gallery", "museum"],
}


def osm_feature_identifier(tags: Mapping[str, Any]) -> str:
    """Return a stable OSM element identifier from live or saved columns."""
    element = tags.get("element_type", tags.get("element"))
    osmid = tags.get("osmid", tags.get("id"))
    if element is None or osmid is None:
        raise ValueError("OSM feature requires element/type and id/osmid columns")
    return f"{element}/{osmid}"


def classify_osm_feature(tags: Mapping[str, Any]) -> str | None:
    """Assign one documented everyday-destination category."""
    amenity = tags.get("amenity")
    shop = tags.get("shop")
    highway = tags.get("highway")
    public_transport = tags.get("public_transport")
    railway = tags.get("railway")
    leisure = tags.get("leisure")
    landuse = tags.get("landuse")
    tourism = tags.get("tourism")

    if amenity in {"clinic", "doctors", "hospital", "pharmacy"}:
        return "health"
    if amenity in {"college", "kindergarten", "school", "university"}:
        return "education"
    if amenity == "marketplace" or shop in {
        "bakery",
        "butcher",
        "convenience",
        "greengrocer",
        "grocery",
        "seafood",
        "supermarket",
    }:
        return "food"
    if (
        highway == "bus_stop"
        or public_transport in {"platform", "station", "stop_position"}
        or railway in {"halt", "station", "subway_entrance", "tram_stop"}
    ):
        return "transport"
    if leisure in {"garden", "park", "playground"} or landuse == "recreation_ground":
        return "green"
    if amenity in {"community_centre", "social_facility", "townhall"}:
        return "civic"
    if amenity in {"arts_centre", "cinema", "library", "theatre"} or tourism in {
        "gallery",
        "museum",
    }:
        return "culture"
    if leisure in {
        "fitness_centre",
        "pitch",
        "sports_centre",
        "stadium",
        "swimming_pool",
    }:
        return "sport"
    return None
