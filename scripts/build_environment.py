"""Build hot-season land-surface-temperature and greenery indicators."""

from __future__ import annotations

import argparse
import json
import math
import tomllib
import warnings
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd
import planetary_computer as pc
import rasterio
import requests
from pystac import Item
from pystac_client import Client
from rasterio.enums import Resampling
from rasterio.transform import Affine, from_origin
from rasterio.vrt import WarpedVRT
from shapely.geometry import box

from ahmedabad_scanner.environment import (
    circular_point_statistics,
    landsat_clear_mask,
    landsat_surface_temperature_c,
    normalized_difference_vegetation_index,
    sentinel_clear_mask,
    sentinel_surface_reflectance,
)

matplotlib.use("Agg")
import matplotlib.pyplot as plt

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/ahmedabad_pilot.toml"))
    parser.add_argument(
        "--reuse",
        action="store_true",
        help="Reuse saved composite rasters instead of querying and reading satellite scenes.",
    )
    return parser.parse_args()


def aligned_grid(bounds: tuple[float, float, float, float], resolution: float) -> tuple[Affine, int, int]:
    min_x, min_y, max_x, max_y = bounds
    left = math.floor(min_x / resolution) * resolution
    bottom = math.floor(min_y / resolution) * resolution
    right = math.ceil(max_x / resolution) * resolution
    top = math.ceil(max_y / resolution) * resolution
    width = int(round((right - left) / resolution))
    height = int(round((top - bottom) / resolution))
    return from_origin(left, top, resolution, resolution), width, height


def select_evenly(items: list[Item], maximum: int) -> list[Item]:
    ordered = sorted(items, key=lambda item: item.datetime or datetime.min.replace(tzinfo=UTC))
    if len(ordered) <= maximum:
        return ordered
    indices = np.linspace(0, len(ordered) - 1, maximum).round().astype(int)
    return [ordered[index] for index in dict.fromkeys(indices)]


def read_asset_to_grid(
    item: Item,
    asset_key: str,
    *,
    crs: str,
    transform: Affine,
    width: int,
    height: int,
    resampling: Resampling,
) -> np.ndarray:
    signed = pc.sign(item.assets[asset_key])
    with rasterio.Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".TIF,.tif",
    ):
        with rasterio.open(signed.href) as source:
            with WarpedVRT(
                source,
                crs=crs,
                transform=transform,
                width=width,
                height=height,
                resampling=resampling,
            ) as vrt:
                return vrt.read(1)


def sentinel_offset_and_quantification(item: Item) -> tuple[float, float]:
    signed = pc.sign(item.assets["product-metadata"])
    response = requests.get(signed.href, timeout=120)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    quantification = None
    offsets: list[float] = []
    for element in root.iter():
        name = element.tag.rsplit("}", 1)[-1]
        if name == "BOA_QUANTIFICATION_VALUE" and element.text:
            quantification = float(element.text)
        elif name == "BOA_ADD_OFFSET" and element.text:
            offsets.append(float(element.text))
    if quantification is None or not offsets:
        raise ValueError(f"Missing Sentinel-2 reflectance scaling metadata for {item.id}")
    if len(set(offsets)) != 1:
        raise ValueError(f"Band-specific Sentinel-2 offsets require explicit mapping for {item.id}")
    return offsets[0], quantification


def nanmedian_stack(arrays: list[np.ndarray]) -> np.ndarray:
    stack = np.stack(arrays).astype("float32")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        return np.nanmedian(stack, axis=0).astype("float32")


def valid_count_stack(arrays: list[np.ndarray]) -> np.ndarray:
    return np.sum(np.isfinite(np.stack(arrays)), axis=0).astype("uint16")


