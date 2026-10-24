from __future__ import annotations

import json
from pathlib import Path
from collections import Counter

import geopandas as gpd
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box

from ahmedabad_scanner.local_profile_assets import (
    ASSET_VERSION,
    build_manifest,
    enrich_gtfs_route_ids,
    select_columns,
    verify_asset,
    write_atomic_fgb,
    _write_pois,
    add_building_centroids,
    validate_centroid_fields,
    prepare_building_location_points,
    merge_building_location_manifest,
)


def test_add_building_centroids_uses_full_source_geometry_in_target_crs():
    frame = gpd.GeoDataFrame(
        {"building_id": [1]},
        geometry=[MultiPolygon([box(0, 0, 2, 2), box(10, 0, 12, 2)])],
        crs="EPSG:32643",
    )
    result = add_building_centroids(frame)
    assert result.geometry.iloc[0].equals(frame.geometry.iloc[0])
    assert result[["centroid_x", "centroid_y"]].iloc[0].tolist() == [6.0, 1.0]


def test_validate_centroid_fields_rejects_non_finite_values():
    frame = gpd.GeoDataFrame(
        {"centroid_x": [1.0, float("nan")], "centroid_y": [2.0, 3.0]},
        geometry=[Point(0, 0), Point(1, 1)],
        crs="EPSG:32643",
    )
    try:
        validate_centroid_fields(frame)
    except ValueError as exc:
        assert "finite" in str(exc)
    else:
        raise AssertionError("expected non-finite centroid validation failure")


def test_select_columns_preserves_requested_fields_and_geometry():
    frame = gpd.GeoDataFrame(
        {"building_id": [1], "footprint_area_m2": [10.0], "compact": [0.5], "extra": ["ignore"]},
        geometry=[box(0, 0, 1, 1)],
        crs="EPSG:32643",
    )
    selected = select_columns(frame, ["building_id", "footprint_area_m2", "compact"])
    assert list(selected.columns) == ["building_id", "footprint_area_m2", "compact", "geometry"]


def test_write_atomic_fgb_and_verify_reports_bbox_count_fields_and_index(tmp_path):
    frame = gpd.GeoDataFrame(
        {"u": [1], "v": [2], "length_m": [5.0], "highway": ["residential"]},
        geometry=[LineString([(0, 0), (5, 0)])],
        crs="EPSG:32643",
    )
    path = tmp_path / "edges.fgb"
    write_atomic_fgb(frame, path, layer="edges")
    report = verify_asset(path, layer="edges", expected_fields=["u", "v", "length_m", "highway"], audit_bbox=(0, -1, 6, 1))
    assert report["count"] == 1
    assert report["crs"] == "EPSG:32643"
    assert report["fields"] == ["u", "v", "length_m", "highway"]
    assert report["audit_count"] == 1
    assert report["spatial_index_verified"] is True
    assert not (tmp_path / "edges.fgb.tmp").exists()


def test_verify_asset_requires_finite_centroids_in_audit_bbox(tmp_path):
    frame = gpd.GeoDataFrame(
        {"centroid_x": [1.0], "centroid_y": [2.0]},
        geometry=[box(0, 0, 5, 5)],
        crs="EPSG:32643",
    )
    path = tmp_path / "buildings.fgb"
    write_atomic_fgb(frame, path, layer="buildings")
    report = verify_asset(path, layer="buildings", expected_fields=["centroid_x", "centroid_y"], audit_bbox=(-1, -1, 6, 6))
    assert report["audit_count"] == 1


def test_gtfs_route_ids_are_derived_from_route_model():
    stops = gpd.GeoDataFrame(
        {"stop_id": ["s1", "s2"], "stop_name": ["A", "B"]},
        geometry=[Point(72.5, 23.0), Point(72.6, 23.1)],
        crs="EPSG:4326",
    )
    model = {"route_ids": ["r1", "r2"], "stop_routes": [[0], [0, 1]]}
    result = enrich_gtfs_route_ids(stops, model)
    assert result["route_ids"].tolist() == [["r1"], ["r1", "r2"]]


def test_manifest_is_versioned_and_contains_required_provenance():
    manifest = build_manifest(
        assets={"buildings": {"path": "buildings.fgb", "count": 1, "fields": ["building_id"]}},
        sources={"buildings": {"path": "data/source.gpkg", "sha256": "abc"}},
        bounds=[0, 1, 2, 3],
        audit_center=[1, 2],
    )
    assert manifest["manifest_version"] == ASSET_VERSION
    assert manifest["allowed_radii_m"] == [400, 800, 1200]
    assert manifest["assets"]["buildings"]["provenance_status"]
    assert manifest["caveats"]["remote_sensing"]


