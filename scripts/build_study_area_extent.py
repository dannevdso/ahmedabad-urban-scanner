#!/usr/bin/env python3
"""Export the screenshot-digitised Ahmedabad–Gandhinagar study-area bundle."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
from PIL import Image, ImageDraw

from ahmedabad_scanner.study_area import BLACK_LINE_VERTICES_PX, digitised_study_area

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCREENSHOT = (
    Path.home()
    / "Dropbox/999 MAC Screenshots/Screenshot 2026-10-17 at 5.16.14\u202fPM.png"
)
OUTPUT_STEM = "ahmedabad-gandhinagar-black-line"

CALIBRATION_ANCHORS = [
    {"name": "Pethapur", "pixel": [410, 71], "longitude": 72.6690097, "latitude": 23.2658686},
    {"name": "Kalol", "pixel": [154, 111], "longitude": 72.4966223, "latitude": 23.2452165},
    {"name": "Bopal Lake", "pixel": [103, 445], "longitude": 72.4587752, "latitude": 23.0385802},
    {"name": "Ahmedabad", "pixel": [275, 445], "longitude": 72.5800568, "latitude": 23.0215374},
    {"name": "Raysan", "pixel": [398, 225], "longitude": 72.6483285, "latitude": 23.1663954},
    {"name": "Sabarmati Ashram", "pixel": [278, 384], "longitude": 72.5809398, "latitude": 23.0606666},
    {"name": "Jetalpur", "pixel": [295, 665], "longitude": 72.5966176, "latitude": 22.8923003},
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screenshot", type=Path, default=DEFAULT_SCREENSHOT)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "config" / "study_areas")
    parser.add_argument(
        "--preview-dir", type=Path, default=ROOT / "outputs" / "study_area"
    )
    return parser.parse_args()


def draw_digitisation_preview(screenshot: Path, output: Path) -> None:
    image = Image.open(screenshot).convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    points = list(BLACK_LINE_VERTICES_PX)
    draw.polygon(points, fill=(255, 0, 0, 38))
    draw.line(points + [points[0]], fill=(255, 0, 0, 230), width=3)
    for index, (x, y) in enumerate(points, start=1):
        draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=(255, 255, 255, 255), outline=(220, 0, 0, 255), width=2)
        if index in {1, 10, 20, 30}:
            draw.text((x + 5, y - 8), str(index), fill=(180, 0, 0, 255))
    Image.alpha_composite(image, overlay).convert("RGB").save(output, quality=95)


def main() -> None:
    args = parse_args()
    screenshot = args.screenshot.expanduser().resolve()
    if not screenshot.exists():
        raise FileNotFoundError(f"Screenshot not found: {screenshot}")

    output_dir = args.output_dir.resolve()
    preview_dir = args.preview_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)

    polygon = digitised_study_area()
    if not polygon.is_valid:
        raise ValueError("Digitised polygon is invalid")

    record = {
        "area_id": "ahm_gnr_black_line_20261017",
        "name": "Ahmedabad–Gandhinagar black-line study area",
        "status": "approximate_screenshot_digitisation",
        "source": "user_supplied_map_screenshot",
    }
    frame = gpd.GeoDataFrame([record], geometry=[polygon], crs="EPSG:4326")
    projected = frame.to_crs("EPSG:32643")
    area_km2 = float(projected.geometry.area.iloc[0] / 1_000_000)
    perimeter_km = float(projected.geometry.length.iloc[0] / 1_000)
    bounds = [float(value) for value in frame.total_bounds]

    geojson_path = output_dir / f"{OUTPUT_STEM}.geojson"
    gpkg_path = output_dir / f"{OUTPUT_STEM}.gpkg"
    shapefile_zip_path = output_dir / f"{OUTPUT_STEM}-shapefile.zip"
    metadata_path = output_dir / f"{OUTPUT_STEM}.metadata.json"
    bbox_path = output_dir / f"{OUTPUT_STEM}.bbox.txt"
    config_path = output_dir / f"{OUTPUT_STEM}.toml"
    preview_path = preview_dir / f"{OUTPUT_STEM}-digitisation-preview.png"

    geojson_path.write_text(frame.to_json(drop_id=True, to_wgs84=True), encoding="utf-8")
    if gpkg_path.exists():
        gpkg_path.unlink()
    frame.to_file(gpkg_path, layer="study_area", driver="GPKG")

    with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as temporary:
        temporary_dir = Path(temporary)
        shp_path = temporary_dir / f"{OUTPUT_STEM}.shp"
        frame.to_file(shp_path, driver="ESRI Shapefile", encoding="UTF-8")
        with zipfile.ZipFile(shapefile_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(temporary_dir.glob(f"{OUTPUT_STEM}.*")):
                archive.write(path, arcname=path.name)

    metadata = {
        "generated_utc": datetime.now(UTC).isoformat(),
        "area_id": record["area_id"],
        "name": record["name"],
        "status": record["status"],
        "source_screenshot": str(screenshot),
        "source_image_pixels": list(Image.open(screenshot).size),
        "digitised_vertex_count": len(BLACK_LINE_VERTICES_PX),
        "crs": "EPSG:4326",
        "recommended_metric_crs": "EPSG:32643",
        "bbox_wgs84": bounds,
        "area_km2": round(area_km2, 2),
        "perimeter_km": round(perimeter_km, 2),
        "calibration": {
            "method": "north-up Web-Mercator screen fit using visible place labels and landmarks",
            "anchors": CALIBRATION_ANCHORS,
            "estimated_positional_uncertainty": "approximately ±1 km; labels and screenshot georeferencing are not survey control",
        },
        "intended_coverage": [
            "Ahmedabad ring-road area",
            "Bopal",
            "South Bopal",
            "Gandhinagar",
        ],
        "limitations": [
            "This is an approximate digitisation of the black line in the supplied screenshot.",
            "It is not an administrative boundary, statutory development-plan boundary, or survey-grade geometry.",
            "Replace it with an exact exported polygon if the original map drawing becomes available.",
            "Use the polygon geometry for clipping; use the bbox file only for coarse download queries.",
        ],
        "outputs": {
            "geojson": str(geojson_path),
            "geopackage": str(gpkg_path),
            "shapefile_zip": str(shapefile_zip_path),
            "bbox": str(bbox_path),
            "preview": str(preview_path),
        },
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    bbox_path.write_text(
        "min_lon,min_lat,max_lon,max_lat\n" + ",".join(f"{value:.9f}" for value in bounds) + "\n",
        encoding="utf-8",
    )
    config_path.write_text(
        "[study_area]\n"
        f'name = "{record["name"]}"\n'
        f'geometry = "config/study_areas/{geojson_path.name}"\n'
        'crs = "EPSG:4326"\n'
        'analysis_crs = "EPSG:32643"\n'
        f"bbox = [{', '.join(f'{value:.9f}' for value in bounds)}]\n"
        f'quality_status = "{record["status"]}"\n'
        'note = "Use polygon geometry for clipping; bbox is for coarse acquisition only."\n',
        encoding="utf-8",
    )
    draw_digitisation_preview(screenshot, preview_path)

    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
