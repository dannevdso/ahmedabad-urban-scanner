#!/usr/bin/env python3
"""Publish supplied development-plan imagery and a compact AMC key-map boundary."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from PIL import Image
from pyproj import Transformer
from shapely import make_valid
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, mapping

ROOT = Path(__file__).resolve().parents[1]
SUPPLIED_DEVELOPMENT_PLAN = Path.home() / "Library/Application Support/Hermes/composer-images/12_94643_modified_26c4fe.tiff"
SUPPLIED_AMC_BOUNDARY = Path.home() / ".hermes/attachments/amc_boundary.geojson"
PUBLIC_DATA = ROOT / "web/public/data"
PROJECT_SOURCE_COPY = ROOT / "data/external/development-plan"
BOUNDARY_OUTPUT = PUBLIC_DATA / "local-profile"
DEVELOPMENT_PLAN_ATTRIBUTION = {
    "publisher": "ARPM Studio",
    "title": "Development Plan for Ahmedabad 2041",
    "url": "https://arpm.studio/projects/ahmedabad-dp-2041",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def provenance_path(path: Path) -> str:
    """Publish repository-relative paths without exposing a local home directory."""
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return f"external-inputs/{path.name}"


def _round_coordinates(coordinates: list[tuple[float, float]]) -> list[list[float]]:
    return [[round(float(x), 12), round(float(y), 12)] for x, y in coordinates]


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def _write_compact_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, separators=(",", ":")) + "\n")


def publish_development_plan(source_path: Path, output_dir: Path, *, source_copy_dir: Path | None = None) -> dict:
    """Copy the supplied GeoTIFF and publish an RGBA-identical browser PNG plus audit manifest."""
    source_path = Path(source_path)
    output_dir = Path(output_dir)
    source_copy_dir = output_dir if source_copy_dir is None else Path(source_copy_dir)
    if not source_path.is_file():
        raise FileNotFoundError(source_path)

    output_dir.mkdir(parents=True, exist_ok=True)
    source_copy_dir.mkdir(parents=True, exist_ok=True)
    source_copy = source_copy_dir / "development-plan-source.tiff"
    shutil.copyfile(source_path, source_copy)

    with rasterio.open(source_path) as source:
        if str(source.crs) != "EPSG:3857":
            raise ValueError(f"Expected EPSG:3857, got {source.crs}")
        if source.count != 4 or tuple(source.dtypes) != ("uint8",) * 4:
            raise ValueError("Development plan must be uint8 RGBA")
        rgba = np.moveaxis(source.read([1, 2, 3, 4]), 0, -1)
        bounds = source.bounds
        transformer = Transformer.from_crs(source.crs, "EPSG:4326", always_xy=True)
        coordinates = _round_coordinates([
            transformer.transform(bounds.left, bounds.top),
            transformer.transform(bounds.right, bounds.top),
            transformer.transform(bounds.right, bounds.bottom),
            transformer.transform(bounds.left, bounds.bottom),
        ])
        pixel_size = [float(source.transform.a), abs(float(source.transform.e))]
        source_metadata = {
            "path": provenance_path(source_path),
            "immutable_project_copy": provenance_path(source_copy),
            "sha256": sha256(source_path),
            "bytes": source_path.stat().st_size,
            "crs": str(source.crs),
            "dimensions": [source.width, source.height],
            "bands": [item.name for item in source.colorinterp],
            "dtype": "uint8",
            "pixel_size_m": pixel_size,
            "bounds_epsg3857": [float(bounds.left), float(bounds.bottom), float(bounds.right), float(bounds.top)],
        }

    derivative = output_dir / "development-plan.png"
    Image.fromarray(rgba, mode="RGBA").save(derivative, format="PNG", optimize=True)
    decoded = np.asarray(Image.open(derivative).convert("RGBA"))
    if decoded.shape != rgba.shape or not np.array_equal(decoded, rgba):
        raise ValueError("PNG derivative does not preserve source RGBA pixels")

    manifest = {
        "manifest_version": "development-plan.v1",
        "status": "supplied/unverified experimental contextual raster",
        "source": source_metadata,
        "attribution": DEVELOPMENT_PLAN_ATTRIBUTION,
        "derivative": {
            "file": derivative.name,
            "sha256": sha256(derivative),
            "bytes": derivative.stat().st_size,
            "format": "PNG RGBA",
            "dimensions": [int(rgba.shape[1]), int(rgba.shape[0])],
            "rgba_preserved": True,
        },
        "maplibre_image_coordinates": coordinates,
        "wgs84_bounds": [coordinates[0][0], coordinates[2][1], coordinates[2][0], coordinates[0][1]],
        "source_embeds_legend_and_north_arrow": True,
        "interpretation": "Visual contextual material only. Do not classify, recolor, crop, or treat as verified analytical evidence.",
    }
    _write_json(output_dir / "development-plan-manifest.json", manifest)
    return manifest


def _polygonal(geometry):
    if isinstance(geometry, (Polygon, MultiPolygon)):
        return geometry
    if isinstance(geometry, GeometryCollection):
        polygons = [part for part in geometry.geoms if isinstance(part, (Polygon, MultiPolygon))]
        return MultiPolygon([polygon for part in polygons for polygon in (part.geoms if isinstance(part, MultiPolygon) else [part])])
    raise ValueError(f"Unexpected repaired geometry type: {geometry.geom_type}")


def _exterior_only(geometry):
    """Return the same polygonal geometry with every interior ring removed."""
    if isinstance(geometry, Polygon):
        return Polygon(geometry.exterior.coords)
    if isinstance(geometry, MultiPolygon):
        return MultiPolygon([Polygon(part.exterior.coords) for part in geometry.geoms])
    raise ValueError(f"Expected Polygon or MultiPolygon, got {geometry.geom_type}")


def _polygon_vertex_counts(geometry) -> tuple[int, int]:
    polygons = [geometry] if isinstance(geometry, Polygon) else list(geometry.geoms)
    return (
        sum(len(polygon.exterior.coords) for polygon in polygons),
        sum(len(polygon.interiors) for polygon in polygons),
    )


def publish_ahmedabad_boundary(source_path: Path, output_dir: Path) -> dict:
    """Publish one attribute-free EPSG:4326 boundary using exterior shells only."""
    source_path = Path(source_path)
    output_dir = Path(output_dir)
    zones = gpd.read_file(source_path, engine="pyogrio")
    if str(zones.crs) != "EPSG:4326":
        raise ValueError(f"Expected EPSG:4326 boundary, got {zones.crs}")
    if len(zones) != 1:
        raise ValueError(f"Expected exactly one supplied boundary feature, got {len(zones)}")
    geometry = zones.geometry.iloc[0]
    if geometry.geom_type not in {"Polygon", "MultiPolygon"} or geometry.is_empty or not geometry.is_valid:
        raise ValueError("Supplied boundary must be one valid Polygon or MultiPolygon")

    source_exterior_vertices, source_interior_rings = _polygon_vertex_counts(geometry)
    boundary = _exterior_only(geometry)
    if not boundary.is_valid:
        raise ValueError("Exterior-only boundary is not valid")
    output_exterior_vertices, output_interior_rings = _polygon_vertex_counts(boundary)
    bounds = [round(float(value), 6) for value in boundary.bounds]
    payload = {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": {}, "geometry": mapping(boundary)}],
    }
    target = output_dir / "ahmedabad-boundary.geojson"
    _write_compact_json(target, payload)
    report = {
        "file": target.name,
        "source": {
            "path": provenance_path(source_path),
            "sha256": sha256(source_path),
            "feature_count": int(len(zones)),
            "crs": str(zones.crs),
            "geometry_type": geometry.geom_type,
            "exterior_vertex_count": source_exterior_vertices,
            "interior_ring_count": source_interior_rings,
        },
        "output": {
            "feature_count": 1,
            "geometry_type": boundary.geom_type,
            "exterior_vertex_count": output_exterior_vertices,
            "interior_ring_count": output_interior_rings,
            "bounds_wgs84": bounds,
            "sha256": sha256(target),
            "bytes": target.stat().st_size,
        },
        "method": "Copied every polygon exterior shell only; interior rings were intentionally omitted; no simplification or coordinate transformation was applied.",
    }
    _write_json(output_dir / "ahmedabad-boundary-manifest.json", report)
    return report


def update_public_metadata(metadata_path: Path, development_plan: dict, boundary: dict) -> None:
    """Add lightweight provenance records without recalculating other web data."""
    metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
    context_key = "supplied-unverified-experimental"
    metadata.setdefault("contexts", {})[context_key] = {
        "scopeLabel": "Supplied contextual raster",
        "statusLabel": "Unverified / experimental",
        "temporalLabel": "Source date not verified",
        "caveat": "Supplied development-plan visual context from ARPM Studio, Development Plan for Ahmedabad 2041; provenance, accuracy, and temporal currency are not verified. It is not analytical evidence.",
        "sourceAttribution": development_plan.get("attribution", DEVELOPMENT_PLAN_ATTRIBUTION),
    }
    metadata.setdefault("overlay_contexts", {})["developmentPlan"] = context_key
    metadata.setdefault("overlay_legends", {})["developmentPlan"] = {
        "key": "developmentPlan",
        "title": "Development plan",
        "kind": "single-symbol",
        "geometry": "raster",
        "context_key": context_key,
        "entries": [{"label": "Supplied visual context (see embedded legend)", "color": "#525252", "shape": "raster"}],
        "caveat": "Supplied visual raster with its own embedded legend and north arrow; provenance, accuracy, and temporal currency are unverified. No separate analytical colour scale is claimed.",
        "numeric_applicable": False,
        "unit": "",
        "unit_status": "not_documented",
        "validation_status": "unverified",
        "source": development_plan,
        "attribution": development_plan.get("attribution", DEVELOPMENT_PLAN_ATTRIBUTION),
    }
    metadata["development_plan_publication"] = development_plan
    metadata["ahmedabad_boundary_publication"] = boundary
    _write_json(metadata_path, metadata)


def main() -> None:
    development_plan = publish_development_plan(SUPPLIED_DEVELOPMENT_PLAN, PUBLIC_DATA, source_copy_dir=PROJECT_SOURCE_COPY)
    boundary = publish_ahmedabad_boundary(SUPPLIED_AMC_BOUNDARY, BOUNDARY_OUTPUT)
    update_public_metadata(PUBLIC_DATA / "metadata.json", development_plan, boundary)
    print(json.dumps({"development_plan": development_plan, "ahmedabad_boundary": boundary}, indent=2))


if __name__ == "__main__":
    main()
