"""Create a documented current-study network subset for expensive centrality."""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
from shapely.geometry import box


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--network", type=Path, default=Path("data/derived/planx/ahmedabad-gandhinagar-outputs/prepared_network.gpkg"))
    parser.add_argument("--output", type=Path, default=Path("data/derived/planx/ahmedabad-gandhinagar-outputs/centrality_network.gpkg"))
    parser.add_argument("--size-m", type=float, default=12000.0)
    args = parser.parse_args()
    network = gpd.read_file(args.network, layer="prepared_network")
    minx, miny, maxx, maxy = network.total_bounds
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    mask = box(cx - args.size_m / 2, cy - args.size_m / 2, cx + args.size_m / 2, cy + args.size_m / 2)
    subset = network[network.geometry.intersects(mask)].copy()
    subset["centrality_subset"] = "12km_current_study_center_tile"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        args.output.unlink()
    subset.to_file(args.output, layer="prepared_network", driver="GPKG", engine="pyogrio", index=False)
    report = {
        "generated_utc": datetime.now(UTC).isoformat(),
        "source": str(args.network),
        "output": str(args.output),
        "selection": "centered metric-CRS square clipped from the current-study prepared network",
        "size_m": args.size_m,
        "bounds_metric": [float(v) for v in mask.bounds],
        "source_count": int(len(network)),
        "selected_count": int(len(subset)),
        "selected_bounds_metric": [float(v) for v in subset.total_bounds],
        "limitation": "Centrality is reported only for this bounded current-study tile because global centrality on the 135,115-segment prepared network exceeded the safe execution window; it is not a citywide centrality result.",
    }
    args.output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
