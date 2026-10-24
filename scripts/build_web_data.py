"""Export compact GeoJSON and metadata for the static urban-scanner website."""

from __future__ import annotations

import json
import shutil
import tomllib
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import pandas as pd

from ahmedabad_scanner.gtfs import add_transit_isochrone_spatial_index, prepare_gtfs_service_intensity, prepare_transit_route_model, prepare_web_gtfs
from ahmedabad_scanner.local_area_profile import LOCAL_AREA_PROFILE_SCHEMA
from ahmedabad_scanner.open_buildings import load_open_buildings_region
from ahmedabad_scanner.poi import load_overpass_pois
from ahmedabad_scanner.web_export import (
    classification_metadata,
    prepare_web_raw_buildings,
    prepare_web_vector_layer,
    prepare_web_space_syntax,
    prepare_web_space_syntax_points,
)

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config/ahmedabad_pilot.toml"
FLOOD_RISK_SOURCE = ROOT.parent / "vedas-gis-extractor/other_download/ahm_urban_flood_risk_zones/ahm_urban_flood_risk_zones.PROVISIONAL.geojson"
FLOOD_RISK_FILENAME = "ahm-urban-flood-risk-zones.geojson"
FLOOD_RISK_CLASSES = ("Very High Risk Areas", "High Risk Areas", "Moderate Risk Areas")
TPS_SOURCE = ROOT / "data/external/newdata/tps_provisional_merged.geojson"
TPS_FILENAME = "tps-provisional.geojson"
TPS_REQUIRED_FIELDS = ("source_id", "tps_name", "tps_no", "tps_status")

CONTEXT_CATALOG = {
    "full-study-current": {
        "scopeLabel": "Full-study current",
        "statusLabel": "Current study",
        "temporalLabel": "2026 current-study products",
        "caveat": "Full-study current result for the Ahmedabad–Gandhinagar study boundary; product-specific temporal or proxy limitations still apply.",
    },
    "current-study-bounded": {
        "scopeLabel": "Bounded current-study subset",
        "statusLabel": "Subset computation",
        "temporalLabel": "2026 current-study workflow",
        "caveat": "Current-study output limited to a documented bounded tile or subset; it is not a full-study result.",
    },
    "current-study-sampled": {
        "scopeLabel": "Sampled current-study",
        "statusLabel": "Sampled/modelled",
        "temporalLabel": "2026 current-study workflow",
        "caveat": "Current-study model output based on sampled origins, facilities, or destinations; it is not a complete population or all-pairs study.",
    },
    "current-study-proxy": {
        "scopeLabel": "Current-study morphology proxy",
        "statusLabel": "Screening/modelled",
        "temporalLabel": "2026 current-study workflow",
        "caveat": "Current-study morphology proxy for screening only; not measured heat exposure or climate risk.",
    },
    "archived-navrangpura": {
        "scopeLabel": "Archived Navrangpura pilot",
        "statusLabel": "Archived pilot",
        "temporalLabel": "Earlier pilot workflow",
        "caveat": "Retained from the archived Navrangpura pilot; do not interpret it as a current full-study result.",
    },
    "contextual-gtfs": {
        "scopeLabel": "Contextual GTFS",
        "statusLabel": "Supplied feed",
        "temporalLabel": "Feed date not verified",
        "caveat": "Supplied GTFS context; provenance and service-date currency are not confirmed.",
    },
    "contextual-osm": {
        "scopeLabel": "Contextual OSM",
        "statusLabel": "Mapped context",
        "temporalLabel": "OSM snapshot",
        "caveat": "OpenStreetMap-mapped context; coverage and completeness are not equivalent to observed service availability.",
    },
    "contextual-vedas": {
        "scopeLabel": "AMC flood-risk context",
        "statusLabel": "Supplied VEDAS/ISRO layer",
        "temporalLabel": "Source date not verified",
        "caveat": "Provisional urban flood-risk zones from the VEDAS/ISRO portal; source risk classes are retained as supplied and the source method/date have not been independently verified.",
    },
    "supplied-external": {
        "scopeLabel": "Supplied external",
        "statusLabel": "Not rerun",
        "temporalLabel": "Source date not verified",
        "caveat": "Supplied clipped external layer; the underlying analysis was not rerun for this study.",
    },
    "supplied-unverified-experimental": {
        "scopeLabel": "Supplied contextual raster",
        "statusLabel": "Unverified / experimental",
        "temporalLabel": "Source date not verified",
        "caveat": "Supplied development-plan visual context; provenance, accuracy, and temporal currency are not verified. It is not analytical evidence.",
    },
    "unverified-height": {
        "scopeLabel": "Unverified height-dependent",
        "statusLabel": "Not validated",
        "temporalLabel": "Date shown in layer description",
        "caveat": "Height-dependent raster is published for inspection but has not been validated for this study; do not treat it as verified evidence.",
    },
    "modelled-building-height": {
        "scopeLabel": "Full-study modelled raster",
        "statusLabel": "Modelled proxy",
        "temporalLabel": "2023 annual slice",
        "caveat": "Google Research Open Buildings Temporal modelled height; not surveyed height. 30 m overview switches to the detailed tile pyramid at zoom 8; source effective resolution is ~4 m, source storage grid is 0.5 m, and presence threshold is 0.2.",
    },
    "scope-unverified": {
        "scopeLabel": "Scope not verified",
        "statusLabel": "Unverified",
        "temporalLabel": "Temporal status not verified",
        "caveat": "Scope, provenance, and temporal status are not verified.",
    },
}

