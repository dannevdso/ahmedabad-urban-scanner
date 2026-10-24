from pathlib import Path


def test_web_surface_contains_no_removed_overlay_name():
    root = Path(__file__).parents[1]
    removed_name = "crit" + "icality"
    paths = [root / "web" / "index.html", root / "web" / "src", root / "web" / "public", root / "web" / "dist"]
    offenders = []
    for path in paths:
        if path.is_file():
            candidates = [path]
        elif path.exists():
            candidates = [item for item in path.rglob("*") if item.is_file() and item.suffix in {".html", ".js", ".json", ".geojson", ".css"}]
        else:
            candidates = []
        for candidate in candidates:
            if removed_name in candidate.read_text(errors="ignore"):
                offenders.append(str(candidate.relative_to(root)))
    assert offenders == []