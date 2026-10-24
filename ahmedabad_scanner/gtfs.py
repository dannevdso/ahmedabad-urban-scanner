"""GTFS ZIP audit and web-export helpers."""

from __future__ import annotations

import csv
import io
from pathlib import Path
from zipfile import ZipFile

import geopandas as gpd
import networkx as nx
import pandas as pd
from shapely.geometry import LineString, Point, box, mapping
from shapely.strtree import STRtree


def read_gtfs_csv(path: Path, name: str) -> pd.DataFrame:
    with ZipFile(path) as archive:
        with archive.open(name) as raw:
            return pd.read_csv(raw, dtype=str)


def _gtfs_time_to_seconds(value: str) -> int:
    hours, minutes, seconds = (int(part) for part in value.split(":"))
    return hours * 3600 + minutes * 60 + seconds


def _format_gtfs_seconds(value: int) -> str:
    hours = value // 3600
    minutes = (value % 3600) // 60
    return f"{hours:02d}:{minutes:02d}"


def _stop_points(path: Path) -> gpd.GeoDataFrame:
    stops = read_gtfs_csv(path, "stops.txt")
    stops["stop_lat"] = pd.to_numeric(stops["stop_lat"], errors="coerce")
    stops["stop_lon"] = pd.to_numeric(stops["stop_lon"], errors="coerce")
    stops = stops.dropna(subset=["stop_lat", "stop_lon"]).copy()
    return gpd.GeoDataFrame(
        stops[["stop_id", "stop_name"]],
        geometry=gpd.points_from_xy(stops["stop_lon"], stops["stop_lat"]),
        crs="EPSG:4326",
    )


def prepare_gtfs_service_intensity(
    path: Path,
) -> gpd.GeoDataFrame:
    """Count all-day, peak-period, and average-hourly departures at every stop."""
    stop_times = read_gtfs_csv(path, "stop_times.txt")
    stop_times["departure_seconds"] = stop_times["departure_time"].map(_gtfs_time_to_seconds)
    trips = read_gtfs_csv(path, "trips.txt")[["trip_id", "route_id"]]
    departures = stop_times.merge(trips, on="trip_id", how="left", validate="many_to_one")
    departures["morning_peak"] = departures["departure_seconds"].between(8 * 3600, 10 * 3600, inclusive="left")
    departures["evening_peak"] = departures["departure_seconds"].between(17 * 3600, 19 * 3600, inclusive="left")
    intensity = departures.groupby("stop_id", as_index=False).agg(
        daily_departures=("trip_id", "size"),
        morning_peak_departures=("morning_peak", "sum"),
        evening_peak_departures=("evening_peak", "sum"),
        routes_served=("route_id", "nunique"),
    )

    merged = _stop_points(path).merge(intensity, on="stop_id", how="left", validate="one_to_one")
    result = gpd.GeoDataFrame(merged, geometry="geometry", crs="EPSG:4326")
    count_fields = ["daily_departures", "morning_peak_departures", "evening_peak_departures", "routes_served"]
    result[count_fields] = result[count_fields].fillna(0).astype(int)
    service_day_start = int(departures["departure_seconds"].min())
    service_day_end = int(departures["departure_seconds"].max())
    service_day_hours = (service_day_end - service_day_start) / 3600
    if service_day_hours > 0:
        result["departures_per_hour"] = (result["daily_departures"] / service_day_hours).round(2)
    else:
        result["departures_per_hour"] = 0.0
    result["service_day"] = (
        f"{_format_gtfs_seconds(service_day_start)}–{_format_gtfs_seconds(service_day_end)}"
    )
    result.attrs.update(
        service_day_start=_format_gtfs_seconds(service_day_start),
        service_day_end=_format_gtfs_seconds(service_day_end),
        service_day_hours=round(service_day_hours, 3),
    )
    return result


