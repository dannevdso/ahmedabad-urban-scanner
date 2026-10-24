"""Build the Navrangpura pedestrian network and accessibility indicators."""

from __future__ import annotations

import argparse
import json
import tomllib
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import matplotlib
import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd
from shapely.geometry import box

from ahmedabad_scanner.accessibility import (
    add_walking_times,
    nearest_facility_times,
    reachable_facility_counts,
)
from ahmedabad_scanner.destinations import (
    OSM_DESTINATION_TAGS,
    classify_osm_feature,
    osm_feature_identifier,
)

matplotlib.use("Agg")
import matplotlib.pyplot as plt

CATEGORY_ORDER = [
    "health",
    "education",
    "food",
    "transport",
    "green",
    "civic",
    "culture",
    "sport",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/ahmedabad_pilot.toml"))
    parser.add_argument("--reuse", action="store_true", help="Reuse saved OSM GraphML and raw destination GeoPackage")
    return parser.parse_args()


def buffered_bbox(
    bbox: tuple[float, float, float, float], *, metric_crs: str, buffer_m: float
) -> tuple[float, float, float, float]:
    boundary = gpd.GeoSeries([box(*bbox)], crs="EPSG:4326").to_crs(metric_crs)
    buffered = boundary.buffer(buffer_m).to_crs("EPSG:4326").total_bounds
    return tuple(float(value) for value in buffered)


def destination_points(features: gpd.GeoDataFrame, metric_crs: str) -> gpd.GeoDataFrame:
    records = features.reset_index().copy()
    records["category"] = records.apply(classify_osm_feature, axis=1)
    records = records[records["category"].notna() & records.geometry.notna() & ~records.geometry.is_empty].copy()
    records = records.to_crs(metric_crs)
    records.geometry = records.geometry.representative_point()
    records["source"] = "OpenStreetMap"
    records["destination_id"] = records.apply(osm_feature_identifier, axis=1)
    records = records.drop_duplicates(subset="destination_id", keep="first")
    return records.reset_index(drop=True)


def safe_quantiles(series: pd.Series) -> dict[str, float | None]:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return {"p50": None, "p90": None, "p95": None, "max": None}
    return {
        "p50": round(float(values.quantile(0.50)), 3),
        "p90": round(float(values.quantile(0.90)), 3),
        "p95": round(float(values.quantile(0.95)), 3),
        "max": round(float(values.max()), 3),
    }


def main() -> None:
    args = parse_args()
    project_root = args.config.resolve().parent.parent
    with args.config.open("rb") as file:
        config = tomllib.load(file)

    metric_crs = config["project"]["analysis_crs"]
    bbox = tuple(float(value) for value in config["boundary"]["bbox"])
    access = config["access"]
    query_bbox = buffered_bbox(
        bbox,
        metric_crs=metric_crs,
        buffer_m=float(access["network_buffer_m"]),
    )

    raw_dir = project_root / "data/osm"
    derived_dir = project_root / "data/derived"
    output_dir = project_root / "outputs/accessibility"
    report_dir = project_root / "reports"
    for directory in (raw_dir, derived_dir, output_dir, report_dir):
        directory.mkdir(parents=True, exist_ok=True)

    graph_path = raw_dir / "navrangpura_walk_buffered.graphml"
    raw_destinations_path = raw_dir / "navrangpura_destinations_buffered.gpkg"
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(project_root / "data/osmnx-cache")
    ox.settings.requests_timeout = 300
    ox.settings.log_console = True

    if args.reuse and graph_path.exists():
        graph = ox.load_graphml(graph_path)
    else:
        graph = ox.graph_from_bbox(
            query_bbox,
            network_type=str(access["network_type"]),
            simplify=True,
            retain_all=True,
            truncate_by_edge=True,
        )
        ox.save_graphml(graph, graph_path)

    if args.reuse and raw_destinations_path.exists():
        raw_destinations = gpd.read_file(raw_destinations_path)
    else:
        raw_destinations = ox.features_from_bbox(query_bbox, OSM_DESTINATION_TAGS)
        raw_destinations.to_file(raw_destinations_path, driver="GPKG")

    graph = ox.project_graph(graph, to_crs=metric_crs)
    graph = add_walking_times(graph, speed_kmh=float(access["walk_speed_kmh"]))
    nodes, edges = ox.graph_to_gdfs(graph)
    destinations = destination_points(raw_destinations, metric_crs)

    destination_nodes, destination_snap_distances = ox.distance.nearest_nodes(
        graph,
        X=destinations.geometry.x.to_numpy(),
        Y=destinations.geometry.y.to_numpy(),
        return_dist=True,
    )
    destinations["network_node"] = destination_nodes
    destinations["network_snap_distance_m"] = destination_snap_distances

    buildings_path = project_root / config["inputs"]["buildings"]
    buildings = gpd.read_parquet(buildings_path).to_crs(metric_crs)
    origins = buildings.geometry.representative_point()
    building_nodes, building_snap_distances = ox.distance.nearest_nodes(
        graph,
        X=origins.x.to_numpy(),
        Y=origins.y.to_numpy(),
        return_dist=True,
    )
    buildings["network_node"] = building_nodes
    buildings["network_snap_distance_m"] = building_snap_distances
    metres_per_minute = float(access["walk_speed_kmh"]) * 1000 / 60
    buildings["building_connection_min"] = buildings["network_snap_distance_m"] / metres_per_minute
    buildings["network_snap_ok"] = buildings["network_snap_distance_m"] <= float(access["max_snap_distance_m"])

    thresholds = [int(value) for value in access["cutoffs_minutes"]]
    max_time = float(access["max_analysis_time_min"])
    category_summaries: dict[str, object] = {}
    for category in CATEGORY_ORDER:
        category_destinations = destinations[destinations["category"].eq(category)]
        facility_nodes = category_destinations["network_node"].astype(int).tolist()
        nearest = nearest_facility_times(
            graph,
            facility_nodes=facility_nodes,
            cutoff_min=max_time,
        )
        counts = reachable_facility_counts(
            graph,
            facility_nodes=facility_nodes,
            thresholds_min=thresholds,
        )
        network_times = pd.Series(buildings["network_node"].map(nearest), index=buildings.index, dtype="float64")
        buildings[f"walk_{category}_min"] = network_times + buildings["building_connection_min"]
        buildings.loc[~buildings["network_snap_ok"], f"walk_{category}_min"] = np.nan
        for threshold in thresholds:
            buildings[f"count_{category}_{threshold}min"] = (
                buildings["network_node"].map(counts[threshold]).fillna(0).astype("int32")
            )
        category_summaries[category] = {
            "destinations": int(len(category_destinations)),
            "unique_network_nodes": int(category_destinations["network_node"].nunique()),
            "nearest_time_min": safe_quantiles(buildings[f"walk_{category}_min"]),
            "buildings_within_15min_pct": round(
                float(buildings[f"walk_{category}_min"].le(15).mean() * 100), 2
            ),
        }

    fifteen_minute_columns = [f"walk_{category}_min" for category in CATEGORY_ORDER]
    buildings["essential_categories_15min"] = buildings[fifteen_minute_columns].le(15).sum(axis=1).astype("int8")
    buildings["all_categories_15min"] = buildings["essential_categories_15min"].eq(len(CATEGORY_ORDER))

    building_access_path = derived_dir / "navrangpura-building-accessibility.parquet"
    destination_path = derived_dir / "navrangpura-osm-destinations.parquet"
    network_nodes_path = derived_dir / "navrangpura-walk-nodes.parquet"
    network_edges_path = derived_dir / "navrangpura-walk-edges.parquet"
    buildings.to_parquet(building_access_path, index=False)
    destinations.to_parquet(destination_path, index=False)
    nodes.reset_index().to_parquet(network_nodes_path, index=False)
    edge_output = edges.reset_index()[["u", "v", "key", "length", "walk_time_min", "geometry"]]
    edge_output.to_parquet(network_edges_path, index=False)

    map_path = output_dir / "navrangpura_accessibility_summary.png"
    fig, axes = plt.subplots(2, 2, figsize=(16, 15), constrained_layout=True)
    plots = [
        ("essential_categories_15min", "Essential categories within 15 minutes", "viridis", 0, len(CATEGORY_ORDER)),
        ("walk_health_min", "Walk to nearest healthcare (minutes)", "magma_r", 0, 30),
        ("walk_food_min", "Walk to nearest food destination (minutes)", "magma_r", 0, 30),
        ("walk_green_min", "Walk to nearest mapped green space (minutes)", "magma_r", 0, 30),
    ]
    for ax, (column, title, cmap, vmin, vmax) in zip(axes.flat, plots):
        edges.plot(ax=ax, color="#d8d8d8", linewidth=0.18, alpha=0.5)
        buildings.plot(
            ax=ax,
            column=column,
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
            linewidth=0,
            legend=True,
            missing_kwds={"color": "#bbbbbb", "label": "No data"},
        )
        ax.set_title(title)
        ax.set_axis_off()
    fig.suptitle(
        f"Navrangpura pedestrian-network accessibility · {access['walk_speed_kmh']} km/h",
        fontsize=17,
    )
    fig.savefig(map_path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    undirected = graph.to_undirected()
    components = list(nx.connected_components(undirected))
    summary = {
        "generated_utc": datetime.now(UTC).isoformat(),
        "study_area": config["project"]["study_area"],
        "study_bbox_wgs84": list(bbox),
        "query_bbox_wgs84": list(query_bbox),
        "network_buffer_m": float(access["network_buffer_m"]),
        "network_source": "OpenStreetMap contributors via OSMnx/Overpass",
        "network_type": access["network_type"],
        "walking_speed_kmh": float(access["walk_speed_kmh"]),
        "thresholds_minutes": thresholds,
        "counts_include_building_connection": bool(access["counts_include_building_connection"]),
        "network": {
            "nodes": int(graph.number_of_nodes()),
            "directed_edges": int(graph.number_of_edges()),
            "weak_components": int(nx.number_weakly_connected_components(graph)),
            "largest_undirected_component_nodes": int(max(len(component) for component in components)),
        },
        "buildings": {
            "count": int(len(buildings)),
            "snap_distance_m": safe_quantiles(buildings["network_snap_distance_m"]),
            "over_max_snap_distance": int((~buildings["network_snap_ok"]).sum()),
            "all_eight_categories_15min_pct": round(float(buildings["all_categories_15min"].mean() * 100), 2),
            "median_categories_15min": float(buildings["essential_categories_15min"].median()),
        },
        "destinations": {
            "total": int(len(destinations)),
            "by_category": category_summaries,
            "snap_distance_m": safe_quantiles(destinations["network_snap_distance_m"]),
        },
        "outputs": {
            "building_accessibility": str(building_access_path.relative_to(project_root)),
            "destinations": str(destination_path.relative_to(project_root)),
            "network_graphml": str(graph_path.relative_to(project_root)),
            "network_nodes": str(network_nodes_path.relative_to(project_root)),
            "network_edges": str(network_edges_path.relative_to(project_root)),
            "summary_map": str(map_path.relative_to(project_root)),
        },
        "limitations": [
            "Destination completeness reflects OpenStreetMap coverage and has not yet been validated against municipal registers.",
            "Nearest walking times include the straight-line building-to-network connection; destination counts are calculated from the snapped network node and exclude that connection leg.",
            "Polygon destinations use an interior representative point rather than a verified public entrance.",
            "Proximity does not measure facility capacity, quality, affordability, opening hours, safety, or actual use.",
        ],
    }
    report_path = report_dir / "navrangpura_accessibility_summary.json"
    report_path.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    print(f"Saved accessibility buildings: {building_access_path}")
    print(f"Saved destinations: {destination_path}")
    print(f"Saved map: {map_path}")
    print(f"Saved summary: {report_path}")


if __name__ == "__main__":
    main()
