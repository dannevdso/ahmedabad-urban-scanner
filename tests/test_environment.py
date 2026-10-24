from __future__ import annotations

import numpy as np
import pytest
from affine import Affine

from ahmedabad_scanner.environment import (
    circular_point_statistics,
    landsat_clear_mask,
    landsat_surface_temperature_c,
    normalized_difference_vegetation_index,
    sentinel_clear_mask,
    sentinel_surface_reflectance,
)


def test_landsat_surface_temperature_applies_collection_2_scale_and_offset():
    raw = np.array([0, 40000], dtype=np.uint16)

    result = landsat_surface_temperature_c(raw)

    assert np.isnan(result[0])
    assert result[1] == pytest.approx(12.5708)


def test_ndvi_handles_zero_denominator_as_missing():
    nir = np.array([0.8, 0.0, 0.2])
    red = np.array([0.2, 0.0, 0.4])

    result = normalized_difference_vegetation_index(nir, red)

    assert result[0] == pytest.approx(0.6)
    assert np.isnan(result[1])
    assert result[2] == pytest.approx(-1 / 3)


def test_landsat_clear_mask_rejects_fill_cloud_shadow_and_snow():
    qa = np.array([0, 1, 1 << 3, 1 << 4, 1 << 5, 1 << 7], dtype=np.uint16)

    result = landsat_clear_mask(qa)

    assert result.tolist() == [True, False, False, False, False, True]


def test_sentinel_clear_mask_keeps_only_dark_land_vegetation_bare_soil_and_water():
    scl = np.arange(12, dtype=np.uint8)

    result = sentinel_clear_mask(scl)

    assert np.flatnonzero(result).tolist() == [2, 4, 5, 6]


def test_sentinel_reflectance_applies_baseline_offset_and_quantification():
    raw = np.array([0, 1000, 5000], dtype=np.uint16)

    result = sentinel_surface_reflectance(raw, additive_offset=-1000)

    assert np.isnan(result[0])
    assert result[1] == pytest.approx(0.0)
    assert result[2] == pytest.approx(0.4)


def test_circular_point_statistics_uses_metric_pixel_centres():
    data = np.arange(1, 10, dtype=float).reshape(3, 3)
    transform = Affine(1, 0, 0, 0, -1, 3)

    result = circular_point_statistics(
        data,
        transform,
        x=1.5,
        y=1.5,
        radius_m=1.01,
        threshold=6.0,
    )

    assert result["valid_pixels"] == 5
    assert result["median"] == pytest.approx(5.0)
    assert result["mean"] == pytest.approx(5.0)
    assert result["threshold_fraction"] == pytest.approx(2 / 5)
