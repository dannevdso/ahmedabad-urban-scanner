"""Download and clean reproducible OSM layers for the supplied study boundary.

The script deliberately writes only under data/external/osm and reports source,
quality, and limitations. It does not touch web/frontend files or run PlanX.
"""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import osmnx as ox
import pandas as pd
from shapely.geometry import Polygon

DEFAULT_BOUNDARY = Path("data/external/boundary/ahmedabad-gandhinagar-black-line.gpkg")
DEFAULT_OUTPUT = Path("data/external/osm/ahmedabad-gandhinagar-osm.gpkg")
DEFAULT_REPORT = Path("reports/ahmedabad_gandhinagar_osm_audit.json")
DEFAULT_ENDPOINT = "https://overpass-api.de/api/interpreter"

OSM_TAGS: dict[str, list[str] | bool] = {
    "amenity": True,
    "building": True,
    "highway": True,
    "landuse": True,
    "leisure": True,
    "natural": True,
    "public_transport": True,
    "railway": True,
    "shop": True,
    "tourism": True,
    "waterway": True,
}


def source_metadata(retrieved_utc: str, endpoint: str) -> dict[str, str]:
    return {
        "source": "OpenStreetMap via Overpass API",
        "endpoint": endpoint,
        "retrieved_utc": retrieved_utc,
        "license": "ODbL 1.0",
        "attribution": "© OpenStreetMap contributors",
    }


def geometry_quality(frame: gpd.GeoDataFrame) -> dict[str, int]:
    nonempty = frame.geometry.notna() & ~frame.geometry.is_empty
    valid = nonempty & frame.geometry.is_valid
    return {
        "rows": int(len(frame)),
        "nonempty": int(nonempty.sum()),
        "valid": int(valid.sum()),
        "invalid": int((nonempty & ~frame.geometry.is_valid).sum()),
        "empty": int((frame.geometry.notna() & frame.geometry.is_empty).sum()),
    }


def _stable_osm_id(row: pd.Series) -> str:
    element = row.get("element", row.get("element_type"))
    osmid = row.get("osmid", row.get("id"))
    return f"{element}/{osmid}"


