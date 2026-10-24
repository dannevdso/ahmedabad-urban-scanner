from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from PIL import Image
from rasterio.features import geometry_mask
from rasterio.warp import Resampling, calculate_default_transform, reproject, transform_bounds
from shapely.geometry import box

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "data/external/open-buildings-height/temporal-2023"
BOUNDARY = ROOT / "config/study_areas/ahmedabad-gandhinagar-black-line.gpkg"
OUTPUT_DIR = ROOT / "web/public/data/building-height-fine"
MANIFEST_PATH = ROOT / "web/public/data/building-height-fine-manifest.json"
EFFECTIVE_RESOLUTION_M = 4
SOURCE_STORAGE_RESOLUTION_M = 0.5
FINE_MIN_ZOOM = 8
FINE_MAX_ZOOM = 16
FINE_ZOOM_LEVELS = (8, 11, 14, 16)
TILE_SIZE = 256
WEB_MERCATOR = "EPSG:3857"


def xyz_bounds(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    n = 2**z
    left = x / n * 40075016.68557849 - 20037508.342789244
    right = (x + 1) / n * 40075016.68557849 - 20037508.342789244
    top = 20037508.342789244 - y / n * 40075016.68557849
    bottom = 20037508.342789244 - (y + 1) / n * 40075016.68557849
    return left, bottom, right, top


def tile_range(bounds: tuple[float, float, float, float], z: int) -> tuple[range, range]:
    left, bottom, right, top = bounds
    n = 2**z
    world = 40075016.68557849
    def tx(x: float) -> int: return math.floor((x + world / 2) / world * n)
    def ty(y: float) -> int: return math.floor((world / 2 - y) / world * n)
    return range(max(0, tx(left)), min(n - 1, tx(right)) + 1), range(max(0, ty(top)), min(n - 1, ty(bottom)) + 1)


def build_tile_inventory(root: Path = OUTPUT_DIR) -> list[dict[str, object]]:
    rows = []
    for path in sorted(root.glob("*/*/*.webp")):
        if path.stat().st_size == 0:
            path.unlink()
            continue
        z, x = (int(part) for part in path.relative_to(root).parts[:2])
        rows.append({"z": z, "x": x, "y": int(path.stem), "path": str(path.relative_to(root)), "bytes": path.stat().st_size})
    return rows


def validate_fine_manifest(manifest: dict) -> None:
    required = {"effective_resolution_m", "source_storage_resolution_m", "presence_threshold", "switch_zoom", "tiles"}
    missing = required - manifest.keys()
    if missing:
        raise ValueError(f"fine manifest missing fields: {sorted(missing)}")
    if manifest["effective_resolution_m"] != 4 or manifest["source_storage_resolution_m"] != 0.5:
        raise ValueError("fine tile resolution contract is invalid")
    if manifest["switch_zoom"] != FINE_MIN_ZOOM:
        raise ValueError("fine tile switch zoom is invalid")
    if "published_web_tile_count" in manifest and manifest["published_web_tile_count"] != len(manifest["tiles"]):
        raise ValueError("published web tile count does not match tile inventory")


def _rgba(height: np.ndarray, valid: np.ndarray) -> np.ndarray:
    # Google-like teal -> green -> yellow -> orange -> red, clamped at 30 m.
    stops = np.array([[0, 128, 128], [34, 197, 94], [250, 204, 21], [249, 115, 22], [220, 38, 38]], dtype=np.float32)
    scaled = np.clip(height, 0, 30) / 30 * (len(stops) - 1)
    lo = np.floor(scaled).astype(int)
    hi = np.minimum(lo + 1, len(stops) - 1)
    frac = (scaled - lo)[..., None]
    rgb = stops[lo] * (1 - frac) + stops[hi] * frac
    result = np.zeros((*height.shape, 4), dtype=np.uint8)
    result[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    result[..., 3] = np.where(valid, 220, 0).astype(np.uint8)
    return result


def generate() -> dict:
    if not SOURCE_DIR.exists():
        raise FileNotFoundError(SOURCE_DIR)
    boundary = gpd.read_file(BOUNDARY).to_crs(WEB_MERCATOR)
    geometry = boundary.geometry.union_all()
    bounds = geometry.bounds
    source_paths = sorted(SOURCE_DIR.glob("*.tif"))
    if len(source_paths) != 16:
        raise ValueError(f"expected 16 source tiles, found {len(source_paths)}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for child in OUTPUT_DIR.iterdir():
        if child.is_dir(): shutil.rmtree(child)
        else: child.unlink()
    written = []
    for z in FINE_ZOOM_LEVELS:
        xs, ys = tile_range(bounds, z)
        for x in xs:
            for y in ys:
                left, bottom, right, top = xyz_bounds(z, x, y)
                if not box(left, bottom, right, top).intersects(geometry): continue
                transform = rasterio.transform.from_bounds(left, bottom, right, top, TILE_SIZE, TILE_SIZE)
                height = np.full((TILE_SIZE, TILE_SIZE), np.nan, dtype=np.float32)
                presence = np.full((TILE_SIZE, TILE_SIZE), np.nan, dtype=np.float32)
                tile_geom = box(left, bottom, right, top)
                for source_path in source_paths:
                    with rasterio.open(source_path) as src:
                        src_bounds = transform_bounds(src.crs, WEB_MERCATOR, *src.bounds)
                        if not tile_geom.intersects(box(*src_bounds)): continue
                        htmp = np.full_like(height, np.nan)
                        ptmp = np.full_like(presence, np.nan)
                        reproject(rasterio.band(src, 2), htmp, src_transform=src.transform, src_crs=src.crs, dst_transform=transform, dst_crs=WEB_MERCATOR, src_nodata=-99, dst_nodata=np.nan, resampling=Resampling.average)
                        reproject(rasterio.band(src, 3), ptmp, src_transform=src.transform, src_crs=src.crs, dst_transform=transform, dst_crs=WEB_MERCATOR, src_nodata=-99, dst_nodata=np.nan, resampling=Resampling.average)
                        use = np.isfinite(ptmp) & ((~np.isfinite(presence)) | (ptmp > presence))
                        height[use], presence[use] = htmp[use], ptmp[use]
                valid = np.isfinite(height) & np.isfinite(presence) & (presence >= 0.2)
                valid &= ~geometry_mask([geometry], out_shape=height.shape, transform=transform, invert=False)
                if not valid.any(): continue
                rgba = _rgba(np.nan_to_num(height, nan=0), valid)
                path = OUTPUT_DIR / str(z) / str(x) / f"{y}.webp"
                path.parent.mkdir(parents=True, exist_ok=True)
                Image.fromarray(rgba, "RGBA").save(path, "WEBP", lossless=True, method=6)
                written.append(path)
    tiles = build_tile_inventory()
    manifest = {
        "status": "complete", "effective_resolution_m": 4, "source_storage_resolution_m": 0.5,
        "source_year": 2023, "band": "building_height", "unit": "metres", "presence_threshold": 0.2,
        "switch_zoom": FINE_MIN_ZOOM, "max_zoom": FINE_MAX_ZOOM, "zoom_levels": list(FINE_ZOOM_LEVELS), "tile_size": 256,
        "source": "GOOGLE/Research/open-buildings-temporal/v1", "source_raster_tile_count": 16,
        "published_web_tile_count": len(tiles),
        "source_boundary": str(BOUNDARY.relative_to(ROOT)), "tiles": tiles,
        "caveat": "Modelled, not surveyed; effective 4 m display aggregation from 0.5 m storage grid; not a per-footprint attribute.",
    }
    validate_fine_manifest(manifest)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    print(json.dumps(generate(), indent=2))
