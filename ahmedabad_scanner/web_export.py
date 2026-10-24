"""Prepare compact, evidence-labelled data for the static web scanner."""

from __future__ import annotations

import geopandas as gpd
import pandas as pd

WEB_COLUMNS: dict[str, tuple[str, int | None]] = {
    "building_id": ("id", None),
    "footprint_area_m2": ("area_m2", 1),
    "confidence": ("confidence", 3),
    "essential_categories_15min": ("categories_15min", None),
    "all_categories_15min": ("all_categories_15min", None),
    "network_snap_distance_m": ("network_snap_m", 1),
    "walk_health_min": ("health_min", 1),
    "walk_education_min": ("education_min", 1),
    "walk_food_min": ("food_min", 1),
    "walk_transport_min": ("transport_min", 1),
    "walk_green_min": ("green_min", 1),
    "walk_civic_min": ("civic_min", 1),
    "walk_culture_min": ("culture_min", 1),
    "walk_sport_min": ("sport_min", 1),
    "lst_c_100m_median": ("lst_c", 2),
    "ndvi_50m_median": ("ndvi", 3),
    "vegetation_fraction_50m": ("vegetation_fraction", 3),
    "heat_percentile_pilot": ("heat_percentile", 3),
    "greenery_percentile_pilot": ("greenery_percentile", 3),
    "heat_green_priority_pilot": ("heat_green_priority", 3),
    "environment_data_ok": ("environment_ok", None),
    "planx_compactness": ("planx_compactness", 3),
    "planx_convexity": ("planx_convexity", 3),
    "planx_elongation": ("planx_elongation", 3),
    "planx_cell_m2": ("planx_cell_m2", 1),
}


def quantile_breaks(series: pd.Series, *, classes: int = 9) -> list[float]:
    """Return ordered, unique quantile breaks for graduated map symbology."""
    if classes < 2:
        raise ValueError("Graduated symbology requires at least two classes")
    values = pd.Series(pd.to_numeric(series, errors="coerce"), index=series.index).dropna()
    if values.empty:
        return []
    quantiles = values.quantile([index / classes for index in range(1, classes)])
    breaks: list[float] = []
    for value in quantiles.tolist():
        rounded = round(float(value), 12)
        if not breaks or rounded > breaks[-1]:
            breaks.append(rounded)
    return breaks


CLASSIFICATION_PALETTES = {
    "viridis": ["#440154", "#482878", "#3e4989", "#31688e", "#26828e", "#35b779", "#fde725"],
    "inferno": ["#000004", "#320a5a", "#781c6d", "#bb3754", "#ed6925", "#fbb61a", "#fcffa4"],
    "heat": ["#ffffcc", "#ffeda0", "#feb24c", "#fd8d3c", "#f03b20", "#bd0026", "#800026"],
}
CATEGORY_PALETTES = {
    "viridis": ["#440154", "#482878", "#3e4989", "#31688e", "#26828e", "#1f9e89", "#35b779", "#6ece58", "#fde725"],
    "inferno": CLASSIFICATION_PALETTES["inferno"],
}