def write_float_raster(
    path: Path,
    data: np.ndarray,
    *,
    crs: str,
    transform: Affine,
    tags: dict[str, str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    output = np.where(np.isfinite(data), data, -9999).astype("float32")
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=output.shape[0],
        width=output.shape[1],
        count=1,
        dtype="float32",
        crs=crs,
        transform=transform,
        nodata=-9999,
        compress="deflate",
        tiled=True,
    ) as destination:
        destination.write(output, 1)
        destination.update_tags(**tags)


def write_count_raster(
    path: Path,
    data: np.ndarray,
    *,
    crs: str,
    transform: Affine,
    tags: dict[str, str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=data.shape[0],
        width=data.shape[1],
        count=1,
        dtype="uint16",
        crs=crs,
        transform=transform,
        nodata=0,
        compress="deflate",
        tiled=True,
    ) as destination:
        destination.write(data.astype("uint16"), 1)
        destination.update_tags(**tags)


def read_local_float_raster(path: Path) -> tuple[np.ndarray, Affine, str]:
    with rasterio.open(path) as source:
        data = source.read(1).astype("float32")
        data[data == source.nodata] = np.nan
        return data, source.transform, source.crs.to_string()


def read_local_count_raster(path: Path) -> tuple[np.ndarray, Affine, str]:
    with rasterio.open(path) as source:
        return source.read(1), source.transform, source.crs.to_string()


def quantiles(series: pd.Series) -> dict[str, float | None]:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return {"min": None, "p10": None, "p50": None, "p90": None, "max": None}
    return {
        "min": round(float(values.min()), 3),
        "p10": round(float(values.quantile(0.10)), 3),
        "p50": round(float(values.quantile(0.50)), 3),
        "p90": round(float(values.quantile(0.90)), 3),
        "max": round(float(values.max()), 3),
    }


def main() -> None:
    args = parse_args()
    project_root = args.config.resolve().parent.parent
    with args.config.open("rb") as file:
        config = tomllib.load(file)

    environment = config["environment"]
    bbox = tuple(float(value) for value in config["boundary"]["bbox"])
    metric_crs = str(config["project"]["analysis_crs"])
    boundary = gpd.GeoSeries([box(*bbox)], crs="EPSG:4326").to_crs(metric_crs)
    analysis_bounds = tuple(
        float(value)
        for value in boundary.buffer(float(environment["raster_buffer_m"])).total_bounds
    )

    raw_dir = project_root / "data/satellite/stac"
    raster_dir = project_root / "data/derived/environment"
    output_dir = project_root / "outputs/environment"
    report_dir = project_root / "reports"
    for directory in (raw_dir, raster_dir, output_dir, report_dir):
        directory.mkdir(parents=True, exist_ok=True)

    lst_path = raster_dir / "navrangpura-hot-season-lst-c.tif"
    lst_count_path = raster_dir / "navrangpura-hot-season-lst-scene-count.tif"
    ndvi_path = raster_dir / "navrangpura-hot-season-ndvi.tif"
    ndvi_count_path = raster_dir / "navrangpura-hot-season-ndvi-scene-count.tif"

    landsat_items: list[Item] = []
    sentinel_items: list[Item] = []
    if args.reuse and all(
        path.exists() for path in (lst_path, lst_count_path, ndvi_path, ndvi_count_path)
    ):
        lst, lst_transform, lst_crs = read_local_float_raster(lst_path)
        lst_count, _, _ = read_local_count_raster(lst_count_path)
        ndvi, ndvi_transform, ndvi_crs = read_local_float_raster(ndvi_path)
        ndvi_count, _, _ = read_local_count_raster(ndvi_count_path)
        if lst_crs != metric_crs or ndvi_crs != metric_crs:
            raise ValueError("Saved environmental rasters do not use the configured analysis CRS")
        landsat_manifest = json.loads((raw_dir / "landsat_items.json").read_text())
        sentinel_manifest = json.loads((raw_dir / "sentinel_items.json").read_text())
        landsat_ids = [feature["id"] for feature in landsat_manifest["features"]]
        sentinel_ids = [feature["id"] for feature in sentinel_manifest["features"]]
    else:
        catalog = Client.open(STAC_URL)
        landsat_candidates = list(
            catalog.search(
                collections=["landsat-c2-l2"],
                bbox=bbox,
                datetime=str(environment["hot_season_date_range"]),
                query={"eo:cloud_cover": {"lt": float(environment["landsat_max_cloud_pct"])}},
            ).items()
        )
        landsat_items = select_evenly(
            landsat_candidates, int(environment["landsat_max_scenes"])
        )
        if not landsat_items:
            raise RuntimeError("No Landsat Collection 2 Level-2 scenes matched the configuration")

        sentinel_candidates = [
            item
            for item in catalog.search(
                collections=["sentinel-2-l2a"],
                bbox=bbox,
                datetime=str(environment["hot_season_date_range"]),
                query={"eo:cloud_cover": {"lt": float(environment["sentinel_max_cloud_pct"])}},
            ).items()
            if item.properties.get("s2:mgrs_tile") == str(environment["sentinel_mgrs_tile"])
        ]
        sentinel_items = select_evenly(
            sentinel_candidates, int(environment["sentinel_max_scenes"])
        )
        if not sentinel_items:
            raise RuntimeError("No Sentinel-2 L2A scenes matched the configuration")

        landsat_manifest = {
            "type": "FeatureCollection",
            "features": [item.to_dict() for item in landsat_items],
        }
        sentinel_manifest = {
            "type": "FeatureCollection",
            "features": [item.to_dict() for item in sentinel_items],
        }
        (raw_dir / "landsat_items.json").write_text(json.dumps(landsat_manifest, indent=2) + "\n")
        (raw_dir / "sentinel_items.json").write_text(json.dumps(sentinel_manifest, indent=2) + "\n")
        landsat_ids = [item.id for item in landsat_items]
        sentinel_ids = [item.id for item in sentinel_items]

        lst_transform, lst_width, lst_height = aligned_grid(
            analysis_bounds, float(environment["landsat_resolution_m"])
        )
        lst_scenes: list[np.ndarray] = []
        for item in landsat_items:
            temperature_raw = read_asset_to_grid(
                item,
                "lwir11",
                crs=metric_crs,
                transform=lst_transform,
                width=lst_width,
                height=lst_height,
                resampling=Resampling.bilinear,
            )
            qa_pixel = read_asset_to_grid(
                item,
                "qa_pixel",
                crs=metric_crs,
                transform=lst_transform,
                width=lst_width,
                height=lst_height,
                resampling=Resampling.nearest,
            )
            temperature = landsat_surface_temperature_c(temperature_raw)
            temperature[~landsat_clear_mask(qa_pixel)] = np.nan
            temperature[(temperature < 10) | (temperature > 75)] = np.nan
            lst_scenes.append(temperature.astype("float32"))
        lst = nanmedian_stack(lst_scenes)
        lst_count = valid_count_stack(lst_scenes)

        ndvi_transform, ndvi_width, ndvi_height = aligned_grid(
            analysis_bounds, float(environment["sentinel_resolution_m"])
        )
        ndvi_scenes: list[np.ndarray] = []
        for item in sentinel_items:
            red_raw = read_asset_to_grid(
                item,
                "B04",
                crs=metric_crs,
                transform=ndvi_transform,
                width=ndvi_width,
                height=ndvi_height,
                resampling=Resampling.bilinear,
            )
            nir_raw = read_asset_to_grid(
                item,
                "B08",
                crs=metric_crs,
                transform=ndvi_transform,
                width=ndvi_width,
                height=ndvi_height,
                resampling=Resampling.bilinear,
            )
            scl = read_asset_to_grid(
                item,
                "SCL",
                crs=metric_crs,
                transform=ndvi_transform,
                width=ndvi_width,
                height=ndvi_height,
                resampling=Resampling.nearest,
            )
            additive_offset, quantification = sentinel_offset_and_quantification(item)
            red = sentinel_surface_reflectance(
                red_raw,
                additive_offset=additive_offset,
                quantification_value=quantification,
            )
            nir = sentinel_surface_reflectance(
                nir_raw,
                additive_offset=additive_offset,
                quantification_value=quantification,
            )
            scene_ndvi = normalized_difference_vegetation_index(nir, red)
            scene_ndvi[~sentinel_clear_mask(scl)] = np.nan
            scene_ndvi[(scene_ndvi < -1) | (scene_ndvi > 1)] = np.nan
            ndvi_scenes.append(scene_ndvi.astype("float32"))
        ndvi = nanmedian_stack(ndvi_scenes)
        ndvi_count = valid_count_stack(ndvi_scenes)

        common_tags = {
            "source_catalog": STAC_URL,
            "date_range": str(environment["hot_season_date_range"]),
            "generated_utc": datetime.now(UTC).isoformat(),
        }
        write_float_raster(
            lst_path,
            lst,
            crs=metric_crs,
            transform=lst_transform,
            tags={
                **common_tags,
                "source": "USGS Landsat Collection 2 Level-2 via Microsoft Planetary Computer",
                "metric": "median daytime land surface temperature, degrees Celsius",
                "scene_ids": ",".join(landsat_ids),
            },
        )
        write_count_raster(
            lst_count_path,
            lst_count,
            crs=metric_crs,
            transform=lst_transform,
            tags={**common_tags, "metric": "valid Landsat observations per composite pixel"},
        )
        write_float_raster(
            ndvi_path,
            ndvi,
            crs=metric_crs,
            transform=ndvi_transform,
            tags={
                **common_tags,
                "source": "Copernicus Sentinel-2 L2A via Microsoft Planetary Computer",
                "metric": "median normalized difference vegetation index",
                "scene_ids": ",".join(sentinel_ids),
            },
        )
        write_count_raster(
            ndvi_count_path,
            ndvi_count,
            crs=metric_crs,
            transform=ndvi_transform,
            tags={**common_tags, "metric": "valid Sentinel-2 observations per composite pixel"},
        )

    building_input = project_root / config["inputs"]["building_accessibility"]
    buildings = gpd.read_parquet(building_input).to_crs(metric_crs)
    points = buildings.geometry.representative_point()
    lst_radius = float(environment["lst_neighbourhood_m"])
    ndvi_radius = float(environment["ndvi_neighbourhood_m"])
    vegetation_threshold = float(environment["vegetation_ndvi_threshold"])

    lst_statistics = [
        circular_point_statistics(
            lst,
            lst_transform,
            x=point.x,
            y=point.y,
            radius_m=lst_radius,
        )
        for point in points
    ]
    ndvi_statistics = [
        circular_point_statistics(
            ndvi,
            ndvi_transform,
            x=point.x,
            y=point.y,
            radius_m=ndvi_radius,
            threshold=vegetation_threshold,
        )
        for point in points
    ]
    lst_count_statistics = [
        circular_point_statistics(
            lst_count.astype("float32"),
            lst_transform,
            x=point.x,
            y=point.y,
            radius_m=lst_radius,
        )
        for point in points
    ]
    ndvi_count_statistics = [
        circular_point_statistics(
            ndvi_count.astype("float32"),
            ndvi_transform,
            x=point.x,
            y=point.y,
            radius_m=ndvi_radius,
        )
        for point in points
    ]

    buildings["lst_c_100m_median"] = [record["median"] for record in lst_statistics]
    buildings["lst_valid_fraction_100m"] = [record["valid_fraction"] for record in lst_statistics]
    buildings["lst_scene_count_100m_median"] = [record["median"] for record in lst_count_statistics]
    buildings["ndvi_50m_median"] = [record["median"] for record in ndvi_statistics]
    buildings["vegetation_fraction_50m"] = [
        record["threshold_fraction"] for record in ndvi_statistics
    ]
    buildings["ndvi_valid_fraction_50m"] = [record["valid_fraction"] for record in ndvi_statistics]
    buildings["ndvi_scene_count_50m_median"] = [record["median"] for record in ndvi_count_statistics]

    minimum_scenes = int(environment["minimum_valid_scenes"])
    buildings["environment_data_ok"] = (
        buildings["lst_c_100m_median"].notna()
        & buildings["ndvi_50m_median"].notna()
        & buildings["lst_scene_count_100m_median"].ge(minimum_scenes)
        & buildings["ndvi_scene_count_50m_median"].ge(minimum_scenes)
    )
    valid = buildings["environment_data_ok"]
    buildings["heat_percentile_pilot"] = np.nan
    buildings["greenery_percentile_pilot"] = np.nan
    buildings.loc[valid, "heat_percentile_pilot"] = buildings.loc[
        valid, "lst_c_100m_median"
    ].rank(pct=True, method="average")
    greenery_score = (
        buildings.loc[valid, "ndvi_50m_median"].rank(pct=True, method="average")
        + buildings.loc[valid, "vegetation_fraction_50m"].rank(pct=True, method="average")
    ) / 2
    buildings.loc[valid, "greenery_percentile_pilot"] = greenery_score
    buildings["heat_green_priority_pilot"] = (
        buildings["heat_percentile_pilot"]
        + (1 - buildings["greenery_percentile_pilot"])
    ) / 2

    output_buildings = raster_dir.parent / "navrangpura-building-environment.parquet"
    buildings.to_parquet(output_buildings, index=False)

    map_path = output_dir / "navrangpura_environment_summary.png"
    extent = (
        ndvi_transform.c,
        ndvi_transform.c + ndvi_transform.a * ndvi.shape[1],
        ndvi_transform.f + ndvi_transform.e * ndvi.shape[0],
        ndvi_transform.f,
    )
    lst_extent = (
        lst_transform.c,
        lst_transform.c + lst_transform.a * lst.shape[1],
        lst_transform.f + lst_transform.e * lst.shape[0],
        lst_transform.f,
    )
    fig, axes = plt.subplots(2, 2, figsize=(16, 15), constrained_layout=True)
    image = axes[0, 0].imshow(lst, extent=lst_extent, cmap="inferno", vmin=np.nanpercentile(lst, 2), vmax=np.nanpercentile(lst, 98))
    axes[0, 0].set_title("Median hot-season daytime land surface temperature (°C)")
    fig.colorbar(image, ax=axes[0, 0], shrink=0.75)
    image = axes[0, 1].imshow(ndvi, extent=extent, cmap="RdYlGn", vmin=-0.2, vmax=0.7)
    axes[0, 1].set_title("Median hot-season Sentinel-2 NDVI")
    fig.colorbar(image, ax=axes[0, 1], shrink=0.75)
    buildings.plot(
        ax=axes[1, 0],
        column="vegetation_fraction_50m",
        cmap="YlGn",
        vmin=0,
        vmax=1,
        linewidth=0,
        legend=True,
        missing_kwds={"color": "#bbbbbb", "label": "No data"},
    )
    axes[1, 0].set_title(f"Vegetated-pixel fraction within {ndvi_radius:g} m (NDVI ≥ {vegetation_threshold:g})")
    buildings.plot(
        ax=axes[1, 1],
        column="heat_green_priority_pilot",
        cmap="magma",
        vmin=0,
        vmax=1,
        linewidth=0,
        legend=True,
        missing_kwds={"color": "#bbbbbb", "label": "No data"},
    )
    axes[1, 1].set_title("Relative heat–greenery priority within pilot (0–1)")
    for axis in axes.flat:
        axis.set_axis_off()
    fig.suptitle(
        f"Navrangpura heat and greenery scanner · {environment['hot_season_date_range']}",
        fontsize=17,
    )
    fig.savefig(map_path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    summary: dict[str, Any] = {
        "generated_utc": datetime.now(UTC).isoformat(),
        "study_area": config["project"]["study_area"],
        "study_bbox_wgs84": list(bbox),
        "analysis_crs": metric_crs,
        "hot_season_date_range": environment["hot_season_date_range"],
        "landsat": {
            "collection": "landsat-c2-l2",
            "source": "USGS Landsat Collection 2 Level-2 via Microsoft Planetary Computer",
            "scene_count": len(landsat_ids),
            "scene_ids": landsat_ids,
            "resolution_m": float(environment["landsat_resolution_m"]),
            "cloud_threshold_pct": float(environment["landsat_max_cloud_pct"]),
            "surface_temperature_c": quantiles(buildings["lst_c_100m_median"]),
        },
        "sentinel_2": {
            "collection": "sentinel-2-l2a",
            "source": "Copernicus Sentinel-2 L2A via Microsoft Planetary Computer",
            "scene_count": len(sentinel_ids),
            "scene_ids": sentinel_ids,
            "mgrs_tile": environment["sentinel_mgrs_tile"],
            "resolution_m": float(environment["sentinel_resolution_m"]),
            "cloud_threshold_pct": float(environment["sentinel_max_cloud_pct"]),
            "ndvi": quantiles(buildings["ndvi_50m_median"]),
            "vegetation_fraction": quantiles(buildings["vegetation_fraction_50m"]),
        },
        "buildings": {
            "count": int(len(buildings)),
            "environment_data_ok": int(buildings["environment_data_ok"].sum()),
            "environment_data_ok_pct": round(float(buildings["environment_data_ok"].mean() * 100), 2),
            "heat_green_priority_ge_0_8": int(buildings["heat_green_priority_pilot"].ge(0.8).sum()),
        },
        "parameters": {
            "raster_buffer_m": float(environment["raster_buffer_m"]),
            "lst_neighbourhood_m": lst_radius,
            "ndvi_neighbourhood_m": ndvi_radius,
            "vegetation_ndvi_threshold": vegetation_threshold,
            "minimum_valid_scenes": minimum_scenes,
        },
        "outputs": {
            "building_environment": str(output_buildings.relative_to(project_root)),
            "lst_composite": str(lst_path.relative_to(project_root)),
            "lst_scene_count": str(lst_count_path.relative_to(project_root)),
            "ndvi_composite": str(ndvi_path.relative_to(project_root)),
            "ndvi_scene_count": str(ndvi_count_path.relative_to(project_root)),
            "summary_map": str(map_path.relative_to(project_root)),
        },
        "limitations": [
            "Landsat surface temperature is an approximately 10:30 local-time satellite observation of surface skin temperature, not air temperature or personal heat exposure.",
            "The hot-season median combines several acquisition dates and does not represent a single heatwave or daily maximum.",
            "NDVI indicates photosynthetically active vegetation but does not directly measure tree canopy, shade, vegetation quality, or public accessibility.",
            "Fifty- and 100-metre neighbourhood values describe the surroundings of each building, not conditions inside the building.",
            "Heat and greenery percentiles are relative only to this pilot extent and must be recalculated when the study area changes.",
        ],
    }
    report_path = report_dir / "navrangpura_environment_summary.json"
    report_path.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    print(f"Saved building environment indicators: {output_buildings}")
    print(f"Saved map: {map_path}")
    print(f"Saved summary: {report_path}")


if __name__ == "__main__":
    main()
