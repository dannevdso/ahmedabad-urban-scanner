"""Download Overture data and build a City2Graph morphological graph."""

from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import city2graph as c2g
from shapely import Point


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--place", default=None, help="Place name for Nominatim geocoding")
    parser.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        metavar=("MIN_LON", "MIN_LAT", "MAX_LON", "MAX_LAT"),
        help="Bounding box in WGS84; use instead of --place for localities without polygon boundaries",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("data/overturemaps"), help="Directory for downloaded data and outputs"
    )
    parser.add_argument("--distance", type=float, default=500, help="Analysis radius in projected metres")
    parser.add_argument("--clipping-buffer", type=float, default=300, help="Morphology edge-effect buffer in metres")
    parser.add_argument(
        "--plot-all-buildings",
        action="store_true",
        help="Plot all downloaded building footprints behind the clipped morphological graph",
    )
    parser.add_argument(
        "--focus-graph",
        action="store_true",
        help="Set the map extent to the morphological graph instead of the full download area",
    )
    parser.add_argument("--dpi", type=int, default=150, help="Output PNG resolution")
    parser.add_argument("--figure-name", default=None, help="Optional output PNG filename")
    parser.add_argument("--release", default=None, help="Optional pinned Overture release, e.g. 2026-01-21.0")
    parser.add_argument("--skip-download", action="store_true", help="Reuse GeoJSON files already in output-dir")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.bbox and args.place:
        raise ValueError("Use either --place or --bbox, not both")
    if not args.bbox and not args.place:
        args.place = "Liverpool, UK"
    data_dir = args.output_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    prefix = (
        "bbox_"
        if args.bbox
        else args.place.lower().replace(",", "").replace(" ", "_") + "_"
    )

    if not args.skip_download:
        area_label = args.bbox if args.bbox else args.place
        print(f"Downloading segment, building, and connector data for {area_label}...")
        c2g.load_overture_data(
            area=args.bbox,
            place_name=None if args.bbox else args.place,
            types=["segment", "building", "connector"],
            output_dir=str(data_dir),
            prefix=prefix,
            save_to_file=True,
            return_data=False,
            release=args.release,
        )

    buildings_path = data_dir / f"{prefix}building.geojson"
    segments_path = data_dir / f"{prefix}segment.geojson"
    connectors_path = data_dir / f"{prefix}connector.geojson"
    for path in (buildings_path, segments_path, connectors_path):
        if not path.exists():
            raise FileNotFoundError(f"Expected downloaded file is missing: {path}")

    buildings = gpd.read_file(buildings_path).to_crs(epsg=27700)
    segments = gpd.read_file(segments_path).to_crs(epsg=27700)
    connectors = gpd.read_file(connectors_path).to_crs(epsg=27700)
    segments = segments[segments["subtype"] == "road"].copy()
    segments = c2g.process_overture_segments(
        segments_gdf=segments,
        get_barriers=True,
        connectors_gdf=connectors,
    )

    # Use the geocoder's boundary or the centre of the supplied WGS84 bbox.
    if args.bbox:
        min_lon, min_lat, max_lon, max_lat = args.bbox
        center_point = gpd.GeoSeries(
            [Point((min_lon + max_lon) / 2, (min_lat + max_lat) / 2)],
            crs="EPSG:4326",
        ).to_crs(epsg=27700)
    else:
        boundary = c2g.get_boundaries(args.place).to_crs(epsg=27700)
        center_point = gpd.GeoSeries([boundary.geometry.iloc[0].centroid], crs=boundary.crs)
    nodes, edges = c2g.morphological_graph(
        buildings_gdf=buildings,
        segments_gdf=segments,
        center_point=center_point,
        distance=args.distance,
        clipping_buffer=args.clipping_buffer,
        primary_barrier_col="barrier_geometry",
        contiguity="queen",
        keep_buildings=True,
        keep_segments=True,
    )

    print(f"Buildings: {len(buildings):,}")
    print(f"Road segments after processing: {len(segments):,}")
    print(f"Place nodes: {len(nodes['place']):,}")
    print(f"Movement nodes: {len(nodes['movement']):,}")
    for edge_type, edge_gdf in edges.items():
        print(f"{edge_type}: {len(edge_gdf):,}")

    figure_path = data_dir / (args.figure_name or f"{prefix}city2graph.png")
    fig, ax = plt.subplots(figsize=(14, 12))
    if args.plot_all_buildings:
        buildings.plot(ax=ax, color="#e0e0e0", edgecolor="#c0c0c0", linewidth=0.15, alpha=0.7)
    nodes["place"]["building_geometry"].plot(ax=ax, color="#e0e0e0", edgecolor="#c0c0c0", linewidth=0.3)
    nodes["movement"]["segment_geometry"].plot(ax=ax, color="#404040", linewidth=0.7, alpha=0.6)
    c2g.plot_graph(
        nodes=nodes,
        edges=edges,
        subplots=False,
        ax=ax,
        bgcolor="#f9f9f9",
        labelcolor="#000000",
        node_color={"place": "red", "movement": "blue"},
        edge_color={
            ("place", "touched_to", "place"): "#B22222",
            ("movement", "connected_to", "movement"): "#0000FF",
            ("place", "faced_to", "movement"): "#7B68EE",
        },
        markersize=10,
        linewidth=0.2,
    )
    if args.focus_graph:
        graph_bounds = gpd.GeoSeries(
            list(nodes["place"].geometry) + list(nodes["movement"].geometry),
            crs=buildings.crs,
        ).total_bounds
        min_x, min_y, max_x, max_y = graph_bounds
        pad_x = max((max_x - min_x) * 0.05, 100)
        pad_y = max((max_y - min_y) * 0.05, 100)
        ax.set_xlim(min_x - pad_x, max_x + pad_x)
        ax.set_ylim(min_y - pad_y, max_y + pad_y)
    ax.set_axis_off()
    fig.savefig(figure_path, dpi=args.dpi, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved map: {figure_path}")


if __name__ == "__main__":
    main()
