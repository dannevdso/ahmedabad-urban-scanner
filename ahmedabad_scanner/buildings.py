"""Building preparation for the Ahmedabad Urban Scanner."""

from __future__ import annotations

import math

import geopandas as gpd
from shapely import make_valid
from shapely.geometry import box


def _shape_axes(geometry: object) -> tuple[float | None, float | None]:
    rectangle = geometry.minimum_rotated_rectangle
    if rectangle.is_empty or rectangle.geom_type != "Polygon":
        return None, None
    coordinates = list(rectangle.exterior.coords)
    edges: list[tuple[float, float]] = []
    for start, end in zip(coordinates, coordinates[1:]):
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        edges.append((math.hypot(dx, dy), math.degrees(math.atan2(dy, dx)) % 180))
    positive_lengths = [length for length, _ in edges if length > 0]
    if len(positive_lengths) < 2:
        return None, None
    longest_length, orientation = max(edges, key=lambda edge: edge[0])
    shortest_length = min(positive_lengths)
    return longest_length / shortest_length, orientation


def prepare_building_frame(
    source: gpd.GeoDataFrame,
    *,
    study_bbox: tuple[float, float, float, float],
    analysis_crs: str,
    min_area_m2: float,
) -> gpd.GeoDataFrame:
    """Select pilot buildings and calculate metric footprint measures.

    Buildings are selected using a representative point inside the configured
    WGS84 bounding box. Their full footprints are retained so boundary-crossing
    structures are not truncated.
    """
    if source.crs is None:
        raise ValueError("Building source must declare a CRS")
    if "id" not in source.columns:
        raise ValueError("Building source must contain an 'id' column")

    buildings = source[source.geometry.notna() & ~source.geometry.is_empty].copy()
    buildings.geometry = buildings.geometry.map(make_valid)
    buildings = buildings[
        buildings.geometry.geom_type.isin(["Polygon", "MultiPolygon"])
    ].copy()
    buildings = buildings.drop_duplicates(subset="id", keep="first")

    wgs84 = buildings.to_crs("EPSG:4326")
    study_area = box(*study_bbox)
    selected = wgs84.geometry.representative_point().within(study_area)
    buildings = buildings.loc[selected.to_numpy()].copy().to_crs(analysis_crs)

    buildings["footprint_area_m2"] = buildings.geometry.area
    buildings = buildings[buildings["footprint_area_m2"] >= min_area_m2].copy()
    buildings["perimeter_m"] = buildings.geometry.length
    buildings["compactness"] = (
        4 * math.pi * buildings["footprint_area_m2"] / buildings["perimeter_m"].pow(2)
    ).clip(upper=1.0)
    axes = buildings.geometry.map(_shape_axes)
    buildings["elongation"] = [axis[0] for axis in axes]
    buildings["orientation_deg"] = [axis[1] for axis in axes]
    buildings = buildings.rename(columns={"id": "building_id"})
    return buildings.reset_index(drop=True)


def prepare_open_buildings_frame(
    source: gpd.GeoDataFrame,
    *,
    study_bbox: tuple[float, float, float, float],
    analysis_crs: str,
    min_area_m2: float,
    confidence_min: float,
) -> gpd.GeoDataFrame:
    """Prepare Google Open Buildings V3 polygons for the pilot."""
    required = {"full_plus_code", "confidence", "geometry"}
    missing = required.difference(source.columns)
    if missing:
        raise ValueError(f"Open Buildings source is missing columns: {sorted(missing)}")

    candidates = source[source["confidence"] >= confidence_min].copy()
    candidates["id"] = candidates["full_plus_code"].astype(str)
    candidates["source"] = "google_open_buildings_v3"
    return prepare_building_frame(
        candidates,
        study_bbox=study_bbox,
        analysis_crs=analysis_crs,
        min_area_m2=min_area_m2,
    )
