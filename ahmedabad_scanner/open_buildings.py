"""Google Open Buildings V3 acquisition helpers."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry.base import BaseGeometry
from s2sphere import LatLng, LatLngRect, RegionCoverer

OPEN_BUILDINGS_COLUMNS = [
    "latitude",
    "longitude",
    "area_in_meters",
    "confidence",
    "geometry_wkt",
    "full_plus_code",
]


def s2_tokens_for_bbox(
    bbox: tuple[float, float, float, float], *, level: int = 6
) -> list[str]:
    """Return fixed-level S2 tokens covering a WGS84 bounding box."""
    min_lon, min_lat, max_lon, max_lat = bbox
    rectangle = LatLngRect.from_point_pair(
        LatLng.from_degrees(min_lat, min_lon),
        LatLng.from_degrees(max_lat, max_lon),
    )
    coverer = RegionCoverer()
    coverer.min_level = level
    coverer.max_level = level
    coverer.max_cells = 1_000_000
    return sorted(cell.to_token() for cell in coverer.get_covering(rectangle))


def load_open_buildings_bbox(
    paths: list[Path],
    *,
    bbox: tuple[float, float, float, float],
    chunk_size: int = 250_000,
) -> gpd.GeoDataFrame:
    """Load Open Buildings polygons whose published centroids fall in a bbox."""
    min_lon, min_lat, max_lon, max_lat = bbox
    selected_chunks: list[gpd.GeoDataFrame] = []
    for path in paths:
        for chunk in pd.read_csv(
            path,
            header=None,
            names=OPEN_BUILDINGS_COLUMNS,
            chunksize=chunk_size,
            compression="gzip",
        ):
            selected = chunk[
                chunk["longitude"].between(min_lon, max_lon)
                & chunk["latitude"].between(min_lat, max_lat)
            ].copy()
            if selected.empty:
                continue
            geometry = gpd.GeoSeries.from_wkt(selected.pop("geometry_wkt"), crs="EPSG:4326")
            selected_chunks.append(gpd.GeoDataFrame(selected, geometry=geometry))

    if not selected_chunks:
        return gpd.GeoDataFrame(
            columns=[column for column in OPEN_BUILDINGS_COLUMNS if column != "geometry_wkt"] + ["geometry"],
            geometry="geometry",
            crs="EPSG:4326",
        )
    return gpd.GeoDataFrame(
        pd.concat(selected_chunks, ignore_index=True),
        geometry="geometry",
        crs="EPSG:4326",
    )


def load_open_buildings_region(
    paths: list[Path],
    *,
    region: BaseGeometry,
    chunk_size: int = 250_000,
) -> gpd.GeoDataFrame:
    """Load building polygons intersecting a WGS84 study-area geometry."""
    candidates = load_open_buildings_bbox(paths, bbox=region.bounds, chunk_size=chunk_size)
    if candidates.empty:
        return candidates
    mask = candidates.geometry.intersects(region)
    return candidates.loc[mask].reset_index(drop=True)
