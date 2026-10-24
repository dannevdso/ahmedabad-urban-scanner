from __future__ import annotations

import geopandas as gpd
from shapely.geometry import LineString, box

from ahmedabad_scanner.space_syntax import clip_space_syntax_to_boundary


def test_clip_space_syntax_keeps_inside_and_clips_crossing_segments() -> None:
    syntax = gpd.GeoDataFrame(
        {"seg_id": [1, 2, 3], "NC_400": [10, 20, 30]},
        geometry=[
            LineString([(0.25, 1), (0.75, 1)]),
            LineString([(-1, 1), (2, 1)]),
            LineString([(-2, -2), (-1, -1)]),
        ],
        crs="EPSG:32643",
    )
    boundary = gpd.GeoDataFrame(geometry=[box(0, 0, 1, 2)], crs="EPSG:32643")

    result = clip_space_syntax_to_boundary(syntax, boundary)

    assert result["seg_id"].tolist() == [1, 2]
    assert result.loc[result["seg_id"] == 1, "geometry"].iloc[0].equals(syntax.geometry.iloc[0])
    assert result.loc[result["seg_id"] == 2, "geometry"].iloc[0].equals(
        LineString([(0, 1), (1, 1)])
    )
    assert result.crs.to_epsg() == 32643
