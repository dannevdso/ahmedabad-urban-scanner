#!/usr/bin/env python3
"""Build the truthful web preview for the 2023 modelled building-height raster."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
from matplotlib import colormaps
from PIL import Image
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/external/open-buildings-height/ahmedabad-gandhinagar-building-height-2023.tif"
OUT = ROOT / "web/public/data"
OUTPUT_IMAGE = OUT / "building-height-2023.png"
OUTPUT_MANIFEST = OUT / "building-height-raster-manifest.json"


def palette_stops(cmap_name: str) -> list[dict[str, object]]:
    return [
        {
            "value": index / 6,
            "color": "#%02x%02x%02x" % tuple(int(channel * 255) for channel in colormaps[cmap_name](index / 6)[:3]),
        }
        for index in range(7)
    ]


def main() -> int:
    if not SOURCE.exists():
        raise FileNotFoundError(f"Authoritative source TIFF is missing: {SOURCE}")
    OUT.mkdir(parents=True, exist_ok=True)
    for stale in (OUTPUT_IMAGE, OUTPUT_MANIFEST):
        if stale.exists():
            stale.unlink()
    with rasterio.open(SOURCE) as raster:
        values = raster.read(1).astype("float32")
        valid = np.isfinite(values) & (values != raster.nodata)
        if not valid.any():
            raise ValueError("Building-height source contains no valid pixels")
        vmin = float(values[valid].min())
        vmax = float(values[valid].max())
        display_range = [round(vmin, 3), round(vmax, 3)]
        normalized = np.clip((values - display_range[0]) / (display_range[1] - display_range[0]), 0, 1)
        rgba = (colormaps["viridis"](normalized) * 255).astype("uint8")
        rgba[~valid, 3] = 0
        rgba[valid, 3] = 180
        Image.fromarray(rgba, mode="RGBA").save(OUTPUT_IMAGE, optimize=True)
        corners = [
            (raster.transform.c, raster.transform.f),
            (raster.transform.c + raster.transform.a * raster.width, raster.transform.f),
            (raster.transform.c + raster.transform.a * raster.width, raster.transform.f + raster.transform.e * raster.height),
            (raster.transform.c, raster.transform.f + raster.transform.e * raster.height),
        ]
        transformer = Transformer.from_crs(raster.crs, "EPSG:4326", always_xy=True)
        coordinates = [transformer.transform(x, y) for x, y in corners]
        manifest = {
            "image": f"./data/{OUTPUT_IMAGE.name}",
            "coordinates": coordinates,
            "source": str(SOURCE.relative_to(ROOT)),
            "source_name": "Google Research Open Buildings Temporal",
            "source_collection": "GOOGLE/Research/open-buildings-temporal/v1",
            "source_year": 2023,
            "band": "building_height",
            "unit": "metres",
            "resolution_m": 30,
            "presence_threshold": 0.2,
            "valid_pixels": int(valid.sum()),
            "min": vmin,
            "max": float(values[valid].max()),
            "colormap": "viridis",
            "palette_stops": palette_stops("viridis"),
            "display_range": display_range,
            "validation_status": "verified",
            "scope": "full-study-boundary raster",
            "caveat": "Modelled height, not surveyed height; pixel-level analytical overlay, not a per-footprint building attribute.",
        }
    OUTPUT_MANIFEST.write_text(json.dumps({"building-height": manifest}, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
