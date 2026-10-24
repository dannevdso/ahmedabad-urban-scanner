"""Pure calculations for satellite-derived environmental indicators."""

from __future__ import annotations

import numpy as np
from affine import Affine
from rasterio.transform import rowcol, xy


def circular_point_statistics(
    data: np.ndarray,
    transform: Affine,
    *,
    x: float,
    y: float,
    radius_m: float,
    threshold: float | None = None,
) -> dict[str, float | int]:
    """Summarize finite raster pixels whose centres fall inside a metric circle."""
    values = np.asarray(data, dtype="float64")
    centre_row, centre_col = rowcol(transform, x, y)
    resolution = max(abs(transform.a), abs(transform.e))
    reach = int(np.ceil(radius_m / resolution))
    row_min = max(0, centre_row - reach)
    row_max = min(values.shape[0], centre_row + reach + 1)
    col_min = max(0, centre_col - reach)
    col_max = min(values.shape[1], centre_col + reach + 1)

    rows, cols = np.mgrid[row_min:row_max, col_min:col_max]
    pixel_x, pixel_y = xy(transform, rows, cols, offset="center")
    pixel_x = np.asarray(pixel_x).reshape(rows.shape)
    pixel_y = np.asarray(pixel_y).reshape(rows.shape)
    circle = (pixel_x - x) ** 2 + (pixel_y - y) ** 2 <= radius_m**2
    window = values[row_min:row_max, col_min:col_max]
    selected = window[circle]
    valid = selected[np.isfinite(selected)]
    total_pixels = int(selected.size)
    valid_pixels = int(valid.size)
    result: dict[str, float | int] = {
        "mean": float(np.mean(valid)) if valid_pixels else np.nan,
        "median": float(np.median(valid)) if valid_pixels else np.nan,
        "valid_pixels": valid_pixels,
        "total_pixels": total_pixels,
        "valid_fraction": valid_pixels / total_pixels if total_pixels else 0.0,
    }
    if threshold is not None:
        result["threshold_fraction"] = (
            float(np.mean(valid >= threshold)) if valid_pixels else np.nan
        )
    return result


def landsat_clear_mask(qa_pixel: np.ndarray) -> np.ndarray:
    """Return pixels without Landsat fill, cloud, shadow, cirrus, or snow flags."""
    qa = np.asarray(qa_pixel, dtype="uint16")
    bad_bits = sum(1 << bit for bit in range(6))
    return (qa & bad_bits) == 0


def sentinel_clear_mask(scene_classification: np.ndarray) -> np.ndarray:
    """Return Sentinel-2 SCL pixels suitable for land-surface NDVI."""
    scl = np.asarray(scene_classification)
    return np.isin(scl, (2, 4, 5, 6))


def sentinel_surface_reflectance(
    raw: np.ndarray,
    *,
    additive_offset: float,
    quantification_value: float = 10_000.0,
) -> np.ndarray:
    """Convert Sentinel-2 L2A integer values to bottom-of-atmosphere reflectance."""
    values = np.asarray(raw, dtype="float64")
    result = (values + additive_offset) / quantification_value
    result[values == 0] = np.nan
    return result


def landsat_surface_temperature_c(
    raw: np.ndarray,
    *,
    scale: float = 0.00341802,
    offset: float = 149.0,
) -> np.ndarray:
    """Convert Landsat Collection 2 ST_B10 integers to degrees Celsius."""
    values = np.asarray(raw, dtype="float64")
    result = values * scale + offset - 273.15
    result[values == 0] = np.nan
    return result


def normalized_difference_vegetation_index(
    nir: np.ndarray,
    red: np.ndarray,
) -> np.ndarray:
    """Calculate NDVI while treating a zero denominator as missing."""
    nir_values = np.asarray(nir, dtype="float64")
    red_values = np.asarray(red, dtype="float64")
    denominator = nir_values + red_values
    result = np.full(np.broadcast_shapes(nir_values.shape, red_values.shape), np.nan)
    np.divide(
        nir_values - red_values,
        denominator,
        out=result,
        where=denominator != 0,
    )
    return result
