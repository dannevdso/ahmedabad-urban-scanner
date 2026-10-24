"""Helpers for building clean, reproducible PlanX pilot input layers."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping

import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon

from ahmedabad_scanner.destinations import classify_osm_feature, osm_feature_identifier


def deduplicate_undirected_network(edges: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Collapse directed edge pairs, retaining the least-cost edge per pair."""
    required = {"u", "v", "length", "walk_time_min", "geometry"}
    missing = required.difference(edges.columns)
    if missing:
        raise ValueError(f"network edges missing columns: {sorted(missing)}")
    result = edges.copy()
    result = result[result.geometry.notna() & ~result.geometry.is_empty].copy()
    result["_u"] = result[["u", "v"]].min(axis=1)
    result["_v"] = result[["u", "v"]].max(axis=1)
    result = result[result["_u"] != result["_v"]]
    result = result.sort_values(["_u", "_v", "walk_time_min", "length", "key" if "key" in result else "_u"], kind="mergesort")
    result = result.drop_duplicates(["_u", "_v"], keep="first").copy()
    result["u"] = result.pop("_u").astype("int64")
    result["v"] = result.pop("_v").astype("int64")
    result = result.sort_values(["u", "v"], kind="mergesort").reset_index(drop=True)
    return gpd.GeoDataFrame(result, geometry="geometry", crs=edges.crs)


def add_stable_building_ids(buildings: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Add deterministic geometry-derived IDs without depending on row order."""
    if buildings.crs is None:
        raise ValueError("buildings require a CRS before stable IDs are generated")
    result = buildings.copy()
    result["building_id"] = [
        "bldg_" + hashlib.sha1(geometry.wkb, usedforsecurity=False).hexdigest()[:16]
        if geometry is not None and not geometry.is_empty
        else "bldg_" + hashlib.sha1(f"empty-{index}".encode(), usedforsecurity=False).hexdigest()[:16]
        for index, geometry in enumerate(result.geometry)
    ]
    if result["building_id"].duplicated().any():
        raise ValueError("building geometries produced duplicate stable building IDs")
    return result


def thin_points_on_grid(
    points: gpd.GeoDataFrame,
    *,
    spacing_m: float,
    source_id: str,
    output_id: str,
    prefix: str,
) -> gpd.GeoDataFrame:
    """Keep the lexicographically first source point in each deterministic grid cell."""
    if spacing_m <= 0:
        raise ValueError("spacing_m must be positive")
    if source_id not in points.columns:
        raise ValueError(f"points missing source ID column: {source_id}")
    result = points.copy()
    result = result[result.geometry.notna() & ~result.geometry.is_empty].copy()
    result["_grid_x"] = (result.geometry.x // spacing_m).astype("int64")
    result["_grid_y"] = (result.geometry.y // spacing_m).astype("int64")
    result["_source_sort"] = result[source_id].astype(str)
    result = result.sort_values(["_grid_x", "_grid_y", "_source_sort"], kind="mergesort")
    result = result.drop_duplicates(["_grid_x", "_grid_y"], keep="first").copy()
    result = result.sort_values(["_grid_x", "_grid_y", "_source_sort"], kind="mergesort").reset_index(drop=True)
    result[output_id] = [f"{prefix}_{index:06d}" for index in range(1, len(result) + 1)]
    return gpd.GeoDataFrame(result.drop(columns=["_grid_x", "_grid_y", "_source_sort"]), geometry="geometry", crs=points.crs)


def extract_green_spaces(raw: gpd.GeoDataFrame, *, metric_crs: str) -> gpd.GeoDataFrame:
    """Extract polygonal OSM features classified as green space."""
    result = raw.copy()
    result["category"] = result.apply(classify_osm_feature, axis=1)
    result = result[result["category"].eq("green") & result.geometry.notna() & ~result.geometry.is_empty].copy()
    result = result[result.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    if result.empty:
        return gpd.GeoDataFrame(result, geometry="geometry", crs=raw.crs).to_crs(metric_crs)
    result = result.to_crs(metric_crs)
    result["green_space_id"] = result.apply(osm_feature_identifier, axis=1)
    result = result.drop_duplicates("green_space_id", keep="first").reset_index(drop=True)
    return gpd.GeoDataFrame(result, geometry="geometry", crs=metric_crs)


def validate_planx_layers(
    layers: Mapping[str, gpd.GeoDataFrame],
    *,
    expected_crs: str,
    id_columns: Mapping[str, str] | None = None,
) -> None:
    """Validate CRS, non-empty valid geometry, and optional ID uniqueness."""
    id_columns = id_columns or {}
    for name, layer in layers.items():
        if layer.crs is None or layer.crs.to_string() != expected_crs:
            raise ValueError(f"{name} has wrong CRS: expected {expected_crs}, got {layer.crs}")
        if layer.geometry.isna().any() or layer.geometry.is_empty.any() or (~layer.geometry.is_valid).any():
            raise ValueError(f"{name} contains null, empty, or invalid geometry")
        column = id_columns.get(name)
        if column:
            if column not in layer.columns:
                raise ValueError(f"{name} missing ID column {column}")
            if layer[column].isna().any() or layer[column].duplicated().any():
                raise ValueError(f"{name} has missing or duplicate values in {column}")


def make_study_area(bbox_wgs84: tuple[float, float, float, float], *, metric_crs: str) -> gpd.GeoDataFrame:
    """Create the configured WGS84 bbox as a projected polygon."""
    boundary = gpd.GeoDataFrame({"study_area_id": ["navrangpura"]}, geometry=[Polygon([(bbox_wgs84[0], bbox_wgs84[1]), (bbox_wgs84[2], bbox_wgs84[1]), (bbox_wgs84[2], bbox_wgs84[3]), (bbox_wgs84[0], bbox_wgs84[3]), (bbox_wgs84[0], bbox_wgs84[1])])], crs="EPSG:4326")
    return boundary.to_crs(metric_crs)
