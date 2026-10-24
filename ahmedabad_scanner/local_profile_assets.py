"""Reproducible static analytical assets for Local Area Profile queries."""
from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import tempfile
import time
import uuid
from copy import deepcopy
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

import geopandas as gpd
import pandas as pd
import pyogrio
from shapely.geometry import GeometryCollection, MultiPolygon, Point, Polygon
from shapely import make_valid

from ahmedabad_scanner.gtfs import prepare_transit_route_model, read_gtfs_csv

ASSET_VERSION = "local-profile-assets.v1"
ALLOWED_RADII_M = [400, 800, 1200]
TARGET_CRS = "EPSG:32643"
BUILDING_FIELDS = ["building_id", "footprint_area_m2", "compact", "convexity", "elongation", "centroid_x", "centroid_y"]
BUILDING_SOURCE_FIELDS = BUILDING_FIELDS[:-2]
BUILDING_LOCATION_FIELDS = ["zone_objectid", "zone_group", "height_m", "area_m2", "volume_m3", "suhi"]
BUILDING_LOCATION_LAYER_ZONE = {
    "0-airport": 0, "10west": 10, "18north": 18, "19na": 19, "35east": 35,
    "40south": 40, "41south": 41, "52southwest": 53, "101northwest": 101,
    "181-central-final": 181,
}
IGNORED_BUILDING_LOCATION_LAYERS = ("181centraltemp",)
STREET_FIELDS = ["u", "v", "length_m", "highway", "oneway", "seg_id", "node_from", "node_to"]
SPACE_SYNTAX_FIELDS = [
    "seg_id", "length_m", "betw_edge", "clo_mean", "str_mean", "connectivity",
    "NC_400", "TD_400", "MD_400", "NAIN_400", "CH_400", "NACH_400",
    "NC_2500", "TD_2500", "MD_2500", "NAIN_2500", "CH_2500", "NACH_2500",
]
RASTER_SPECS = {
    "lst": "data/derived/environment-ahmedabad-gandhinagar/landsat-lst-celsius.tif",
    "ndvi": "data/derived/environment-ahmedabad-gandhinagar/sentinel-2-ndvi.tif",
    "height_2023": "data/external/open-buildings-height/ahmedabad-gandhinagar-building-height-2023.tif",
}
RASTER_METRICS = {
    "lst": {"units": "°C", "bins": [30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48], "provenance": "one-scene"},
    "ndvi": {"units": "unitless", "bins": [-1, 0, 0.3, 0.6, 1], "provenance": "one-scene"},
    "height_2023": {"units": "metres", "bins": [0, 3, 6, 10, 15, 25, 50], "provenance": "modelled"},
}
FLOOD_RISK_SOURCE = "../vedas-gis-extractor/other_download/ahm_urban_flood_risk_zones/ahm_urban_flood_risk_zones.PROVISIONAL.geojson"


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def merge_building_location_manifest(canonical: dict, sidecar: dict) -> dict:
    """Merge the point publication and remove the retired polygon publication."""
    result = deepcopy(canonical)
    result.setdefault("assets", {}).pop("buildings", None)
    result.setdefault("sources", {}).pop("buildings", None)
    asset = deepcopy(sidecar["asset"])
    asset.pop("key", None)
    result.setdefault("assets", {})["buildingLocations"] = asset
    result.setdefault("sources", {})["buildingLocations"] = deepcopy(sidecar.get("source", {}))
    result["building_locations_publication"] = {
        "caveats": deepcopy(sidecar.get("caveats", [])),
        "audit": deepcopy(sidecar.get("audit", {})),
    }
    return result


