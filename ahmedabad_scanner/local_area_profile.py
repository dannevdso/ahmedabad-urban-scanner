"""Audited local-area profile calculations and the ``local-area-profile.v1`` contract."""
from __future__ import annotations

from collections import defaultdict
from math import ceil, pi
from typing import Iterable

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point

PROFILE_RADII_M = (400, 800, 1200)
FLOOD_RISK_CLASSES = (
    ("veryHigh", "Very high", "Very High Risk Areas"),
    ("high", "High", "High Risk Areas"),
    ("moderate", "Moderate", "Moderate Risk Areas"),
    ("low", "Low", None),
)
SECTION_KEYS = ("overview", "buildings", "streetsConnectivity", "spaceSyntaxCentrality", "environment", "publicTransport", "parksEducation", "availability", "methods")
FIXED_CLASS_METADATA = {
    "building_count": {"method": "fixed", "bins": [0, 25, 100, 250, 500, 1000, 2500]},
    "footprint_area_m2": {"method": "fixed", "bins": [0, 25, 100, 250, 500, 1000, 5000]},
    "street_length_km": {"method": "fixed", "bins": [0, 1, 3, 5, 10, 20, 50]},
    "intersection_density_per_km2": {"method": "fixed", "bins": [0, 5, 10, 20, 40, 80]},
    "public_transport_stops": {"method": "fixed", "bins": [0, 1, 3, 5, 10, 25]},
}
BUILDING_LOCATION_BINS = {
    "provisionalHeightM": [0, 3, 6, 10, 20, 50, 100],
    "provisionalAreaM2": [0, 25, 100, 250, 500, 1000, 5000],
    "derivedVolumeM3": [0, 100, 500, 2000, 10000, 50000, 250000],
}
SUHI_CATEGORIES = (
    ("low", "Low"),
    ("moderate", "Moderate"),
    ("high", "High"),
    ("veryHigh", "Very High"),
    ("extremeHigh", "Extreme High"),
)
LOCAL_AREA_PROFILE_SCHEMA = {
    "contractVersion": "local-area-profile.v1",
    "selection": {"center": "[x, y]", "radiusM": list(PROFILE_RADII_M), "types": ["circle", "tps"], "tps": {"source_id": "internal feature identifier", "tps_name": "human identifier", "tps_no": "human identifier", "tps_status": "context"}},
    "sections": list(SECTION_KEYS),
    "multiRadiusWrapper": "local-area-profiles.v1",
    "buildingFootprintField": "footprint_area_m2 preferred; geometry.area fallback",
    "streetTopology": "authoritative u/v or node identifiers; clip-created boundary points excluded",
    "histograms": FIXED_CLASS_METADATA,
}


def _availability(available: int, denominator: int) -> dict:
    return {"available": int(available), "denominator": int(denominator)}


def _unavailable(reason: str, denominator: int = 0) -> dict:
    return {"status": "unavailable", "data": None, "availability": _availability(0, denominator), "reason": reason}


def _section(data, *, source=None, provenance=None, warnings=None, availability=None) -> dict:
    return {"status": "available", "data": data, "availability": availability or _availability(1, 1), "source": source, "provenance": provenance, "warnings": list(warnings or [])}


def _summary(values: Iterable[object], bins: list[float] | None = None) -> dict:
    numeric = pd.to_numeric(pd.Series(list(values)), errors="coerce")
    array = np.asarray(numeric, dtype=float)
    series = pd.Series(array[np.isfinite(array)])
    def histogram() -> dict:
        if not bins:
            return {"bins": [], "counts": [], "method": "fixed", "interval": "left_closed_right_open_except_last", "underflowCount": 0, "overflowCount": 0, "totalCount": int(len(series))}
        edges = np.asarray(bins, dtype=float)
        counts = np.histogram(series.to_numpy(dtype=float), bins=edges)[0].astype(int).tolist() if not series.empty else [0] * (len(bins) - 1)
        return {"bins": bins, "counts": counts, "method": "fixed", "interval": "left_closed_right_open_except_last", "underflowCount": int((series < edges[0]).sum()), "overflowCount": int((series > edges[-1]).sum()), "totalCount": int(len(series))}
    if series.empty:
        result = {key: None for key in ("mean", "median", "min", "max", "std")}
        result["histogram"] = histogram()
        return result
    result = {"mean": round(float(series.mean()), 6), "median": round(float(series.median()), 6), "min": round(float(series.min()), 6), "max": round(float(series.max()), 6), "std": round(float(series.std(ddof=0)), 6)}
    if bins:
        result["histogram"] = histogram()
    return result


