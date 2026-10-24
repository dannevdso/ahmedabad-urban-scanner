from __future__ import annotations

from pathlib import Path

import geopandas as gpd
from shapely.geometry import box

from scripts.audit_inputs import audit_layer


def test_audit_layer_reads_geoparquet(tmp_path: Path) -> None:
    path = tmp_path / "buildings.parquet"
    gpd.GeoDataFrame(
        {"building_id": ["one"]},
        geometry=[box(72.55, 23.02, 72.5502, 23.0202)],
        crs="EPSG:4326",
    ).to_parquet(path)

    result = audit_layer(
        path,
        (72.5443429, 23.0159998, 72.5843429, 23.0559998),
    )

    assert result["rows"] == 1
    assert result["intersects_study_bbox_rows"] == 1