def test_pois_export_uses_approved_representative_points_and_exact_categories(tmp_path):
    source = tmp_path / "approved-pois.geojson"
    features = []
    for index in range(765):
        features.append({"type": "Feature", "properties": {"osm_id": f"way/{index}", "poi_type": "parks", "name": f"P{index}"}, "geometry": {"type": "Point", "coordinates": [72.5 + index * 0.00001, 23.0]}})
    features.append({"type": "Feature", "properties": {"osm_id": "way/765", "poi_type": "schools", "name": "S"}, "geometry": {"type": "Point", "coordinates": [72.6, 23.0]}})
    source.write_text(json.dumps({"type": "FeatureCollection", "features": features}))

    report = _write_pois(source, tmp_path / "stage", tmp_path, (0, 0, 100000, 100000))

    assert report["count"] == 766
    assert report["category_counts"] == {"park": 765, "school": 1}
    frame = gpd.read_file(tmp_path / "stage" / "parks-schools.fgb")
    assert len(frame) == 766
    assert set(frame.geometry.geom_type) == {"Point"}
    assert set(frame["representative_point_rule"]) == {"approved-source-point"}


def test_manifest_exposes_browser_constructible_raster_metric_definitions():
    manifest = build_manifest(
        assets={
            "lst": {"path": "lst.tif", "metadata": {"crs": "EPSG:32643", "origin": [1, 2], "pixelSize": [10, -10], "width": 4, "height": 5, "nodata": -9999, "units": "°C"}},
            "ndvi": {"path": "ndvi.tif", "metadata": {"crs": "EPSG:32643", "origin": [1, 2], "pixelSize": [10, -10], "width": 4, "height": 5, "nodata": -9999}},
        },
        sources={},
        bounds=[0, 1, 2, 3],
        audit_center=[1, 2],
    )
    metric = manifest["metrics"]["lst"]
    assert metric["url"] == "lst.tif"
    assert metric["origin"] == [1, 2]
    assert metric["pixelSize"] == [10, -10]
    assert metric["width"] == 4 and metric["height"] == 5
    assert metric["nodata"] == -9999
    assert metric["units"] == "°C"
    assert metric["oneScene"] is True
    assert metric["bins"] == [30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48]
    assert "vegetationFraction" in manifest["metrics"]


def test_manifest_includes_flood_risk_asset_contract():
    manifest = build_manifest(
        assets={"floodRisk": {"path": "flood-risk.fgb", "fields": ["uf_risk"]}},
        sources={}, bounds=[0, 1, 2, 3], audit_center=[1, 2],
    )
    assert manifest["assets"]["floodRisk"]["path"] == "flood-risk.fgb"
    assert manifest["assets"]["floodRisk"]["claim_type"] == "exact source geometry/fields"


def test_prepare_building_location_points_filters_conflicts_ignored_outliers_and_preserves_central_count_only():
    zones = gpd.GeoDataFrame(
        {"objectid": [53, 181]},
        geometry=[box(0, 0, 10, 10), box(20, 0, 30, 10)],
        crs="EPSG:4326",
    )
    layers = {
        "52southwest": gpd.GeoDataFrame(
            {"height": [3, 4, 5], "area": [10, 11, 12], "suhi": [" High SUHI ", "low SUHI", "moderate SUHI"], "conflict": [False, True, False]},
            geometry=[Point(1, 1), Point(2, 2), Point(11, 1)], crs="EPSG:4326",
        ),
        "181-central-final": gpd.GeoDataFrame({"height": [None]}, geometry=[Point(21, 1)], crs="EPSG:4326"),
        "181centraltemp": gpd.GeoDataFrame({"height": [9], "area": [99], "suhi": [9.0], "conflict": [False]}, geometry=[Point(21, 2)], crs="EPSG:4326"),
    }
    points, audit = prepare_building_location_points(layers, zones)
    assert len(points) == 2
    assert set(points["zone_group"]) == {"enriched", "central"}
    assert points.loc[points["zone_group"] == "central", ["height_m", "area_m2", "volume_m3", "suhi"]].isna().all(axis=None)
    assert points.loc[points["zone_group"] == "enriched", "suhi"].tolist() == [" High SUHI "]
    assert set(points.columns) == {"zone_objectid", "zone_group", "height_m", "area_m2", "volume_m3", "suhi", "geometry"}
    assert audit["dropped_conflict"] == 1
    assert audit["dropped_outside_declared_zone"] == 1
    assert audit["ignored_layers"] == ["181centraltemp"]
    assert audit["layer_zone_mapping"]["52southwest"] == 53


def test_building_location_sidecar_merges_as_the_sole_buildings_publication():
    canonical = {"assets": {"buildings": {"path": "buildings.fgb", "sha256": "old"}}, "sources": {}}
    sidecar = {
        "asset": {"key": "buildingLocations", "path": "building-locations.fgb", "sha256": "new", "count": 162421},
        "source": {"buildings": {"path": "buildings.gpkg"}, "amc_zones": {"path": "amc_zones.geojson"}},
        "caveats": ["prototype"],
        "audit": {"dropped_conflict": 8995},
    }

    merged = merge_building_location_manifest(canonical, sidecar)

    assert "buildings" not in merged["assets"]
    assert "buildings" not in merged["sources"]
    assert merged["assets"]["buildingLocations"]["path"] == "building-locations.fgb"
    assert merged["sources"]["buildingLocations"] == sidecar["source"]
    assert merged["building_locations_publication"]["audit"]["dropped_conflict"] == 8995
    assert canonical["assets"] == {"buildings": {"path": "buildings.fgb", "sha256": "old"}}
