"""Reproduce the post's OSM POI accessibility graphs for Navrangpura."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import city2graph as c2g
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import osmnx as ox
import pandas as pd
from matplotlib.lines import Line2D

CRS_WGS84 = "EPSG:4326"
CRS_METRIC = "EPSG:32643"  # Ahmedabad / UTM zone 43N
DEFAULT_BBOX = (72.5443429, 23.0159998, 72.5843429, 23.0559998)
TAGS = {
    "amenity": ["school", "hospital", "clinic", "doctors", "pharmacy", "marketplace"],
    "shop": True,
    "leisure": ["gym", "sports_centre"],
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir", type=Path, default=Path("data/navrangpura-ahmedabad"))
    p.add_argument("--output-dir", type=Path, default=Path("data/navrangpura-ahmedabad/accessibility"))
    p.add_argument("--radius", type=float, default=2500, help="Graph radius in metres")
    p.add_argument("--beta", type=float, default=0.5)
    p.add_argument("--skip-osm", action="store_true", help="Reuse cached POIs instead of querying OSM")
    return p.parse_args()


def category(row: pd.Series) -> str:
    for key in ("amenity", "shop", "leisure"):
        value = row.get(key)
        if value is not None and not pd.isna(value) and value not in ("", False):
            return f"{key}={value}"
    return "other"


def category_group(value: str) -> str:
    if value.startswith("amenity=school"):
        return "Education"
    if value.startswith("amenity="):
        return "Health / civic"
    if value.startswith("leisure="):
        return "Leisure"
    if value.startswith("shop="):
        return "Shopping"
    return "Other"


def plot_graph(nodes: gpd.GeoDataFrame, edges: gpd.GeoDataFrame, title: str, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 10))
    edges.plot(ax=ax, color="#00d9ff", linewidth=0.7, alpha=0.65)
    nodes.plot(ax=ax, color="#ff4fd8", markersize=10, alpha=0.85)
    ax.set_title(title)
    ax.set_aspect("equal")
    ax.set_axis_off()
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def plot_comparison(
    poi: gpd.GeoDataFrame,
    roads: gpd.GeoDataFrame,
    graphs: dict[str, tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]],
    path: Path,
) -> None:
    edge_colors = {
        "fixed_euclidean": "#00d9ff",
        "waxman_manhattan": "#ff4fd8",
        "waxman_euclidean": "#00c878",
        "waxman_network": "#ff9f1c",
    }
    poi_colors = {
        "Education": "#1f77b4",
        "Health / civic": "#d62728",
        "Leisure": "#9467bd",
        "Shopping": "#2ca02c",
        "Other": "#7f7f7f",
    }
    fig, axes = plt.subplots(2, 2, figsize=(16, 14), constrained_layout=True)
    for ax, (name, (nodes, edges)) in zip(axes.flat, graphs.items()):
        roads.plot(ax=ax, color="#d0d0d0", linewidth=0.25, alpha=0.45)
        edges.plot(ax=ax, color=edge_colors[name], linewidth=0.45, alpha=0.48)
        for group, color in poi_colors.items():
            subset = poi[poi["category_group"].eq(group)]
            if not subset.empty:
                subset.plot(ax=ax, color=color, markersize=9, alpha=0.9)
        ax.set_title(name.replace("_", " ").title())
        ax.set_aspect("equal")
        ax.set_axis_off()
    edge_handles = [Line2D([0], [0], color=color, lw=2, label=name.replace("_", " ").title()) for name, color in edge_colors.items()]
    poi_handles = [Line2D([0], [0], marker="o", color="w", markerfacecolor=color, markersize=7, label=group) for group, color in poi_colors.items()]
    fig.legend(handles=edge_handles + poi_handles, loc="lower center", ncol=4, frameon=True)
    fig.suptitle("Navrangpura POI access graphs — comparison of distance models", fontsize=16)
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def plot_network_highres(
    poi: gpd.GeoDataFrame,
    roads: gpd.GeoDataFrame,
    nodes: gpd.GeoDataFrame,
    edges: gpd.GeoDataFrame,
    path: Path,
) -> None:
    """Save the bottom-right network panel as a standalone high-resolution map."""
    poi_colors = {
        "Education": "#1f77b4",
        "Health / civic": "#d62728",
        "Leisure": "#9467bd",
        "Shopping": "#2ca02c",
        "Other": "#7f7f7f",
    }
    fig, ax = plt.subplots(figsize=(14, 14))
    roads.plot(ax=ax, color="#d0d0d0", linewidth=0.30, alpha=0.48)
    edges.plot(ax=ax, color="#ff9f1c", linewidth=0.85, alpha=0.78)
    for group, color in poi_colors.items():
        subset = poi[poi["category_group"].eq(group)]
        if not subset.empty:
            subset.plot(ax=ax, color=color, markersize=18, alpha=0.92)
    handles = [
        Line2D([0], [0], color="#ff9f1c", lw=3, label="Waxman network edges"),
        *[
            Line2D([0], [0], marker="o", color="w", markerfacecolor=color, markersize=9, label=group)
            for group, color in poi_colors.items()
        ],
    ]
    ax.legend(handles=handles, loc="lower center", ncol=3, frameon=True)
    ax.set_title("Navrangpura POI access — Waxman network graph", fontsize=18, pad=14)
    ax.set_aspect("equal")
    ax.set_axis_off()
    fig.savefig(path, dpi=400, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    segment_path = args.data_dir / "bbox_segment.geojson"
    if not segment_path.exists():
        raise FileNotFoundError(segment_path)

    poi_path = args.output_dir / "osm_pois.geojson"
    if args.skip_osm and poi_path.exists():
        poi = gpd.read_file(poi_path)
    else:
        poi = ox.features_from_bbox(DEFAULT_BBOX, TAGS).reset_index()
        poi = poi[poi.geometry.notna()].copy()
        poi["category"] = poi.apply(category, axis=1)
        poi.to_file(poi_path, driver="GeoJSON")
    poi = poi.to_crs(CRS_METRIC)
    poi = poi.set_geometry(poi.geometry.centroid)
    poi = poi.dropna(subset=["geometry"]).reset_index(drop=True)
    poi["category_group"] = poi["category"].map(category_group)

    segments = gpd.read_file(segment_path)
    segments = segments[segments["subtype"].eq("road")].copy().to_crs(CRS_METRIC)
    segments = segments[segments.geometry.notna() & ~segments.geometry.is_empty].copy()

    outputs: dict[str, object] = {
        "bbox_wgs84": list(DEFAULT_BBOX),
        "crs_analysis": CRS_METRIC,
        "radius_m": args.radius,
        "beta": args.beta,
        "poi_count": int(len(poi)),
        "poi_by_category": {str(k): int(v) for k, v in poi["category"].value_counts().items()},
        "road_segment_count": int(len(segments)),
    }

    graph_specs = {
        "fixed_euclidean": lambda: c2g.fixed_radius_graph(poi, radius=args.radius, distance_metric="euclidean"),
        "waxman_manhattan": lambda: c2g.waxman_graph(poi, r0=args.radius, beta=args.beta, seed=42, distance_metric="manhattan"),
        "waxman_euclidean": lambda: c2g.waxman_graph(poi, r0=args.radius, beta=args.beta, seed=42, distance_metric="euclidean"),
        "waxman_network": lambda: c2g.waxman_graph(poi, r0=args.radius, beta=args.beta, seed=42, distance_metric="network", network_gdf=segments),
    }
    graph_outputs: dict[str, tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]] = {}
    for name, builder in graph_specs.items():
        nodes, edges = builder()
        graph_outputs[name] = (nodes, edges)
        graph_dir = args.output_dir / name
        graph_dir.mkdir(exist_ok=True)
        edges.to_file(graph_dir / "edges.geojson", driver="GeoJSON")
        nodes.to_file(graph_dir / "nodes.geojson", driver="GeoJSON")
        plot_graph(nodes, edges, name.replace("_", " ").title(), graph_dir / "graph.png")
        outputs[name] = {"nodes": int(len(nodes)), "edges": int(len(edges))}

    plot_comparison(poi, segments, graph_outputs, args.output_dir / "comparison_multicolor.png")
    network_nodes, network_edges = graph_outputs["waxman_network"]
    plot_network_highres(
        poi,
        segments,
        network_nodes,
        network_edges,
        args.output_dir / "waxman_network_highres.png",
    )

    (args.output_dir / "summary.json").write_text(json.dumps(outputs, indent=2) + "\n")
    print(json.dumps(outputs, indent=2))
    print(f"Saved outputs: {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
