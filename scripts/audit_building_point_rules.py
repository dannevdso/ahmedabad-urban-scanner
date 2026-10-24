#!/usr/bin/env python3
"""Audit candidate building-point source rules without modifying source attachments.

Reads supplied source files read-only, repairs invalid AMC geometries only in
memory, and writes a concise Markdown/JSON evidence report.  It intentionally
publishes no building asset and never rewrites source geometries.

Run:
  uv run python scripts/audit_building_point_rules.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import shapely
from pyproj import Transformer
from shapely import make_valid
from shapely.ops import transform

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUILDINGS = Path.home() / ".hermes/attachments/buildings.gpkg"
DEFAULT_ZONES = Path.home() / ".hermes/attachments/amc_zones.geojson"
DEFAULT_JSON = ROOT / "reports" / "building_point_zone_rules_audit.json"
DEFAULT_MD = ROOT / "reports" / "building_point_zone_rules_audit.md"
IGNORED_LAYER = "181centraltemp"
CENTRAL_LAYER = "181-central-final"
ENRICHED_LAYERS = [
    "0-airport", "10west", "18north", "19na", "35east", "40south",
    "41south", "52southwest", "101northwest",
]
LAYER_ZONE = {
    "0-airport": 0,
    "10west": 10,
    "18north": 18,
    "19na": 19,
    "35east": 35,
    "40south": 40,
    "41south": 41,
    "52southwest": 53,
    "101northwest": 101,
    "181-central-final": 181,
}
RELEVANT_FIELDS = [
    "source_id", "tile_id", "occurrence", "angle", "area", "height",
    "elevation", "risk", "suhi", "volume", "conflict", "bldg_id",
    "num_floors",
]
ANALYTICAL_FIELDS = ["occurrence", "angle", "area", "height", "elevation", "risk", "suhi", "volume", "conflict", "bldg_id"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def native(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if np.isnan(value) else float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if pd.isna(value):
        return None
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    return value


def compact_bounds(bounds: tuple[float, float, float, float] | list[float]) -> list[float]:
    return [round(float(v), 9) for v in bounds]


def component_counts(geom) -> dict[str, int]:
    counts: Counter[str] = Counter()
    if geom is None or geom.is_empty:
        return {"empty": 1}
    def visit(value):
        if value.geom_type.startswith("Multi") or value.geom_type == "GeometryCollection":
            for part in value.geoms:
                visit(part)
        else:
            counts[value.geom_type] += 1
    visit(geom)
    return dict(sorted(counts.items()))


def polygonal_components(geom) -> list[Any]:
    """Return polygonal parts recursively, excluding make_valid line artifacts."""
    if geom is None or geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [geom]
    if geom.geom_type == "MultiPolygon":
        return list(geom.geoms)
    if geom.geom_type == "GeometryCollection":
        parts: list[Any] = []
        for child in geom.geoms:
            parts.extend(polygonal_components(child))
        return parts
    return []


def controlled_repair(geom) -> tuple[Any, Any, dict[str, int]]:
    """Make geometry valid, then retain only polygonal area for zoning predicates."""
    made_valid = make_valid(geom) if not geom.is_valid else geom
    polygon_parts = polygonal_components(made_valid)
    if not polygon_parts:
        raise ValueError("Zone repair produced no polygonal components.")
    assignment_geom = shapely.union_all(polygon_parts)
    discarded = component_counts(made_valid)
    for kind, count in component_counts(assignment_geom).items():
        if kind in discarded:
            discarded[kind] -= count
            if discarded[kind] == 0:
                del discarded[kind]
    return made_valid, assignment_geom, discarded


def bool_count(series: pd.Series) -> int:
    return int(series.fillna(False).astype(bool).sum())


def dataframe_schema(info: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"name": str(name), "ogr_type": str(dtype)}
        for name, dtype in zip(info.get("fields", []), info.get("dtypes", []), strict=True)
    ]


def gpkg_metadata(path: Path) -> dict[str, Any]:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        contents = conn.execute(
            "SELECT table_name, data_type, identifier, srs_id FROM gpkg_contents ORDER BY table_name"
        ).fetchall()
        geometry = conn.execute(
            "SELECT table_name, column_name, geometry_type_name, srs_id FROM gpkg_geometry_columns ORDER BY table_name"
        ).fetchall()
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
        metadata_rows = []
        if "gpkg_metadata" in tables:
            metadata_rows = conn.execute(
                "SELECT md_scope, mime_type, metadata FROM gpkg_metadata ORDER BY id"
            ).fetchall()
        return {
            "gpkg_contents": [dict(zip(["table_name", "data_type", "identifier", "srs_id"], row, strict=True)) for row in contents],
            "gpkg_geometry_columns": [dict(zip(["table_name", "column_name", "geometry_type_name", "srs_id"], row, strict=True)) for row in geometry],
            "metadata_row_count": len(metadata_rows),
            "metadata_scopes_and_mime_types": [
                {"scope": row[0], "mime_type": row[1], "metadata_preview": str(row[2])[:240]}
                for row in metadata_rows
            ],
        }
    finally:
        conn.close()


def coordinate_keys(gdf: gpd.GeoDataFrame) -> pd.Series:
    # Exact binary-equivalent coordinates after WKB decoding; no rounding/tolerance.
    return gdf.geometry.map(lambda geom: f"{geom.x:.17g}|{geom.y:.17g}" if geom is not None and not geom.is_empty else "<empty>")


def value_signature(frame: pd.DataFrame, fields: list[str]) -> pd.Series:
    present = [field for field in fields if field in frame.columns]
    if not present:
        return pd.Series("", index=frame.index)
    return frame[present].astype("string").fillna("<NULL>").agg("\x1f".join, axis=1)


def records_consistent(frame: pd.DataFrame, fields: list[str]) -> tuple[int, int]:
    """Return repeated groups and groups whose selected values are invariant."""
    available = [field for field in fields if field in frame.columns]
    if "source_id" not in frame or not available:
        return 0, 0
    repeat = frame.groupby("source_id", dropna=False).size()
    repeated_ids = repeat[repeat > 1].index
    groups = 0
    consistent = 0
    for source_id in repeated_ids:
        group = frame.loc[frame["source_id"].eq(source_id), available]
        groups += 1
        if all(group[field].astype("string").fillna("<NULL>").nunique(dropna=False) == 1 for field in available):
            consistent += 1
    return groups, consistent


def covers_mask(geom, points: gpd.GeoSeries) -> np.ndarray:
    # `covers` intentionally includes boundary points; this avoids arbitrary loss
    # from floating-point equality at a zone edge.
    return np.asarray(shapely.covers(geom, points.array), dtype=bool)


def md_table(headers: list[str], rows: list[list[Any]]) -> str:
    escaped_headers = [str(item).replace("|", "\\|") for item in headers]
    lines = ["| " + " | ".join(escaped_headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        escaped = [str(item).replace("|", "\\|").replace("\n", "<br>") for item in row]
        lines.append("| " + " | ".join(escaped) + " |")
    return "\n".join(lines)


def pct(numerator: int, denominator: int) -> str:
    return "—" if not denominator else f"{100 * numerator / denominator:.2f}%"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--buildings", type=Path, default=DEFAULT_BUILDINGS)
    parser.add_argument("--zones", type=Path, default=DEFAULT_ZONES)
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown-out", type=Path, default=DEFAULT_MD)
    args = parser.parse_args()
    buildings_path = args.buildings.resolve()
    zones_path = args.zones.resolve()
    if not buildings_path.is_file() or not zones_path.is_file():
        raise FileNotFoundError("Both input attachments must exist.")

    before_hashes = {str(buildings_path): sha256(buildings_path), str(zones_path): sha256(zones_path)}
    layers_raw = pyogrio.list_layers(buildings_path)
    layer_names = [str(row[0]) for row in layers_raw]
    unexpected = set(layer_names) - ({IGNORED_LAYER, CENTRAL_LAYER} | set(ENRICHED_LAYERS))
    missing_active = set(LAYER_ZONE) - set(layer_names)
    if unexpected or missing_active:
        raise RuntimeError(f"Unexpected/missing layer contract: unexpected={sorted(unexpected)}, missing={sorted(missing_active)}")

    layer_inventory: list[dict[str, Any]] = []
    data: dict[str, gpd.GeoDataFrame] = {}
    for layer in layer_names:
        info = pyogrio.read_info(buildings_path, layer=layer)
        gdf = gpd.read_file(buildings_path, layer=layer, engine="pyogrio")
        data[layer] = gdf
        missingness = {
            field: int(gdf[field].isna().sum()) if field in gdf else None
            for field in RELEVANT_FIELDS
        }
        layer_inventory.append({
            "layer": layer,
            "status": "ignored" if layer == IGNORED_LAYER else ("count_only" if layer == CENTRAL_LAYER else "enriched"),
            "rows": int(len(gdf)),
            "crs": str(gdf.crs),
            "declared_geometry_type": str(info.get("geometry_type")),
            "observed_geometry_types": {str(k): int(v) for k, v in gdf.geom_type.value_counts(dropna=False).items()},
            "fields": dataframe_schema(info),
            "relevant_missingness": missingness,
            "bounds": compact_bounds(gdf.total_bounds),
        })

    zones = gpd.read_file(zones_path, engine="pyogrio")
    if "objectid" not in zones.columns:
        raise RuntimeError("AMC zones lack required objectid field.")
    zones["objectid"] = zones["objectid"].astype(int)
    zones = zones.set_index("objectid", drop=False)
    if set(LAYER_ZONE.values()) != set(zones.index):
        raise RuntimeError(f"Zone objectid contract differs: found {sorted(zones.index)}")

    transformer = Transformer.from_crs(zones.crs, "EPSG:32643", always_xy=True).transform
    zone_audit: dict[str, Any] = {}
    repaired_geoms: dict[int, Any] = {}
    for objectid, row in zones.iterrows():
        original = row.geometry
        made_valid, repaired, discarded_components = controlled_repair(original)
        repaired_geoms[int(objectid)] = repaired
        original_projected = transform(transformer, original)
        repaired_projected = transform(transformer, repaired)
        zone_audit[str(objectid)] = {
            "objectid": int(objectid),
            "unique_id": native(row["unique_id"]) if "unique_id" in zones.columns else None,
            "name_fields": {field: native(row[field]) for field in zones.columns if field != "geometry" and field not in {"objectid", "unique_id"}},
            "original_geometry_type": original.geom_type,
            "original_components": component_counts(original),
            "valid_before": bool(original.is_valid),
            "invalid_reason_before": None if original.is_valid else shapely.is_valid_reason(original),
            "make_valid_geometry_type": made_valid.geom_type,
            "make_valid_components": component_counts(made_valid),
            "discarded_nonpolygon_components": discarded_components,
            "repaired_geometry_type": repaired.geom_type,
            "repaired_components": component_counts(repaired),
            "valid_after": bool(repaired.is_valid),
            "area_before_m2": float(original_projected.area),
            "area_after_m2": float(repaired_projected.area),
            "area_change_m2": float(repaired_projected.area - original_projected.area),
            "area_change_pct": None if original_projected.area == 0 else float(100 * (repaired_projected.area - original_projected.area) / original_projected.area),
            "bounds": compact_bounds(original.bounds),
        }

    enriched = pd.concat([data[layer].assign(_layer=layer) for layer in ENRICHED_LAYERS], ignore_index=True)
    enriched_gdf = gpd.GeoDataFrame(enriched, geometry="geometry", crs=data[ENRICHED_LAYERS[0]].crs)
    enriched["_coordinate_key"] = coordinate_keys(enriched_gdf)
    enriched["_attribute_signature"] = value_signature(enriched, ANALYTICAL_FIELDS + ["source_id", "tile_id"])
    duplicate_groups = enriched.groupby("_coordinate_key", dropna=False).size()
    duplicate_coordinate_keys = duplicate_groups[duplicate_groups > 1]
    exact_coordinate_rows = int(duplicate_coordinate_keys.sum())
    exact_coordinate_extra_rows = int((duplicate_coordinate_keys - 1).sum())
    full_record_fields = [field for field in enriched.columns if field not in {"geometry", "_layer", "_coordinate_key", "_attribute_signature"}]
    full_duplicate_rows = int(enriched.duplicated(subset=["_coordinate_key", *full_record_fields], keep="first").sum())
    source_groups, source_consistent = records_consistent(enriched, ANALYTICAL_FIELDS)
    source_counts = enriched.groupby("source_id", dropna=False).size() if "source_id" in enriched else pd.Series(dtype=int)
    repeated_source_rows = int(source_counts[source_counts > 1].sum()) if len(source_counts) else 0
    repeated_source_extra_rows = int((source_counts[source_counts > 1] - 1).sum()) if len(source_counts) else 0
    repeated_source_coordinate_groups = 0
    repeated_source_multi_coordinate_groups = 0
    if "source_id" in enriched:
        for _, group in enriched.groupby("source_id", dropna=False):
            if len(group) > 1:
                repeated_source_coordinate_groups += 1
                if group["_coordinate_key"].nunique() > 1:
                    repeated_source_multi_coordinate_groups += 1
    conflict_by_layer = {
        layer: {
            "rows": int(len(data[layer])),
            "conflict_true": bool_count(data[layer]["conflict"]) if "conflict" in data[layer] else None,
            "conflict_null": int(data[layer]["conflict"].isna().sum()) if "conflict" in data[layer] else None,
        }
        for layer in ENRICHED_LAYERS
    }
    duplicate_by_layer = {}
    for layer in ENRICHED_LAYERS:
        frame = data[layer].copy()
        frame["_coordinate_key"] = coordinate_keys(frame)
        c = frame.groupby("_coordinate_key").size()
        ids = frame.groupby("source_id", dropna=False).size() if "source_id" in frame else pd.Series(dtype=int)
        groups, consistent = records_consistent(frame, ANALYTICAL_FIELDS)
        duplicate_by_layer[layer] = {
            "rows": int(len(frame)),
            "unique_source_id": int(frame["source_id"].nunique(dropna=False)) if "source_id" in frame else None,
            "source_id_extra_rows": int((ids[ids > 1] - 1).sum()) if len(ids) else None,
            "exact_coordinate_duplicate_groups": int((c > 1).sum()),
            "exact_coordinate_extra_rows": int((c[c > 1] - 1).sum()),
            "repeated_source_id_groups": groups,
            "repeated_source_id_groups_with_invariant_analytical_fields": consistent,
        }

    # Materiality of repairs and exact zone correspondence.  Source geometry is
    # never changed; raw and repaired predicates are evaluated independently.
    zone_mapping: dict[str, Any] = {}
    all_active = pd.concat([data[layer].assign(_layer=layer) for layer in LAYER_ZONE], ignore_index=True)
    active_gdf = gpd.GeoDataFrame(all_active, geometry="geometry", crs=data[ENRICHED_LAYERS[0]].crs)
    raw_geoms = {int(index): row.geometry for index, row in zones.iterrows()}
    coverage_masks_raw: dict[int, np.ndarray] = {}
    coverage_masks_repaired: dict[int, np.ndarray] = {}
    for objectid in sorted(zones.index):
        coverage_masks_raw[int(objectid)] = covers_mask(raw_geoms[int(objectid)], active_gdf.geometry)
        coverage_masks_repaired[int(objectid)] = covers_mask(repaired_geoms[int(objectid)], active_gdf.geometry)

    for layer, objectid in LAYER_ZONE.items():
        subset_indices = np.flatnonzero(active_gdf["_layer"].to_numpy() == layer)
        raw = coverage_masks_raw[objectid][subset_indices]
        repaired = coverage_masks_repaired[objectid][subset_indices]
        zone_mapping[layer] = {
            "objectid": objectid,
            "source_rows": int(len(subset_indices)),
            "covered_by_target_before_repair": int(raw.sum()),
            "covered_by_target_after_repair": int(repaired.sum()),
            "target_membership_changed_by_repair": int(np.count_nonzero(raw != repaired)),
            "target_coverage_after_repair_pct": float(100 * repaired.sum() / len(repaired)) if len(repaired) else None,
        }

    southwest_points_idx = np.flatnonzero(active_gdf["_layer"].to_numpy() == "52southwest")
    southwest_other_coverages = {
        str(objectid): int(mask[southwest_points_idx].sum())
        for objectid, mask in coverage_masks_repaired.items()
    }
    southwest = {
        "point_layer": "52southwest",
        "candidate_zone_objectid": 53,
        "naming_evidence": "Layer name uses 52 while AMC zone objectid uses 53; objectid (not unique_id) is the specified zone key.",
        "point_bounds": compact_bounds(data["52southwest"].total_bounds),
        "zone_bounds": compact_bounds(zones.loc[53].geometry.bounds),
        "zone_valid_before": zone_audit["53"]["valid_before"],
        "zone_valid_after": zone_audit["53"]["valid_after"],
        "points_covered_by_53_after_repair": int(coverage_masks_repaired[53][southwest_points_idx].sum()),
        "points_not_covered_by_53_after_repair": int((~coverage_masks_repaired[53][southwest_points_idx]).sum()),
        "coverage_by_each_repaired_zone": southwest_other_coverages,
        "status": "confirmed" if int(coverage_masks_repaired[53][southwest_points_idx].sum()) / len(southwest_points_idx) >= 0.995 else "probable" if int(coverage_masks_repaired[53][southwest_points_idx].sum()) / len(southwest_points_idx) >= 0.90 else "unresolved",
        "status_basis": "Geometry coverage is evaluated with boundary-inclusive covers after controlled in-memory repair; naming mismatch remains a provenance discrepancy.",
    }

    # Proposed precedence audit. Central is deliberately tested first: it is the
    # only count-only zone and must not be double-counted with enriched sources.
    primary_zone_for_row = active_gdf["_layer"].map(LAYER_ZONE).to_numpy(dtype=int)
    central_mask = coverage_masks_repaired[181]
    expected_mask = np.zeros(len(active_gdf), dtype=bool)
    for zone_id, mask in coverage_masks_repaired.items():
        expected_mask |= (primary_zone_for_row == zone_id) & mask
    proposed_publish_mask = expected_mask & (~((active_gdf["_layer"].to_numpy() != CENTRAL_LAYER) & central_mask))
    central_enriched_overlap = int(((active_gdf["_layer"].to_numpy() != CENTRAL_LAYER) & central_mask).sum())
    precedence_audit = {
        "active_rows": int(len(active_gdf)),
        "eligible_in_declared_target_zone_after_repair": int(expected_mask.sum()),
        "enriched_rows_geometrically_in_central_181": central_enriched_overlap,
        "published_after_central_first_exclusion": int(proposed_publish_mask.sum()),
        "dropped_outside_declared_target_zone": int((~expected_mask).sum()),
        "dropped_by_central_precedence_among_target_eligible": int((expected_mask & ~proposed_publish_mask).sum()),
        "central_source_rows_in_181_after_repair": int((expected_mask & (active_gdf["_layer"].to_numpy() == CENTRAL_LAYER)).sum()),
    }
    out_of_target_records = []
    outlier_indices = np.flatnonzero(~expected_mask)
    for index in outlier_indices:
        row = active_gdf.iloc[index]
        declared_objectid = int(primary_zone_for_row[index])
        covered_objectids = [
            int(objectid)
            for objectid in sorted(coverage_masks_repaired)
            if bool(coverage_masks_repaired[objectid][index])
        ]
        identifiers = {
            field: native(row[field])
            for field in ("source_id", "bldg_id", "tile_id")
            if field in active_gdf.columns
        }
        out_of_target_records.append({
            "source_layer": str(row["_layer"]),
            "declared_objectid": declared_objectid,
            "stable_available_identifiers": identifiers,
            "coordinates": {"x": float(row.geometry.x), "y": float(row.geometry.y)},
            "conflict": native(row["conflict"]) if "conflict" in active_gdf.columns else None,
            "repaired_amc_objectids_covering_point": covered_objectids,
        })
    out_of_target_records.sort(key=lambda item: (item["source_layer"], item["coordinates"]["x"], item["coordinates"]["y"]))

    central = data[CENTRAL_LAYER]
    metadata = gpkg_metadata(buildings_path)
    units_provenance = {
        "gpkg_metadata_rows": metadata["metadata_row_count"],
        "field_level_units_or_provenance_found": False,
        "finding": "No field-level units/provenance were found in GeoPackage metadata tables inspected by this audit. Field names and numerical identities are insufficient to assign reader-facing semantics.",
        "evidence": {
            "elevation_equals_height_all_nonnull_enriched_rows": bool(np.isclose(
                pd.to_numeric(enriched.loc[enriched[["elevation", "height"]].notna().all(axis=1), "elevation"], errors="coerce"),
                pd.to_numeric(enriched.loc[enriched[["elevation", "height"]].notna().all(axis=1), "height"], errors="coerce"),
                rtol=0, atol=0,
            ).all()) if {"elevation", "height"}.issubset(enriched.columns) else None,
            "volume_equals_area_times_height_all_complete_enriched_rows": bool(np.isclose(
                enriched.loc[enriched[["volume", "area", "height"]].notna().all(axis=1), "volume"],
                (enriched.loc[enriched[["volume", "area", "height"]].notna().all(axis=1), "area"] * enriched.loc[enriched[["volume", "area", "height"]].notna().all(axis=1), "height"]),
                rtol=0, atol=1e-9,
            ).all()) if {"volume", "area", "height"}.issubset(enriched.columns) else None,
        },
        "blockers": [
            "Confirm height unit and source/derivation before calling height metres.",
            "Confirm area unit and whether it is footprint, modeled footprint, or another area measure before calling it square metres.",
            "Confirm risk and suhi class scales, source period, derivation, and intended interpretation.",
            "Confirm occurrence and angle definitions, units, algorithm, and handling of nulls.",
        ],
    }

    report = {
        "audit_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "buildings_gpkg": str(buildings_path),
            "amc_zones_geojson": str(zones_path),
            "sha256_before": before_hashes,
            "sha256_after": {str(buildings_path): sha256(buildings_path), str(zones_path): sha256(zones_path)},
        },
        "layer_contract": {"ignored": [IGNORED_LAYER], "enriched": ENRICHED_LAYERS, "count_only": [CENTRAL_LAYER]},
        "gpkg_metadata": metadata,
        "layer_inventory": layer_inventory,
        "duplicates_and_conflicts": {
            "enriched_rows": int(len(enriched)),
            "unique_source_id_including_null": int(enriched["source_id"].nunique(dropna=False)),
            "source_id_extra_rows": repeated_source_extra_rows,
            "rows_with_repeated_source_id": repeated_source_rows,
            "repeated_source_id_groups": repeated_source_coordinate_groups,
            "repeated_source_id_groups_with_multiple_exact_coordinates": repeated_source_multi_coordinate_groups,
            "repeated_source_id_groups_with_invariant_analytical_fields": source_consistent,
            "exact_coordinate_duplicate_groups": int(len(duplicate_coordinate_keys)),
            "rows_in_exact_coordinate_duplicate_groups": exact_coordinate_rows,
            "exact_coordinate_extra_rows": exact_coordinate_extra_rows,
            "full_nongeometry_record_duplicate_extra_rows": full_duplicate_rows,
            "conflict_true_total": int(sum(item["conflict_true"] or 0 for item in conflict_by_layer.values())),
            "by_layer": duplicate_by_layer,
            "conflict_by_layer": conflict_by_layer,
        },
        "zones": zone_audit,
        "zone_mapping": zone_mapping,
        "southwest_53_52": southwest,
        "precedence_audit": precedence_audit,
        "out_of_target_records": out_of_target_records,
        "central_availability": {
            "layer": CENTRAL_LAYER,
            "rows": int(len(central)),
            "height_missing": int(central["height"].isna().sum()) if "height" in central else None,
            "area_field_present": "area" in central.columns,
            "volume_field_present": "volume" in central.columns,
            "num_floors_nonnull": int(central["num_floors"].notna().sum()) if "num_floors" in central else None,
        },
        "units_and_provenance": units_provenance,
        "proposed_rules": [
            {"id": "R1", "rule": "A retained row is a source observation, not a confirmed unique physical building, until upstream provenance defines source_id and conflict semantics. Reader-facing labels must say 'building points/records' during pilot validation.", "status": "proposed", "evidence": "source_id repeats and coordinate duplicates both occur; no metadata defines their identity semantics."},
            {"id": "R2", "rule": "Do not deduplicate solely by source_id: retain distinct-coordinate repetitions pending upstream definition. Collapse only records value-equivalent across all retained non-geometry fields at the exact coordinate, preserving one deterministic canonical record and logging all discarded rows.", "status": "proposed", "evidence": "repeated source_id groups include multiple exact coordinates; all-retained-field value-equivalent duplicate count is separately measurable."},
            {"id": "R3", "rule": "Do not use conflict=true rows as automatic exclusions. Publish their count as a data-quality flag; exclude them only if source documentation states conflict means duplicate/invalid observation.", "status": "proposed", "evidence": "the field lacks documented semantics/provenance."},
            {"id": "R4", "rule": "Repair AMC objectid 35 and 53 only in memory using make_valid, extract/union polygonal components, validate output and record component/area changes. Use boundary-inclusive covers for zone membership.", "status": "proposed", "evidence": "both source geometries are invalid; make_valid for 53 emits non-polygon line artifacts, which must not become zoning area."},
            {"id": "R5", "rule": "Assign each layer only to its declared AMC objectid mapping: 0→0-airport, 10→10west, 18→18north, 19→19na, 35→35east, 40→40south, 41→41south, 53→52southwest, 101→101northwest, 181→181-central-final. Drop rows outside their declared target rather than reassigning them to an overlapping source layer.", "status": "proposed", "evidence": "source/zone mapping and target-coverage audit."},
            {"id": "R6", "rule": "Apply objectid 181 Central precedence before all enriched sources. A point geometrically in Central is count-only; an enriched row in Central must not add attribute coverage or produce a second count. Keep Central source rows only when covered by 181.", "status": "proposed", "evidence": "protects count-only semantics; this AMC-zone audit found zero current enriched points covered by 181, so the rule is a regression guard rather than a current-row exclusion."},
            {"id": "R7", "rule": "Counts use eligible published records after the source-zone and Central-precedence filters. Report total count plus count-only Central and enriched subtotals. Do not call the result a de-duplicated building count without provenance approval.", "status": "proposed", "evidence": "unresolved repeated identifiers, coordinates and conflict semantics."},
            {"id": "R8", "rule": "Height, area, volume, risk, SUHI, occurrence and angle are unavailable for reader-facing analytics until their units/provenance are independently confirmed. Elevation must not be separately published where it duplicates height; volume is a derived identity where complete, not an independent source measure.", "status": "proposed", "evidence": "metadata absence plus numerical identity checks."},
            {"id": "R9", "rule": "For every attribute statistic, denominator = retained enriched records inside the profile circle with non-null valid value for that attribute. Central rows never enter attribute denominators. State valid numerator/denominator and Central intersection disclaimer whenever Central count > 0.", "status": "proposed", "evidence": "Central lacks area/volume and height is entirely null."},
        ],
        "acceptance_tests": [
            "Layer inventory test: reject unknown/missing active layers; inventory every known layer including ignored 181centraltemp.",
            "Attachment-integrity test: SHA-256 input hashes must be identical before and after audit/build runs.",
            "Zone-key test: source mapping uses objectid and rejects mappings that rely on unique_id.",
            "Geometry test: 35 and 53 must be invalid before repair, valid after in-memory make_valid, and report geometry components/area delta.",
            "Exclusive-assignment test: every published record has exactly one declared source-zone; records outside it are dropped, never reassigned.",
            "Central-precedence test: enriched records covered by 181 are excluded from enriched counts/attribute denominators; 181-central-final contributes counts only.",
            "Availability test: Central-only profiles return count with height/area/volume unavailable, never zero; mixed profiles expose total, Central count, enriched count and valid denominators.",
            "Duplicate test: repeated source_id is not alone a drop criterion; only records value-equivalent across all retained non-geometry fields at the exact coordinate may collapse, with an audit log.",
            "Conflict test: conflict=true remains measurable and is not excluded without an approved semantic definition.",
            "Southwest test: 52southwest must pass the adopted objectid-53 coverage threshold before publication; otherwise halt for upstream reconciliation.",
        ],
    }
    if report["inputs"]["sha256_before"] != report["inputs"]["sha256_after"]:
        raise RuntimeError("Input attachment hash changed during read-only audit.")

    # Markdown is generated exclusively from the same report dictionary as JSON.
    inv_rows = []
    for item in layer_inventory:
        missing = ", ".join(f"{k}:{v}" for k, v in item["relevant_missingness"].items() if v is not None)
        inv_rows.append([item["layer"], item["status"], item["rows"], item["crs"], item["declared_geometry_type"], missing or "—"])
    dup_rows = []
    for layer in ENRICHED_LAYERS:
        item = duplicate_by_layer[layer]
        conflict = conflict_by_layer[layer]
        dup_rows.append([layer, item["rows"], item["unique_source_id"], item["source_id_extra_rows"], item["exact_coordinate_extra_rows"], conflict["conflict_true"]])
    mapping_rows = []
    for layer, item in zone_mapping.items():
        mapping_rows.append([layer, item["objectid"], item["source_rows"], item["covered_by_target_after_repair"], pct(item["covered_by_target_after_repair"], item["source_rows"]), item["target_membership_changed_by_repair"]])
    outlier_rows = []
    for item in out_of_target_records:
        ids = "; ".join(f"{key}={value}" for key, value in item["stable_available_identifiers"].items())
        outlier_rows.append([
            item["source_layer"],
            item["declared_objectid"],
            ids,
            f"({item['coordinates']['x']:.17g}, {item['coordinates']['y']:.17g})",
            item["conflict"],
            ", ".join(str(value) for value in item["repaired_amc_objectids_covering_point"]) or "—",
        ])
    zone_rows = []
    for objectid in sorted(int(key) for key in zone_audit):
        item = zone_audit[str(objectid)]
        zone_rows.append([objectid, item["valid_before"], item["invalid_reason_before"] or "—", item["repaired_geometry_type"], json.dumps(item["repaired_components"]), f"{item['area_change_m2']:.3f}", f"{item['area_change_pct'] or 0:.7f}%"])
    central_av = report["central_availability"]
    sw = report["southwest_53_52"]
    rules_rows = [[item["id"], item["status"], item["rule"], item["evidence"]] for item in report["proposed_rules"]]
    markdown = f"""# Building point / AMC zone rules audit (Phase 0)