def summarize_raster(values, *, mask=None, expected_cell_count: int | None = None, bins: list[float] | None = None) -> dict:
    """Summarize an in-memory raster/fixture without opening or running a raster."""
    array = np.ma.asarray(values)
    if mask is not None:
        array = np.ma.array(array, mask=np.ma.getmaskarray(array) | np.asarray(mask, dtype=bool))
    valid = np.asarray(array.compressed(), dtype=float)
    valid = valid[np.isfinite(valid)]
    denominator = int(expected_cell_count if expected_cell_count is not None else array.size)
    if not len(valid):
        return {"status": "unavailable", "reason": "no valid raster cells", "validCoveragePct": 0.0, "availability": _availability(0, denominator)}
    summary = _summary(valid.tolist(), bins)
    distribution = summary.pop("histogram", {"bins": [], "counts": []})
    return {"status": "available", **summary, "distribution": distribution, "validCoveragePct": round(100 * len(valid) / denominator, 6) if denominator else None, "availability": _availability(len(valid), denominator)}


def summarize_flood_risk_area(frame: gpd.GeoDataFrame | None, circle) -> dict:
    """Return unioned metric area by supplied flood-risk class inside ``circle``."""
    if frame is None:
        return {"status": "unavailable", "unit": "m²", "categories": [], "totalClassifiedAreaM2": None, "reason": "flood-risk source unavailable"}
    if "uf_risk" not in frame.columns:
        return {"status": "unavailable", "unit": "m²", "categories": [], "totalClassifiedAreaM2": None, "reason": "flood-risk source field uf_risk unavailable"}
    categories = []
    for key, label, source_class in FLOOD_RISK_CLASSES:
        selected = frame[frame["uf_risk"] == source_class] if source_class else frame.iloc[0:0]
        if selected.empty:
            area = None if source_class is None else 0.0
        else:
            clipped = selected.geometry.intersection(circle)
            nonempty = clipped[~clipped.is_empty]
            area = float(nonempty.union_all().area) if len(nonempty) else 0.0
        categories.append({"key": key, "label": label, "sourceClass": source_class, "areaM2": round(area, 3) if area is not None else None, "status": "unavailable" if area is None else "available"})
    total = round(sum(category["areaM2"] or 0.0 for category in categories), 3)
    return {"status": "available", "unit": "m²", "categories": categories, "totalClassifiedAreaM2": total, "caveat": "The supplied VEDAS/ISRO source has no Low risk class; Low is shown as Unavailable rather than zero."}


def profile_radii_m(center: Point, radii_m: Iterable[int] = PROFILE_RADII_M) -> list[dict]:
    if center.is_empty:
        raise ValueError("center must not be empty")
    result = []
    for radius in sorted({int(r) for r in radii_m}):
        if radius <= 0:
            raise ValueError("profile radii must be positive")
        circle = center.buffer(radius)
        result.append({"radius_m": radius, "geometry_type": circle.geom_type, "area_m2": round(float(circle.area), 3), "bounds": [round(float(v), 3) for v in circle.bounds]})
    return result


def _clip_frame(frame, circle):
    selected = frame[frame.geometry.intersects(circle)].copy()
    if selected.empty:
        return selected
    selected["geometry"] = selected.geometry.intersection(circle)
    return selected[~selected.geometry.is_empty & (selected.geometry.length > 0 if selected.geom_type.isin(["LineString", "MultiLineString"]).all() else True)].copy()


