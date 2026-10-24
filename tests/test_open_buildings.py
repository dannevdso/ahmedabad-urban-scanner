from __future__ import annotations

import gzip
from pathlib import Path

from ahmedabad_scanner.open_buildings import (
    load_open_buildings_bbox,
    s2_tokens_for_bbox,
)


def test_s2_tokens_for_bbox_returns_ahmedabad_level_6_cell() -> None:
    tokens = s2_tokens_for_bbox(
        (72.5443429, 23.0159998, 72.5843429, 23.0559998),
        level=6,
    )

    assert tokens == ["395f"]


def test_load_open_buildings_bbox_filters_centroids_before_parsing(tmp_path: Path) -> None:
    source_path = tmp_path / "buildings.csv.gz"
    rows = [
        '23.02,72.55,400,0.91,"POLYGON ((72.55 23.02, 72.5502 23.02, 72.5502 23.0202, 72.55 23.0202, 72.55 23.02))",7JMM2H92+22\n',
        '23.10,72.70,400,0.95,"POLYGON ((72.7 23.1, 72.7002 23.1, 72.7002 23.1002, 72.7 23.1002, 72.7 23.1))",7JMM4P22+22\n',
    ]
    with gzip.open(source_path, "wt") as file:
        file.writelines(rows)

    result = load_open_buildings_bbox(
        [source_path],
        bbox=(72.5443429, 23.0159998, 72.5843429, 23.0559998),
        chunk_size=1,
    )

    assert result["full_plus_code"].tolist() == ["7JMM2H92+22"]
    assert result.crs.to_string() == "EPSG:4326"