Generated from `scripts/audit_building_point_rules.py` at `{report['generated_at_utc']}`. The audit only reads source attachments. SHA-256 hashes were identical before and after execution.

## Scope and integrity

- Buildings: `{buildings_path}` (`{before_hashes[str(buildings_path)]}`)
- AMC zones: `{zones_path}` (`{before_hashes[str(zones_path)]}`)
- Ignored entirely: `{IGNORED_LAYER}`.
- Active enriched layers: {", ".join(ENRICHED_LAYERS)}.
- Active count-only layer: `{CENTRAL_LAYER}`.
- Zone correspondence key: `objectid`, **not** `unique_id`.

## 1. Layer inventory

{md_table(["Layer", "Status", "Rows", "CRS", "Geometry", "Relevant missingness (field:null rows)"], inv_rows)}

All active and ignored GeoPackage layers are inventoried above. Field names/types are in the accompanying JSON report; no full source records are emitted.

## 2. Duplicate and conflict evidence

- Enriched rows: **{report['duplicates_and_conflicts']['enriched_rows']:,}**.
- Unique `source_id` (including null as a distinct value): **{report['duplicates_and_conflicts']['unique_source_id_including_null']:,}**; extra rows beyond one per ID: **{report['duplicates_and_conflicts']['source_id_extra_rows']:,}**.
- Repeated-ID groups: **{report['duplicates_and_conflicts']['repeated_source_id_groups']:,}**; groups using more than one exact coordinate: **{report['duplicates_and_conflicts']['repeated_source_id_groups_with_multiple_exact_coordinates']:,}**; repeated-ID groups invariant across available analytical fields: **{report['duplicates_and_conflicts']['repeated_source_id_groups_with_invariant_analytical_fields']:,}**.
|- Exact-coordinate duplicate groups: **{report['duplicates_and_conflicts']['exact_coordinate_duplicate_groups']:,}**; extra rows: **{report['duplicates_and_conflicts']['exact_coordinate_extra_rows']:,}**. Exact-coordinate records value-equivalent across all retained non-geometry fields, duplicate extra rows: **{report['duplicates_and_conflicts']['full_nongeometry_record_duplicate_extra_rows']:,}**.
- `conflict=true` rows: **{report['duplicates_and_conflicts']['conflict_true_total']:,}**.

