"""Study-area geometry digitised from the user-supplied map screenshot."""

from __future__ import annotations

from math import atan, degrees, exp, pi

from shapely.geometry import Polygon

# North-up Web-Mercator screen calibration fitted from map labels and landmarks.
# x = X_SCALE * longitude + X_OFFSET
# y = Y_SCALE * mercator_y(latitude) + Y_OFFSET
X_SCALE = 1450.499202492312
X_OFFSET = -105002.0769257737
Y_SCALE = -83498.48094191337
Y_OFFSET = 34949.78799611385

# Detected centres of the circular vertices forming the black outline, clockwise
# from the northernmost point. Pixel origin is the screenshot's upper-left.
BLACK_LINE_VERTICES_PX: tuple[tuple[float, float], ...] = (
    (358.5, 69.5),
    (420.5, 105.5),
    (439.5, 98.5),
    (458.5, 101.5),
    (505.5, 134.5),
    (476.5, 181.5),
    (467.5, 234.5),
    (425.5, 304.5),
    (421.5, 316.5),
    (432.5, 321.5),
    (436.5, 337.5),
    (442.5, 398.5),
    (409.5, 487.5),
    (404.645161, 517.774194),
    (400.5, 539.5),
    (393.5, 570.5),
    (365.5, 599.5),
    (327.5, 609.5),
    (280.5, 615.5),
    (245.5, 623.5),
    (209.5, 609.5),
    (158.5, 603.5),
    (131.5, 577.5),
    (116.5, 534.5),
    (117.5, 498.5),
    (80.5, 492.5),
    (68.5, 473.5),
    (41.5, 470.5),
    (36.5, 450.5),
    (80.5, 426.5),
    (125.5, 413.5),
    (164.5, 304.5),
    (201.5, 276.5),
    (221.5, 272.5),
    (237.0, 239.5),
    (323.5, 184.5),
    (322.5, 170.5),
    (334.5, 154.5),
    (317.5, 140.5),
)


def pixel_to_wgs84(x: float, y: float) -> tuple[float, float]:
    """Transform a source-screenshot pixel into an approximate WGS84 position."""
    longitude = (x - X_OFFSET) / X_SCALE
    mercator_y = (y - Y_OFFSET) / Y_SCALE
    latitude = degrees(2 * atan(exp(mercator_y)) - pi / 2)
    return longitude, latitude


def digitised_study_area() -> Polygon:
    """Return the approximate WGS84 polygon traced from the screenshot's black line."""
    return Polygon(pixel_to_wgs84(x, y) for x, y in BLACK_LINE_VERTICES_PX)
