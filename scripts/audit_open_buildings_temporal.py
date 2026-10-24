#!/usr/bin/env python3
"""Acquire and audit Google Open Buildings Temporal tiles for a WGS84 boundary."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import rasterio
from affine import Affine
from shapely.geometry import Polygon
from shapely.ops import transform
from pyproj import Transformer

BUCKET = "open-buildings-temporal-data"
DATASET_VERSION = "v1"
MANIFEST_S2_TOKEN = "39"
YEARS = (2016, 2020, 2023)
BASE_URL = f"https://storage.googleapis.com/{BUCKET}"


def read_boundary(path: Path):
    frame = gpd.read_file(path)
    if frame.empty:
        raise ValueError(f"Boundary has no features: {path}")
    if frame.crs is None:
        raise ValueError(f"Boundary has no CRS: {path}")
    return frame.to_crs("EPSG:4326").geometry.union_all()


def manifest_url(year: int) -> str:
    return f"{BASE_URL}/{DATASET_VERSION}/manifests/{MANIFEST_S2_TOKEN}_EPSG_32643_{year}_06_30.json"


def load_manifest(year: int, metadata_dir: Path) -> tuple[dict, str, str]:
    url = manifest_url(year)
    local = metadata_dir / Path(url).name
    if not local.exists():
        urllib.request.urlretrieve(url, local)
    sha = sha256_file(local)
    with local.open() as handle:
        return json.load(handle), url, sha


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tile_records(manifest: dict, boundary) -> tuple[list[dict], str]:
    crs = manifest["tilesets"][0]["crs"]
    projected_boundary = transform(
        Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform,
        boundary,
    )
    records = []
    for tileset in manifest["tilesets"]:
        for source in tileset["sources"]:
            affine_transform = source["affineTransform"]
            affine = Affine.translation(
                affine_transform["translateX"], affine_transform["translateY"]
            ) * Affine.scale(affine_transform["scaleX"], affine_transform["scaleY"])
            dimensions = source["dimensions"]
            width, height = dimensions["width"], dimensions["height"]
            corners = [affine * p for p in ((0, 0), (width, 0), (width, height), (0, height))]
            polygon = Polygon(corners)
            if not polygon.intersects(projected_boundary):
                continue
            relative = source["uris"][0]
            object_path = manifest["uriPrefix"] + relative
            if object_path.startswith(f"gs://{BUCKET}/"):
                object_path = object_path[len(f"gs://{BUCKET}/"):]
            url = f"{BASE_URL}/{object_path}"
            records.append(
                {
                    "url": url,
                    "object_path": object_path,
                    "relative_uri": relative,
                    "crs": crs,
                    "width": width,
                    "height": height,
                    "bounds_projected": list(polygon.bounds),
                }
            )
    return records, crs


def request_headers(url: str) -> dict:
    result = subprocess.run(
        ["curl", "--fail", "--location", "--silent", "--show-error", "--head", "--dump-header", "-", "--output", "/dev/null", url],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    headers = {}
    for line in result.stdout.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip()] = value.strip()
    return headers


def download(url: str, destination: Path) -> dict:
    tmp = destination.with_suffix(destination.suffix + ".part")
    try:
        with tmp.open("wb") as out:
            subprocess.run(
                ["curl", "--fail", "--location", "--silent", "--show-error", url],
                check=True,
                stdout=out,
                timeout=900,
            )
        tmp.replace(destination)
        return {"status": "downloaded", "bytes": destination.stat().st_size, "sha256": sha256_file(destination)}
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise


def remote_metadata(object_path: str) -> dict:
    encoded = urllib.parse.quote(object_path, safe="")
    metadata_url = f"https://storage.googleapis.com/storage/v1/b/{BUCKET}/o/{encoded}?alt=json"
    result = subprocess.run(
        ["curl", "--fail", "--location", "--silent", "--show-error", metadata_url],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return json.loads(result.stdout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--boundary", type=Path, default=Path("config/study_areas/ahmedabad-gandhinagar-black-line.gpkg"))
    parser.add_argument("--metadata-dir", type=Path, default=Path("data/open-buildings-temporal/metadata/manifests"))
    parser.add_argument("--data-dir", type=Path, default=Path("data/open-buildings-temporal/geotiffs"))
    parser.add_argument("--no-download", action="store_true")
    args = parser.parse_args()

    boundary = read_boundary(args.boundary)
    args.metadata_dir.mkdir(parents=True, exist_ok=True)
    args.data_dir.mkdir(parents=True, exist_ok=True)
    audit = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "boundary": str(args.boundary.resolve()),
        "boundary_crs": "EPSG:4326",
        "boundary_bounds_wgs84": list(boundary.bounds),
        "requested_years": list(YEARS),
        "source_notebook": "https://colab.research.google.com/github/google-research/google-research/blob/master/building_detection/open_buildings_temporal_download_region_geotiffs.ipynb#scrollTo=UajWyhy2s2KG",
        "source_app": "https://mmeka-ee.projects.earthengine.app/view/open-buildings-temporal-dataset",
        "bucket": BUCKET,
        "manifest_s2_token": MANIFEST_S2_TOKEN,
        "manifest_s2_level": 2,
        "years": {},
    }

    for year in YEARS:
        year_result = {"manifest_url": manifest_url(year), "tiles": [], "failures": []}
        try:
            manifest, url, manifest_sha = load_manifest(year, args.metadata_dir)
            year_result.update({"manifest_sha256": manifest_sha, "manifest_local": str((args.metadata_dir / Path(url).name).resolve())})
            tiles, crs = tile_records(manifest, boundary)
            year_result["crs"] = crs
            year_result["intersecting_tile_count"] = len(tiles)
            for index, tile in enumerate(tiles):
                filename = args.data_dir / str(year) / Path(tile["relative_uri"]).name
                filename.parent.mkdir(parents=True, exist_ok=True)
                record = {**tile, "local_path": str(filename.resolve())}
                try:
                    headers = request_headers(tile["url"])
                    normalized_headers = {key.lower(): value for key, value in headers.items()}
                    metadata = remote_metadata(tile["object_path"])
                    record.update({
                        "http_status": 200,
                        "content_length": int(metadata.get("size", normalized_headers.get("content-length", "0")) or 0),
                        "etag": normalized_headers.get("etag"),
                        "last_modified": normalized_headers.get("last-modified"),
                        "generation": metadata.get("generation"),
                        "remote_md5_base64": metadata.get("md5Hash"),
                        "remote_crc32c_base64": metadata.get("crc32c"),
                    })
                    if args.no_download:
                        record["status"] = "head_only"
                    elif filename.exists():
                        record.update({"status": "already_present", "bytes": filename.stat().st_size, "sha256": sha256_file(filename)})
                    else:
                        record.update(download(tile["url"], filename))
                        with rasterio.open(filename) as dataset:
                            record["raster_crs"] = dataset.crs.to_string() if dataset.crs else None
                            record["raster_bounds"] = list(dataset.bounds)
                            record["raster_width"] = dataset.width
                            record["raster_height"] = dataset.height
                            record["raster_count"] = dataset.count
                except urllib.error.HTTPError as error:
                    record.update({"status": "http_error", "http_status": error.code, "error": str(error)})
                    year_result["failures"].append(record)
                except Exception as error:  # preserve exact failure for audit
                    record.update({"status": "error", "error": repr(error)})
                    year_result["failures"].append(record)
                year_result["tiles"].append(record)
        except Exception as error:
            year_result["manifest_failure"] = repr(error)
        audit["years"][str(year)] = year_result

    output = Path("reports/open_buildings_temporal_acquisition.json")
    output.write_text(json.dumps(audit, indent=2) + "\n")
    print(json.dumps({"output": str(output.resolve()), "years": {y: {"tiles": v.get("intersecting_tile_count"), "failures": len(v.get("failures", []))} for y, v in audit["years"].items()}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
