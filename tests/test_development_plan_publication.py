from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image


SOURCE_TIFF = Path.home() / "Library/Application Support/Hermes/composer-images/12_94643_modified_26c4fe.tiff"
AMC_BOUNDARY = Path.home() / ".hermes/attachments/amc_boundary.geojson"
SOURCE_SHA256 = "a9a3e97cdd19c3a4230b8c1fd09ab21c2b33409b0c2453ffe0300b45ecb0cddf"


def test_publish_development_plan_preserves_rgba_pixels_georeferencing_and_audit(tmp_path):
    from scripts.build_development_plan_assets import publish_development_plan

    publication = publish_development_plan(SOURCE_TIFF, tmp_path)
    derivative = tmp_path / "development-plan.png"
    project_copy = tmp_path / "development-plan-source.tiff"
    manifest = json.loads((tmp_path / "development-plan-manifest.json").read_text())

    assert publication["derivative"]["file"] == "development-plan.png"
    assert project_copy.read_bytes() == SOURCE_TIFF.read_bytes()
    assert hashlib.sha256(project_copy.read_bytes()).hexdigest() == SOURCE_SHA256
    assert manifest["source"]["sha256"] == SOURCE_SHA256
    assert manifest["source"]["crs"] == "EPSG:3857"
    assert manifest["source"]["dimensions"] == [1949, 1919]
    assert manifest["source"]["bands"] == ["red", "green", "blue", "alpha"]
    assert manifest["derivative"]["dimensions"] == [1949, 1919]
    assert manifest["derivative"]["rgba_preserved"] is True
    assert manifest["maplibre_image_coordinates"] == [
        [72.175196139126, 23.364584536618],
        [72.860609370435, 23.364584536618],
        [72.860609370435, 22.74362328497],
        [72.175196139126, 22.74362328497],
    ]
    assert manifest["attribution"] == {
        "publisher": "ARPM Studio",
        "title": "Development Plan for Ahmedabad 2041",
        "url": "https://arpm.studio/projects/ahmedabad-dp-2041",
    }

    with rasterio.open(SOURCE_TIFF) as source:
        expected = np.moveaxis(source.read([1, 2, 3, 4]), 0, -1)
    actual = np.asarray(Image.open(derivative).convert("RGBA"))
    assert actual.shape == expected.shape == (1919, 1949, 4)
    assert np.array_equal(actual, expected)


def test_publish_ahmedabad_boundary_removes_holes_and_preserves_exterior(tmp_path):
    from scripts.build_development_plan_assets import publish_ahmedabad_boundary

    source = json.loads(AMC_BOUNDARY.read_text())
    source_geometry = source["features"][0]["geometry"]
    publication = publish_ahmedabad_boundary(AMC_BOUNDARY, tmp_path)
    payload = json.loads((tmp_path / "ahmedabad-boundary.geojson").read_text())
    manifest = json.loads((tmp_path / "ahmedabad-boundary-manifest.json").read_text())
    geometry = payload["features"][0]["geometry"]

    assert publication["file"] == "ahmedabad-boundary.geojson"
    assert manifest == publication
    assert publication["source"]["path"] == "external-inputs/amc_boundary.geojson"
    assert publication["source"]["sha256"] == "2d6b5846e9dae8f239cebaafaccf5cb295655953c78e352eef21af819cbfb935"
    assert publication["source"]["feature_count"] == 1
    assert publication["source"]["crs"] == "EPSG:4326"
    assert publication["source"]["exterior_vertex_count"] == 1478
    assert publication["source"]["interior_ring_count"] == 1
    assert publication["output"]["feature_count"] == 1
    assert payload["type"] == "FeatureCollection"
    assert len(payload["features"]) == 1
    assert payload["features"][0]["properties"] == {}
    assert geometry["type"] == "Polygon"
    assert len(geometry["coordinates"]) == 1
    assert geometry["coordinates"][0] == source_geometry["coordinates"][0]
    assert publication["output"]["exterior_vertex_count"] == 1478
    assert publication["output"]["interior_ring_count"] == 0
    assert publication["output"]["bounds_wgs84"] == [72.448455, 22.91047, 72.701959, 23.140851]
    assert publication["output"]["sha256"] == hashlib.sha256((tmp_path / "ahmedabad-boundary.geojson").read_bytes()).hexdigest()
    assert publication["output"]["bytes"] == (tmp_path / "ahmedabad-boundary.geojson").stat().st_size
    assert publication["method"] == "Copied every polygon exterior shell only; interior rings were intentionally omitted; no simplification or coordinate transformation was applied."


def test_web_metadata_catalog_marks_development_plan_as_supplied_unverified_experimental():
    from scripts.build_web_data import CONTEXT_CATALOG, OVERLAY_CONTEXT_KEYS, build_overlay_legends

    assert OVERLAY_CONTEXT_KEYS["developmentPlan"] == "supplied-unverified-experimental"
    assert CONTEXT_CATALOG["supplied-unverified-experimental"]["statusLabel"] == "Unverified / experimental"
    legend = build_overlay_legends({})["developmentPlan"]
    assert legend["context_key"] == "supplied-unverified-experimental"
    assert legend["validation_status"] == "unverified"
    assert "embedded legend" in legend["caveat"]


def test_metadata_update_publishes_context_and_truthful_development_plan_legend(tmp_path):
    from scripts.build_development_plan_assets import update_public_metadata

    metadata_path = tmp_path / "metadata.json"
    update_public_metadata(metadata_path, {"derivative": {"file": "development-plan.png"}}, {"file": "ahmedabad-boundary.geojson"})
    metadata = json.loads(metadata_path.read_text())

    assert metadata["overlay_contexts"]["developmentPlan"] == "supplied-unverified-experimental"
    assert metadata["contexts"]["supplied-unverified-experimental"]["statusLabel"] == "Unverified / experimental"
    assert metadata["overlay_legends"]["developmentPlan"]["validation_status"] == "unverified"
    assert "embedded legend" in metadata["overlay_legends"]["developmentPlan"]["caveat"]
    assert metadata["overlay_legends"]["developmentPlan"]["attribution"] == {
        "publisher": "ARPM Studio",
        "title": "Development Plan for Ahmedabad 2041",
        "url": "https://arpm.studio/projects/ahmedabad-dp-2041",
    }


def test_development_plan_publication_excludes_jantri(tmp_path):
    from scripts.build_development_plan_assets import update_public_metadata

    metadata_path = tmp_path / "metadata.json"
    update_public_metadata(metadata_path, {"attribution": {"publisher": "ARPM Studio"}}, {})
    metadata = json.loads(metadata_path.read_text())
    assert "jantri" not in json.dumps(metadata).lower()
