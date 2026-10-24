#!/usr/bin/env python3
"""Build a projected 30 m terrain-plus-building-height DSM without height imputation."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import Resampling, reproject


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--height", type=Path, default=Path("data/external/open-buildings-height/ahmedabad-gandhinagar-building-height-2023.tif"))
    parser.add_argument("--dem", type=Path, default=Path("data/external/copernicus-dem/ahmedabad-gandhinagar-copernicus-dem-glo30.tif"))
    parser.add_argument("--output", type=Path, default=Path("data/derived/environment-ahmedabad-gandhinagar/ahmedabad-gandhinagar-building-terrain-dsm-30m.tif"))
    args = parser.parse_args()

    with rasterio.open(args.height) as hsrc, rasterio.open(args.dem) as dsrc:
        height = hsrc.read(1).astype("float32")
        height_valid = np.isfinite(height) & (height >= 0) & (height != hsrc.nodata)
        height = np.where(height_valid, height, 0).astype("float32")
        dem = np.full((hsrc.height, hsrc.width), np.nan, dtype="float32")
        reproject(
            source=rasterio.band(dsrc, 1),
            destination=dem,
            src_transform=dsrc.transform,
            src_crs=dsrc.crs,
            src_nodata=dsrc.nodata,
            dst_transform=hsrc.transform,
            dst_crs=hsrc.crs,
            dst_nodata=np.nan,
            resampling=Resampling.bilinear,
        )
        valid = np.isfinite(dem)
        dsm = np.where(valid, dem + height, -9999).astype("float32")
        profile = hsrc.profile.copy()
        profile.update(driver="GTiff", dtype="float32", count=1, nodata=-9999, compress="deflate", predictor=2)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(args.output, "w", **profile) as dst:
            dst.write(dsm, 1)
            dst.set_band_description(1, "Copernicus DEM plus Open Buildings Temporal 2023 height where available")
            dst.update_tags(
                method="DSM = reprojected Copernicus GLO-30 elevation + 2023 Open Buildings Temporal building_height; missing heights treated as zero only in raster cells with no valid building-height pixel",
                height_source=str(args.height),
                terrain_source=str(args.dem),
                height_nodata_preserved="yes; no building-height values were imputed",
            )
    print({"output": str(args.output), "width": profile["width"], "height": profile["height"], "crs": str(profile["crs"]), "valid_dem_pixels": int(valid.sum()), "height_pixels": int(height_valid.sum())})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
