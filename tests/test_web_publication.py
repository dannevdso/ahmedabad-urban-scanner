

def test_local_area_profile_contract_is_a_compact_static_asset():
    from scripts.build_web_data import export_local_area_profile_contract

    path = export_local_area_profile_contract(__import__("pathlib").Path("/tmp"))
    assert path.name == "local-area-profile-schema.json"
    payload = __import__("json").loads(path.read_text())
    assert payload["contractVersion"] == "local-area-profile.v1"
    assert payload["selection"]["radiusM"] == [400, 800, 1200]
    assert payload["sections"] == ["overview", "buildings", "streetsConnectivity", "spaceSyntaxCentrality", "environment", "publicTransport", "parksEducation", "availability", "methods"]
    path.unlink()


def test_tps_publication_validates_and_preserves_duplicate_display_identifiers(tmp_path):
    import json
    from shapely.geometry import mapping, box
    from scripts.build_web_data import publish_tps_zones

    source = tmp_path / "tps.geojson"
    features = [
        {"type": "Feature", "properties": {"source_id": "a", "tps_name": "Same", "tps_no": "1", "tps_status": "draft"}, "geometry": mapping(box(0, 0, 1, 1))},
        {"type": "Feature", "properties": {"source_id": "b", "tps_name": "Same", "tps_no": "1", "tps_status": "draft"}, "geometry": mapping(box(2, 0, 3, 1))},
    ]
    source.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
    report = publish_tps_zones(tmp_path / "out", source_path=source, expected_count=2)
    output = json.loads((tmp_path / "out" / "tps-provisional.geojson").read_text())
    assert report["feature_count"] == 2
    assert report["duplicate_display_identifier_count"] == 1
    assert [f["properties"] for f in output["features"]] == [f["properties"] for f in features]