{md_table(["Layer", "Rows", "Unique source_id", "Repeated-ID extra rows", "Exact-coordinate extra rows", "conflict=true"], dup_rows)}

**Interpretation:** the source proves neither that a repeated `source_id` is one physical building nor that exact-coordinate rows with non-identical records are accidental duplicates. A source row is therefore only a *source observation* pending upstream identity semantics. The only deterministic, reversible collapse proposed here is a record value-equivalent across all retained non-geometry fields at an exact coordinate; it must be logged.

## 3. AMC geometries and controlled in-memory repair

Repairs use Shapely `make_valid` in memory only, then extract and union polygonal components for spatial assignment (so any non-polygon artifacts cannot form zoning area). Areas are measured after projection to EPSG:32643. `covers` includes points on a boundary.

{md_table(["objectid", "Valid before", "Invalid reason", "After type", "After components", "Area change m²", "Area change %"], zone_rows)}

## 4. Layer-to-zone correspondence and repair materiality

{md_table(["Point layer", "AMC objectid", "Rows", "Covered after repair", "Coverage", "Target membership changed by repair"], mapping_rows)}

The source mapping is exclusive: `0-airport→0`, `10west→10`, `18north→18`, `19na→19`, `35east→35`, `40south→40`, `41south→41`, `52southwest→53`, `101northwest→101`, `181-central-final→181`. A point outside its declared target zone is dropped rather than reassigned to another layer.

