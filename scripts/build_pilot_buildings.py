"""Build the Navrangpura pilot from Google Open Buildings V3."""

from __future__ import annotations

import argparse
import json
import tomllib
from pathlib import Path

import geopandas as gpd
import matplotlib
from shapely.geometry import box

from ahmedabad_scanner.buildings import prepare_open_buildings_frame
from ahmedabad_scanner.open_buildings import load_open_buildings_bbox, s2_tokens_for_bbox

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/ahmedabad_pilot.toml"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_root = args.config.resolve().parent.parent
    with args.config.open("rb") as file:
        config = tomllib.load(file)

    bbox = tuple(float(value) for value in config["boundary"]["bbox"])
    source_config = config["building_source"]
    configured_tokens = [str(token) for token in source_config["s2_tokens"]]
    calculated_tokens = s2_tokens_for_bbox(bbox, level=int(source_config["s2_level"]))
    if configured_tokens != calculated_tokens:
        raise ValueError(
            f"Configured S2 tokens {configured_tokens} do not match calculated tokens {calculated_tokens}"
        )

    raw_dir = project_root / source_config["raw_dir"]
    raw_paths = [raw_dir / f"{token}_buildings.csv.gz" for token in configured_tokens]
    missing = [str(path) for path in raw_paths if not path.exists()]
    if missing:
        template = source_config["tile_url_template"]
        commands = [f"curl -L --continue-at - -o {path} {template.format(token=token)}" for token, path in zip(configured_tokens, raw_paths)]
        raise FileNotFoundError("Missing Open Buildings shard(s). Download with:\n" + "\n".join(commands))

    selected_source = load_open_buildings_bbox(raw_paths, bbox=bbox)
    buildings = prepare_open_buildings_frame(
        selected_source,
        study_bbox=bbox,
        analysis_crs=config["project"]["analysis_crs"],
        min_area_m2=float(source_config["min_footprint_area_m2"]),
        confidence_min=float(source_config["confidence_threshold"]),
    )
    if buildings.empty:
        raise RuntimeError("No buildings remained after pilot filtering")

    parquet_path = project_root / config["inputs"]["buildings"]
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    buildings.to_parquet(parquet_path, index=False)

    output_dir = project_root / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    map_path = output_dir / "navrangpura_open_buildings_v3_qa.png"
    fig, ax = plt.subplots(figsize=(12, 12))
    buildings.plot(
        ax=ax,
        column="confidence",
        cmap="viridis",
        vmin=float(source_config["confidence_threshold"]),
        vmax=1.0,
        linewidth=0,
        legend=True,
        legend_kwds={"label": "Google Open Buildings confidence"},
    )
    boundary = gpd.GeoSeries([box(*bbox)], crs="EPSG:4326").to_crs(buildings.crs)
    boundary.boundary.plot(ax=ax, color="#d62728", linewidth=1.2)
    ax.set_title(
        "Navrangpura pilot — Google Open Buildings V3\n"
        f"{len(buildings):,} footprints · confidence ≥ {source_config['confidence_threshold']}"
    )
    ax.set_axis_off()
    fig.savefig(map_path, dpi=240, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    summary = {
        "study_area": config["project"]["study_area"],
        "bbox_wgs84": list(bbox),
        "source": source_config["provider"],
        "dataset": source_config["dataset"],
        "version": source_config["version"],
        "inference_date": source_config["inference_date"],
        "licence": source_config["licence"],
        "s2_level": int(source_config["s2_level"]),
        "s2_tokens": configured_tokens,
        "threshold_precision": float(source_config["threshold_precision"]),
        "confidence_threshold": float(source_config["confidence_threshold"]),
        "source_rows_in_bbox": int(len(selected_source)),
        "prepared_buildings": int(len(buildings)),
        "analysis_crs": str(buildings.crs),
        "area_m2": {
            "min": round(float(buildings["footprint_area_m2"].min()), 2),
            "median": round(float(buildings["footprint_area_m2"].median()), 2),
            "mean": round(float(buildings["footprint_area_m2"].mean()), 2),
            "max": round(float(buildings["footprint_area_m2"].max()), 2),
        },
        "confidence": {
            "min": round(float(buildings["confidence"].min()), 4),
            "median": round(float(buildings["confidence"].median()), 4),
            "mean": round(float(buildings["confidence"].mean()), 4),
            "max": round(float(buildings["confidence"].max()), 4),
        },
        "outputs": {
            "buildings_parquet": str(parquet_path.relative_to(project_root)),
            "qa_map": str(map_path.relative_to(project_root)),
        },
    }
    report_path = project_root / "reports/navrangpura_open_buildings_v3_summary.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    print(f"Saved buildings: {parquet_path}")
    print(f"Saved QA map: {map_path}")
    print(f"Saved summary: {report_path}")


if __name__ == "__main__":
    main()
