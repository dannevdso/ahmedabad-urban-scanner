#!/usr/bin/env python3
"""Create web-map PNG previews for the four Ahmedabad–Gandhinagar environment analyses."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
from matplotlib import colormaps
from PIL import Image
from pyproj import Transformer
from scipy.ndimage import convolve
from rasterio.warp import Resampling, reproject

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / "data/derived/environment-ahmedabad-gandhinagar"
OUT = ROOT / "web/public/data"


def disk(radius: int) -> np.ndarray:
    y, x = np.ogrid[-radius:radius + 1, -radius:radius + 1]
    return ((x * x + y * y) <= radius * radius).astype("float32")


def write_preview(key: str, values: np.ndarray, transform, crs, cmap_name: str, vmin: float, vmax: float) -> dict[str, object]:
    valid = np.isfinite(values)
    normalized = np.clip((values - vmin) / (vmax - vmin), 0, 1)
    rgba = (colormaps[cmap_name](normalized) * 255).astype("uint8")
    rgba[~valid, 3] = 0
    rgba[valid, 3] = 150
    path = OUT / f"environment-{key}.png"
    Image.fromarray(rgba, mode="RGBA").save(path, optimize=True)
    width, height = values.shape[1], values.shape[0]
    corners = [(transform.c, transform.f), (transform.c + transform.a * width, transform.f), (transform.c + transform.a * width, transform.f + transform.e * height), (transform.c, transform.f + transform.e * height)]
    transformer = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    palette_stops = [{"value": index / 6, "color": "#%02x%02x%02x" % tuple(int(channel * 255) for channel in colormaps[cmap_name](index / 6)[:3])} for index in range(7)]
    return {"image": f"./data/{path.name}", "coordinates": [transformer.transform(x, y) for x, y in corners], "valid_pixels": int(valid.sum()), "min": float(values[valid].min()) if valid.any() else None, "max": float(values[valid].max()) if valid.any() else None, "colormap": cmap_name, "palette_stops": palette_stops, "display_range": [vmin, vmax], "validation_status": "verified", "unit": {"surface-temperature": "°C", "ndvi": "unitless", "vegetation-fraction": "0–1", "heat-green-priority": "0–1"}[key]}


def main() -> int:
    with rasterio.open(ENV / "landsat-lst-celsius.tif") as src:
        lst = src.read(1).astype("float32"); lst[lst == src.nodata] = np.nan
        lst_transform, lst_crs = src.transform, src.crs
    with rasterio.open(ENV / "sentinel-2-ndvi.tif") as src:
        ndvi = src.read(1).astype("float32"); ndvi[ndvi == src.nodata] = np.nan
        ndvi_transform, ndvi_crs = src.transform, src.crs
    lst_mask = np.isfinite(lst).astype("float32")
    lst_kernel = disk(4)
    lst_sum = convolve(np.nan_to_num(lst, nan=0), lst_kernel, mode="nearest")
    lst_count = convolve(lst_mask, lst_kernel, mode="nearest")
    lst_mean = np.where(lst_count > 0, lst_sum / lst_count, np.nan)
    ndvi_mask = np.isfinite(ndvi).astype("float32")
    ndvi_kernel = disk(5)
    ndvi_sum = convolve(np.nan_to_num(ndvi, nan=0), ndvi_kernel, mode="nearest")
    ndvi_count = convolve(ndvi_mask, ndvi_kernel, mode="nearest")
    ndvi_mean = np.where(ndvi_count > 0, ndvi_sum / ndvi_count, np.nan)
    green = np.where(np.isfinite(ndvi), (ndvi >= 0.3).astype("float32"), 0)
    green_fraction = np.where(ndvi_count > 0, convolve(green, ndvi_kernel, mode="nearest") / ndvi_count, np.nan)
    ndvi_mean_lst = np.full(lst_mean.shape, np.nan, dtype="float32")
    green_fraction_lst = np.full(lst_mean.shape, np.nan, dtype="float32")
    reproject(ndvi_mean, ndvi_mean_lst, src_transform=ndvi_transform, src_crs=ndvi_crs, dst_transform=lst_transform, dst_crs=lst_crs, dst_nodata=np.nan, resampling=Resampling.average)
    reproject(green_fraction, green_fraction_lst, src_transform=ndvi_transform, src_crs=ndvi_crs, dst_transform=lst_transform, dst_crs=lst_crs, dst_nodata=np.nan, resampling=Resampling.average)
    if np.isfinite(lst_mean).any() and np.isfinite(ndvi_mean_lst).any():
        heat_rank = np.full(lst_mean.shape, np.nan, dtype="float32")
        green_rank = np.full(lst_mean.shape, np.nan, dtype="float32")
        lv = lst_mean[np.isfinite(lst_mean)]
        nv = ndvi_mean_lst[np.isfinite(ndvi_mean_lst)]
        gv = green_fraction_lst[np.isfinite(green_fraction_lst)]
        heat_rank[np.isfinite(lst_mean)] = np.searchsorted(np.sort(lv), lst_mean[np.isfinite(lst_mean)], side="right") / len(lv)
        both = np.isfinite(ndvi_mean_lst) & np.isfinite(green_fraction_lst)
        green_rank[both] = (np.searchsorted(np.sort(nv), ndvi_mean_lst[both], side="right") / len(nv) + np.searchsorted(np.sort(gv), green_fraction_lst[both], side="right") / len(gv)) / 2
        priority = (heat_rank + (1 - green_rank)) / 2
    else:
        priority = np.full(lst_mean.shape, np.nan, dtype="float32")
    manifest = {
        "surface-temperature": write_preview("surface-temperature", lst_mean, lst_transform, lst_crs, "inferno", 35, 55),
        "ndvi": write_preview("ndvi", ndvi_mean, ndvi_transform, ndvi_crs, "RdYlGn", -0.2, 0.7),
        "vegetation-fraction": write_preview("vegetation-fraction", green_fraction, ndvi_transform, ndvi_crs, "YlGn", 0, 1),
        "heat-green-priority": write_preview("heat-green-priority", priority, lst_transform, lst_crs, "magma", 0, 1),
    }
    (OUT / "environment-raster-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