ANALYSIS_STATUS = (
    "Published products mix full-study current results, bounded current-study subsets, sampled current-study model outputs, "
    "morphology proxies, archived/historical pilot outputs, contextual external layers, supplied external layers, scenario products, "
    "and unverified products; each item must be interpreted using its displayed provenance context. "
    "Space syntax was not rerun; the supplied clipped external layer is published as raw fields."
)

INDICATOR_CONTEXT_KEYS = {
    "buildingArea": "full-study-current",
    "categories": "contextual-osm",
    "health": "contextual-osm",
    "education": "contextual-osm",
    "food": "contextual-osm",
    "transport": "contextual-osm",
    "green": "contextual-osm",
    "civic": "contextual-osm",
    "culture": "contextual-osm",
    "sport": "contextual-osm",
    "lst": "full-study-current",
    "ndvi": "full-study-current",
    "vegetation": "full-study-current",
    "priority": "full-study-current",
    "planxCompactness": "full-study-current",
    "planxConvexity": "full-study-current",
    "planxElongation": "full-study-current",
    "planxCellArea": "archived-navrangpura",
}

OVERLAY_CONTEXT_KEYS = {
    "gtfsShapes": "contextual-gtfs",
    "gtfsStops": "contextual-gtfs",
    "gtfsServiceDay": "contextual-gtfs",
    "gtfsMorningPeak": "contextual-gtfs",
    "gtfsEveningPeak": "contextual-gtfs",
    "gtfsDeparturesPerHour": "contextual-gtfs",
    "transitIsochrones": "contextual-gtfs",
    "floodRiskZones": "contextual-vedas",
    "centrality": "full-study-current",

    "heatRisk": "current-study-proxy",
    "shadowCasting": "unverified-height",
    "sunHours": "unverified-height",
    "skyViewFactor": "unverified-height",
    "solarIrradiation": "unverified-height",
    "environmentSurfaceTemperature": "full-study-current",
    "environmentNdvi": "full-study-current",
    "environmentVegetationFraction": "full-study-current",
    "environmentHeatGreenPriority": "full-study-current",
    "buildingHeight": "modelled-building-height",
    "developmentPlan": "supplied-unverified-experimental",

    "spaceSyntax": "supplied-external",
    "spaceSyntaxPoints": "supplied-external",
    "publicPois": "contextual-osm",
    "poi-parks": "contextual-osm",
    "poi-schools": "contextual-osm",
}

PLANX_OVERLAY_KEYS = tuple(OVERLAY_CONTEXT_KEYS)

GENERATED_WEB_DATA_FILES = frozenset({
    "buildings.geojson", "gtfs-stops.geojson", "gtfs-shapes.geojson", "gtfs-service-intensity.geojson", "transit-isochrone-model.json", "pois.geojson",
    "planx-centrality.geojson", "planx-heat-risk.geojson", FLOOD_RISK_FILENAME,
    "space-syntax.geojson", "space-syntax-points.geojson", "metadata.json", "local-area-profile-schema.json", TPS_FILENAME,
})
STALE_WEB_DATA_FILES = frozenset({
    "planx-network.geojson", "planx-link-criticality.geojson", "planx-deadends.geojson",
    "planx-service-areas.geojson", "planx-proposed-sites.geojson", "planx-green-connectivity.geojson",
    "planx-routes.geojson", "planx-transit-frequency.geojson", "planx-transit-access.geojson",
    "planx-green-access.geojson",
})


def clean_generated_web_data(output_dir: Path, *, keep: set[str] | None = None) -> None:
    """Remove generated publication files before rebuilding, including deleted products."""
    keep = keep or set()
    for filename in (GENERATED_WEB_DATA_FILES | STALE_WEB_DATA_FILES) - keep:
        path = output_dir / filename
        if path.exists():
            path.unlink()


def publish_flood_risk_zones(output_dir: Path, *, source_path: Path = FLOOD_RISK_SOURCE) -> dict:
    """Copy the supplied VEDAS GeoJSON byte-for-byte after validating its risk field."""
    payload = json.loads(source_path.read_text())
    features = payload.get("features", [])
    counts = Counter((feature.get("properties") or {}).get("uf_risk") for feature in features)
    if payload.get("type") != "FeatureCollection":
        raise ValueError("Flood-risk source must be a GeoJSON FeatureCollection")
    if set(counts) != set(FLOOD_RISK_CLASSES):
        raise ValueError(f"Flood-risk source classes do not match the expected uf_risk values: {sorted(map(str, counts))}")
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / FLOOD_RISK_FILENAME
    shutil.copyfile(source_path, target)
    return {
        "source": str(source_path),
        "file": FLOOD_RISK_FILENAME,
        "feature_count": len(features),
        "risk_field": "uf_risk",
        "risk_class_counts": {label: counts[label] for label in FLOOD_RISK_CLASSES},
    }


