#!/usr/bin/env python3
"""Audit the Vite output and write a deterministic GitHub Pages manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import re
import sys
from pathlib import Path, PurePosixPath

GITHUB_FILE_LIMIT = 100 * 1024 * 1024
GITHUB_PAGES_LIMIT = 1024 * 1024 * 1024
BINARY_EXTENSIONS = {".fgb", ".pmtiles", ".tif", ".tiff"}
DENIED_PARTS = {
    ".env",
    ".git",
    ".venv",
    "__pycache__",
    "archive",
    "archives",
    "backup",
    "backups",
    "cache",
    "credentials",
    "node_modules",
    "output",
    "outputs",
    "prototype",
    "prototypes",
    "rollback",
    "rollbacks",
    "tmp",
    "temp",
}
DENIED_SUFFIXES = {".bak", ".key", ".pem", ".pfx", ".tmp"}
SECRET_PATTERNS = {
    "local home-directory path": re.compile(rb"(?:/Users/[^/\s\"']+|/home/[^/\s\"']+)/"),
    "private key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "GitHub token": re.compile(rb"(?:ghp|github_pat)_[A-Za-z0-9_]{20,}"),
    "AWS access key": re.compile(rb"AKIA[0-9A-Z]{16}"),
    "Google API key": re.compile(rb"AIza[0-9A-Za-z_-]{30,}"),
}
MIME_OVERRIDES = {
    ".fgb": "application/flatgeobuf",
    ".geojson": "application/geo+json",
    ".json": "application/json",
    ".pmtiles": "application/octet-stream",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".webp": "image/webp",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def content_type(path: Path) -> str:
    return MIME_OVERRIDES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def load_expected_public_files(public_dir: Path, policy_path: Path) -> set[str]:
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    expected = set(policy["root_files"])
    expected.update(f"data/{name}" for name in policy["data_files"])
    expected.update(f"data/local-profile/{name}" for name in policy["local_profile_files"])

    tile_manifest_path = public_dir / policy["tile_manifest"]
    tile_manifest = json.loads(tile_manifest_path.read_text(encoding="utf-8"))
    tile_paths = [entry["path"] for entry in tile_manifest.get("tiles", [])]
    declared_count = tile_manifest.get("published_web_tile_count")
    if declared_count != len(tile_paths):
        raise ValueError(
            f"Tile manifest declares {declared_count} files but lists {len(tile_paths)}"
        )
    if len(tile_paths) != len(set(tile_paths)):
        raise ValueError("Tile manifest contains duplicate paths")
    expected.update(f"{policy['tile_root']}/{path}" for path in tile_paths)
    return expected


def relative_files(root: Path, excluded: set[str] | None = None) -> dict[str, Path]:
    excluded = excluded or set()
    return {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if path.is_file() and path.relative_to(root).as_posix() not in excluded
    }


def validate_safe_path(relative: str) -> None:
    path = PurePosixPath(relative)
    lowered_parts = {part.lower() for part in path.parts}
    if lowered_parts & DENIED_PARTS:
        raise ValueError(f"Denied publication path: {relative}")
    if path.suffix.lower() in DENIED_SUFFIXES or path.name.lower().endswith("~"):
        raise ValueError(f"Denied publication file: {relative}")
    if path.name in {".DS_Store", "Thumbs.db"}:
        raise ValueError(f"Temporary OS file in publication: {relative}")


def scan_for_secrets(path: Path, relative: str) -> None:
    if path.suffix.lower() not in {".css", ".html", ".js", ".json", ".txt", ".xml"}:
        return
    with path.open("rb") as stream:
        data = stream.read()
    for label, pattern in SECRET_PATTERNS.items():
        if pattern.search(data):
            raise ValueError(f"Possible {label} found in {relative}")


def audit_and_manifest(
    public_dir: Path,
    dist_dir: Path,
    policy_path: Path,
    manifest_name: str = "publication-manifest.json",
    file_limit: int = GITHUB_FILE_LIMIT,
    site_limit: int = GITHUB_PAGES_LIMIT,
) -> dict:
    expected_public = load_expected_public_files(public_dir, policy_path)
    actual_public = relative_files(public_dir)
    missing_public = sorted(expected_public - actual_public.keys())
    unexpected_public = sorted(actual_public.keys() - expected_public)
    if missing_public or unexpected_public:
        raise ValueError(
            "Publication allowlist mismatch. "
            f"Missing: {missing_public[:20]}; unexpected: {unexpected_public[:20]}"
        )

    dist_files = relative_files(dist_dir, {manifest_name})
    missing_dist = sorted(expected_public - dist_files.keys())
    if missing_dist:
        raise ValueError(f"Vite output is missing public assets: {missing_dist[:20]}")

    generated = set(dist_files) - expected_public
    invalid_generated = sorted(
        path for path in generated
        if path != "index.html"
        and not (
            path.startswith("assets/")
            and PurePosixPath(path).suffix in {".css", ".js", ".map", ".mjs", ".wasm"}
        )
    )
    if invalid_generated:
        raise ValueError(f"Unexpected generated Vite files: {invalid_generated[:20]}")

    entries = []
    total_size = 0
    for relative, path in sorted(dist_files.items()):
        validate_safe_path(relative)
        size = path.stat().st_size
        if size > file_limit:
            raise ValueError(
                f"{relative} is {size} bytes, above GitHub's {file_limit}-byte file limit"
            )
        scan_for_secrets(path, relative)
        digest = sha256(path)
        entries.append(
            {
                "path": relative,
                "size": size,
                "content_type": content_type(path),
                "sha256": digest,
            }
        )
        total_size += size

        source = public_dir / relative
        if source.is_file() and source.suffix.lower() in BINARY_EXTENSIONS:
            source_digest = sha256(source)
            if source_digest != digest:
                raise ValueError(f"Binary content changed during build: {relative}")

    result = {
        "manifest_version": "github-pages-publication.v1",
        "site": "Ahmedabad Urban Scanner",
        "custom_domain": "ahd.da-za.com",
        "manifest_self_excluded": True,
        "manifest_note": "This file cannot include its own SHA-256; every other published file is listed.",
        "file_count": len(entries),
        "total_size": total_size,
        "limits": {
            "per_file_bytes": file_limit,
            "published_site_bytes": site_limit,
        },
        "files": entries,
    }
    manifest_path = dist_dir / manifest_name
    previous_size = -1
    for _ in range(8):
        manifest_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest_size = manifest_path.stat().st_size
        result["manifest_size"] = manifest_size
        result["published_size_including_manifest"] = total_size + manifest_size
        if manifest_size == previous_size:
            break
        previous_size = manifest_size
    manifest_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    final_total = total_size + manifest_path.stat().st_size
    result["manifest_size"] = manifest_path.stat().st_size
    result["published_size_including_manifest"] = final_total
    if final_total > site_limit:
        manifest_path.unlink(missing_ok=True)
        raise ValueError(
            f"Published site is {final_total} bytes, above GitHub Pages' {site_limit}-byte limit"
        )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--public", type=Path, default=Path("web/public"))
    parser.add_argument("--dist", type=Path, default=Path("web/dist"))
    parser.add_argument("--policy", type=Path, default=Path("web/pages-publication-assets.json"))
    parser.add_argument("--manifest-name", default="publication-manifest.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = audit_and_manifest(
            args.public.resolve(),
            args.dist.resolve(),
            args.policy.resolve(),
            args.manifest_name,
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"publication audit failed: {error}", file=sys.stderr)
        return 1
    mib = result["published_size_including_manifest"] / (1024 * 1024)
    print(
        f"publication audit passed: {result['file_count'] + 1} files, "
        f"{result['published_size_including_manifest']} bytes ({mib:.2f} MiB)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