def summarize_length_weighted(frame: gpd.GeoDataFrame, fields: Iterable[str], weight_field: str = "length_m", circle=None) -> dict:
    """Clip line features first, then use clipped geometry length as weights."""
    work = frame.copy()
    if circle is not None:
        work = _clip_frame(work, circle)
        weights = work.geometry.length
        actual_weight_field = "clipped_geometry_length_m"
    elif weight_field in work:
        weights = pd.to_numeric(work[weight_field], errors="coerce")
        actual_weight_field = weight_field
    else:
        return {field: {"status": "unavailable", "availability": _availability(0, len(work)), "reason": f"missing {weight_field}"} for field in fields}
    result = {}
    for field in fields:
        if field not in work:
            result[field] = {"status": "unavailable", "availability": _availability(0, len(work)), "reason": f"missing {field}"}
            continue
        values = pd.to_numeric(work[field], errors="coerce")
        valid = values.notna() & weights.notna() & (weights > 0)
        total = float(weights[valid].sum())
        weighted = float((values[valid] * weights[valid]).sum() / total) if total else None
        result[field] = {"status": "available" if weighted is not None else "unavailable", "weighted_mean": round(weighted, 6) if weighted is not None else None, "weight_field": actual_weight_field, "weight_total": round(total, 6), "availability": _availability(int(valid.sum()), len(work))}
    return result


def _metric_frame(frame, crs):
    if frame is None:
        return None
    if frame.crs is None:
        raise ValueError("spatial inputs must declare a CRS")
    return frame.to_crs(crs)


def _building_summary(buildings, circle, *, exact_selection: bool = False):
    selected = buildings[buildings.geometry.intersects(circle) if exact_selection else buildings.geometry.centroid.within(circle)].copy()
    clipped = buildings.geometry.intersection(circle)
    nonempty = clipped[~clipped.is_empty]
    union_area = float(nonempty.union_all().area) if len(nonempty) else 0.0
    if "footprint_area_m2" in selected:
        area_values = selected["footprint_area_m2"]
        area_source = "footprint_area_m2"
    else:
        area_values = selected.geometry.area
        area_source = "geometry.area"
    data = {"buildingCount": int(len(selected)), "buildingInclusionRule": "exact_polygon_intersection" if exact_selection else "centroid_within_circle", "footprintAreaSource": area_source, "footprintCoverageM2": round(union_area, 3), "footprintCoveragePct": round(100 * union_area / circle.area, 6), "footprintAreaM2": _summary(area_values, FIXED_CLASS_METADATA["footprint_area_m2"]["bins"]), "buildingMetrics": {}}
    for source, public in (("compact", "compactness"), ("convexity", "convexity"), ("elongation", "elongation")):
        if source not in selected:
            data["buildingMetrics"][public] = {"status": "unavailable", "sourceField": source, "summary": _summary([]), "availability": _availability(0, len(selected)), "reason": f"missing {source}"}
        else:
            valid = selected[source].notna().sum()
            data["buildingMetrics"][public] = {"status": "available" if valid else "unavailable", "sourceField": source, "summary": _summary(selected[source]), "availability": _availability(int(valid), len(selected))}
    return data


def _building_location_summary(points, selection, selection_area_m2: float):
    """Summarize the published point analytical asset without treating Central nulls as zero."""
    selected = points[points.geometry.map(selection.covers)].copy()
    central = selected[selected["zone_group"] == "central"]
    enriched = selected[selected["zone_group"] == "enriched"]
    data = {
        "totalLocationCount": int(len(selected)),
        "centralLocationCount": int(len(central)),
        "enrichedLocationCount": int(len(enriched)),
        "buildingInclusionRule": "boundary_inclusive_point_coverage",
        "centralCountOnly": True,
    }
    for field, key, unit in (("height_m", "provisionalHeightM", "m"), ("area_m2", "provisionalAreaM2", "m²"), ("volume_m3", "derivedVolumeM3", "m³")):
        numeric = pd.to_numeric(enriched.get(field, pd.Series(dtype=float)), errors="coerce")
        valid = numeric[np.isfinite(numeric)]
        metric_summary = _summary(valid.tolist(), BUILDING_LOCATION_BINS[key])
        data[key] = {
            "status": "available" if len(valid) else "unavailable",
            "unit": unit,
            "summary": metric_summary,
            "distribution": metric_summary["histogram"],
            "availability": _availability(len(valid), len(enriched)),
            "reason": None if len(valid) else "no valid enriched values; Central is count-only",
        }
    suhi_categories = _summarize_suhi_categories(enriched.get("suhi", pd.Series(dtype=object)).tolist())
    data["suhi"] = {
        "status": "available" if suhi_categories["totalCount"] else "unavailable",
        "kind": "categorical",
        "unit": "unverified categorical class",
        "summary": {"dominantClass": suhi_categories["dominantClass"]},
        "distribution": {"categories": suhi_categories["categories"], "totalCount": suhi_categories["totalCount"]},
        "availability": _availability(suhi_categories["totalCount"], len(enriched)),
        "reason": None if suhi_categories["totalCount"] else "no valid enriched SUHI classes; Central is count-only",
    }
    area_values = pd.to_numeric(enriched.get("area_m2", pd.Series(dtype=float)), errors="coerce")
    valid_area = area_values[np.isfinite(area_values)]
    total_stored_area = float(valid_area.sum()) if len(valid_area) else None
    data["summedStoredAreaM2"] = total_stored_area
    data["storedAreaSharePct"] = round(100 * total_stored_area / selection_area_m2, 6) if total_stored_area is not None and selection_area_m2 else None
    data["storedAreaSelectionBasis"] = "point-selected stored area / exact selection area; not exact footprint-union coverage"
    return data