def prepare_transit_route_model(path: Path) -> dict:
    """Prepare compact stop↔route indexes for interactive route-reach mapping."""
    stops = read_gtfs_csv(path, "stops.txt")
    stops["stop_lat"] = pd.to_numeric(stops["stop_lat"], errors="coerce")
    stops["stop_lon"] = pd.to_numeric(stops["stop_lon"], errors="coerce")
    stops = stops.dropna(subset=["stop_id", "stop_lat", "stop_lon"]).drop_duplicates("stop_id").reset_index(drop=True)
    stop_indexes = {stop_id: index for index, stop_id in enumerate(stops["stop_id"])}

    trips_full = read_gtfs_csv(path, "trips.txt")
    trips = trips_full[["trip_id", "route_id"]]
    route_ids = trips["route_id"].dropna().drop_duplicates().tolist()
    route_indexes = {route_id: index for index, route_id in enumerate(route_ids)}
    stop_times = read_gtfs_csv(path, "stop_times.txt")
    stop_times["stop_sequence"] = pd.to_numeric(stop_times["stop_sequence"], errors="coerce")
    stop_times["departure_seconds"] = stop_times["departure_time"].map(_gtfs_time_to_seconds)
    route_stop_rows = (
        stop_times.dropna(subset=["trip_id", "stop_id", "stop_sequence"])
        .merge(trips, on="trip_id", how="inner", validate="many_to_one")
    )
    route_stops: list[list[int]] = [[] for _ in route_ids]
    for route_id, group in route_stop_rows.groupby("route_id", sort=False):
        route_index = route_indexes.get(route_id)
        if route_index is None:
            continue
        route_stops[route_index] = sorted(
            {stop_indexes[stop_id] for stop_id in group["stop_id"] if stop_id in stop_indexes}
        )
    stop_routes: list[list[int]] = [[] for _ in range(len(stops))]
    for route_index, indexes in enumerate(route_stops):
        for stop_index in indexes:
            stop_routes[stop_index].append(route_index)

    service_hours = list(range(4, 25))
    service_hour_indexes = {hour: index for index, hour in enumerate(service_hours)}
    stop_route_service: list[list[list[object]]] = [[] for _ in stops.index]
    departures = stop_times.merge(trips, on="trip_id", how="inner", validate="many_to_one")
    for stop_index, stop_id in enumerate(stops["stop_id"]):
        stop_departures = departures[departures["stop_id"] == stop_id]
        for route_index in stop_routes[stop_index]:
            route_id = route_ids[route_index]
            route_departures = stop_departures.loc[stop_departures["route_id"] == route_id, "departure_seconds"]
            unique_times = sorted(set(int(value) for value in route_departures.dropna()))
            headway = None
            if len(unique_times) >= 2:
                headway = round(sum(b - a for a, b in zip(unique_times, unique_times[1:])) / (len(unique_times) - 1) / 60, 2)
            hourly_counts = [0] * len(service_hours)
            for departure in route_departures.dropna().astype(int):
                hour = min(24, departure // 3600)
                bucket = service_hour_indexes.get(hour)
                if bucket is not None:
                    hourly_counts[bucket] += 1
            stop_route_service[stop_index].append([route_index, headway, hourly_counts])

    try:
        routes_table = read_gtfs_csv(path, "routes.txt")
    except KeyError:
        routes_table = pd.DataFrame(columns=["route_id", "route_short_name", "route_long_name"])
    route_rows = routes_table.set_index("route_id", drop=False) if "route_id" in routes_table else pd.DataFrame()
    try:
        shapes_table = read_gtfs_csv(path, "shapes.txt")
    except KeyError:
        shapes_table = pd.DataFrame(columns=["shape_id"])
    valid_shape_ids = set()
    if "shape_id" in shapes_table:
        valid_shape_ids = set(shapes_table.groupby("shape_id").size().loc[lambda counts: counts >= 2].index)
    routes_with_geometry = set()
    if "shape_id" in trips_full:
        routes_with_geometry = set(trips_full.loc[trips_full["shape_id"].isin(list(valid_shape_ids)), "route_id"])

    routes = []
    for route_id in route_ids:
        metadata = route_rows.loc[route_id] if route_id in route_rows.index else {}
        if isinstance(metadata, pd.DataFrame):
            metadata = metadata.iloc[0]
        routes.append({
            "id": str(route_id),
            "short_name": str(metadata.get("route_short_name", "") or ""),
            "long_name": str(metadata.get("route_long_name", "") or ""),
            "has_geometry": route_id in routes_with_geometry,
        })

    return {
        "stops": [
            {
                "id": str(row.stop_id),
                "name": str(row.stop_name),
                "lon": round(float(row.stop_lon), 7),
                "lat": round(float(row.stop_lat), 7),
            }
            for row in stops.itertuples()
        ],
        "route_ids": [str(route_id) for route_id in route_ids],
        "routes": routes,
        "route_stops": route_stops,
        "stop_routes": stop_routes,
        "stop_route_service": stop_route_service,
        "service_hours": service_hours,
    }


def add_transit_isochrone_spatial_index(
    route_model: dict,
    boundary,
    *,
    network: gpd.GeoDataFrame | Path,
    cell_size_m: int = 250,
    walking_speed_kmh: float = 4.8,
    nearby_stop_minutes: int = 5,
    catchment_minutes: int = 15,
    max_snap_distance_m: float = 400,
) -> dict:
    """Add street-network walking links for nearby stops and catchment cells."""
    if walking_speed_kmh <= 0:
        raise ValueError("walking_speed_kmh must be positive")
    if nearby_stop_minutes <= 0 or catchment_minutes <= 0:
        raise ValueError("walking thresholds must be positive")
    metres_per_second = walking_speed_kmh * 1000 / 3600
    network_frame = gpd.read_file(network, layer="prepared_network", engine="pyogrio") if isinstance(network, Path) else network.copy()
    if network_frame.crs is None:
        raise ValueError("prepared street network must declare a projected CRS")

    graph = nx.Graph()
    node_points: dict[int, Point] = {}
    for row in network_frame.itertuples():
        coordinates = list(row.geometry.coords)
        node_from = int(row.node_from)
        node_to = int(row.node_to)
        node_points.setdefault(node_from, Point(coordinates[0]))
        node_points.setdefault(node_to, Point(coordinates[-1]))
        length = float(row.length_m)
        if graph.has_edge(node_from, node_to):
            graph[node_from][node_to]["length_m"] = min(graph[node_from][node_to]["length_m"], length)
        else:
            graph.add_edge(node_from, node_to, length_m=length)

    node_ids = list(node_points)
    node_geometries = [node_points[node_id] for node_id in node_ids]
    node_tree = STRtree(node_geometries)

    def snap_points(points: list[Point]) -> list[tuple[int | None, float]]:
        snapped = []
        for point in points:
            nearest_index = int(node_tree.nearest(point))
            distance = float(point.distance(node_geometries[nearest_index]))
            snapped.append((node_ids[nearest_index] if distance <= max_snap_distance_m else None, distance))
        return snapped

    stops = route_model["stops"]
    stop_frame = gpd.GeoDataFrame(
        {"stop_index": range(len(stops))},
        geometry=[Point(stop["lon"], stop["lat"]) for stop in stops],
        crs="EPSG:4326",
    ).to_crs(network_frame.crs)
    stop_snaps = snap_points(list(stop_frame.geometry))
    node_to_stops: dict[int, list[int]] = {}
    for stop_index, (node_id, _) in enumerate(stop_snaps):
        if node_id is not None:
            node_to_stops.setdefault(node_id, []).append(stop_index)

    nearby_cutoff_m = nearby_stop_minutes * 60 * metres_per_second
    footpaths: list[list[int]] = []
    for from_index, (from_node, from_snap_m) in enumerate(stop_snaps):
        if from_node is None or from_snap_m > nearby_cutoff_m:
            continue
        distances = nx.single_source_dijkstra_path_length(
            graph, from_node, cutoff=max(0, nearby_cutoff_m - from_snap_m), weight="length_m"
        )
        for node_id, network_distance in distances.items():
            for to_index in node_to_stops.get(node_id, []):
                if to_index == from_index:
                    continue
                total_distance = from_snap_m + network_distance + stop_snaps[to_index][1]
                if total_distance <= nearby_cutoff_m:
                    footpaths.append([from_index, to_index, max(1, round(total_distance / metres_per_second))])
    footpaths.sort()

    projected_boundary = gpd.GeoSeries([boundary], crs="EPSG:4326").to_crs(network_frame.crs).iloc[0]
    min_x, min_y, max_x, max_y = projected_boundary.bounds
    projected_cells = []
    cell_points = []
    x = min_x
    while x < max_x:
        y = min_y
        while y < max_y:
            cell = box(x, y, min(x + cell_size_m, max_x), min(y + cell_size_m, max_y)).intersection(projected_boundary)
            if not cell.is_empty:
                projected_cells.append(cell)
                cell_points.append(cell.representative_point())
            y += cell_size_m
        x += cell_size_m
    cell_snaps = snap_points(cell_points)
    catchment_cutoff_m = catchment_minutes * 60 * metres_per_second
    linked_cells = []
    cell_links = []
    for cell, (cell_node, cell_snap_m) in zip(projected_cells, cell_snaps, strict=True):
        if cell_node is None or cell_snap_m > catchment_cutoff_m:
            continue
        distances = nx.single_source_dijkstra_path_length(
            graph, cell_node, cutoff=max(0, catchment_cutoff_m - cell_snap_m), weight="length_m"
        )
        links = []
        for node_id, network_distance in distances.items():
            for stop_index in node_to_stops.get(node_id, []):
                total_distance = cell_snap_m + network_distance + stop_snaps[stop_index][1]
                if total_distance <= catchment_cutoff_m:
                    links.append([stop_index, max(1, round(total_distance / metres_per_second))])
        if links:
            linked_cells.append(cell)
            cell_links.append(sorted(links))
    web_cells = gpd.GeoSeries(linked_cells, crs=network_frame.crs).to_crs("EPSG:4326")

    return {
        **route_model,
        "walking_speed_kmh": walking_speed_kmh,
        "walking_model": "prepared street network",
        "cell_size_m": cell_size_m,
        "nearby_stop_seconds": nearby_stop_minutes * 60,
        "catchment_seconds": catchment_minutes * 60,
        "max_snap_distance_m": max_snap_distance_m,
        "snapped_stop_count": sum(node_id is not None for node_id, _ in stop_snaps),
        "footpaths": footpaths,
        "cells": [
            {"geometry": mapping(geometry), "area_m2": float(projected_cell.area), "links": links}
            for projected_cell, geometry, links in zip(linked_cells, web_cells, cell_links, strict=True)
        ],
    }


def prepare_web_gtfs(path: Path) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Return GTFS stops and ordered route shapes as WGS84 GeoDataFrames."""
    stop_points = _stop_points(path)

    shapes = read_gtfs_csv(path, "shapes.txt")
    trips = read_gtfs_csv(path, "trips.txt")
    try:
        routes = read_gtfs_csv(path, "routes.txt")
    except KeyError:
        routes = pd.DataFrame(columns=["route_id", "route_short_name", "route_long_name"])
    route_metadata = routes.set_index("route_id").to_dict("index")
    shape_routes = trips[["shape_id", "route_id"]].dropna().drop_duplicates()
    for column in ("shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"):
        shapes[column] = pd.to_numeric(shapes[column], errors="coerce")
    shapes = shapes.dropna(subset=["shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"])
    rows = []
    for shape_id, group in shapes.groupby("shape_id", sort=False):
        ordered = group.sort_values("shape_pt_sequence")
        coordinates = list(zip(ordered["shape_pt_lon"], ordered["shape_pt_lat"]))
        if len(coordinates) >= 2:
            for route_id in shape_routes.loc[shape_routes["shape_id"] == shape_id, "route_id"].drop_duplicates():
                metadata = route_metadata.get(route_id, {})
                short_name = str(metadata.get("route_short_name", "") or "")
                long_name = str(metadata.get("route_long_name", "") or "")
                rows.append({
                    "shape_id": shape_id,
                    "route_id": str(route_id),
                    "route_label": short_name or long_name or str(route_id),
                    "geometry": LineString(coordinates),
                })
    route_shapes = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    return stop_points, route_shapes