Precedence audit after repair:

- Active rows: **{report['precedence_audit']['active_rows']:,}**.
- In their declared target zone: **{report['precedence_audit']['eligible_in_declared_target_zone_after_repair']:,}**.
- Enriched rows geometrically covered by Central 181: **{report['precedence_audit']['enriched_rows_geometrically_in_central_181']:,}**.
- Published after Central-first exclusion: **{report['precedence_audit']['published_after_central_first_exclusion']:,}**.
- Dropped outside declared source-zone: **{report['precedence_audit']['dropped_outside_declared_target_zone']:,}**.
- Target-eligible rows dropped by Central precedence: **{report['precedence_audit']['dropped_by_central_precedence_among_target_eligible']:,}**.

Out-of-target records (all four; no additional source records are emitted):

{md_table(["Source layer", "Declared AMC objectid", "Stable identifiers", "Exact point (x, y)", "conflict", "Repaired AMC objectids covering point"], outlier_rows)}

## 5. Southwest 53 / 52 audit

**Status: {sw['status'].upper()}.** `{sw['point_layer']}` has **{sw['points_covered_by_53_after_repair']:,}/{sw['points_covered_by_53_after_repair'] + sw['points_not_covered_by_53_after_repair']:,}** points covered by repaired AMC objectid 53 ({pct(sw['points_covered_by_53_after_repair'], sw['points_covered_by_53_after_repair'] + sw['points_not_covered_by_53_after_repair'])}). Polygon 53 was valid after repair: `{sw['zone_valid_after']}`. Its bounds and the point-layer bounds are recorded in JSON. {sw['naming_evidence']}