def _normalize_suhi_class(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split()).strip().casefold()
    if not normalized:
        return None
    if normalized.endswith(" suhi"):
        normalized = normalized[:-5].strip()
    return {
        "low": "Low",
        "moderate": "Moderate",
        "high": "High",
        "very high": "Very High",
        "extreme high": "Extreme High",
    }.get(normalized, "Other/unknown")


def _summarize_suhi_categories(values: Iterable[object]) -> dict:
    labels = [label for _, label in SUHI_CATEGORIES]
    counts = {label: 0 for label in labels}
    for value in values:
        normalized = _normalize_suhi_class(value)
        if normalized is not None:
            counts[normalized] = counts.get(normalized, 0) + 1
    categories = [{"key": key, "label": label, "count": counts[label]} for key, label in SUHI_CATEGORIES]
    if counts.get("Other/unknown", 0):
        categories.append({"key": "otherUnknown", "label": "Other/unknown", "count": counts["Other/unknown"]})
    total = sum(counts.values())
    dominant = next((label for label in labels + ["Other/unknown"] if counts.get(label, 0) and counts.get(label, 0) == max(counts.values(), default=0)), None)
    return {"categories": categories, "totalCount": total, "dominantClass": dominant}


def _street_summary(edges, circle):
    if edges is None:
        return _unavailable("street network source unavailable")
    ordered = edges.sort_values("seg_id", ascending=False, kind="stable") if "seg_id" in edges.columns else edges
    clipped = ordered[ordered.geometry.intersects(circle)].copy()
    clipped["geometry"] = clipped.geometry.intersection(circle)
    clipped = clipped[~clipped.geometry.is_empty & (clipped.geometry.length > 0)].copy()
    node_fields = ("u", "v") if {"u", "v"}.issubset(edges.columns) else (("source", "target") if {"source", "target"}.issubset(edges.columns) else None)
    if node_fields is None:
        return _unavailable("authoritative u/v or source/target topology unavailable", len(edges))
    coords = {}
    degrees = defaultdict(int)
    graph = defaultdict(set)
    # A simplified u/v identifier can occur on several prepared segments. Use
    # the endpoint from the lowest stable seg_id so bbox/read order cannot alter
    # topology counts between Python and browser range queries.
    for _, row in ordered.iterrows():
        for node, point in zip(node_fields, (row.geometry.coords[0], row.geometry.coords[-1])):
            coords[row[node]] = Point(point)
    for _, row in clipped.iterrows():
        u, v = row[node_fields[0]], row[node_fields[1]]
        if u in coords and coords[u].within(circle): degrees[u] += 1
        if v in coords and coords[v].within(circle): degrees[v] += 1
        graph[u].add(v); graph[v].add(u)
    nodes = {n for n, point in coords.items() if point.within(circle)}
    links = len(clipped)
    components = []
    unseen = set(nodes)
    while unseen:
        stack = [unseen.pop()]; comp = set(stack)
        while stack:
            for nxt in graph[stack.pop()] & unseen:
                unseen.remove(nxt); comp.add(nxt); stack.append(nxt)
        components.append(comp)
    connected_ratio = max(map(len, components), default=0) / len(nodes) if nodes else None
    area_km2 = circle.area / 1_000_000
    data = {"clippedLengthM": round(float(clipped.geometry.length.sum()), 3), "intersectionDensityPerKm2": round(sum(degrees[n] >= 3 for n in nodes) / area_km2, 6) if area_km2 else None, "linkNodeRatio": round(links / len(nodes), 6) if nodes else None, "connectedNodeRatio": round(connected_ratio, 6) if connected_ratio is not None else None, "nodeRule": "authoritative_u_v_only; clip-created boundary points excluded", "connectedNodeRule": "largest connected component nodes / authoritative nodes within circle"}
    return _section(data, availability=_availability(len(clipped), len(edges)))


