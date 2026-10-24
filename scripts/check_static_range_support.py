#!/usr/bin/env python3
"""Verify HTTP byte-range behavior required by static geospatial readers."""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_ASSETS = (
    "data/buildings.pmtiles",
    "data/local-profile/centrality.fgb",
    "data/local-profile/ndvi.tif",
)


def check_range(base_url: str, relative_path: str, start: int = 0, end: int = 31) -> str:
    url = urllib.parse.urljoin(base_url.rstrip("/") + "/", relative_path)
    request = urllib.request.Request(
        url,
        headers={"Range": f"bytes={start}-{end}", "User-Agent": "ahmedabad-urban-scanner-range-check/1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read()
            status = response.status
            content_range = response.headers.get("Content-Range", "")
            accept_ranges = response.headers.get("Accept-Ranges", "")
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"{url}: HTTP {error.code}") from error
    expected_length = end - start + 1
    if status != 206:
        raise RuntimeError(f"{url}: expected HTTP 206, received {status}")
    if not content_range.lower().startswith(f"bytes {start}-{end}/"):
        raise RuntimeError(f"{url}: invalid Content-Range {content_range!r}")
    if len(body) != expected_length:
        raise RuntimeError(f"{url}: expected {expected_length} bytes, received {len(body)}")
    if accept_ranges and accept_ranges.lower() != "bytes":
        raise RuntimeError(f"{url}: unexpected Accept-Ranges {accept_ranges!r}")
    return f"PASS {relative_path}: 206, {content_range}, {len(body)} bytes"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url")
    parser.add_argument("assets", nargs="*", default=DEFAULT_ASSETS)
    args = parser.parse_args()
    failures = []
    for asset in args.assets:
        try:
            print(check_range(args.base_url, asset))
        except (OSError, RuntimeError) as error:
            failures.append(str(error))
    if failures:
        for failure in failures:
            print(f"FAIL {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
