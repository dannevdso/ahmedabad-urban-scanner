"""Build reversible stripped-building PMTiles candidates without touching production assets.

The source is the canonical full-study building input used by the project’s web
publication and local-profile fallback. Candidate archives are written only to
the caller-provided experiment directory.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import geopandas as gpd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "data/derived/planx/ahmedabad-gandhinagar-full-buildings-inputs.gpkg"
DEFAULT_OUT = Path.home() / ".hermes/cache/scratch/ahmedabad-building-pmtiles-experiment"
LAYER = "buildings"
TIPPECANOE = "/opt/homebrew/bin/tippecanoe"


def run(command: list[str]) -> None:
    print("$", " ".join(command), flush=True)
    subprocess.run(command, check=True)


def build_candidate(source: Path, out_dir: Path, name: str, properties: list[str]) -> dict[str, object]:
    geojson = out_dir / f"{name}.geojson"
    pmtiles = out_dir / f"{name}.pmtiles"
    columns = ["geometry", *properties]
    frame = gpd.read_file(source, layer=LAYER, columns=columns, engine="pyogrio")
    if frame.crs is None:
        raise ValueError("canonical source has no CRS")
    frame = frame.to_crs("EPSG:4326")
    frame = frame[columns]
    frame.to_file(geojson, driver="GeoJSON", engine="pyogrio", index=False)
    run([
        TIPPECANOE,
        "-o", str(pmtiles),
        "-l", "buildings",
        "-Z1",
        "-z16",
        "--drop-densest-as-needed",
        "--extend-zooms-if-still-dropping",
        "--force",
        str(geojson),
    ])
    return {
        "name": name,
        "geojson": str(geojson),
        "pmtiles": str(pmtiles),
        "feature_count": int(len(frame)),
        "properties": properties,
        "source_crs": str(frame.crs),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "source": str(args.source),
        "source_layer": LAYER,
        "tippecanoe": TIPPECANOE,
        "tippecanoe_options": ["-l", "buildings", "-Z1", "-z16", "--drop-densest-as-needed", "--extend-zooms-if-still-dropping"],
        "candidates": [
            build_candidate(args.source, args.out_dir, "A-geometry-only", []),
            build_candidate(args.source, args.out_dir, "B-geometry-footprint-area", ["footprint_area_m2"]),
        ],
    }
    (args.out_dir / "build-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