This geometry result supports the pairing operationally only at the stated coverage threshold; it does **not** resolve why the identifiers differ. The identifier provenance remains unresolved and should be documented before reader-facing publication.

## 6. Central availability and denominator rules

`{CENTRAL_LAYER}` has **{central_av['rows']:,}** rows. `height` nulls: **{central_av['height_missing'] if central_av['height_missing'] is not None else '—'}**; `area` field present: **{central_av['area_field_present']}**; `volume` field present: **{central_av['volume_field_present']}**; non-null `num_floors`: **{central_av['num_floors_nonnull'] if central_av['num_floors_nonnull'] is not None else '—'}**.

- Central contributes **counts only**.
- A profile intersecting Central reports total point-record count, Central count, enriched count, and a Central count-only disclaimer.
- Height/area/derived-volume/risk/SUHI/occurrence/angle denominators are each the retained enriched records inside the profile circle with a non-null valid value for that field. Central never enters those denominators.
- Attribute values missing from Central are **Unavailable**, never zero. Attribute coverage cannot be inferred from the total count when Central is present.

## 7. Units and provenance

{units_provenance['finding']}

Numerical checks: `elevation == height` on complete records: **{units_provenance['evidence']['elevation_equals_height_all_nonnull_enriched_rows']}**. `volume == area × height` on complete records: **{units_provenance['evidence']['volume_equals_area_times_height_all_complete_enriched_rows']}**.

Blockers:
""" + "\n".join(f"- {item}" for item in units_provenance["blockers"]) + f"""

## 8. Proposed rules

{md_table(["ID", "Status", "Rule", "Evidence"], rules_rows)}

## 9. Testable acceptance statements

""" + "\n".join(f"{index}. {statement}" for index, statement in enumerate(report["acceptance_tests"], start=1)) + "\n"

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.markdown_out.write_text(markdown, encoding="utf-8")
    print(json.dumps({
        "json_report": str(args.json_out),
        "markdown_report": str(args.markdown_out),
        "active_rows": report["precedence_audit"]["active_rows"],
        "southwest_status": southwest["status"],
        "input_hashes_unchanged": True,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