def classification_metadata(
    series: pd.Series,
    *,
    property_name: str,
    palette: str = "viridis",
    classes: int = 7,
) -> dict:
    """Describe deterministic classes for the values that will reach GeoJSON."""
    numeric = pd.to_numeric(series, errors="coerce")
    values = numeric.dropna().astype(float)
    colors = CLASSIFICATION_PALETTES[palette]
    unique = sorted(set(values.tolist()))
    result = {
        "property": property_name,
        "method": "constant" if len(unique) == 1 else "quantile",
        "breaks": [],
        "thresholds": [],
        "class_count": 1 if len(unique) == 1 else min(classes, len(colors)),
        "count": int(len(series)),
        "non_null_count": int(len(values)),
        "zero_count": int((values == 0).sum()),
        "unique_count": len(unique),
        "min": unique[0] if unique else None,
        "max": unique[-1] if unique else None,
        "palette": colors[:1] if len(unique) == 1 else colors,
        "display_precision": 12,
        "note": "Constant field; no variation." if len(unique) == 1 else "Up to seven quantile classes derived from published values; duplicate thresholds are removed.",
    }
    if not unique:
        result.update(method="no-data", class_count=0, palette=["#9ca3af"], note="No published numeric values.")
        return result
    if len(unique) == 1:
        result["value"] = unique[0]
        result["legend_entries"] = [{"label": _format_display_number(unique[0]), "color": result["palette"][0], "value": unique[0]}]
        return result
    if property_name == "connectivity":
        result.update(
            method="categorical",
            values=unique,
            breaks=[],
            thresholds=[],
            class_count=len(unique),
            palette=CATEGORY_PALETTES[palette][:len(unique)],
            note="Exact connectivity categories from published values.",
        )
        result["legend_entries"] = [
            {"label": _format_display_number(value), "color": color, "value": value}
            for value, color in zip(result["values"], result["palette"])
        ]
        return result
    breaks = quantile_breaks(values, classes=classes)
    breaks = [value for value in breaks if value > unique[0]]
    result["breaks"] = breaks
    result["thresholds"] = breaks
    result["class_count"] = len(breaks) + 1
    result["palette"] = colors[:result["class_count"]]
    result["note"] = f"Up to seven quantile classes derived from published values; {result['class_count']} effective classes after duplicate thresholds were removed."
    bounds = [result["min"], *breaks, result["max"]]
    result["legend_entries"] = [
        {
            "label": f"{_format_display_number(bounds[index])}–{'<' if index < len(bounds) - 2 else ''}{_format_display_number(bounds[index + 1])}",
            "color": color,
            "min": bounds[index],
            "max": bounds[index + 1],
        }
        for index, color in enumerate(result["palette"])
    ]
    return result


def _format_display_number(value: float | None) -> str:
    if value is None:
        return "No data"
    numeric = float(value)
    if numeric == 0:
        return "0"
    if abs(numeric) < 1e-12 or abs(numeric) >= 1e8:
        return f"{numeric:.6e}"
    if abs(numeric) < 1e-3:
        return f"{numeric:.12f}".rstrip("0").rstrip(".")
    return format(numeric, ".12g")


def natural_breaks(series: pd.Series, *, classes: int = 7, max_points: int = 2000) -> list[float]:
    """Return Fisher-Jenks-style natural-break lower bounds on a bounded sample."""
    if classes < 2:
        raise ValueError("Natural-break symbology requires at least two classes")
    values = pd.Series(pd.to_numeric(series, errors="coerce"), index=series.index).dropna()
    data = sorted({float(value) for value in values.tolist()})
    if not data:
        return []
    if len(data) > max_points:
        indices = [round(index * (len(data) - 1) / (max_points - 1)) for index in range(max_points)]
        data = [data[index] for index in indices]
    classes = min(classes, len(data))
    count = len(data)
    prefix = [0.0]
    prefix_sq = [0.0]
    for value in data:
        prefix.append(prefix[-1] + value)
        prefix_sq.append(prefix_sq[-1] + value * value)

    def segment_variance(start: int, end: int) -> float:
        size = end - start
        total = prefix[end] - prefix[start]
        total_sq = prefix_sq[end] - prefix_sq[start]
        return total_sq - (total * total / size)

    costs = [[float("inf")] * (count + 1) for _ in range(classes + 1)]
    starts = [[0] * (count + 1) for _ in range(classes + 1)]
    costs[0][0] = 0.0
    for class_count in range(1, classes + 1):
        for end in range(class_count, count + 1):
            for start in range(class_count - 1, end):
                candidate = costs[class_count - 1][start] + segment_variance(start, end)
                if candidate < costs[class_count][end]:
                    costs[class_count][end] = candidate
                    starts[class_count][end] = start

    boundaries = []
    end = count
    for class_count in range(classes, 1, -1):
        start = starts[class_count][end]
        boundaries.append(data[start])
        end = start
    return [data[0], *reversed(boundaries)]


