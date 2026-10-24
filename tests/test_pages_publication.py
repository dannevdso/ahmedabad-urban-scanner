from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.audit_pages_publication import audit_and_manifest


def make_site(tmp_path: Path) -> tuple[Path, Path, Path]:
    public = tmp_path / "public"
    dist = tmp_path / "dist"
    public.mkdir()
    dist.mkdir()

    policy = {
        "root_files": [".nojekyll", "CNAME", "da-za-logo.png"],
        "data_files": ["building-height-fine-manifest.json", "buildings.pmtiles"],
        "local_profile_files": ["centrality.fgb", "ndvi.tif"],
        "tile_manifest": "data/building-height-fine-manifest.json",
        "tile_root": "data/building-height-fine",
    }
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")

    files = {
        ".nojekyll": b"",
        "CNAME": b"ahd.da-za.com\n",
        "da-za-logo.png": b"png",
        "data/building-height-fine-manifest.json": json.dumps(
            {
                "published_web_tile_count": 1,
                "tiles": [{"path": "8/1/2.webp"}],
            }
        ).encode(),
        "data/building-height-fine/8/1/2.webp": b"webp",
        "data/buildings.pmtiles": b"pmtiles-binary",
        "data/local-profile/centrality.fgb": b"fgb-binary",
        "data/local-profile/ndvi.tif": b"tif-binary",
    }
    for relative, content in files.items():
        for root in (public, dist):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")
    (dist / "assets").mkdir()
    (dist / "assets/app.js").write_text("console.log('ok')", encoding="utf-8")
    return public, dist, policy_path


def test_audit_writes_complete_manifest_and_preserves_binaries(tmp_path: Path) -> None:
    public, dist, policy = make_site(tmp_path)
    result = audit_and_manifest(public, dist, policy, file_limit=1024, site_limit=100_000)

    manifest_path = dist / "publication-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    listed = {entry["path"] for entry in manifest["files"]}
    assert listed == {
        path.relative_to(dist).as_posix()
        for path in dist.rglob("*")
        if path.is_file() and path != manifest_path
    }
    assert manifest["manifest_self_excluded"] is True
    assert manifest["published_size_including_manifest"] == sum(
        path.stat().st_size for path in dist.rglob("*") if path.is_file()
    )
    assert result["file_count"] == len(listed)
    assert (dist / "data/buildings.pmtiles").read_bytes() == (public / "data/buildings.pmtiles").read_bytes()


def test_audit_rejects_unallowlisted_public_file(tmp_path: Path) -> None:
    public, dist, policy = make_site(tmp_path)
    (public / "data/private-source.gpkg").write_bytes(b"private")
    (dist / "data/private-source.gpkg").write_bytes(b"private")

    with pytest.raises(ValueError, match="allowlist mismatch"):
        audit_and_manifest(public, dist, policy, file_limit=1024, site_limit=100_000)


def test_audit_rejects_file_over_limit(tmp_path: Path) -> None:
    public, dist, policy = make_site(tmp_path)

    with pytest.raises(ValueError, match="above GitHub"):
        audit_and_manifest(public, dist, policy, file_limit=4, site_limit=100_000)
