"""Build PlanX-ready GeoPackage inputs for the Navrangpura pilot."""

from __future__ import annotations

import argparse
import json
import shutil
import tomllib
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import pandas as pd

from ahmedabad_scanner.planx_inputs import (
    add_stable_building_ids,
    deduplicate_undirected_network,
    extract_green_spaces,
    make_study_area,
    thin_points_on_grid,
    validate_planx_layers,
)

CATEGORIES = ["health", "education", "food", "transport", "green", "civic", "culture", "sport"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/ahmedabad_pilot.toml"))
    parser.add_argument("--grid-spacing-m", type=float, default=250.0)
    parser.add_argument("--criticality-grid-spacing-m", type=float, default=2000.0)
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def _read_metric(path: Path, metric_crs: str) -> gpd.GeoDataFrame:
    frame = gpd.read_parquet(path)
    if frame.crs is None:
        raise ValueError(f"input has no CRS: {path}")
    return frame.to_crs(metric_crs)


def _clean_buildings(buildings: gpd.GeoDataFrame, metric_crs: str) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    buildings = buildings[buildings.geometry.notna() & ~buildings.geometry.is_empty].copy()
    buildings = buildings[buildings.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    source_ids = buildings["building_id"].astype(str) if "building_id" in buildings.columns else pd.Series("", index=buildings.index, dtype="string")
    buildings = add_stable_building_ids(buildings)
    buildings["source_building_id"] = source_ids.to_numpy()
    keep = [column for column in ["building_id", "source_building_id", "footprint_area_m2", "confidence", "source", "geometry"] if column in buildings.columns]
    buildings = buildings[keep].to_crs(metric_crs).reset_index(drop=True)
    centroids = buildings[["building_id"]].copy()
    centroids["geometry"] = buildings.geometry.representative_point()
    centroids = gpd.GeoDataFrame(centroids, geometry="geometry", crs=metric_crs)
    return buildings, centroids


def _clean_destinations(destinations: gpd.GeoDataFrame, metric_crs: str) -> gpd.GeoDataFrame:
    destinations = destinations.to_crs(metric_crs).copy()
    destinations = destinations[destinations.geometry.notna() & ~destinations.geometry.is_empty].copy()
    destinations["destination_id"] = destinations["destination_id"].astype(str)
    destinations["category"] = destinations["category"].astype(str)
    destinations = destinations.drop_duplicates("destination_id", keep="first")
    destinations["name"] = destinations.get("name", pd.Series(index=destinations.index, dtype="string")).fillna("").astype(str)
    return destinations[["destination_id", "category", "name", "geometry"]].reset_index(drop=True)


def _write_layer(frame: gpd.GeoDataFrame, output: Path, layer: str) -> None:
    frame.to_file(output, layer=layer, driver="GPKG", index=False)


def build_planx_inputs(
    config_path: Path,
    output: Path,
    grid_spacing_m: float = 250.0,
    criticality_grid_spacing_m: float = 2000.0,
) -> dict[str, object]:
    project_root = config_path.resolve().parent.parent
    with config_path.open("rb") as file:
        config = tomllib.load(file)
    metric_crs = str(config["project"]["analysis_crs"])
    inputs = config["inputs"]
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    for sidecar in output.parent.glob(output.stem + "-journal*" ):
        sidecar.unlink()

    edges = _read_metric(project_root / inputs["network_edges"], metric_crs)
    network = deduplicate_undirected_network(edges)
    network = network[["u", "v", "key", "length", "walk_time_min", "geometry"]]

    nodes = _read_metric(project_root / inputs["network_nodes"], metric_crs).reset_index(drop=True)
    nodes["node_id"] = nodes["osmid"].astype(str) if "osmid" in nodes else nodes.index.astype(str)
    candidate_sites = thin_points_on_grid(nodes[["node_id", "geometry"]], spacing_m=grid_spacing_m, source_id="node_id", output_id="candidate_id", prefix="site")
    candidate_sites["source_node_id"] = candidate_sites["node_id"]
    candidate_sites["candidate_type"] = "network_node"
    candidate_sites = candidate_sites[["candidate_id", "source_node_id", "candidate_type", "geometry"]]

    buildings_raw = _read_metric(project_root / inputs["buildings"], metric_crs)
    buildings, building_centroids = _clean_buildings(buildings_raw, metric_crs)
    representative_origins = thin_points_on_grid(
        building_centroids,
        spacing_m=grid_spacing_m,
        source_id="building_id",
        output_id="origin_id",
        prefix="origin",
    )
    representative_origins["demand_weight"] = 1.0
    representative_origins = representative_origins[["origin_id", "building_id", "demand_weight", "geometry"]]
    criticality_origins = thin_points_on_grid(
        building_centroids,
        spacing_m=criticality_grid_spacing_m,
        source_id="building_id",
        output_id="origin_id",
        prefix="criticality",
    )
    criticality_origins = criticality_origins[["origin_id", "building_id", "geometry"]]

    destinations = _clean_destinations(_read_metric(project_root / inputs["destinations"], metric_crs), metric_crs)
    raw_destinations = gpd.read_file(project_root / "data/osm/navrangpura_destinations_buffered.gpkg")
    green_spaces = extract_green_spaces(raw_destinations, metric_crs=metric_crs)
    green_spaces = green_spaces[["green_space_id", "category", "geometry"]]
    study_area = make_study_area(tuple(float(value) for value in config["boundary"]["bbox"]), metric_crs=metric_crs)
    civic = destinations[destinations["category"].eq("civic")].copy()

    layers: dict[str, gpd.GeoDataFrame] = {
        "raw_network": network,
        "buildings": buildings,
        "building_centroids": building_centroids,
        "destinations": destinations,
        "categories": destinations.copy(),
        "green_spaces": green_spaces,
        "study_area": study_area,
        "representative_origins": representative_origins,
        "criticality_origins": criticality_origins,
        "candidate_sites": candidate_sites,
        "civic_facilities": civic,
    }
    id_columns = {
        "buildings": "building_id",
        "building_centroids": "building_id",
        "destinations": "destination_id",
        "categories": "destination_id",
        "green_spaces": "green_space_id",
        "study_area": "study_area_id",
        "representative_origins": "origin_id",
        "criticality_origins": "origin_id",
        "candidate_sites": "candidate_id",
        "civic_facilities": "destination_id",
    }
    validate_planx_layers(layers, expected_crs=metric_crs, id_columns=id_columns)

    for name, layer in layers.items():
        _write_layer(layer, output, name)
    for category in CATEGORIES:
        subset = destinations[destinations["category"].eq(category)].copy()
        if not subset.empty:
            _write_layer(subset, output, f"destination_{category}")

    summary = {
        "generated_utc": datetime.now(UTC).isoformat(),
        "study_area": config["project"]["study_area"],
        "crs": metric_crs,
        "grid_spacing_m": grid_spacing_m,
        "criticality_grid_spacing_m": criticality_grid_spacing_m,
        "bounds": {name: [round(float(value), 3) for value in layer.total_bounds] for name, layer in layers.items()},
        "counts": {name: int(len(layer)) for name, layer in layers.items()},
        "destination_categories": {category: int((destinations["category"] == category).sum()) for category in CATEGORIES},
        "layers": list(layers) + [f"destination_{category}" for category in CATEGORIES if (destinations["category"] == category).any()],
        "output": str(output.relative_to(project_root)),
        "limitations": [
            "Network is reduced from directed edges to one least-cost representative per unordered node pair; reverse-direction asymmetries are not retained.",
            "Representative origins and candidate sites are deterministic 250 m grid samples, not a complete demand or feasibility inventory.",
            "Link criticality uses a separate deterministic 2,000 m origin grid to keep segment-removal rerouting computationally bounded; it is an exploratory civic-access vulnerability screen.",
            "Building demand weight is set uniformly to 1.0 because population, occupancy, and floor-area demand are unavailable.",
            "OSM destination and green-space completeness, classification, access permissions, and facility capacity are not independently validated.",
            "Polygon destination points use the supplied representative points and are not verified public entrances.",
        ],
    }
    summary_path = output.with_suffix(".json")
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    args = parse_args()
    config_path = args.config
    project_root = config_path.resolve().parent.parent
    output = args.output or project_root / "data/derived/planx/navrangpura-planx-inputs.gpkg"
    summary = build_planx_inputs(
        config_path,
        output,
        args.grid_spacing_m,
        args.criticality_grid_spacing_m,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
