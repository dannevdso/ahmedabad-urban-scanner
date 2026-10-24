#!/usr/bin/env python3
"""Join clipped Open Buildings Temporal height pixels to current PlanX buildings."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.mask import mask


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--buildings", type=Path, default=Path("data/derived/planx/ahmedabad-gandhinagar-planx-inputs.gpkg"))
    parser.add_argument("--building-layer", default="buildings")
    parser.add_argument("--height", type=Path, default=Path("data/external/open-buildings-height/ahmedabad-gandhinagar-building-height-2023.tif"))
    parser.add_argument("--output", type=Path, default=Path("data/derived/planx/ahmedabad-gandhinagar-buildings-height.gpkg"))
    parser.add_argument("--audit", type=Path, default=Path("reports/ahmedabad_gandhinagar_building_height_join.json"))
    args = parser.parse_args()

    buildings = gpd.read_file(args.buildings, layer=args.building_layer, engine="pyogrio")
    with rasterio.open(args.height) as raster:
        if buildings.crs is None:
            raise ValueError("Building layer has no CRS")
        buildings = buildings.to_crs(raster.crs)
        means = np.full(len(buildings), np.nan, dtype="float32")
        maxima = np.full(len(buildings), np.nan, dtype="float32")
        counts = np.zeros(len(buildings), dtype="int32")
        for index, geometry in enumerate(buildings.geometry):
            if geometry is None or geometry.is_empty:
                continue
            values, _ = mask(raster, [geometry], crop=True, filled=False, indexes=1)
            valid = values.compressed()
            valid = valid[np.isfinite(valid) & (valid >= 0)]
            if valid.size:
                means[index] = float(valid.mean())
                maxima[index] = float(valid.max())
                counts[index] = int(valid.size)

    buildings["height_m"] = means
    buildings["height_max_m"] = maxima
    buildings["height_pixel_count"] = counts
    args.output.parent.mkdir(parents=True, exist_ok=True)
    buildings.to_file(args.output, layer="buildings", driver="GPKG", engine="pyogrio")
    valid = buildings["height_m"].notna()
    audit = {
        "status": "complete",
        "source_buildings": str(args.buildings),
        "source_height": str(args.height),
        "output": str(args.output),
        "crs": str(buildings.crs),
        "building_count": int(len(buildings)),
        "height_joined_count": int(valid.sum()),
        "height_missing_count": int((~valid).sum()),
        "height_mean_min_m": float(buildings.loc[valid, "height_m"].min()) if valid.any() else None,
        "height_mean_max_m": float(buildings.loc[valid, "height_m"].max()) if valid.any() else None,
        "height_mean_average_m": float(buildings.loc[valid, "height_m"].mean()) if valid.any() else None,
        "join_rule": "mean and maximum valid 30 m building_height pixels intersecting each current PlanX building polygon; nodata and negative values excluded; no imputation",
    }
    args.audit.parent.mkdir(parents=True, exist_ok=True)
    args.audit.write_text(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(audit, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