def join_planx_building_metrics(
    buildings: gpd.GeoDataFrame,
    metrics: gpd.GeoDataFrame,
    tessellation: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """Attach selected descriptive PlanX fields to the canonical buildings."""
    for name, frame in (("buildings", buildings), ("metrics", metrics), ("tessellation", tessellation)):
        if "building_id" not in frame:
            raise ValueError(f"{name} is missing building_id")
        if frame["building_id"].duplicated().any():
            raise ValueError(f"{name} has duplicate building_id values")

    metric_columns = {
        "compact": "planx_compactness",
        "convexity": "planx_convexity",
        "elongation": "planx_elongation",
    }
    missing = set(metric_columns).difference(metrics.columns)
    if missing:
        raise ValueError(f"PlanX building metrics missing columns: {sorted(missing)}")
    if "cell_m2" not in tessellation:
        raise ValueError("PlanX tessellation is missing cell_m2")

    building_ids = set(buildings["building_id"].astype(str))
    metric_id = "source_building_id" if (
        "source_building_id" in metrics
        and set(metrics["source_building_id"].astype(str)) == building_ids
    ) else "building_id"
    tessellation_id = "source_building_id" if (
        "source_building_id" in tessellation
        and set(tessellation["source_building_id"].astype(str)) == building_ids
    ) else "building_id"

    output = buildings.merge(
        metrics[[metric_id, *metric_columns]].rename(
            columns={metric_id: "building_id", **metric_columns}
        ),
        on="building_id",
        how="left",
        validate="one_to_one",
    )
    output = output.merge(
        tessellation[[tessellation_id, "cell_m2"]].rename(
            columns={tessellation_id: "building_id", "cell_m2": "planx_cell_m2"}
        ),
        on="building_id",
        how="left",
        validate="one_to_one",
    )
    return gpd.GeoDataFrame(output, geometry=buildings.geometry.name, crs=buildings.crs)


def prepare_web_buildings(
    buildings: gpd.GeoDataFrame,
    *,
    simplify_tolerance_m: float = 0.5,
) -> gpd.GeoDataFrame:
    """Select, rename, round, simplify, and project building data for GeoJSON."""
    if buildings.crs is None:
        raise ValueError("Building data must have a CRS")

    output = buildings.copy()
    for column in WEB_COLUMNS:
        if column not in output.columns:
            output[column] = None
    output = output[list(WEB_COLUMNS) + [buildings.geometry.name]].copy()
    if output.crs.is_geographic:
        metric = output.to_crs(output.estimate_utm_crs())
    else:
        metric = output
    metric.geometry = metric.geometry.simplify(simplify_tolerance_m, preserve_topology=True)
    output = metric.to_crs("EPSG:4326")

    output = output.rename(columns={source: target for source, (target, _) in WEB_COLUMNS.items()})
    for _, (target, decimals) in WEB_COLUMNS.items():
        if decimals is not None:
            output[target] = pd.to_numeric(output[target], errors="coerce").round(decimals)
        output[target] = output[target].astype(object).where(output[target].notna(), None)
    output["environment_ok"] = output["environment_ok"].map(
        lambda value: bool(value) if value is not None else None
    ).astype(object)
    output["all_categories_15min"] = output["all_categories_15min"].map(
        lambda value: bool(value) if value is not None else None
    ).astype(object)
    return output


def prepare_web_raw_buildings(
    buildings: gpd.GeoDataFrame,
    *,
    simplify_tolerance_m: float = 0.5,
) -> gpd.GeoDataFrame:
    """Prepare raw Open Buildings footprints without analytical joins."""
    required = {"area_in_meters", "confidence", "full_plus_code"}
    missing = required.difference(buildings.columns)
    if missing:
        raise ValueError(f"Open Buildings data missing columns: {sorted(missing)}")
    output = buildings.copy()
    output["building_id"] = output["full_plus_code"].astype(str)
    output["footprint_area_m2"] = pd.to_numeric(output["area_in_meters"], errors="coerce").round(1)
    output["confidence"] = pd.to_numeric(output["confidence"], errors="coerce").round(3)
    output = output[["building_id", "full_plus_code", "footprint_area_m2", "confidence", buildings.geometry.name]].copy()
    metric = output.to_crs(output.estimate_utm_crs()) if output.crs.is_geographic else output
    metric.geometry = metric.geometry.simplify(simplify_tolerance_m, preserve_topology=True)
    return metric.to_crs("EPSG:4326")


def prepare_web_streets(
    edges: gpd.GeoDataFrame,
    *,
    simplify_tolerance_m: float = 0.5,
) -> gpd.GeoDataFrame:
    """Deduplicate directed walk edges and prepare compact WGS84 street lines."""
    if edges.crs is None:
        raise ValueError("Street data must have a CRS")
    required = {"u", "v", "key"}
    missing = required.difference(edges.columns)
    if missing:
        raise ValueError(f"Street data missing required columns: {sorted(missing)}")

    output = edges.copy()
    output["_undirected_id"] = [
        (*sorted((str(u), str(v))), str(key))
        for u, v, key in output[["u", "v", "key"]].itertuples(index=False, name=None)
    ]
    output = output.drop_duplicates("_undirected_id").copy()
    if output.crs.is_geographic:
        output = output.to_crs(output.estimate_utm_crs())
    output.geometry = output.geometry.simplify(simplify_tolerance_m, preserve_topology=True)
    return output[[output.geometry.name]].to_crs("EPSG:4326").reset_index(drop=True)


def prepare_web_space_syntax(
    frame: gpd.GeoDataFrame,
    *,
    simplify_tolerance_m: float = 0.5,
) -> gpd.GeoDataFrame:
    """Prepare clipped external PlanX space-syntax fields without renaming their meaning."""
    fields = {
        "seg_id": ("segment_id", None),
        "connectivity": ("connectivity", None),
        "betw_edge": ("betweenness", 3),
        "clo_mean": ("closeness", 12),
        "str_mean": ("straightness", 3),
        "NC_400": ("nc_400", 3),
        "NC_2500": ("nc_2500", 3),
        "TD_400": ("td_400", 3),
        "MD_400": ("md_400", 3),
        "NAIN_400": ("nain_400", 3),
        "CH_400": ("ch_400", 3),
        "NACH_400": ("nach_400", 3),
        "TD_2500": ("td_2500", 3),
        "MD_2500": ("md_2500", 3),
        "NAIN_2500": ("nain_2500", 3),
        "CH_2500": ("ch_2500", 3),
        "NACH_2500": ("nach_2500", 3),
        "clipped_length_m": ("clipped_length_m", 1),
    }
    return prepare_web_vector_layer(frame, fields, simplify_tolerance_m=simplify_tolerance_m)


def prepare_web_space_syntax_points(
    frame: gpd.GeoDataFrame,
    *,
    simplify_tolerance_m: float = 0.5,
) -> gpd.GeoDataFrame:
    """Prepare segment midpoints for the manual's point-based betweenness renderer."""
    points = frame.copy()
    points.geometry = points.geometry.interpolate(0.5, normalized=True)
    return prepare_web_space_syntax(points, simplify_tolerance_m=simplify_tolerance_m)


def prepare_web_vector_layer(
    frame: gpd.GeoDataFrame,
    fields: dict[str, tuple[str, int | None]],
    *,
    simplify_tolerance_m: float = 0.5,
) -> gpd.GeoDataFrame:
    """Select public fields, round values, simplify, and project a web layer."""
    if frame.crs is None:
        raise ValueError("Web vector layer must have a CRS")
    missing = set(fields).difference(frame.columns)
    if missing:
        raise ValueError(f"Web vector layer missing columns: {sorted(missing)}")
    output = frame[[*fields, frame.geometry.name]].copy()
    if output.crs.is_geographic:
        output = output.to_crs(output.estimate_utm_crs())
    output.geometry = output.geometry.simplify(simplify_tolerance_m, preserve_topology=True)
    output = output.to_crs("EPSG:4326").rename(
        columns={source: target for source, (target, _) in fields.items()}
    )
    for _, (target, decimals) in fields.items():
        if decimals is not None:
            output[target] = pd.to_numeric(output[target], errors="coerce").round(decimals)
        output[target] = output[target].astype(object).where(output[target].notna(), None)
    return output.reset_index(drop=True)
