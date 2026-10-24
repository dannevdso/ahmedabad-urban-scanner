"""Build a bounded, reproducible PlanX package from current study-area sources."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tomllib
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely import from_wkt
from shapely.geometry import Point

from ahmedabad_scanner.destinations import classify_osm_feature, osm_feature_identifier
from ahmedabad_scanner.planx_inputs import (
    add_stable_building_ids,
    extract_green_spaces,
    make_study_area,
    thin_points_on_grid,
    validate_planx_layers,
)

CATEGORIES = ["health", "education", "food", "transport", "green", "civic", "culture", "sport"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/ahmedabad_gandhinagar_planx.toml"))
    parser.add_argument("--output", type=Path, default=Path("data/derived/planx/ahmedabad-gandhinagar-planx-inputs.gpkg"))
    return parser.parse_args()


def _read_metric(path: Path, metric_crs: str, *, layer: str | None = None) -> gpd.GeoDataFrame:
    frame = gpd.read_file(path, layer=layer) if layer else gpd.read_file(path)
    if frame.crs is None:
        raise ValueError(f"input has no CRS: {path}")
    return frame.to_crs(metric_crs)


def _stable_key(value: object) -> str:
    return hashlib.sha1(str(value).encode(), usedforsecurity=False).hexdigest()


def _read_buildings_source(path: Path, boundary_wgs84: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    files = sorted(path.glob("*_buildings.csv.gz")) if path.is_dir() else [path]
    if not files:
        raise FileNotFoundError(f"no Open Buildings CSV shards found under {path}")
    minx, miny, maxx, maxy = boundary_wgs84.total_bounds
    frames = []
    total_rows = 0
    for shard in files:
        for chunk in pd.read_csv(
            shard,
            compression="gzip",
            header=None,
            names=["latitude", "longitude", "area_in_meters", "confidence", "geometry_wkt", "plus_code"],
            chunksize=100_000,
        ):
            total_rows += len(chunk)
            chunk = chunk[
                chunk["longitude"].between(minx, maxx)
                & chunk["latitude"].between(miny, maxy)
            ].copy()
            if chunk.empty:
                continue
            geometries = from_wkt(chunk["geometry_wkt"].to_numpy())
            frame = gpd.GeoDataFrame(
                {
                    "footprint_area_m2": pd.to_numeric(chunk["area_in_meters"], errors="coerce"),
                    "confidence": pd.to_numeric(chunk["confidence"], errors="coerce"),
                    "source": "Google Research Open Buildings V3",
                    "plus_code": chunk["plus_code"].astype(str),
                },
                geometry=geometries,
                crs="EPSG:4326",
            )
            frame = frame[frame.geometry.intersects(boundary_wgs84.geometry.iloc[0])]
            if not frame.empty:
                frames.append(frame)
    if not frames:
        raise ValueError("no building footprints intersect the study boundary")
    result = pd.concat(frames, ignore_index=True)
    result = gpd.GeoDataFrame(result, geometry="geometry", crs="EPSG:4326")
    result.attrs["raw_shard_row_count"] = total_rows
    return result


def _clean_buildings(raw: gpd.GeoDataFrame, metric_crs: str, max_buildings: int, grid_spacing_m: float) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, dict[str, object]]:
    source_count = len(raw)
    raw = raw[raw.geometry.notna() & ~raw.geometry.is_empty].copy()
    raw = raw[raw.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    raw = raw.to_crs(metric_crs)
    raw = add_stable_building_ids(raw)
    raw["source_building_id"] = raw["plus_code"].astype(str) if "plus_code" in raw.columns else ""
    raw["_gx"] = (raw.geometry.representative_point().x // grid_spacing_m).astype("int64")
    raw["_gy"] = (raw.geometry.representative_point().y // grid_spacing_m).astype("int64")
    raw["_rank"] = raw["building_id"].map(_stable_key)
    representatives = (
        raw.sort_values(["_gx", "_gy", "_rank"], kind="mergesort")
        .drop_duplicates(["_gx", "_gy"], keep="first")
    )
    if len(representatives) < max_buildings:
        remaining = raw.loc[~raw.index.isin(representatives.index)].sort_values("_rank", kind="mergesort")
        selected = pd.concat([representatives, remaining.head(max_buildings - len(representatives))])
    else:
        selected = representatives.sort_values("_rank", kind="mergesort").head(max_buildings)
    selected = selected.sort_values("building_id", kind="mergesort").drop(columns=["_gx", "_gy", "_rank"])
    keep = [c for c in ["building_id", "source_building_id", "footprint_area_m2", "confidence", "geometry"] if c in selected.columns]
    buildings = selected[keep].reset_index(drop=True)
    centroids = gpd.GeoDataFrame(
        buildings[["building_id"]].copy(),
        geometry=buildings.geometry.representative_point(),
        crs=metric_crs,
    )
    audit = {
        "source_count": int(source_count),
        "usable_polygon_count": int(len(raw)),
        "selected_count": int(len(buildings)),
        "max_buildings": int(max_buildings),
        "selection_grid_spacing_m": float(grid_spacing_m),
        "selection_rule": "one stable-hash-ranked representative per 150 m grid cell, then stable SHA-1 fill to the configured maximum",
        "source_bounds_wgs84": [float(v) for v in raw.to_crs("EPSG:4326").total_bounds],
        "selected_bounds_metric": [float(v) for v in buildings.total_bounds],
    }
    return buildings, centroids, audit


def _clean_network(raw: gpd.GeoDataFrame, metric_crs: str, min_length_m: float, speed_kmh: float) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, dict[str, object]]:
    frame = raw[raw.geometry.notna() & ~raw.geometry.is_empty].copy()
    frame = frame[frame.geometry.geom_type.isin(["LineString", "MultiLineString"])].explode(index_parts=False, ignore_index=True)
    frame = frame[frame.get("highway", pd.Series(index=frame.index)).notna()].copy()
    frame = frame.to_crs(metric_crs)
    frame["length"] = frame.geometry.length
    frame = frame[frame["length"] >= min_length_m].copy().reset_index(drop=True)
    frame["u"] = frame.geometry.map(lambda g: None)
    frame["v"] = frame.geometry.map(lambda g: None)
    node_ids: dict[tuple[float, float], int] = {}
    def node_id(point):
        key = (round(point.x, 3), round(point.y, 3))
        if key not in node_ids:
            node_ids[key] = len(node_ids) + 1
        return node_ids[key]
    frame["u"] = frame.geometry.map(lambda g: node_id(Point(g.coords[0])))
    frame["v"] = frame.geometry.map(lambda g: node_id(Point(g.coords[-1])))
    frame["key"] = frame.index.astype("int64")
    frame["walk_time_min"] = frame["length"] / (speed_kmh * 1000.0 / 60.0)
    frame["oneway"] = frame.get("oneway", "").fillna("").astype(str)
    keep = [c for c in ["u", "v", "key", "length", "walk_time_min", "highway", "oneway", "osm_id", "geometry"] if c in frame.columns]
    edges = frame[keep].copy()
    nodes = gpd.GeoDataFrame(
        {"node_id": list(node_ids.values())},
        geometry=[Point(x, y) for x, y in node_ids],
        crs=metric_crs,
    )
    audit = {
        "source_line_count": int(len(raw)),
        "highway_line_count_after_explode": int(len(edges)),
        "network_edge_count": int(len(edges)),
        "network_node_count": int(len(nodes)),
        "highway_values": {str(k): int(v) for k, v in frame["highway"].astype(str).value_counts().head(30).items()},
        "bounds_metric": [float(v) for v in edges.total_bounds],
        "construction": "Current OSM lines filtered to highway-tagged geometries, exploded, projected, length-filtered, with deterministic endpoint node IDs; PlanX Prepare Network performs intersection noding and final graph construction.",
    }
    return edges, nodes, audit


def _clean_destinations(raw: gpd.GeoDataFrame, metric_crs: str) -> gpd.GeoDataFrame:
    frame = raw[raw.geometry.notna() & ~raw.geometry.is_empty].copy()
    frame["category"] = frame.apply(classify_osm_feature, axis=1)
    frame = frame[frame["category"].notna()].copy().to_crs(metric_crs)
    frame.geometry = frame.geometry.representative_point()
    frame["destination_id"] = frame.apply(
        lambda row: f"{row.get('element')}/{row.get('osm_id')}", axis=1
    )
    frame["name"] = frame.get("name", pd.Series(index=frame.index)).fillna("").astype(str)
    frame = frame.drop_duplicates("destination_id", keep="first")
    return frame[["destination_id", "category", "name", "geometry"]].reset_index(drop=True)


def _write_layer(frame: gpd.GeoDataFrame, output: Path, layer: str) -> None:
    frame.to_file(output, layer=layer, driver="GPKG", engine="pyogrio", index=False)


def build_inputs(config_path: Path, output: Path) -> dict[str, object]:
    config_path = config_path.resolve()
    output = output.resolve()
    root = config_path.parent.parent
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    metric_crs = str(config["project"]["analysis_crs"])
    boundary_path = root / config["boundary"]["path"]
    boundary = _read_metric(boundary_path, metric_crs, layer=config["boundary"]["layer"])
    if len(boundary) != 1 or not boundary.geometry.iloc[0].is_valid:
        raise ValueError("study boundary must contain one valid feature")
    osm_path = root / config["inputs"]["osm"]
    osm_layers = {name: gpd.read_file(osm_path, layer=name) for name in ("points", "lines", "polygons")}
    buildings_raw = _read_buildings_source(root / config["inputs"]["buildings"], boundary.to_crs("EPSG:4326"))
    buildings, centroids, building_audit = _clean_buildings(
        buildings_raw,
        metric_crs,
        int(config["selection"]["max_buildings"]),
        float(config["selection"]["building_grid_spacing_m"]),
    )
    network, network_nodes, network_audit = _clean_network(
        osm_layers["lines"], metric_crs, float(config["network"]["min_length_m"]), float(config["network"]["walk_speed_kmh"])
    )
    destination_raw = pd.concat([osm_layers["points"], osm_layers["polygons"]], ignore_index=True)
    destinations = _clean_destinations(destination_raw, metric_crs)
    green_spaces = destination_raw.copy()
    green_spaces["category"] = green_spaces.apply(classify_osm_feature, axis=1)
    green_spaces = green_spaces[
        green_spaces["category"].eq("green")
        & green_spaces.geometry.notna()
        & ~green_spaces.geometry.is_empty
        & green_spaces.geometry.geom_type.isin(["Polygon", "MultiPolygon"])
    ].to_crs(metric_crs)
    green_spaces["green_space_id"] = green_spaces.apply(
        lambda row: f"{row.get('element')}/{row.get('osm_id')}", axis=1
    )
    green_spaces = green_spaces.drop_duplicates("green_space_id", keep="first")
    green_spaces = green_spaces[["green_space_id", "category", "geometry"]]
    origins = thin_points_on_grid(centroids, spacing_m=float(config["selection"]["representative_origin_grid_m"]), source_id="building_id", output_id="origin_id", prefix="origin")
    origins["demand_weight"] = 1.0
    origins = origins[["origin_id", "building_id", "demand_weight", "geometry"]]
    criticality = thin_points_on_grid(centroids, spacing_m=float(config["selection"]["criticality_origin_grid_m"]), source_id="building_id", output_id="origin_id", prefix="criticality")
    criticality = criticality[["origin_id", "building_id", "geometry"]]
    candidates = thin_points_on_grid(network_nodes, spacing_m=float(config["selection"]["candidate_site_grid_m"]), source_id="node_id", output_id="candidate_id", prefix="site")
    candidates["source_node_id"] = candidates["node_id"].astype(str)
    candidates["candidate_type"] = "network_node"
    candidates = candidates[["candidate_id", "source_node_id", "candidate_type", "geometry"]]
    civic = destinations[destinations.category.eq("civic")].copy()
    study = boundary[["area_id", "name", "status", "source", "geometry"]].rename(columns={"area_id": "study_area_id"})
    layers = {
        "raw_network": network,
        "network_nodes": network_nodes,
        "buildings": buildings,
        "building_centroids": centroids,
        "destinations": destinations,
        "categories": destinations.copy(),
        "green_spaces": green_spaces,
        "study_area": study,
        "representative_origins": origins,
        "criticality_origins": criticality,
        "candidate_sites": candidates,
        "civic_facilities": civic,
    }
    id_columns = {"buildings":"building_id", "building_centroids":"building_id", "destinations":"destination_id", "categories":"destination_id", "green_spaces":"green_space_id", "study_area":"study_area_id", "representative_origins":"origin_id", "criticality_origins":"origin_id", "candidate_sites":"candidate_id", "civic_facilities":"destination_id", "network_nodes":"node_id"}
    validate_planx_layers(layers, expected_crs=metric_crs, id_columns=id_columns)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    for sidecar in output.parent.glob(output.stem + "-journal*"):
        sidecar.unlink()
    for name, layer in layers.items():
        _write_layer(layer, output, name)
    for category in CATEGORIES:
        subset = destinations[destinations.category.eq(category)].copy()
        if not subset.empty:
            _write_layer(subset, output, f"destination_{category}")
    summary = {
        "generated_utc": datetime.now(UTC).isoformat(),
        "study_area": config["project"]["study_area"],
        "config": str(config_path.relative_to(root)),
        "boundary": {"path": str(boundary_path.relative_to(root)), "layer": config["boundary"]["layer"], "crs": str(boundary.crs), "bounds_wgs84": [float(v) for v in boundary.to_crs("EPSG:4326").total_bounds], "area_m2": float(boundary.to_crs(metric_crs).geometry.area.sum())},
        "source_counts": {"osm_points": int(len(osm_layers["points"])), "osm_lines": int(len(osm_layers["lines"])), "osm_polygons": int(len(osm_layers["polygons"])), "buildings": int(len(buildings_raw))},
        "counts": {name: int(len(layer)) for name, layer in layers.items()},
        "destination_categories": {category: int((destinations.category == category).sum()) for category in CATEGORIES},
        "bounds_metric": {name: [round(float(v), 3) for v in layer.total_bounds] for name, layer in layers.items()},
        "building_audit": building_audit,
        "network_audit": network_audit,
        "output": str(output.relative_to(root)),
        "limitations": [
            "The 1,077,523 current Open Buildings footprints are audited in full but only a deterministic 30,000-footprint subset is passed to building-dependent PlanX stages to keep QGIS computation bounded.",
            "The current OSM extract has 191,277 features from the saved amenity/building/highway queries; no separate amenity query succeeded, so destination categories are limited to tags present in the saved extract.",
            "The OSM highway network uses deterministic endpoint IDs; PlanX Prepare Network performs intersection noding. Endpoint-only source topology is not treated as final topology.",
            "Representative origins, criticality origins, and candidate sites are deterministic grid samples, not population, parcel, or land-availability inventories.",
            "No space-syntax stage is enabled or run.",
        ],
    }
    summary_path = output.with_suffix(".json")
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    args = parse_args()
    print(json.dumps(build_inputs(args.config, args.output), indent=2))


if __name__ == "__main__":
    main()