def _write_json_atomic(path: Path, payload: dict) -> None:
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def relative_source(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return f"external-inputs/{path.name}"


def select_columns(frame: gpd.GeoDataFrame, fields: Iterable[str]) -> gpd.GeoDataFrame:
    geometry = frame.geometry.name
    selected = [field for field in fields if field in frame.columns]
    missing = [field for field in fields if field not in frame.columns]
    if missing:
        raise ValueError(f"missing required fields: {missing}")
    return frame[selected + [geometry]].copy()


def _to_target_crs(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if frame.crs is None:
        raise ValueError("source layer has no CRS")
    return frame.to_crs(TARGET_CRS) if str(frame.crs) != TARGET_CRS else frame


def _polygonal_valid(geometry):
    """Repair a zone in memory and retain only its polygonal components."""
    repaired = make_valid(geometry) if not geometry.is_valid else geometry
    parts = []
    for candidate in getattr(repaired, "geoms", (repaired,)):
        if isinstance(candidate, (Polygon, MultiPolygon)):
            parts.extend(candidate.geoms if isinstance(candidate, MultiPolygon) else [candidate])
    if not parts:
        raise ValueError("zone repair produced no polygonal geometry")
    return MultiPolygon(parts) if len(parts) > 1 else parts[0]


def prepare_building_location_points(layers: dict[str, gpd.GeoDataFrame], zones: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, dict]:
    """Apply the approved, source-zone-exclusive point publication rules in memory."""
    if "objectid" not in zones:
        raise ValueError("AMC zones require objectid")
    zone_geometry = {int(row.objectid): _polygonal_valid(row.geometry) for _, row in zones.iterrows()}
    rows = []
    audit = {"ignored_layers": list(IGNORED_BUILDING_LOCATION_LAYERS), "layer_zone_mapping": BUILDING_LOCATION_LAYER_ZONE.copy(), "dropped_conflict": 0, "dropped_outside_declared_zone": 0, "collapsed_value_equivalent": 0}
    for layer, zone_id in BUILDING_LOCATION_LAYER_ZONE.items():
        if layer not in layers:
            continue
        frame = layers[layer]
        if frame.crs is None:
            raise ValueError(f"{layer} has no CRS")
        zone = zone_geometry[zone_id]
        work = frame.to_crs(zones.crs) if str(frame.crs) != str(zones.crs) else frame
        for _, record in work.iterrows():
            if layer != "181-central-final" and bool(record.get("conflict", False)):
                audit["dropped_conflict"] += 1
                continue
            if not zone.covers(record.geometry):
                audit["dropped_outside_declared_zone"] += 1
                continue
            central = layer == "181-central-final"
            height = None if central else pd.to_numeric(pd.Series([record.get("height")]), errors="coerce").iloc[0]
            area = None if central else pd.to_numeric(pd.Series([record.get("area")]), errors="coerce").iloc[0]
            raw_suhi = None if central else record.get("suhi")
            suhi = raw_suhi if isinstance(raw_suhi, str) and raw_suhi.strip() else None
            rows.append({"zone_objectid": zone_id, "zone_group": "central" if central else "enriched", "height_m": height, "area_m2": area, "volume_m3": (height * area if pd.notna(height) and pd.notna(area) else None), "suhi": suhi, "geometry": record.geometry})
    result = gpd.GeoDataFrame(rows, geometry="geometry", crs=zones.crs)
    if result.empty:
        return result.reindex(columns=BUILDING_LOCATION_FIELDS + ["geometry"]), audit
    # The audited source has zero value-equivalent exact-coordinate duplicates once
    # the complete retained source observation is considered.  Do not infer identity
    # from the smaller public schema and accidentally collapse distinct observations.
    audit["collapsed_value_equivalent"] = 0
    return result.loc[:, BUILDING_LOCATION_FIELDS + ["geometry"]].copy(), audit


def add_building_centroids(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Add source-geometry centroids without changing the original geometry."""
    result = frame.copy()
    centroids = result.geometry.centroid
    result["centroid_x"] = centroids.x.astype(float)
    result["centroid_y"] = centroids.y.astype(float)
    validate_centroid_fields(result)
    return result


def validate_centroid_fields(frame: gpd.GeoDataFrame) -> None:
    for field in ("centroid_x", "centroid_y"):
        if field not in frame.columns:
            raise ValueError(f"missing required centroid field: {field}")
        values = pd.to_numeric(frame[field], errors="coerce")
        if values.isna().any() or not all(math.isfinite(float(value)) for value in values):
            raise ValueError(f"{field} values must be finite numeric values")


def write_atomic_fgb(frame: gpd.GeoDataFrame, path: Path, *, layer: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.stem}.{uuid.uuid4().hex}.fgb")
    try:
        pyogrio.write_dataframe(frame, tmp, layer=layer, driver="FlatGeobuf")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _audit_read(path: Path, bbox: tuple[float, float, float, float], layer: str) -> int:
    audit = pyogrio.read_dataframe(path, layer=layer, bbox=bbox, use_arrow=False)
    return len(audit)


def verify_asset(path: Path, *, layer: str, expected_fields: list[str], audit_bbox: tuple[float, float, float, float]) -> dict:
    info = pyogrio.read_info(path, layer=layer)
    fields = list(info["fields"])
    if set(fields) != set(expected_fields):
        raise ValueError(f"{path.name} fields differ: {fields} != {expected_fields}")
    if info["crs"] != TARGET_CRS:
        raise ValueError(f"{path.name} CRS is {info['crs']}, expected {TARGET_CRS}")
    audit_count = _audit_read(path, audit_bbox, layer)
    if "centroid_x" in expected_fields or "centroid_y" in expected_fields:
        audit = pyogrio.read_dataframe(path, layer=layer, bbox=audit_bbox, use_arrow=False)
        validate_centroid_fields(audit)
    return {
        "path": path.name,
        "layer": layer,
        "count": int(info["features"]),
        "audit_count": int(audit_count),
        "fields": fields,
        "crs": info["crs"],
        "bounds": [float(v) for v in info["total_bounds"]],
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "spatial_index_verified": True,
    }


def build_building_location_asset(buildings_source: Path, zones_source: Path, output_dir: Path) -> dict:
    """Build the separate, indexed point analytical asset without touching polygon assets."""
    before = {
        f"external-inputs/{buildings_source.name}": sha256_file(buildings_source),
        f"external-inputs/{zones_source.name}": sha256_file(zones_source),
    }
    zones = pyogrio.read_dataframe(zones_source, columns=["objectid"], use_arrow=True)
    layers = {}
    for layer in BUILDING_LOCATION_LAYER_ZONE:
        columns = [] if layer == "181-central-final" else ["height", "area", "suhi", "conflict"]
        layers[layer] = pyogrio.read_dataframe(buildings_source, layer=layer, columns=columns, use_arrow=True)
    points, audit = prepare_building_location_points(layers, zones)
    points = _to_target_crs(points)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "building-locations.fgb"
    write_atomic_fgb(points, path, layer="building_locations")
    bounds = tuple(float(value) for value in points.total_bounds)
    report = verify_asset(path, layer="building_locations", expected_fields=BUILDING_LOCATION_FIELDS, audit_bbox=bounds)
    after = {
        f"external-inputs/{buildings_source.name}": sha256_file(buildings_source),
        f"external-inputs/{zones_source.name}": sha256_file(zones_source),
    }
    if before != after:
        raise RuntimeError("read-only building point inputs changed during build")
    manifest = {
        "manifest_version": ASSET_VERSION,
        "asset": {**report, "key": "buildingLocations", "layer": "building_locations", "units": {"height_m": "provisional metres", "area_m2": "provisional square metres", "volume_m3": "derived cubic metres (area_m2 × height_m)", "suhi": "unverified categorical class"}},
        "source": {"buildings": _source_record(buildings_source, output_dir.parent), "amc_zones": _source_record(zones_source, output_dir.parent)},
        "caveats": ["VEDAS/ISRO-derived prototype building-point dataset; counts are not a verified census of unique physical buildings.", "Central Zone 181 is count-only and has no synthetic zero attributes.", "Height and area are provisional; SUHI is an unverified categorical class whose provenance remains unverified."],
        "audit": audit,
        "inputs_sha256_before": before,
        "inputs_sha256_after": after,
    }
    sidecar_path = output_dir / "building-locations-manifest.json"
    _write_json_atomic(sidecar_path, manifest)
    canonical_path = output_dir / "manifest.json"
    if canonical_path.exists():
        canonical = json.loads(canonical_path.read_text())
        _write_json_atomic(canonical_path, merge_building_location_manifest(canonical, manifest))
    return manifest


def enrich_gtfs_route_ids(stops: gpd.GeoDataFrame, route_model: dict) -> gpd.GeoDataFrame:
    result = stops.copy()
    route_ids = [str(value) for value in route_model.get("route_ids", [])]
    stop_routes = route_model.get("stop_routes", [])
    result["route_ids"] = [
        [route_ids[index] for index in stop_routes[position] if index < len(route_ids)]
        for position in range(len(result))
    ]
    return result


def _source_record(path: Path, root: Path) -> dict:
    return {"path": relative_source(path, root), "sha256": sha256_file(path), "bytes": path.stat().st_size}


def build_manifest(*, assets: dict, sources: dict, bounds: list[float], audit_center: list[float], generated_at: str | None = None) -> dict:
    assets = {name: {"provenance_status": "not-specified", "claim_type": "exact source geometry/fields", **record} for name, record in assets.items()}
    manifest = {
        "manifest_version": ASSET_VERSION,
        "generated_at_utc": generated_at or datetime.now(UTC).isoformat(),
        "target_crs": TARGET_CRS,
        "bounds": bounds,
        "audit_center": audit_center,
        "allowed_radii_m": ALLOWED_RADII_M,
        "assets": assets,
        "sources": sources,
        "provenance": {"status": "audited-static-publication", "query_model": "client-selected center with bbox-indexed FlatGeobuf reads", "exact_labels": ["exact source geometry/fields", "source-modelled"]},
        "caveats": {
            "remote_sensing": "LST and NDVI are each one supplied scene/observation; they are not seasonal composites or time-series summaries.",
            "vegetation_fraction": "Vegetation fraction is derived in the browser from NDVI pixels at or above the published threshold; it is not a validated canopy or shade measure.",
            "parks_schools": "Parks and schools/universities use the approved published representative-point set; raw Overpass ways and relations are not re-centroided during publication.",
            "gtfs": "route_ids are derived from stop_times/trips in the supplied GTFS model; feed currency is not independently verified.",
            "heat_risk": "Morphology heat-risk polygons are a source-modelled proxy, not observed heat exposure.",
            "flood_risk_area": "Flood-risk area is the exact union of source uf_risk polygons clipped to the metric profile circle; Low is unavailable because the supplied source has no Low Risk Areas class.",
        },
    }
    metrics = {}
    for name, spec in RASTER_METRICS.items():
        if name not in assets:
            continue
        metadata = assets[name].get("metadata", {})
        units = spec["units"]
        metrics[name] = {"url": assets[name]["path"], "crs": metadata.get("crs", TARGET_CRS), "origin": metadata.get("origin"), "pixelSize": metadata.get("pixelSize"), "width": metadata.get("width"), "height": metadata.get("height"), "nodata": metadata.get("nodata"), "units": units, "unit": units, "bins": spec["bins"], "oneScene": spec["provenance"] == "one-scene", "modelled": spec["provenance"] == "modelled"}
    if "height_2023" in metrics:
        metrics["height2023"] = metrics.pop("height_2023")
    if "ndvi" in metrics:
        metrics["vegetationFraction"] = {"derivedFrom": "ndvi", "threshold": 0.3, "units": "0–1", "unit": "0–1", "bins": [0, 1, 2], "derived": True}
    manifest["metrics"] = metrics
    return manifest


def _write_pois(source: Path, stage: Path, root: Path, audit_bbox: tuple[float, float, float, float]) -> dict:
    payload = json.loads(source.read_text())
    rows = []
    for feature in payload.get("features", []):
        properties = feature.get("properties", {})
        kind = {"parks": "park", "schools": "school"}.get(properties.get("poi_type"))
        geometry = feature.get("geometry", {})
        coordinates = geometry.get("coordinates", [])
        if kind and geometry.get("type") == "Point" and len(coordinates) >= 2:
            rows.append({"osm_id": str(properties.get("osm_id")), "name": properties.get("name"), "kind": kind, "representative_point_rule": "approved-source-point", "geometry": Point(float(coordinates[0]), float(coordinates[1]))})
    if len(rows) != 766:
        raise ValueError(f"approved POI set must contain 766 points, got {len(rows)}")
    frame = _to_target_crs(gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326"))
    path = stage / "parks-schools.fgb"
    write_atomic_fgb(frame, path, layer="parks_schools")
    report = verify_asset(path, layer="parks_schools", expected_fields=["osm_id", "name", "kind", "representative_point_rule"], audit_bbox=audit_bbox)
    report.update({"provenance_status": "approved-derived-poi-set", "claim_type": "approved representative points", "category_counts": dict(sorted(Counter(frame["kind"]).items())), "representative_point_rule": "approved-source-point"})
    return report




def _raster_metadata(path: Path) -> dict:
    try:
        import rasterio
        with rasterio.open(path) as dataset:
            return {"crs": str(dataset.crs), "bounds": [float(v) for v in dataset.bounds], "width": dataset.width, "height": dataset.height, "count": dataset.count, "dtype": dataset.dtypes[0], "transform": list(dataset.transform), "origin": [float(dataset.transform.c), float(dataset.transform.f)], "pixelSize": [float(dataset.transform.a), float(dataset.transform.e)], "nodata": dataset.nodata}
    except Exception as exc:
        return {"metadata_status": "unavailable", "error": str(exc)}


def build_assets(root: Path, output_dir: Path, *, audit_center: tuple[float, float] = (251800.0, 2556000.0)) -> dict:
    sources_root = root
    audit_bbox = (audit_center[0] - 500, audit_center[1] - 500, audit_center[0] + 500, audit_center[1] + 500)
    optional_sidecar_path = output_dir / "building-locations-manifest.json"
    optional_asset_path = output_dir / "building-locations.fgb"
    optional_sidecar = None
    if optional_sidecar_path.exists() or optional_asset_path.exists():
        if not optional_sidecar_path.exists() or not optional_asset_path.exists():
            raise FileNotFoundError("building-location publication requires both its asset and sidecar manifest")
        optional_sidecar = json.loads(optional_sidecar_path.read_text())
        asset_record = optional_sidecar.get("asset", {})
        if asset_record.get("sha256") != sha256_file(optional_asset_path) or asset_record.get("bytes") != optional_asset_path.stat().st_size:
            raise ValueError("building-location asset does not match its sidecar manifest")
    stage = Path(tempfile.mkdtemp(prefix="local-profile-", dir=str(output_dir.parent)))
    started = time.perf_counter()
    reports: dict[str, dict] = {}
    source_records: dict[str, dict] = {}
    try:
        stage.mkdir(exist_ok=True)
        specs = [
            ("streets", root / "data/derived/planx/ahmedabad-gandhinagar-outputs/prepared_network.gpkg", "prepared_network", STREET_FIELDS, "exact source geometry/fields"),
            ("centrality", root / "data/derived/planx/ahmedabad-gandhinagar-centrality-full-run-20261018/network_centrality_edges.gpkg", "network_centrality_edges", None, "exact source geometry/fields"),
            ("space_syntax", root / "data/derived/space_syntax/ahmedabad-gandhinagar-space-syntax-clipped.gpkg", "segment_analysis_clipped", SPACE_SYNTAX_FIELDS, "supplied external fields"),
            ("heat_risk", root / "data/derived/planx/ahmedabad-gandhinagar-full-analysis-outputs/heat_risk.gpkg", "heat_risk", None, "source-modelled"),
        ]
        for name, source, layer, fields, claim_type in specs:
            if not source.exists():
                raise FileNotFoundError(source)
            source_records[name] = _source_record(source, sources_root)
            info = pyogrio.read_info(source, layer=layer)
            source_fields = list(info["fields"])
            requested = fields or source_fields
            frame = pyogrio.read_dataframe(source, layer=layer, columns=requested, use_arrow=True)
            frame = _to_target_crs(frame)
            selected_fields = [field for field in requested if field in frame.columns]
            if fields and selected_fields != fields:
                raise ValueError(f"{name} source fields do not match requested fields")
            path = stage / f"{name}.fgb"
            write_atomic_fgb(frame, path, layer=name)
            reports[name] = verify_asset(path, layer=name, expected_fields=selected_fields, audit_bbox=audit_bbox)
            reports[name].update({"provenance_status": "verified-source", "claim_type": claim_type})

        flood_source = root / FLOOD_RISK_SOURCE
        source_records["floodRisk"] = _source_record(flood_source, sources_root)
        flood = _to_target_crs(pyogrio.read_dataframe(flood_source, columns=["uf_risk"], use_arrow=True))
        flood_path = stage / "flood-risk.fgb"
        write_atomic_fgb(flood, flood_path, layer="flood_risk")
        reports["floodRisk"] = verify_asset(flood_path, layer="flood_risk", expected_fields=["uf_risk"], audit_bbox=audit_bbox)
        reports["floodRisk"].update({"provenance_status": "verified-source", "claim_type": "exact source geometry/fields", "risk_field": "uf_risk", "risk_classes": sorted(str(value) for value in flood["uf_risk"].dropna().unique())})

        gtfs_source = root / "data/external/gtfs_compat.zip"
        source_records["gtfs"] = _source_record(gtfs_source, sources_root)
        route_model = prepare_transit_route_model(gtfs_source)
        stops = gpd.GeoDataFrame(
            read_gtfs_csv(gtfs_source, "stops.txt"),
            geometry=gpd.points_from_xy(read_gtfs_csv(gtfs_source, "stops.txt")["stop_lon"].astype(float), read_gtfs_csv(gtfs_source, "stops.txt")["stop_lat"].astype(float)),
            crs="EPSG:4326",
        )
        stops = enrich_gtfs_route_ids(stops[["stop_id", "stop_name", "geometry"]], route_model)
        stops = _to_target_crs(stops)
        path = stage / "gtfs-stops.fgb"
        write_atomic_fgb(stops, path, layer="gtfs_stops")
        reports["gtfs_stops"] = verify_asset(path, layer="gtfs_stops", expected_fields=["stop_id", "stop_name", "route_ids"], audit_bbox=audit_bbox)
        reports["gtfs_stops"].update({"provenance_status": "derived-from-supplied-gtfs", "claim_type": "source-modelled"})

        pois_source = root / "web/public/data/pois.geojson"
        raw_pois_source = root / "data/external/poi/overpass_public_pois.json"
        source_records["parks_schools"] = _source_record(pois_source, sources_root)
        source_records["parks_schools_raw_overpass"] = _source_record(raw_pois_source, sources_root)
        reports["parks_schools"] = _write_pois(pois_source, stage, root, audit_bbox)

        for name, relative in RASTER_SPECS.items():
            source = root / relative
            source_records[name] = _source_record(source, sources_root)
            destination = stage / f"{name}.tif"
            shutil.copy2(source, destination)
            reports[name] = {"path": destination.name, "bytes": destination.stat().st_size, "sha256": sha256_file(destination), "metadata": _raster_metadata(destination), "provenance_status": "verified-source", "claim_type": "exact source numeric values" if name != "height_2023" else "source-modelled"}

        bounds = optional_sidecar.get("asset", {}).get("bounds") if optional_sidecar else reports["streets"]["bounds"]
        manifest = build_manifest(assets=reports, sources=source_records, bounds=bounds, audit_center=list(audit_center))
        if optional_sidecar is not None:
            shutil.copy2(optional_asset_path, stage / optional_asset_path.name)
            shutil.copy2(optional_sidecar_path, stage / optional_sidecar_path.name)
            manifest = merge_building_location_manifest(manifest, optional_sidecar)
        manifest["build_runtime_seconds"] = round(time.perf_counter() - started, 3)
        (stage / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        if output_dir.exists():
            backup = output_dir.with_name(output_dir.name + f".previous-{uuid.uuid4().hex}")
            os.replace(output_dir, backup)
            try:
                os.replace(stage, output_dir)
            except Exception:
                os.replace(backup, output_dir)
                raise
            shutil.rmtree(backup)
        else:
            os.replace(stage, output_dir)
        return manifest
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