def publish_tps_zones(output_dir: Path, *, source_path: Path = TPS_SOURCE, expected_count: int = 312) -> dict:
    """Publish the validated TPS source, retaining separate duplicate display identifiers."""
    frame = gpd.read_file(source_path, engine="pyogrio")
    missing = set(TPS_REQUIRED_FIELDS) - set(frame.columns)
    if missing:
        raise ValueError(f"TPS source missing fields: {sorted(missing)}")
    if len(frame) != expected_count:
        raise ValueError(f"TPS source must contain {expected_count} features, got {len(frame)}")
    if str(frame.crs) != "EPSG:4326":
        raise ValueError(f"TPS source CRS is {frame.crs}, expected EPSG:4326")
    if not set(frame.geometry.geom_type).issubset({"Polygon", "MultiPolygon"}) or not frame.geometry.is_valid.all():
        raise ValueError("TPS source requires valid Polygon/MultiPolygon geometries")
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / TPS_FILENAME
    shutil.copyfile(source_path, target)
    pairs = frame[["tps_name", "tps_no"]].fillna("").astype(str)
    return {
        "source": str(source_path),
        "file": TPS_FILENAME,
        "feature_count": int(len(frame)),
        "fields": list(TPS_REQUIRED_FIELDS),
        "duplicate_display_identifier_count": int(pairs.duplicated(keep=False).sum() // 2),
    }


SPACE_SYNTAX_SELECTOR_FIELDS = (
    "off", "connectivity", "betweenness", "closeness", "straightness",
    "nc_400", "td_400", "md_400", "nain_400", "ch_400", "nach_400",
    "nc_2500", "td_2500", "md_2500", "nain_2500", "ch_2500", "nach_2500",
)


def _format_legend_number(value):
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


def classification_legend_entries(classification: dict) -> list[dict]:
    if classification.get("method") == "categorical":
        entries = []
        for value, color in zip(classification.get("values", []), classification.get("palette", [])):
            label = _format_legend_number(value)
            entries.append({"label": label, "color": color, "value": value})
        return entries
    if classification.get("legend_entries"):
        return classification["legend_entries"]
    if classification.get("method") == "constant":
        value = classification.get("value", classification.get("min"))
        return [{"label": _format_legend_number(value), "color": classification.get("palette", ["#440154"])[0], "value": value}]
    if classification.get("method") != "quantile":
        return []
    bounds = [classification.get("min"), *classification.get("breaks", []), classification.get("max")]
    return [{"label": f"{_format_legend_number(bounds[i])}–{'<' if i < len(bounds) - 2 else ''}{_format_legend_number(bounds[i + 1])}", "color": color, "min": bounds[i], "max": bounds[i + 1]} for i, color in enumerate(classification.get("palette", []))]


def _legend_record(key, title, kind, geometry, context_key, *, renderer_property=None, unit="", unit_status="not_documented", caveat="", numeric_applicable=False, entries=None, **extra):
    return {"key": key, "title": title, "kind": kind, "geometry": geometry, "renderer_property": renderer_property, "unit": unit, "unit_status": unit_status, "context_key": context_key, "caveat": caveat, "numeric_applicable": numeric_applicable, "entries": entries or [], **extra}


def build_overlay_legends(classifications: dict, *, raster_manifests: dict | None = None) -> dict:
    classifications = classifications or {}
    raster_manifests = raster_manifests or {}
    legends = {}
    symbols = {
        "gtfsShapes": ("GTFS routes", "line", "#0f766e"), "gtfsStops": ("GTFS stops", "circle", "#b45309"),

    }
    for key, (title, geometry, color) in symbols.items():
        caveat = "Current renderer uses one symbol; numeric values are not visually encoded."
        legends[key] = _legend_record(key, title, "single-symbol", geometry, OVERLAY_CONTEXT_KEYS[key], caveat=caveat, entries=[{"label": title, "color": color, "shape": geometry}])
    legends["floodRiskZones"] = _legend_record(
        "floodRiskZones",
        "Urban flood-risk zones",
        "categorical",
        "fill",
        OVERLAY_CONTEXT_KEYS["floodRiskZones"],
        renderer_property="uf_risk",
        unit="risk class",
        unit_status="verified",
        caveat="Provisional VEDAS/ISRO flood-risk zones. The uf_risk categories are retained exactly as supplied; source date and methodology have not been independently verified.",
        entries=[
            {"label": "Very High Risk Areas", "value": "Very High Risk Areas", "color": "#7f0000", "shape": "fill"},
            {"label": "High Risk Areas", "value": "High Risk Areas", "color": "#d7301f", "shape": "fill"},
            {"label": "Moderate Risk Areas", "value": "Moderate Risk Areas", "color": "#fdbb84", "shape": "fill"},
        ],
    )
    legends["transitIsochrones"] = _legend_record(
        "transitIsochrones",
        "15-minute route-reach walking catchment",
        "categorical",
        "fill",
        OVERLAY_CONTEXT_KEYS["transitIsochrones"],
        unit="15-minute street-network walk",
        unit_status="verified",
        numeric_applicable=True,
        entries=[
            {"label": "Within 15 minutes of an accessible route stop", "color": "#2563eb", "value": 15},
            {"label": "Stop on an accessible route", "color": "#7c3aed", "shape": "circle"},
            {"label": "Selected or 5-minute-walk seed stop", "color": "#f59e0b", "shape": "circle"},
        ],
        caveat="Route-reach catchment, not total public-transport journey time: select a stop, add stops within a 5-minute walk on the prepared street network, include every stop on their GTFS routes, then union 15-minute street-network walking catchments around those route stops. Waiting and in-vehicle times are not constrained. Feed provenance remains unresolved.",
    )
    for key, title, prop in (("centrality", "Network centrality (full prepared network)", "betweenness"),):
        classification = {**classifications.get(key, {}).get(prop, {}), "property": prop}
        caveats = {
            "centrality": "Full prepared-network centrality result: 135,115 analysed edges; betweenness uses 500 sampled sources and is not an all-pairs metric.",
        }
        legends[key] = _legend_record(key, title, "classification", "line", OVERLAY_CONTEXT_KEYS[key], renderer_property=prop, numeric_applicable=True, entries=classification_legend_entries(classification), classification=classification, caveat=caveats[key])
    heat_classification = {**classifications.get("heatRisk", {}).get("heat_risk", {}), "property": "heat_risk"}
    legends["heatRisk"] = _legend_record(
        "heatRisk",
        "Heat-risk morphology proxy",
        "classification",
        "fill",
        OVERLAY_CONTEXT_KEYS["heatRisk"],
        renderer_property="heat_risk",
        numeric_applicable=True,
        entries=classification_legend_entries(heat_classification),
        classification=heat_classification,
        caveat="Morphology proxy based on 30,000 buildings and 35 green spaces; not observed heat. Values are the published heat_risk proxy field; missing values remain no data.",
    )

    service_specs = (
        ("gtfsServiceDay", "Whole service day", "daily_departures", "departures, whole service day", "All scheduled departures in the GTFS service day, including extended times after 24:00."),
        ("gtfsMorningPeak", "Morning peak (08:00–10:00)", "morning_peak_departures", "departures, 08:00–10:00", "Scheduled departures from 08:00 inclusive to 10:00 exclusive."),
        ("gtfsEveningPeak", "Evening peak (17:00–19:00)", "evening_peak_departures", "departures, 17:00–19:00", "Scheduled departures from 17:00 inclusive to 19:00 exclusive."),
        ("gtfsDeparturesPerHour", "Average departures per hour", "departures_per_hour", "average departures/hour", "Whole-day scheduled departures divided by the observed GTFS service-day span."),
    )
    for key, title, property_name, unit, period_note in service_specs:
        classification = {**classifications.get(key, {}).get(property_name, {}), "property": property_name}
        legends[key] = _legend_record(
            key, title, "classification", "circle", OVERLAY_CONTEXT_KEYS[key],
            renderer_property=property_name, unit=unit, unit_status="verified", numeric_applicable=True,
            entries=classification_legend_entries(classification), classification=classification,
            caveat=f"{period_note} Route count is retained separately and is not treated as service frequency. Values describe scheduled service, not verified operations, reliability, capacity, or ridership. Feed provenance remains unresolved.",
        )

    raster_specs = {"shadowCasting": ("Shadow casting", "binary-raster", "0/1", "verified", "unverified"), "sunHours": ("Sun hours", "continuous-raster", "hours", "verified", "unverified"), "skyViewFactor": ("Sky view factor", "continuous-raster", "unitless", "verified", "unverified"), "solarIrradiation": ("Solar irradiation", "continuous-raster", "", "not_documented", "unverified"), "environmentSurfaceTemperature": ("Surface temperature raster", "continuous-raster", "°C", "verified", "verified"), "environmentNdvi": ("NDVI raster", "continuous-raster", "unitless", "verified", "verified"), "environmentVegetationFraction": ("Vegetation fraction raster", "continuous-raster", "0–1", "verified", "verified"), "environmentHeatGreenPriority": ("Heat–green priority raster", "continuous-raster", "0–1", "verified", "verified"), "buildingHeight": ("2023 modelled building height", "continuous-raster", "metres", "verified", "verified")}
    manifest_keys = {"shadowCasting": "shadow-casting", "sunHours": "sun-hours", "skyViewFactor": "sky-view-factor", "solarIrradiation": "solar-irradiation", "environmentSurfaceTemperature": "surface-temperature", "environmentNdvi": "ndvi", "environmentVegetationFraction": "vegetation-fraction", "environmentHeatGreenPriority": "heat-green-priority", "buildingHeight": "building-height"}
    for key, (title, kind, unit, unit_status, validation_status) in raster_specs.items():
        manifest_key = manifest_keys[key]
        manifest = {"environmentSurfaceTemperature": {"display_range": [35, 55], "colormap": "inferno"}, "environmentNdvi": {"display_range": [-0.2, 0.7], "colormap": "RdYlGn"}, "environmentVegetationFraction": {"display_range": [0, 1], "colormap": "YlGn"}, "environmentHeatGreenPriority": {"display_range": [0, 1], "colormap": "magma"}, "shadowCasting": {"display_range": [0, 1], "colormap": "gray"}, "sunHours": {"display_range": [0, 13], "colormap": "YlOrRd"}, "skyViewFactor": {"display_range": [0.55, 1], "colormap": "viridis"}, "solarIrradiation": {"display_range": [4, 8.1], "colormap": "inferno"}, "buildingHeight": {"display_range": [0, 30], "colormap": "teal-green-yellow-orange-red"}}[key] | raster_manifests.get(manifest_key, {})
        if key == "buildingHeight":
            manifest |= raster_manifests.get("building-height-fine", {})
        if kind == "binary-raster":
            entries = [{"label": "0 (not shadowed)", "value": 0, "color": "transparent"}, {"label": "1 (shadowed)", "value": 1, "color": "#1e1e1e"}]
        elif manifest.get("display_range"):
            lower, upper = manifest["display_range"]
            entries = [{"label": f"{lower}–{upper} {unit}".strip(), "min": lower, "max": upper, "colormap": manifest.get("colormap"), "palette_stops": manifest.get("palette_stops", [])}]
        else:
            entries = []
        caveat = "Google Research Open Buildings Temporal modelled height; not surveyed height; 2023; 30 m pixels below zoom 8, switching to the detailed tile pyramid at zoom 8; source effective resolution is ~4 m; source storage grid is 0.5 m; presence threshold 0.2; values above 30 m are clamped red for display." if key == "buildingHeight" else ("Palette/range are evidence-based manifest metadata; height-dependent products remain unverified." if validation_status == "unverified" else "Raster preview uses the documented generation range and colormap.")
        legends[key] = _legend_record(key, title, kind, "raster", OVERLAY_CONTEXT_KEYS[key], unit=manifest.get("unit", unit), unit_status=unit_status, numeric_applicable=True, entries=entries, validation_status=validation_status, source={"manifest_key": manifest_key, **manifest}, caveat=caveat)
    legends["developmentPlan"] = _legend_record(
        "developmentPlan",
        "Development plan",
        "single-symbol",
        "raster",
        OVERLAY_CONTEXT_KEYS["developmentPlan"],
        caveat="Supplied visual raster with its own embedded legend and north arrow; provenance, accuracy, and temporal currency are unverified. No separate analytical colour scale is claimed.",
        entries=[{"label": "Supplied visual context (see embedded legend)", "color": "#525252", "shape": "raster"}],
        validation_status="unverified",
        source=raster_manifests.get("development-plan", {}),
    )
    legends["publicPois"] = _legend_record("publicPois", "Public-interest POIs", "categorical", "circle", OVERLAY_CONTEXT_KEYS["publicPois"], caveat="Category-specific symbols are published by the poi-* records.")
    poi_colors = {"parks": "#15803d", "schools": "#2563eb"}
    for key in ["poi-parks", "poi-schools"]:
        category = key.removeprefix("poi-")
        legends[key] = _legend_record(key, category.replace("-", " ").title(), "single-symbol", "circle", OVERLAY_CONTEXT_KEYS[key], entries=[{"label": category, "color": poi_colors[category], "shape": "circle"}])
    space_syntax_titles = {
        "off": "Off", "connectivity": "Connectivity", "betweenness": "Edge betweenness",
        "closeness": "Mean closeness", "straightness": "Mean straightness",
        "nc_400": "NC 400 m", "td_400": "TD 400 m", "md_400": "MD 400 m",
        "nain_400": "NAIN 400 m", "ch_400": "CH 400 m", "nach_400": "NACH 400 m",
        "nc_2500": "NC 2,500 m", "td_2500": "TD 2,500 m", "md_2500": "MD 2,500 m",
        "nain_2500": "NAIN 2,500 m", "ch_2500": "CH 2,500 m", "nach_2500": "NACH 2,500 m",
    }
    legends["spaceSyntax"] = {field: _legend_record(field, space_syntax_titles[field], "off" if field == "off" else "classification", "none" if field == "off" else ("circle" if field == "betweenness" else "line"), "supplied-external", renderer_property=None if field == "off" else field, numeric_applicable=field != "off", entries=[] if field == "off" else classification_legend_entries({**classifications.get("spaceSyntax", {}).get(field, {}), "property": field}), classification=classifications.get("spaceSyntax", {}).get(field), caveat="off means no legend." if field == "off" else "Uses the exact existing space-syntax classification.") for field in SPACE_SYNTAX_SELECTOR_FIELDS}
    legends["spaceSyntaxPoints"] = _legend_record("spaceSyntaxPoints", "Space-syntax betweenness points", "classification", "circle", "supplied-external", renderer_property="betweenness", numeric_applicable=True)
    return legends


def numeric_summary(series: pd.Series) -> dict[str, float | None]:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return {"min": None, "p10": None, "median": None, "p90": None, "max": None}
    return {
        "min": round(float(values.min()), 3),
        "p10": round(float(values.quantile(0.1)), 3),
        "median": round(float(values.median()), 3),
        "p90": round(float(values.quantile(0.9)), 3),
        "max": round(float(values.max()), 3),
    }


def planx_building_statistics() -> dict[str, dict[str, object]]:
    """Expose full-study PlanX indicator statistics with explicit provenance."""
    report_path = ROOT / "reports/ahmedabad_gandhinagar_planx_full_building_form_audit.json"
    report = json.loads(report_path.read_text())
    fields = {
        "footprint_area_m2": "footprint_area_m2",
        "planx_compactness": "compact",
        "planx_convexity": "convexity",
        "planx_elongation": "elongation",
    }
    result = {}
    for public_field, source_field in fields.items():
        result[public_field] = {
            **report["statistics"][source_field],
            "source_field": source_field,
            "scope": "full-study",
            "context": "Ahmedabad–Gandhinagar black-line study area; full building-metrics output",
            "report_path": str(report_path.relative_to(ROOT)),
            "provenance": report["paths"],
        }
    return result


def write_geojson(frame: gpd.GeoDataFrame, path: Path) -> None:
    payload = json.loads(frame.to_json(drop_id=True, show_bbox=False))
    path.write_text(json.dumps(payload, separators=(",", ":")) + "\n")


def _first_layer(path: Path) -> gpd.GeoDataFrame:
    layers = gpd.list_layers(path)
    if layers.empty:
        raise ValueError(f"No layers in {path}")
    return gpd.read_file(path, layer=str(layers.iloc[0]["name"]), engine="pyogrio")


EXPECTED_FULL_CENTRALITY_EDGE_COUNT = 135_115


def _centrality_edge_count(path: Path) -> int:
    return len(_first_layer(path))


def _centrality_candidates(repository_root: Path) -> tuple[Path, Path, Path]:
    if (repository_root / "data/derived/planx").exists():
        planx_root = repository_root / "data/derived/planx"
        return (
            planx_root / "ahmedabad-gandhinagar-centrality-full-run-20261018/network_centrality_edges.gpkg",
            planx_root / "ahmedabad-gandhinagar-centrality-full-run-20261018/execution.json",
            planx_root / "ahmedabad-gandhinagar-centrality-tile/network_centrality_edges.gpkg",
        )
    return (
        repository_root / "full/network_centrality_edges.gpkg",
        repository_root / "full/execution.json",
        repository_root / "bounded/network_centrality_edges.gpkg",
    )


def select_centrality_source(repository_root: Path = ROOT, *, expected_edge_count: int = EXPECTED_FULL_CENTRALITY_EDGE_COUNT) -> Path:
    """Select the verified full-network result, otherwise retain the bounded fallback."""
    full_path, execution_path, bounded_path = _centrality_candidates(repository_root)
    if full_path.exists() and execution_path.exists():
        try:
            execution = json.loads(execution_path.read_text())
            if execution.get("analysis_status") == "ok" and _centrality_edge_count(full_path) == expected_edge_count:
                return full_path
        except (OSError, ValueError, KeyError):
            pass
    return bounded_path


def export_planx_layers(output_dir: Path) -> dict[str, int]:
    """Publish non-space-syntax PlanX outputs that were actually produced."""
    root = ROOT / "data/derived/planx/ahmedabad-gandhinagar-full-analysis-outputs"
    if not root.exists():
        root = ROOT / "data/derived/planx/outputs"
    centrality_source = select_centrality_source(ROOT)
    specs = {
        "planx-centrality.geojson": (str(centrality_source), {"seg_id": ("seg_id", None), "betw_edge": ("betweenness", 3), "clo_mean": ("closeness", 3), "str_mean": ("straightness", 3), "centrality_subset": ("centrality_subset", None)}),

        "planx-heat-risk.geojson": ("heat_risk.gpkg", {"uhi_risk": ("heat_risk", 4)}),
    }
    counts = {}
    for filename, (source, fields) in specs.items():
        path = Path(source) if Path(source).is_absolute() else root / source
        if not path.exists():
            continue
        frame = _first_layer(path)
        available = {key: value for key, value in fields.items() if key in frame.columns}
        if not available:
            continue
        output = prepare_web_vector_layer(frame, available)
        write_geojson(output, output_dir / filename)
        counts[filename] = len(output)
    return counts


def export_space_syntax(output_dir: Path) -> dict[str, int]:
    """Publish the supplied clipped layer only; never execute a space-syntax job."""
    path = ROOT / "data/derived/space_syntax/ahmedabad-gandhinagar-space-syntax-clipped.gpkg"
    if not path.exists():
        return {}
    frame = _first_layer(path)
    line = prepare_web_space_syntax(frame)
    points = prepare_web_space_syntax_points(frame)
    write_geojson(line, output_dir / "space-syntax.geojson")
    write_geojson(points, output_dir / "space-syntax-points.geojson")
    return {"space-syntax.geojson": len(line), "space-syntax-points.geojson": len(points)}


def build_overlay_classifications(output_dir: Path) -> dict:
    """Classify exactly the numeric values written to the public GeoJSON files."""
    def properties(filename: str) -> pd.DataFrame:
        payload = json.loads((output_dir / filename).read_text())
        return pd.DataFrame([feature.get("properties", {}) for feature in payload.get("features", [])])

    def classify(frame: pd.DataFrame, property_name: str, palette: str = "viridis") -> dict:
        if property_name not in frame:
            return classification_metadata(pd.Series(dtype=float), property_name=property_name, palette=palette)
        return classification_metadata(frame[property_name], property_name=property_name, palette=palette)

    def load(filename: str) -> pd.DataFrame:
        return properties(filename) if (output_dir / filename).exists() else pd.DataFrame()

    centrality = load("planx-centrality.geojson")
    service_intensity = load("gtfs-service-intensity.geojson")
    syntax = load("space-syntax.geojson")
    fields = ["connectivity", "betweenness", "closeness", "straightness", "nc_400", "td_400", "md_400", "nain_400", "ch_400", "nach_400", "nc_2500", "td_2500", "md_2500", "nain_2500", "ch_2500", "nach_2500"]
    syntax_result = {
        field: classify(syntax, field, "inferno" if field.startswith(("td_", "ch_", "nach_")) else "viridis")
        for field in fields
    }
    return {
        "centrality": {"betweenness": classify(centrality, "betweenness")},
        "gtfsServiceDay": {"daily_departures": classify(service_intensity, "daily_departures", "viridis")},
        "gtfsMorningPeak": {"morning_peak_departures": classify(service_intensity, "morning_peak_departures", "viridis")},
        "gtfsEveningPeak": {"evening_peak_departures": classify(service_intensity, "evening_peak_departures", "viridis")},
        "gtfsDeparturesPerHour": {"departures_per_hour": classify(service_intensity, "departures_per_hour", "viridis")},
        "heatRisk": {"heat_risk": classify(load("planx-heat-risk.geojson"), "heat_risk", "heat")},
        "spaceSyntax": syntax_result,
    }


PUBLISHED_POI_TYPES = frozenset({"parks", "schools"})


def select_published_pois(pois: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Retain only the POI categories approved for public map controls."""
    return pois.loc[pois["poi_type"].isin(sorted(PUBLISHED_POI_TYPES))].copy()


def export_local_area_profile_contract(output_dir: Path) -> Path:
    """Publish only the audited compact contract; profile values are computed on demand."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "local-area-profile-schema.json"
    path.write_text(json.dumps(LOCAL_AREA_PROFILE_SCHEMA, separators=(",", ":")) + "\n")
    return path


def main() -> None:
    with CONFIG_PATH.open("rb") as file:
        config = tomllib.load(file)
    output_dir = ROOT / "web/public/data"
    output_dir.mkdir(parents=True, exist_ok=True)
    clean_generated_web_data(output_dir)
    export_local_area_profile_contract(output_dir)
    flood_risk_publication = publish_flood_risk_zones(output_dir)
    boundary = gpd.read_file(
        ROOT / "data/external/boundary/ahmedabad-gandhinagar-black-line.gpkg",
        engine="pyogrio",
    ).to_crs("EPSG:4326").geometry.union_all()
    raw_paths = sorted((ROOT / "data/google-open-buildings-v3/raw").glob("*_buildings.csv.gz"))
    buildings = prepare_web_raw_buildings(load_open_buildings_region(raw_paths, region=boundary))
    form_root = ROOT / "data/derived/planx/ahmedabad-gandhinagar-full-building-outputs"
    if not (form_root / "building_metrics.gpkg").exists():
        form_root = ROOT / "data/derived/planx/ahmedabad-gandhinagar-building-form-outputs"
    metrics_path = form_root / "building_metrics.gpkg"
    tessellation_path = form_root / "tessellation.gpkg"
    if metrics_path.exists():
        metrics = _first_layer(metrics_path)
        buildings["_source_occurrence"] = buildings.groupby("building_id", sort=False).cumcount()
        metric_fields = metrics[["source_building_id", "compact", "convexity", "elongation"]].copy()
        metric_fields["_source_occurrence"] = metric_fields.groupby("source_building_id", sort=False).cumcount()
        metric_fields = metric_fields.rename(
            columns={
                "source_building_id": "building_id",
                "compact": "planx_compactness",
                "convexity": "planx_convexity",
                "elongation": "planx_elongation",
            }
        )
        buildings = buildings.merge(
            metric_fields, on=["building_id", "_source_occurrence"], how="left", validate="one_to_one"
        ).drop(columns=["_source_occurrence"])
        if tessellation_path.exists():
            tessellation = _first_layer(tessellation_path)
            tessellation_fields = tessellation[["source_building_id", "cell_m2"]].rename(
                columns={"source_building_id": "building_id", "cell_m2": "planx_cell_m2"}
            )
            buildings = buildings.merge(tessellation_fields, on="building_id", how="left", validate="many_to_one")
    buildings_path = output_dir / "buildings.geojson"
    write_geojson(buildings, buildings_path)

    gtfs_path = ROOT / "data/external/gtfs_compat.zip"
    stops, shapes = prepare_web_gtfs(gtfs_path)
    service_intensity = prepare_gtfs_service_intensity(gtfs_path)
    transit_isochrone_model = add_transit_isochrone_spatial_index(
        prepare_transit_route_model(gtfs_path),
        boundary,
        network=ROOT / "data/derived/planx/ahmedabad-gandhinagar-full-analysis-outputs/prepared_network.gpkg",
    )
    gtfs_exports = {
        "gtfs-stops.geojson": stops,
        "gtfs-shapes.geojson": shapes,
        "gtfs-service-intensity.geojson": service_intensity,
    }
    for filename, frame in gtfs_exports.items():
        write_geojson(frame, output_dir / filename)
    (output_dir / "transit-isochrone-model.json").write_text(json.dumps(transit_isochrone_model, separators=(",", ":")))

    pois = select_published_pois(load_overpass_pois(ROOT / "data/external/poi/overpass_public_pois.json", boundary))
    pois_path = output_dir / "pois.geojson"
    write_geojson(pois, pois_path)

    planx_exports = export_planx_layers(output_dir) if (ROOT / "data/derived/planx/outputs").exists() else {}
    space_syntax_exports = export_space_syntax(output_dir)
    overlay_classifications = build_overlay_classifications(output_dir)
    development_plan_manifest = json.loads((output_dir / "development-plan-manifest.json").read_text()) if (output_dir / "development-plan-manifest.json").exists() else {}
    ahmedabad_boundary_manifest_path = output_dir / "local-profile/ahmedabad-boundary-manifest.json"
    ahmedabad_boundary_publication = json.loads(ahmedabad_boundary_manifest_path.read_text()) if ahmedabad_boundary_manifest_path.exists() else {}

    bounds = [round(float(value), 7) for value in buildings.total_bounds]
    metadata = {
        "generated_utc": datetime.now(UTC).isoformat(),
        "title": "Ahmedabad Urban Scanner",
        "study_area": "Ahmedabad–Gandhinagar user-defined study boundary",
        "building_count": int(len(buildings)),
        "building_properties": [column for column in buildings.columns if column != buildings.geometry.name],
        "gtfs_stop_count": int(len(stops)),
        "gtfs_shape_count": int(len(shapes)),
        "gtfs_service_intensity": {
            "service_day": service_intensity.attrs["service_day_start"] + "–" + service_intensity.attrs["service_day_end"],
            "service_day_hours": service_intensity.attrs["service_day_hours"],
            "morning_peak": "08:00–10:00",
            "evening_peak": "17:00–19:00",
            "stop_count": int(len(service_intensity)),
            "stops_with_service": int((service_intensity["daily_departures"] > 0).sum()),
            "scheduled_departures": int(service_intensity["daily_departures"].sum()),
            "maximum_stop_departures": int(service_intensity["daily_departures"].max()),
            "method": "S_i = sum_r F_ir, counting GTFS stop_times departures at stop i for the whole service day and the half-open peak windows 08:00–10:00 and 17:00–19:00; average departures per hour divides whole-day departures by the observed service-day span.",
        },
        "transit_isochrones": {
            "method": "Selected stop plus stops within a 5-minute prepared-street-network walk; all stops on routes serving those seeds; 15-minute prepared-street-network walking catchment from each route stop.",
            "thresholds_minutes": [15],
            "origin_count": len(transit_isochrone_model["stops"]),
            "route_count": len(transit_isochrone_model["route_ids"]),
            "service_hours": transit_isochrone_model["service_hours"],
            "stop_route_service": "Each stop entry is [routeIndex, averageHeadwayMinutesOrNull, hourlyCounts]; counts are scheduled departures per service hour and headways use consecutive unique departure times.",
            "cell_area": "area_m2 is measured on each projected catchment cell before WGS84 conversion.",
            "nearby_stop_link_count": len(transit_isochrone_model["footpaths"]),
            "destination_cell_count": len(transit_isochrone_model["cells"]),
            "cell_size_m": transit_isochrone_model["cell_size_m"],
            "walking_speed_kmh": transit_isochrone_model["walking_speed_kmh"],
            "walking_model": transit_isochrone_model["walking_model"],
            "nearby_stop_minutes": transit_isochrone_model["nearby_stop_seconds"] / 60,
            "catchment_minutes": transit_isochrone_model["catchment_seconds"] / 60,
            "max_snap_distance_m": transit_isochrone_model["max_snap_distance_m"],
            "snapped_stop_count": transit_isochrone_model["snapped_stop_count"],
        },
        "poi_count": int(len(pois)),
        "poi_counts": {str(key): int(value) for key, value in pois["poi_type"].value_counts().items()},
        "bounds_wgs84": bounds,
        "centre_wgs84": [round((bounds[0] + bounds[2]) / 2, 7), round((bounds[1] + bounds[3]) / 2, 7)],
        "sources": {
            "buildings": "Google Research Open Buildings V3, S2 level 6 polygon tiles",
            "gtfs": "data/external/gtfs_compat.zip; audited locally before publication",
            "pois": "OpenStreetMap contributors via Overpass API; queried from the documented study-area bounding box",
            "flood_risk_zones": "VEDAS/ISRO portal provisional urban flood-risk zones; supplied GeoJSON copied without geometry or attribute transformation",
            "development_plan": "Supplied GeoTIFF copied unchanged to a project source copy and rendered as an RGBA-identical PNG; supplied/unverified experimental context only.",
        },
        "statistics": planx_building_statistics(),
        "contexts": CONTEXT_CATALOG,
        "indicator_contexts": INDICATOR_CONTEXT_KEYS,
        "overlay_contexts": OVERLAY_CONTEXT_KEYS,
        "analysis_status": ANALYSIS_STATUS,
        "planx_exports": planx_exports,
        "centrality_publication": {
            "source": str(select_centrality_source(ROOT).relative_to(ROOT)),
            "scope": "full-study-current",
            "analysis_status": "ok",
            "edge_count": EXPECTED_FULL_CENTRALITY_EDGE_COUNT,
            "provenance": "PlanX networkcentrality on the 135,115-edge prepared Ahmedabad–Gandhinagar network; radius=0, samples=500, cost_field=cost_fwd.",
        },
        "flood_risk_publication": flood_risk_publication,
        "development_plan_publication": development_plan_manifest,
        "ahmedabad_boundary_publication": ahmedabad_boundary_publication,
        "space_syntax_exports": space_syntax_exports,
        "overlay_classifications": overlay_classifications,
        "overlay_legends": build_overlay_legends(
            overlay_classifications,
            raster_manifests={
                **(json.loads((output_dir / "planx-raster-manifest.json").read_text()) if (output_dir / "planx-raster-manifest.json").exists() else {}),
                **(json.loads((output_dir / "environment-raster-manifest.json").read_text()) if (output_dir / "environment-raster-manifest.json").exists() else {}),
                **(json.loads((output_dir / "building-height-raster-manifest.json").read_text()) if (output_dir / "building-height-raster-manifest.json").exists() else {}),
                "development-plan": development_plan_manifest,
                "building-height-fine": json.loads((output_dir / "building-height-fine-manifest.json").read_text()) if (output_dir / "building-height-fine-manifest.json").exists() else {},
            },
        ),
        "classification_note": "Data-derived quantiles use up to seven classes with interior i/N thresholds and duplicate thresholds removed; connectivity uses exact categories, constant fields are marked as having no variation, and missing values are neutral gray.",
        "interpretation": [
            "Building footprints are Google Open Buildings V3 detections, not cadastral or occupancy records.",
            "The supplied GTFS feed is published as provided and requires provenance confirmation before analytical use.",
            "Transit service intensity provides mutually exclusive whole-day, 08:00–10:00, 17:00–19:00, and average-departures-per-hour views; route count is a separate attribute and is not treated as frequency.",
            "The route-reach walking catchment is not a timetable-constrained transit isochrone: it expands from the selected stop and nearby stops to every stop on their routes, then applies a 15-minute street-network walk around each route stop.",
            "PlanX outputs are pilot diagnostics; space syntax was not rerun in this session.",
        ],
    }
    metadata_path = output_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
    summary = {
        "buildings": len(buildings),
        "gtfs_stops": len(stops),
        "gtfs_shapes": len(shapes),
        "gtfs_service_intensity_stops": len(service_intensity),
        "planx_exports": planx_exports,
        "space_syntax_exports": space_syntax_exports,
        "scope_notes": {
            "centrality": "Full prepared-network centrality; 135,115 analysed edges with 500 sampled sources.",
            "heat_risk": "Morphology proxy based on 30,000 buildings and 35 green spaces; not observed heat.",
            "proposed_sites": "Archived historical hypothetical facility-location scenario; not a siting recommendation.",
        },
        "building_geojson": str(buildings_path.relative_to(ROOT)),
        "building_geojson_bytes": buildings_path.stat().st_size,
        "bounds_wgs84": bounds,
    }
    report_path = ROOT / "reports/web_export_summary.json"
    report_path.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
