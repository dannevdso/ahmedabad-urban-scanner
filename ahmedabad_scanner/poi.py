"""Prepare a compact, categorized GeoJSON layer from an Overpass POI response."""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point, shape

CATEGORY_RULES = (
    ("hospitals", ("amenity", {"hospital", "clinic", "doctors"})),
    ("schools", ("amenity", {"school", "college", "university"})),
    ("parks", ("leisure", {"park", "garden", "playground", "pitch", "sports_centre", "stadium"})),
    ("railway", ("railway", {"station", "halt", "tram_stop", "subway_entrance"})),
    ("transit", ("highway", {"bus_stop"})),
    ("transit", ("public_transport", {"station", "platform", "stop_position"})),
    ("public-services", ("amenity", {"library", "police", "fire_station", "post_office", "community_centre", "townhall", "courthouse"})),
    ("markets", ("amenity", {"marketplace"})),
    ("culture", ("tourism", {"museum", "gallery", "zoo", "theme_park"})),
    ("worship", ("amenity", {"place_of_worship"})),
)


def classify_tags(tags: dict[str, str]) -> str | None:
    for category, (key, values) in CATEGORY_RULES:
        if tags.get(key) in values:
            return category
    return None


def load_overpass_pois(path: Path, boundary) -> gpd.GeoDataFrame:
    payload = json.loads(path.read_text())
    rows = []
    for element in payload.get("elements", []):
        tags = element.get("tags", {})
        category = classify_tags(tags)
        if category is None:
            continue
        center = element.get("center")
        if center is None:
            continue
        geometry = Point(float(center["lon"]), float(center["lat"]))
        if not boundary.contains(geometry):
            continue
        rows.append({
            "osm_id": f"{element['type']}/{element['id']}",
            "poi_type": category,
            "name": tags.get("name"),
            "operator": tags.get("operator"),
            "amenity": tags.get("amenity"),
            "leisure": tags.get("leisure"),
            "railway": tags.get("railway"),
            "public_transport": tags.get("public_transport"),
            "highway": tags.get("highway"),
            "tourism": tags.get("tourism"),
            "geometry": geometry,
        })
    return gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
