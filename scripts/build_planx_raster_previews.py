#!/usr/bin/env python3
"""Create transparent PNG previews and WGS84 extents for PlanX raster outputs."""
from __future__ import annotations

import json
from pathlib import Path

from matplotlib import colormaps
import numpy as np
import rasterio
from pyproj import Transformer
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
IN_ROOT = ROOT / "data/derived/planx/ahmedabad-gandhinagar-full-analysis-outputs"
OUT_ROOT = ROOT / "web/public/data"
SPECS = {
    "shadow-casting": ("shadow_casting_2026-06-21_0800.tif", "gray", 0, 1),
    "sun-hours": ("sun_hours_2026-06-21.tif", "YlOrRd", 0, 13),
    "sky-view-factor": ("sky_view_factor.tif", "viridis", 0.55, 1),
    "solar-irradiation": ("solar_irradiation_2026-06-21.tif", "inferno", 4, 8.1),
}


def palette_stops(cmap_name: str) -> list[dict[str, object]]:
    return [{"value": index / 6, "color": "#%02x%02x%02x" % tuple(int(channel * 255) for channel in colormaps[cmap_name](index / 6)[:3])} for index in range(7)]


def main() -> int:
    manifest: dict[str, object] = {}
    transformer_cache: dict[tuple[str, str], Transformer] = {}
    for key, (filename, cmap_name, vmin, vmax) in SPECS.items():
        source = IN_ROOT / filename
        if not source.exists():
            continue
        with rasterio.open(source) as raster:
            values = raster.read(1).astype("float32")
            valid = np.isfinite(values) & (values != raster.nodata)
            if key == "shadow-casting":
                rgba = np.zeros((*values.shape, 4), dtype="uint8")
                rgba[valid & (values > 0), :3] = 30
                rgba[valid & (values > 0), 3] = 150
            else:
                normalized = np.clip((values - vmin) / (vmax - vmin), 0, 1)
                rgba = (colormaps[cmap_name](normalized) * 255).astype("uint8")
                rgba[~valid, 3] = 0
                rgba[valid, 3] = 150
            output = OUT_ROOT / f"planx-{key}.png"
            Image.fromarray(rgba, mode="RGBA").save(output, optimize=True)
            transform = raster.transform
            corners = [(transform.c, transform.f), (transform.c + transform.a * raster.width, transform.f), (transform.c + transform.a * raster.width, transform.f + transform.e * raster.height), (transform.c, transform.f + transform.e * raster.height)]
            cache_key = (str(raster.crs), "EPSG:4326")
            transformer_cache.setdefault(cache_key, Transformer.from_crs(raster.crs, "EPSG:4326", always_xy=True))
            lonlat = [transformer_cache[cache_key].transform(x, y) for x, y in corners]
            manifest[key] = {"image": f"./data/{output.name}", "coordinates": lonlat, "source": str(source.relative_to(ROOT)), "valid_pixels": int(valid.sum()), "min": float(values[valid].min()) if valid.any() else None, "max": float(values[valid].max()) if valid.any() else None, "colormap": cmap_name, "palette_stops": palette_stops(cmap_name), "display_range": [vmin, vmax], "unit": {"shadow-casting": "0/1", "sun-hours": "hours", "sky-view-factor": "unitless", "solar-irradiation": None}[key], "validation_status": "unverified"}
    (OUT_ROOT / "planx-raster-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
