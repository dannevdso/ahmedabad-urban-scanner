from scripts.build_web_data import (
    ANALYSIS_STATUS,
    CONTEXT_CATALOG,
    INDICATOR_CONTEXT_KEYS,
    OVERLAY_CONTEXT_KEYS,
    PLANX_OVERLAY_KEYS,
    SPACE_SYNTAX_SELECTOR_FIELDS,
    build_overlay_legends,
    classification_legend_entries,
)


def test_context_catalog_has_required_scope_classes_and_complete_labels():
    required = {
        "full-study-current",
        "current-study-bounded",
        "current-study-sampled",
        "current-study-proxy",
        "archived-navrangpura",
        "contextual-gtfs",
        "contextual-osm",
        "contextual-vedas",
        "supplied-external",
        "unverified-height",
        "scope-unverified",
    }
    assert required <= CONTEXT_CATALOG.keys()
    assert all(context["scopeLabel"] for context in CONTEXT_CATALOG.values())
    assert all(context["statusLabel"] for context in CONTEXT_CATALOG.values())
    assert all("caveat" in context and context["caveat"] for context in CONTEXT_CATALOG.values())


def test_context_assignments_cover_visible_indicators_and_overlays():
    assert set(INDICATOR_CONTEXT_KEYS) == {
        "buildingArea",
        "categories",
        "health",
        "education",
        "food",
        "transport",
        "green",
        "civic",
        "culture",
        "sport",
        "lst",
        "ndvi",
        "vegetation",
        "priority",
        "planxCompactness",
        "planxConvexity",
        "planxElongation",
        "planxCellArea",
    }
    assert all(key in CONTEXT_CATALOG for key in INDICATOR_CONTEXT_KEYS.values())
    assert all(key in CONTEXT_CATALOG for key in OVERLAY_CONTEXT_KEYS.values())
    assert OVERLAY_CONTEXT_KEYS["spaceSyntax"] == "supplied-external"
    assert OVERLAY_CONTEXT_KEYS["floodRiskZones"] == "contextual-vedas"


def test_priority_two_context_assignments_and_mixed_provenance_status_are_explicit():
    assert "transitAccess" not in OVERLAY_CONTEXT_KEYS
    assert "greenAccess" not in OVERLAY_CONTEXT_KEYS
    assert {key for key in OVERLAY_CONTEXT_KEYS if key.startswith("poi-")} == {"poi-parks", "poi-schools"}
    assert OVERLAY_CONTEXT_KEYS["heatRisk"] == "current-study-proxy"
    assert OVERLAY_CONTEXT_KEYS["centrality"] == "full-study-current"

    assert "full-study" in ANALYSIS_STATUS
    assert "bounded current-study subset" in ANALYSIS_STATUS
    assert "sampled current-study" in ANALYSIS_STATUS
    assert "archived/historical pilot" in ANALYSIS_STATUS
    assert "contextual external" in ANALYSIS_STATUS
    assert "supplied external" in ANALYSIS_STATUS
    assert "scenario" in ANALYSIS_STATUS
    assert "unverified" in ANALYSIS_STATUS


def test_visible_scope_copy_contains_quantified_limits_for_high_risk_overlays():
    legends = build_overlay_legends({})
    assert "135,115 analysed edges" in legends["centrality"]["caveat"]
    assert "500 sampled sources" in legends["centrality"]["caveat"]
    assert "30,000 buildings" in legends["heatRisk"]["caveat"]
    assert "35 green spaces" in legends["heatRisk"]["caveat"]
    assert "not observed heat" in legends["heatRisk"]["caveat"]
    assert legends["heatRisk"]["renderer_property"] == "heat_risk"
    assert legends["heatRisk"]["kind"] == "classification"


def test_web_export_summary_names_scope_limits():
    summary = __import__("json").loads((__import__("pathlib").Path("reports/web_export_summary.json")).read_text())
    notes = summary["scope_notes"]
    assert "135,115 analysed edges" in notes["centrality"]

    assert "30,000 buildings" in notes["heat_risk"]
    assert "scenario" in notes["proposed_sites"]
    legends = build_overlay_legends({})
    assert set(legends) == set(PLANX_OVERLAY_KEYS)
    assert set(legends["spaceSyntax"]) == set(SPACE_SYNTAX_SELECTOR_FIELDS)
    assert legends["spaceSyntax"]["off"]["kind"] == "off"
    assert legends["spaceSyntax"]["off"]["numeric_applicable"] is False


def test_classification_legend_labels_are_derived_from_existing_classification():
    classification = {"method": "quantile", "min": 0.000000001, "breaks": [0.000000002], "max": 0.000000003, "palette": ["a", "b"]}
    entries = classification_legend_entries(classification)
    assert [entry["label"] for entry in entries] == ["0.000000001–<0.000000002", "0.000000002–0.000000003"]
    assert [entry["color"] for entry in entries] == ["a", "b"]


def test_single_symbol_and_raster_metadata_is_truthful_and_linked():
    legends = build_overlay_legends({})
    assert legends["heatRisk"]["kind"] == "classification"
    assert legends["heatRisk"]["numeric_applicable"] is True
    assert legends["heatRisk"]["renderer_property"] == "heat_risk"
    assert legends["environmentSurfaceTemperature"]["unit"] == "°C"
    assert legends["environmentSurfaceTemperature"]["unit_status"] == "verified"
    assert legends["environmentSurfaceTemperature"]["entries"]
    assert legends["solarIrradiation"]["unit_status"] == "not_documented"
    assert legends["shadowCasting"]["validation_status"] == "unverified"
    assert "transitAccess" not in legends
    assert "greenAccess" not in legends
    assert {key for key in legends if key.startswith("poi-")} == {"poi-parks", "poi-schools"}
    assert legends["floodRiskZones"]["renderer_property"] == "uf_risk"
    assert [entry["label"] for entry in legends["floodRiskZones"]["entries"]] == [
        "Very High Risk Areas",
        "High Risk Areas",
        "Moderate Risk Areas",
    ]