def _transit_summary(stops, cells, circle):
    if stops is None:
        return _unavailable("GTFS stops unavailable")
    inside = stops[stops.geometry.within(circle)]
    if "route_ids" not in inside or cells is None or "route_ids" not in cells:
        return _unavailable("route-serving-stop relationship cannot be proven from supplied model", len(stops))
    routes = {str(route) for values in inside["route_ids"] for route in (values if isinstance(values, (list, tuple, set)) else [values]) if pd.notna(route)}
    if not routes:
        return _unavailable("route-serving-stop relationship cannot be proven from supplied model", len(stops))
    def route_set(value): return {str(x) for x in (value if isinstance(value, (list, tuple, set)) else [value]) if pd.notna(x)}
    selected = cells[cells["route_ids"].map(route_set).map(lambda values: bool(values & routes))]
    union = selected.geometry.union_all() if len(selected) else None
    served_inside = union.intersection(circle) if union is not None else None
    data = {"stopsInsideCircle": int(len(inside)), "routesServingStopsInsideCircle": sorted(routes), "routeReachCells": int(len(selected)), "routeReachCoveragePct": round(100 * served_inside.area / circle.area, 6) if served_inside is not None else 0.0, "routeSelectionRule": "cells whose route_ids intersect routes serving stops inside circle"}
    return _section(data, availability=_availability(len(inside), len(stops)))


def _overview_summary(buildings, streets, environment, transit):
    building_data = buildings.get("data") or {}
    street_data = streets.get("data") or {}
    environment_data = environment.get("data") or {}
    transit_data = transit.get("data") or {}
    vegetation = environment_data.get("vegetationFraction") or environment_data.get("vegetation_fraction") or {}
    routes = transit_data.get("routesServingStopsInsideCircle")
    return {
        "buildingCount": building_data.get("buildingCount"),
        "buildingFootprintCoveragePct": building_data.get("footprintCoveragePct"),
        "intersectionDensityPerKm2": street_data.get("intersectionDensityPerKm2"),
        "vegetationFractionMean": vegetation.get("mean") if isinstance(vegetation, dict) else None,
        "publicTransportStops": transit_data.get("stopsInsideCircle"),
        "directlyServingRoutes": len(routes) if isinstance(routes, list) else None,
    }