def _serialise_tags(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    frame = frame.copy()
    for column in frame.columns:
        if column == frame.geometry.name:
            continue
        if frame[column].map(lambda value: isinstance(value, (list, dict, set, tuple))).any():
            frame[column] = frame[column].map(
                lambda value: json.dumps(value, sort_keys=True, default=str)
                if isinstance(value, (list, dict, set, tuple))
                else value
            )
    return frame


def clean_osm_features(features: gpd.GeoDataFrame, boundary: Polygon) -> gpd.GeoDataFrame:
    """Clip to the exact boundary, remove unusable geometries, and add stable IDs."""
    if features.empty:
        return features.copy()
    frame = features.reset_index() if isinstance(features.index, pd.MultiIndex) else features.copy()
    if frame.crs is None:
        frame = frame.set_crs("EPSG:4326")
    boundary_frame = gpd.GeoDataFrame(geometry=[boundary], crs="EPSG:4326").to_crs(frame.crs)
    frame = gpd.clip(frame, boundary_frame, keep_geom_type=False)
    frame = frame[frame.geometry.notna() & ~frame.geometry.is_empty].copy()
    frame = frame[frame.geometry.is_valid].copy()
    frame["osm_id"] = frame.apply(_stable_osm_id, axis=1)
    frame = frame.drop_duplicates("osm_id", keep="first")
    return _serialise_tags(frame).reset_index(drop=True)


def _read_boundary(path: Path) -> tuple[Polygon, dict[str, Any]]:
    boundary = gpd.read_file(path, layer="study_area")
    if boundary.crs is None:
        raise ValueError("Boundary has no CRS")
    boundary = boundary.to_crs("EPSG:4326")
    if len(boundary) != 1:
        raise ValueError(f"Expected one study_area feature, found {len(boundary)}")
    geometry = boundary.geometry.iloc[0]
    if geometry.is_empty or not geometry.is_valid:
        raise ValueError("Boundary geometry must be non-empty and valid")
    return geometry, {
        "path": str(path),
        "layer": "study_area",
        "rows": int(len(boundary)),
        "crs": str(boundary.crs),
        "geometry_type": geometry.geom_type,
        "geometry_valid": bool(geometry.is_valid),
        "bounds_wgs84": [float(value) for value in geometry.bounds],
        "name": str(boundary.get("name", pd.Series([""])).iloc[0]),
        "status": str(boundary.get("status", pd.Series([""])).iloc[0]),
        "source": str(boundary.get("source", pd.Series([""])).iloc[0]),
    }


def _write_layer(frame: gpd.GeoDataFrame, path: Path, layer_name: str) -> dict[str, Any]:
    frame = frame.copy()
    # GeoPackage field names are case-insensitive and OSMnx responses can
    # contain both an index-derived `id`/`Id` and the stable `osm_id` field.
    seen: set[str] = set()
    keep: list[str] = []
    for column in frame.columns:
        folded = str(column).casefold()
        if folded == "id" or folded in seen:
            continue
        seen.add(folded)
        keep.append(str(column))
    frame = frame[keep]
    frame.to_file(path, layer=layer_name, driver="GPKG", engine="pyogrio", index=False)
    return {
        "layer": layer_name,
        "rows": int(len(frame)),
        "size_bytes_after_write": int(path.stat().st_size),
        "crs": str(frame.crs),
        "geometry_types": {str(k): int(v) for k, v in frame.geometry.geom_type.value_counts().items()},
        "geometry_quality": geometry_quality(frame),
        "columns": [str(column) for column in frame.columns],
    }


def download_and_clean(
    boundary_path: Path,
    output_path: Path,
    endpoint: str,
    requested_keys: list[str] | None = None,
) -> dict[str, Any]:
    boundary, boundary_audit = _read_boundary(boundary_path)
    retrieved = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()
    ox.settings.overpass_url = endpoint.removesuffix("/interpreter")
    ox.settings.overpass_rate_limit = False
    ox.settings.requests_timeout = 120
    ox.settings.log_console = True
    # Query one thematic key at a time so a large mixed query does not monopolise
    # a public Overpass worker and so failures can be retried by theme.
    thematic_frames: list[gpd.GeoDataFrame] = []
    failed_queries: dict[str, str] = {}
    query_tags = {key: OSM_TAGS[key] for key in (requested_keys or list(OSM_TAGS))}
    for key, value in query_tags.items():
        try:
            thematic_frames.append(ox.features_from_polygon(boundary, {key: value}))
        except Exception as error:  # public Overpass capacity varies by minute
            failed_queries[key] = f"{type(error).__name__}: {error}"
    if not thematic_frames:
        raise RuntimeError(f"All Overpass thematic queries failed: {failed_queries}")
    raw = gpd.GeoDataFrame(pd.concat(thematic_frames, ignore_index=False), crs="EPSG:4326")
    raw = raw[~raw.index.duplicated(keep="first")]
    cleaned = clean_osm_features(raw, boundary)
    if cleaned.crs is None:
        cleaned = cleaned.set_crs("EPSG:4326")
    cleaned = cleaned.to_crs("EPSG:4326")

    layers: list[dict[str, Any]] = []
    for layer_name, geometry_type in (("points", "Point"), ("lines", "LineString"), ("polygons", "Polygon")):
        subset = cleaned[cleaned.geometry.geom_type.eq(geometry_type)].copy()
        if geometry_type == "LineString":
            subset = pd.concat([subset, cleaned[cleaned.geometry.geom_type.eq("MultiLineString")]], ignore_index=True)
        elif geometry_type == "Polygon":
            subset = pd.concat([subset, cleaned[cleaned.geometry.geom_type.eq("MultiPolygon")]], ignore_index=True)
        if not subset.empty:
            layers.append(_write_layer(subset, output_path, layer_name))

    report = {
        **source_metadata(retrieved, endpoint),
        "boundary": boundary_audit,
        "query_tags": query_tags,
        "successful_query_keys": [key for key in query_tags if key not in failed_queries],
        "failed_query_keys": failed_queries,
        "raw_feature_count": int(len(raw)),
        "cleaned_feature_count": int(len(cleaned)),
        "output": {
            "path": str(output_path),
            "size_bytes": int(output_path.stat().st_size),
            "crs": "EPSG:4326",
            "layers": layers,
        },
        "limitations": [
            "Overpass is a live API; reruns can change as OpenStreetMap is edited.",
            "The extract contains only objects matching the documented thematic tags; untagged or differently tagged features are excluded.",
            "OSM completeness, positional accuracy, access permissions, names, opening hours, capacity, and facility quality are not independently validated.",
            "The study boundary is user-supplied and does not represent an official administrative boundary.",
            "No frontend map data was changed and no PlanX analysis was run.",
        ],
    }
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boundary", type=Path, default=DEFAULT_BOUNDARY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--keys", help="Comma-separated thematic OSM keys; defaults to all documented keys")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    requested_keys = [key.strip() for key in args.keys.split(",") if key.strip()] if args.keys else None
    report = download_and_clean(args.boundary, args.output, args.endpoint, requested_keys)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
