from pathlib import Path

from scripts.build_building_height_tiles import (
    EFFECTIVE_RESOLUTION_M,
    FINE_MIN_ZOOM,
    FINE_ZOOM_LEVELS,
    build_tile_inventory,
    validate_fine_manifest,
)


def test_fine_tile_contract_uses_four_metre_effective_resolution_and_explicit_switch() -> None:
    assert EFFECTIVE_RESOLUTION_M == 4
    assert FINE_MIN_ZOOM == 8
    assert FINE_ZOOM_LEVELS == (8, 11, 14, 16)


def test_tile_inventory_contains_only_intersecting_nonempty_tiles(tmp_path: Path) -> None:
    fine = tmp_path / "fine"
    (fine / "15" / "100").mkdir(parents=True)
    (fine / "15" / "100" / "200.webp").write_bytes(b"x")
    (fine / "15" / "101").mkdir(parents=True)
    (fine / "15" / "101" / "200.webp").write_bytes(b"y")
    (fine / "15" / "102").mkdir(parents=True)
    (fine / "15" / "102" / "200.webp").write_bytes(b"")
    inventory = build_tile_inventory(fine)
    assert inventory == [{"z": 15, "x": 100, "y": 200, "path": "15/100/200.webp", "bytes": 1}, {"z": 15, "x": 101, "y": 200, "path": "15/101/200.webp", "bytes": 1}]


def test_fine_manifest_requires_provenance_and_switch_metadata() -> None:
    manifest = {
        "effective_resolution_m": 4,
        "source_storage_resolution_m": 0.5,
        "presence_threshold": 0.2,
        "switch_zoom": 8,
        "tiles": [{"z": 15, "x": 1, "y": 2, "path": "15/1/2.webp", "bytes": 12}],
    }
    validate_fine_manifest(manifest)


def test_fine_manifest_requires_clear_source_and_published_tile_counts() -> None:
    manifest = {
        "effective_resolution_m": 4,
        "source_storage_resolution_m": 0.5,
        "presence_threshold": 0.2,
        "switch_zoom": 8,
        "source_raster_tile_count": 16,
        "published_web_tile_count": 1,
        "tiles": [{"z": 15, "x": 1, "y": 2, "path": "15/1/2.webp", "bytes": 12}],
    }
    validate_fine_manifest(manifest)

    manifest["published_web_tile_count"] = 2
    try:
        validate_fine_manifest(manifest)
    except ValueError as error:
        assert "published web tile count" in str(error)
    else:
        raise AssertionError("mismatched published tile count should fail")
