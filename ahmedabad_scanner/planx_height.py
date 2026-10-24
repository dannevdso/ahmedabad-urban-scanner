"""PlanX height-input requirements and source auditing."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd


@dataclass(frozen=True)
class HeightRequirement:
    stage: str
    height_dependency: str
    input_schema: str
    units: str
    current_status: str
    safe_action: str


HEIGHT_REQUIREMENTS = (
    HeightRequirement(
        "heatriskgrid", "direct building height field (optional in plugin; required for height-aware result)",
        "BUILDINGS: polygon layer; HEIGHT_FIELD: numeric field on BUILDINGS",
        "metres; H_REF is metres",
        "blocked", "do not run height-aware variant until coverage and units are verified",
    ),
    HeightRequirement(
        "frontalarea", "direct building height field (plugin also permits a default)",
        "BUILDINGS: polygon layer; HEIGHT_FIELD: numeric field, or DEFAULT_HEIGHT",
        "metres; DEFAULT_HEIGHT is metres",
        "blocked", "do not use DEFAULT_HEIGHT as observed data; require a verified field",
    ),
    HeightRequirement(
        "spacematrix", "floor count, not height; separate height-adjacent stage",
        "BUILDINGS: polygons; LEVELS_FIELD: numeric field; BLOCKS: polygon layer",
        "floor count (dimensionless); DEFAULT_LEVELS is a modelling constant",
        "blocked for observed levels", "run only with verified building:levels or a documented modelling assumption",
    ),
    HeightRequirement(
        "shadowcasting", "DSM raster containing terrain plus building elevations",
        "DSM: raster band 1; projected CRS; numeric elevation surface",
        "elevation and pixel size in metres; UTC_OFFSET in hours",
        "blocked", "requires verified height-bearing DSM and terrain baseline",
    ),
    HeightRequirement(
        "sunhours", "DSM raster containing terrain plus building elevations",
        "DSM: raster band 1; projected CRS; numeric elevation surface",
        "elevation and pixel size in metres; output hours",
        "blocked", "requires verified height-bearing DSM and terrain baseline",
    ),
    HeightRequirement(
        "solarirradiation", "DSM raster containing terrain plus building elevations",
        "DSM: raster band 1; projected CRS; numeric elevation surface",
        "elevation and pixel size in metres; output kWh/m2 per day",
        "blocked", "requires verified height-bearing DSM and terrain baseline",
    ),
    HeightRequirement(
        "annualsolar", "DSM raster containing terrain plus building elevations",
        "DSM: raster band 1; projected CRS; numeric elevation surface",
        "elevation and pixel size in metres; output kWh/m2/yr",
        "blocked", "requires verified height-bearing DSM and terrain baseline",
    ),
    HeightRequirement(
        "skyviewfactor", "DSM raster containing terrain plus building elevations",
        "DSM: raster band 1; projected CRS; numeric elevation surface",
        "elevation and pixel size/radius in metres; output 0–1",
        "blocked", "requires verified height-bearing DSM and terrain baseline",
    ),
    HeightRequirement(
        "viewshed", "DSM raster; observer/target offsets are separate parameters",
        "DSM raster plus OBSERVERS point layer",
        "DSM elevation, observer height and target height in metres; radius in map units",
        "blocked", "requires verified height-bearing DSM",
    ),
    HeightRequirement(
        "visualexposure", "DSM raster; optional landmark extra height",
        "DSM raster plus LANDMARKS polygon layer",
        "DSM elevation and EXTRA_HEIGHT/EYE_HEIGHT in metres; sample step/radius in map units",
        "blocked", "requires verified height-bearing DSM",
    ),
    HeightRequirement(
        "isovistfield", "none; 2-D footprint obstruction only",
        "BUILDINGS: polygon layer in projected CRS",
        "CELL and MAX_DIST in map units; outputs area/perimeter/radii in map units",
        "available", "safe independent pilot candidate; no building heights are consumed",
    ),
)


def _numeric_coverage(frame: gpd.GeoDataFrame, field: str) -> dict[str, Any]:
    values = pd.Series(frame[field].to_numpy())
    numeric = values.astype(str).str.extract(r"([-+]?\d+(?:[.,]\d+)?)", expand=False).str.replace(",", ".", regex=False)
    numbers = pd.to_numeric(numeric, errors="coerce")
    valid = numbers.notna()
    return {
        "field": field,
        "non_null": int(values.notna().sum()),
        "numeric_parseable": int(valid.sum()),
        "positive": int((numbers[valid] > 0).sum()) if int(valid.sum()) else 0,
        "sample_raw": [str(v) for v in values.dropna().head(5).tolist()],
    }


def audit_sources(osm_path: Path, planx_inputs: Path) -> dict[str, Any]:
    polygons = gpd.read_file(osm_path, layer="polygons")
    buildings = gpd.read_file(planx_inputs, layer="buildings")
    osm_buildings = polygons[polygons["building"].notna()].copy()
    return {
        "osm_source": str(osm_path),
        "planx_buildings": str(planx_inputs),
        "osm_polygon_rows": int(len(polygons)),
        "osm_building_polygon_rows": int(len(osm_buildings)),
        "osm_height_fields": {
            "height": _numeric_coverage(osm_buildings, "height"),
            "building:levels": _numeric_coverage(osm_buildings, "building:levels"),
        },
        "planx_building_rows": int(len(buildings)),
        "planx_building_columns": [str(c) for c in buildings.columns],
        "planx_height_columns": [str(c) for c in buildings.columns if "height" in str(c).lower() or "level" in str(c).lower()],
        "current_verdict": "blocked",
        "missing_prerequisite": [
            "A verified building-height field joined to the exact current PlanX buildings layer, with numeric metres and documented source/provenance.",
            "A terrain elevation baseline (DEM) in a projected metric CRS if shadow/solar/visibility outputs are to be called DSM-based rather than flat-ground proxies.",
        ],
    }


def requirements_as_dicts() -> list[dict[str, str]]:
    return [asdict(item) for item in HEIGHT_REQUIREMENTS]