def build_local_area_profile(center: Point, *, radius_m: int = 400, buildings=None, street_edges=None, boundary=None, parks=None, schools=None, transit_stops=None, route_reach_cells=None, space_syntax=None, network_edges=None, environment_rasters=None, flood_risk_zones=None, radii_m=None, center_crs=None, sources=None, provenance=None, warnings=None, selection_geometry=None, selection_crs=None, selection_metadata=None) -> dict:
    """Build one explicit frontend selection. Use :func:`build_local_area_profiles` for multiple radii."""
    if radii_m is not None:
        values = sorted({int(r) for r in radii_m})
        if len(values) != 1:
            raise ValueError("build_local_area_profile accepts one radius; use build_local_area_profiles for multiple radii")
        radius_m = values[0]
    radius_m = int(radius_m)
    if radius_m <= 0: raise ValueError("radius_m must be positive")
    frames = [f for f in (buildings, street_edges, parks, schools, transit_stops, route_reach_cells, space_syntax, network_edges, flood_risk_zones) if f is not None]
    metric_crs = next((f.crs for f in frames if f.crs and not f.crs.is_geographic), None) or (frames[0].estimate_utm_crs() if frames else "EPSG:3857")
    source_center_crs = center_crs or (frames[0].crs if frames else metric_crs)
    center_metric = gpd.GeoSeries([center], crs=source_center_crs).to_crs(metric_crs).iloc[0] if str(source_center_crs) != str(metric_crs) else center
    converted = {name: _metric_frame(frame, metric_crs) for name, frame in (("buildings", buildings), ("street_edges", street_edges), ("parks", parks), ("schools", schools), ("transit_stops", transit_stops), ("route_reach_cells", route_reach_cells), ("space_syntax", space_syntax), ("network_edges", network_edges), ("flood_risk_zones", flood_risk_zones))}
    selection = (gpd.GeoSeries([selection_geometry], crs=selection_crs or source_center_crs).to_crs(metric_crs).iloc[0] if selection_geometry is not None and str(selection_crs or source_center_crs) != str(metric_crs) else selection_geometry) or center_metric.buffer(radius_m)
    is_tps = selection_geometry is not None
    selection_area_m2 = float(selection.area) if is_tps else pi * radius_m * radius_m
    if buildings is not None and {"zone_group", "height_m", "area_m2", "volume_m3", "suhi"}.issubset(buildings.columns):
        b = _section(_building_location_summary(converted["buildings"], selection, selection_area_m2), availability=_availability(1, 1))
    else:
        b = _section(_building_summary(converted["buildings"], selection, exact_selection=is_tps), availability=_availability(1, 1)) if buildings is not None else _unavailable("building source unavailable")
    s = _street_summary(converted["street_edges"], selection)
    syntax_data = summarize_length_weighted(converted["space_syntax"], ["betweenness", "closeness", "straightness"], circle=selection) if space_syntax is not None else None
    syntax = _section(syntax_data) if syntax_data is not None else _unavailable("space syntax source unavailable")
    env = {}
    for name, raster in (environment_rasters or {}).items(): env[name] = summarize_raster(raster)
    environment = _section(env) if env else _unavailable("environment raster summaries unavailable")
    flood_risk_area = summarize_flood_risk_area(converted["flood_risk_zones"], selection)
    if environment["status"] == "unavailable":
        environment = _section({"floodRiskArea": flood_risk_area}) if flood_risk_zones is not None else environment
    else:
        environment["data"]["floodRiskArea"] = flood_risk_area
    transit = _transit_summary(converted["transit_stops"], converted["route_reach_cells"], selection)
    point_data = {name: int(frame.geometry.map(selection.covers).sum()) for name, frame in (("parks", converted["parks"]), ("schools", converted["schools"])) if frame is not None}
    parks_education = _section(point_data) if point_data else _unavailable("parks and schools sources unavailable")
    sections = {"overview": _section(_overview_summary(b, s, environment, transit)), "buildings": b, "streetsConnectivity": s, "spaceSyntaxCentrality": syntax, "environment": environment, "publicTransport": transit, "parksEducation": parks_education, "availability": _section({key: value["status"] for key, value in {"buildings": b, "streetsConnectivity": s, "spaceSyntaxCentrality": syntax, "environment": environment, "publicTransport": transit, "parksEducation": parks_education}.items()}), "methods": _section({"circle": "metric CRS buffer", "fixedClassMetadata": FIXED_CLASS_METADATA, "selection": "exact polygon" if is_tps else "single center/radius"})}
    result = {"contractVersion": "local-area-profile.v1", "center": [float(center.x), float(center.y)], "radiusM": radius_m, "sections": sections, "sources": dict(sources or {}), "provenance": dict(provenance or {}), "warnings": list(warnings or [])}
    result["selection"] = ({"type": "tps", **dict(selection_metadata or {}), "areaM2": round(selection_area_m2, 3)} if is_tps else {"type": "circle", "center": [float(center.x), float(center.y)], "radiusM": radius_m, "areaM2": round(selection_area_m2, 3)})
    return result


def build_local_area_profiles(center: Point, *, radii_m: Iterable[int] = PROFILE_RADII_M, **kwargs) -> dict:
    profiles = [build_local_area_profile(center, radius_m=int(radius), **kwargs) for radius in sorted({int(r) for r in radii_m})]
    return {"contractVersion": "local-area-profiles.v1", "center": [float(center.x), float(center.y)], "radiiM": [p["radiusM"] for p in profiles], "profiles": profiles}
