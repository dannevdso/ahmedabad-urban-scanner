from __future__ import annotations

import geopandas as gpd


def clip_space_syntax_to_boundary(
    syntax: gpd.GeoDataFrame, boundary: gpd.GeoDataFrame
) -> gpd.GeoDataFrame:
    """Clip space-syntax segments to a study boundary."""
    if syntax.crs is None or boundary.crs is None:
        raise ValueError("Both space-syntax and boundary layers require a CRS")
    if syntax.empty or boundary.empty:
        return syntax.iloc[0:0].copy()

    boundary_geometry = boundary.to_crs(syntax.crs).geometry.union_all()
    clipped = syntax.copy()
    clipped["geometry"] = clipped.geometry.intersection(boundary_geometry)
    clipped = clipped.loc[~clipped.geometry.is_empty].copy()
    if clipped.empty:
        return clipped.reset_index(drop=True)

    clipped = clipped.explode(index_parts=False, ignore_index=True)
    clipped = clipped.loc[clipped.geom_type.isin(["LineString", "MultiLineString"])].copy()
    return clipped.reset_index(drop=True)
