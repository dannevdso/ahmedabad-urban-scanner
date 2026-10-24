"""Resumable, dependency-aware orchestration for the PlanX QGIS pilot."""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Mapping

EXPECTED_PLANX_COMMIT = "d24233790b0b93af25a5a9024c078f1ec04089fc"
QGIS_PROCESS = Path("/Applications/QGIS.app/Contents/MacOS/bin/qgis_process")
PLUGIN_RELATIVE = Path(".qgis/profiles/default/python/plugins/planx")
REQUIRED_INPUT_LAYERS = {
    "raw_network", "buildings", "building_centroids", "destinations", "categories",
    "green_spaces", "study_area", "representative_origins", "candidate_sites", "civic_facilities",
}


class PlanXError(RuntimeError):
    pass


class PrerequisiteError(PlanXError):
    pass


def layer_uri(path: Path, layer: str) -> str:
    return f"{path}|layername={layer}"


def build_qgis_command(qgis_process: Path, algorithm: str, parameters: Mapping[str, object]) -> list[str]:
    """Build qgis_process arguments without invoking a shell."""
    command = [str(qgis_process), "run", algorithm]
    for key, value in parameters.items():
        if value is None:
            continue
        values = value if isinstance(value, (list, tuple)) else (value,)
        command.extend(f"--{key}={item}" for item in values)
    return command


@dataclass(frozen=True)
class ManifestEntry:
    name: str
    algorithm: str
    stage: str
    required_layers: tuple[str, ...]
    dependencies: tuple[str, ...]
    parameters: Callable[[Path, Path], dict[str, object]]
    outputs: tuple[tuple[str, str], ...]
    enabled_by_default: bool = True


@dataclass
class RunResult:
    status: str
    logs_path: Path
    commands: list[list[str]] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    missing_layers: list[str] = field(default_factory=list)
    failed: str | None = None


def _out(root: Path, filename: str, layer: str = "") -> str:
    """Return a real output path; qgis_process does not parse sink layer URIs."""
    return str(root / filename)


def _p(root: Path, filename: str, layer: str) -> dict[str, object]:
    return {"OUTPUT": _out(root, filename, layer)}


def _manifest() -> tuple[ManifestEntry, ...]:
    # Parameter names below are the plugin's declared Processing constants, not guesses.
    categories = ("health", "education", "food", "transport", "green", "civic", "culture", "sport")
    def amenity_layers(i): return [layer_uri(i, f"destination_{category}") for category in categories]
    def prepared(i, o): return {"INPUT": layer_uri(i, "raw_network"), "TARGET_CRS": "EPSG:32643", "CREATE_INDEX": True, "SNAP_TOLERANCE": 0, "FORWARD_COST": "walk_time_min", "REVERSE_COST": "walk_time_min", **_p(o, "prepared_network.gpkg", "prepared_network")}
    def centrality(i, o): return {"NETWORK": _out(o, "prepared_network.gpkg"), "COST_FIELD": "cost_fwd", "RADIUS": 0, "SAMPLES": 500, "NODES": _out(o, "network_centrality_nodes.gpkg"), "EDGES": _out(o, "network_centrality_edges.gpkg")}
    def syntax(i, o): return {"NETWORK": _out(o, "prepared_network.gpkg", "prepared_network"), "RADII": "400,800,n", **_p(o, "space_syntax.gpkg", "segments")}
    def morph(i, o): return {"NETWORK": _out(o, "prepared_network.gpkg"), "NODES": _out(o, "street_morphology_nodes.gpkg"), "SUMMARY": _out(o, "street_morphology_summary.gpkg")}
    def dead(i, o): return {"NETWORK": _out(o, "prepared_network.gpkg"), "MIN_BRANCH": 0, "SEGMENTS": _out(o, "deadends_segments.gpkg"), "DEAD_ENDS": _out(o, "deadends_points.gpkg"), "SUMMARY": _out(o, "deadends_summary.gpkg")}
    def link(i, o): return {"NETWORK": _out(o, "prepared_network.gpkg"), "ORIGINS": layer_uri(i, "criticality_origins"), "DESTINATIONS": layer_uri(i, "civic_facilities"), "COST_FIELD": "cost_fwd", "CUTOFF": 45, "CRITICAL": _out(o, "link_criticality.gpkg")}
    def od(i, o): return {"NETWORK": _out(o, "prepared_network.gpkg"), "ORIGINS": layer_uri(i, "representative_origins"), "DESTINATIONS": layer_uri(i, "destinations"), "ORIGIN_ID": "origin_id", "DEST_ID": "destination_id", "COST_FIELD": "cost_fwd", "CUTOFF": 45, "MATRIX": _out(o, "od_matrix.gpkg"), "LINES": _out(o, "od_matrix_lines.gpkg")}
    def routes(i, o): return {"NETWORK": _out(o, "prepared_network.gpkg"), "ORIGINS": layer_uri(i, "representative_origins"), "DESTINATIONS": layer_uri(i, "destinations"), "ORIGIN_ID": "origin_id", "DEST_ID": "destination_id", "COST_FIELD": "cost_fwd", "CUTOFF": 45, "K_NEAREST": 1, "OUT_ROUTES": _out(o, "od_routes.gpkg"), "OUT_LINES": _out(o, "od_route_lines.gpkg")}
    def service(i, o): return {"NETWORK": _out(o, "prepared_network.gpkg"), "FACILITIES": layer_uri(i, "civic_facilities"), "FACILITY_ID": "destination_id", "COST_FIELD": "length_m", "BREAKS": "400,800,1200", "COMBINE": 0, "METHOD": 0, "BUFFER": 30, "HULL_DETAIL": 1, "RINGS": _out(o, "service_area_rings.gpkg"), "EDGES": _out(o, "service_area_edges.gpkg"), "AREAS": _out(o, "service_areas.gpkg"), "CIRCLES": _out(o, "service_area_circles.gpkg"), "SUMMARY": _out(o, "service_area_summary.gpkg")}
    def nearest(i, o): return {"NETWORK": _out(o, "prepared_network.gpkg"), "DEMAND": layer_uri(i, "representative_origins"), "FACILITIES": layer_uri(i, "civic_facilities"), "FACILITY_ID": "destination_id", "COST_FIELD": "cost_fwd", "CUTOFF": 45, "OUTPUT": _out(o, "nearest_facility.gpkg"), "SPIDER": _out(o, "nearest_facility_spider.gpkg"), "ROUTES": _out(o, "nearest_facility_routes.gpkg"), "SUMMARY": _out(o, "nearest_facility_summary.gpkg")}
    def access(i, o): return {"ORIGINS": layer_uri(i, "representative_origins"), "NETWORK": _out(o, "prepared_network.gpkg"), "AMENITIES": amenity_layers(i), "POP_FIELD": "demand_weight", "SPEED": 4.8, "THRESHOLD": 15, "THRESHOLDS": "5,10,15", "DECAY": 0, **_p(o, "access_score.gpkg", "access")}
    def buildings(i, o): return {"BUILDINGS": layer_uri(i, "buildings"), **_p(o, "building_metrics.gpkg", "buildings")}
    def tess(i, o): return {"BUILDINGS": layer_uri(i, "buildings"), "STUDY_AREA": layer_uri(i, "study_area"), "SHRINK": 0.4, "DENSIFY": 2, "LIMIT": 100, **_p(o, "tessellation.gpkg", "tessellation")}
    def green_access(i, o): return {"NETWORK": _out(o, "prepared_network.gpkg"), "DEMAND": layer_uri(i, "representative_origins"), "POP_FIELD": "demand_weight", "GREENS": layer_uri(i, "green_spaces"), "HIERARCHY": "0.5=300, 2=800, 10=2000", "OUT_DEMAND": _out(o, "green_access.gpkg"), "OUT_SUMMARY": _out(o, "green_access_summary.gpkg")}
    def green_conn(i, o): return {"GREENS": layer_uri(i, "green_spaces"), "MAX_GAP": 100, "OUT_PATCHES": _out(o, "green_connectivity.gpkg"), "OUT_SUMMARY": _out(o, "green_connectivity_summary.gpkg")}
    def heat(i, o): return {"BUILDINGS": layer_uri(i, "buildings"), "GREEN": layer_uri(i, "green_spaces"), "CELL_SIZE": 100, "H_REF": 20, **_p(o, "heat_risk.gpkg", "heat")}
    def facility(i, o): return {"NETWORK": _out(o, "prepared_network.gpkg"), "DEMAND": layer_uri(i, "representative_origins"), "POP_FIELD": "demand_weight", "CANDIDATES": layer_uri(i, "candidate_sites"), "CANDIDATE_ID": "candidate_id", "EXISTING": layer_uri(i, "civic_facilities"), "METHOD": 0, "P": 3, "RADIUS": 500, "EXACT_AUDIT": False, "OUT_SITES": _out(o, "facility_location_sites.gpkg"), "OUT_ASSIGN": _out(o, "facility_location_assignments.gpkg")}
    def extract_sites(i, o): return {"INPUT": _out(o, "facility_location_sites.gpkg"), "FIELD": "selected", "OPERATOR": 0, "VALUE": 1, "OUTPUT": _out(o, "intervention_sites.gpkg")}
    def merge_civic(i, o): return {"LAYERS": [layer_uri(i, "civic_facilities"), _out(o, "intervention_sites.gpkg")], "CRS": "EPSG:32643", "OUTPUT": _out(o, "intervention_civic.gpkg")}
    def access_intervention(i, o):
        layers = amenity_layers(i)
        layers[5] = _out(o, "intervention_civic.gpkg")
        return {"ORIGINS": layer_uri(i, "representative_origins"), "NETWORK": _out(o, "prepared_network.gpkg"), "AMENITIES": layers, "POP_FIELD": "demand_weight", "SPEED": 4.8, "THRESHOLD": 15, "THRESHOLDS": "5,10,15", "DECAY": 0, **_p(o, "access_score_intervention.gpkg", "access")}
    def snapshot_baseline(i, o): return {"NAME": "Existing services", "ACCESS": _out(o, "access_score.gpkg"), "OUTPUT_JSON": str(o / "scenario_baseline.json"), "OUT_METRICS": _out(o, "scenario_baseline_metrics.gpkg")}
    def snapshot_intervention(i, o): return {"NAME": "Three proposed civic facilities", "ACCESS": _out(o, "access_score_intervention.gpkg"), "OUTPUT_JSON": str(o / "scenario_intervention.json"), "OUT_METRICS": _out(o, "scenario_intervention_metrics.gpkg")}
    def compare(i, o): return {"SNAPSHOT_A": str(o / "scenario_baseline.json"), "SNAPSHOT_B": str(o / "scenario_intervention.json"), "OUT_TABLE": _out(o, "scenario_compare.gpkg"), "OUTPUT_HTML": str(o / "scenario_compare.html")}
    def rank(i, o): return {"FILES": f"{o / 'scenario_baseline.json'};{o / 'scenario_intervention.json'}", "SIMULATIONS": 200, "WEIGHT_VARIATION": 0.2, "RANDOM_SEED": 42, "WEIGHTS": "", "OUT_TABLE": _out(o, "scenario_rank.gpkg"), "OUT_DETAIL": _out(o, "scenario_rank_detail.gpkg"), "OUTPUT_HTML": str(o / "scenario_rank.html")}
    def report(i, o): return {"TITLE": "Navrangpura PlanX pilot — proposed civic facilities", "ACCESS": _out(o, "access_score_intervention.gpkg"), "ACCESS_SCORE": "score", "OUTPUT": str(o / "performance_report.html")}
    e=[]
    def add(name, alg, stage, layers, deps, fn, outs, enabled_by_default=True):
        algorithm = alg if ":" in alg else f"planx:{alg}"
        declared_outputs = tuple(
            (filename, Path(filename).stem if filename.endswith(".gpkg") else "")
            for filename, _ in outs
        )
        e.append(ManifestEntry(
            name, algorithm, stage, tuple(layers), tuple(deps), fn,
            declared_outputs, enabled_by_default,
        ))
    add("preparenetwork","preparenetwork","prepare",["raw_network"],[],prepared,[("prepared_network.gpkg","prepared_network")])
    add("networkcentrality","networkcentrality","structure",[],["preparenetwork"],centrality,[("network_centrality_nodes.gpkg",""),("network_centrality_edges.gpkg","")])
    add("spacesyntax","spacesyntax","structure",[],["preparenetwork"],syntax,[("space_syntax.gpkg","segments")],enabled_by_default=False)
    add("streetmorphology","streetmorphology","structure",[],["preparenetwork"],morph,[("street_morphology_nodes.gpkg",""),("street_morphology_summary.gpkg","")])
    add("deadends","deadends","structure",[],["preparenetwork"],dead,[("deadends_segments.gpkg",""),("deadends_points.gpkg",""),("deadends_summary.gpkg","")])
    add("linkcriticality","linkcriticality","structure",["criticality_origins","civic_facilities"],["preparenetwork"],link,[("link_criticality.gpkg","critical")])
    add("odmatrix","odmatrix","structure",["representative_origins","destinations"],["preparenetwork"],od,[("od_matrix.gpkg",""),("od_matrix_lines.gpkg","")])
    add("odroutes","odroutes","structure",["representative_origins","destinations"],["preparenetwork"],routes,[("od_routes.gpkg",""),("od_route_lines.gpkg","")])
    add("serviceareas","serviceareas","access",["civic_facilities"],["preparenetwork"],service,[("service_areas.gpkg","areas")])
    add("nearestfacility","nearestfacility","access",["representative_origins","civic_facilities"],["preparenetwork"],nearest,[("nearest_facility.gpkg","demand")])
    add("accessscore","accessscore","access",["representative_origins","categories"],["preparenetwork"],access,[("access_score.gpkg","access")])
    add("buildingmetrics","buildingmetrics","buildings",["buildings"],[],buildings,[("building_metrics.gpkg","buildings")])
    add("tessellation","tessellation","buildings",["buildings","study_area"],[],tess,[("tessellation.gpkg","tessellation")])
    add("greenaccess","greenaccess","green",["representative_origins","green_spaces"],["preparenetwork"],green_access,[("green_access.gpkg","demand")])
    add("greenconnectivity","greenconnectivity","green",["green_spaces"],[],green_conn,[("green_connectivity.gpkg","patches")])
    add("heatriskgrid","heatriskgrid","heat",["buildings","green_spaces"],[],heat,[("heat_risk.gpkg","heat")])
    add("facilitylocation","facilitylocation","facility",["representative_origins","candidate_sites"],["preparenetwork"],facility,[("facility_location_sites.gpkg","sites")])
    add("extractinterventionsites","native:extractbyattribute","scenario",[],["facilitylocation"],extract_sites,[("intervention_sites.gpkg","")])
    add("mergeinterventioncivic","native:mergevectorlayers","scenario",["civic_facilities"],["extractinterventionsites"],merge_civic,[("intervention_civic.gpkg","")])
    add("accessscoreintervention","accessscore","scenario",["representative_origins"],["preparenetwork","mergeinterventioncivic"],access_intervention,[("access_score_intervention.gpkg","")])
    add("scenariosnapshotbaseline","scenariosnapshot","scenario",[],["accessscore"],snapshot_baseline,[("scenario_baseline.json","")])
    add("scenariosnapshotintervention","scenariosnapshot","scenario",[],["accessscoreintervention"],snapshot_intervention,[("scenario_intervention.json","")])
    add("scenariocompare","scenariocompare","scenario",[],["scenariosnapshotbaseline","scenariosnapshotintervention"],compare,[("scenario_compare.html","")])
    add("scenariorank","scenariorank","scenario",[],["scenariosnapshotbaseline","scenariosnapshotintervention"],rank,[("scenario_rank.html","")])
    add("performancereport","performancereport","scenario",[],["accessscoreintervention"],report,[("performance_report.html","")])
    return tuple(e)

MANIFEST = _manifest()


class PlanXRunner:
    def __init__(self, repo_root: Path, qgis_process: Path = QGIS_PROCESS, runner=subprocess.run, output_dir: Path | None = None, log_dir: Path | None = None):
        self.repo_root = Path(repo_root)
        self.qgis_process = Path(qgis_process)
        self._run = runner
        self.output_dir = Path(output_dir) if output_dir is not None else self.repo_root / "data/derived/planx/outputs"
        self.log_dir = Path(log_dir) if log_dir is not None else self.repo_root / "data/derived/planx/logs"

    def _available_layers(self, input_path: Path) -> set[str]:
        if not input_path.exists(): return set()
        try:
            with sqlite3.connect(input_path) as db:
                return {row[0] for row in db.execute("SELECT table_name FROM gpkg_contents")}
        except sqlite3.Error:
            return set()

    def check_plugin(self) -> str:
        plugin = self.repo_root / PLUGIN_RELATIVE
        if not plugin.exists(): raise PrerequisiteError(f"PlanX plugin missing: {plugin}")
        result = subprocess.run(["git", "-C", str(plugin), "rev-parse", "HEAD"], capture_output=True, text=True, check=False)
        commit = result.stdout.strip()
        if commit != EXPECTED_PLANX_COMMIT:
            raise PrerequisiteError(f"PlanX commit mismatch: expected {EXPECTED_PLANX_COMMIT}, found {commit or 'none'}")
        return commit

    def validate_qgis(self) -> None:
        if not self.qgis_process.is_file() or not os.access(self.qgis_process, os.X_OK):
            raise PrerequisiteError(f"qgis_process is not executable: {self.qgis_process}")
        env = self.environment()
        result = self._run([str(self.qgis_process), "list"], env=env, capture_output=True, text=True, check=False)
        if result.returncode != 0: raise PrerequisiteError(result.stderr.strip() or "qgis_process list failed")
        text = result.stdout or ""
        missing = [e.algorithm for e in MANIFEST if e.algorithm not in text]
        if missing: raise PrerequisiteError("PlanX algorithms unavailable: " + ", ".join(missing))

    def environment(self) -> dict[str, str]:
        env = os.environ.copy()
        env.update({"PROJ_LIB": "/Applications/QGIS.app/Contents/Resources/proj", "GDAL_DATA": "/Applications/QGIS.app/Contents/Resources/gdal", "QGIS_PREFIX_PATH": "/Applications/QGIS.app/Contents/MacOS", "QGIS_CUSTOM_CONFIG_PATH": str(self.repo_root / ".qgis")})
        return env

    def _output_exists(self, entry: ManifestEntry) -> bool:
        return all((self.output_dir / filename).exists() for filename, _ in entry.outputs)

    def run(self, input_path: Path, only: set[str] | None = None, reuse: bool = False, dry_run: bool = False) -> RunResult:
        input_path = Path(input_path)
        self.output_dir.mkdir(parents=True, exist_ok=True); self.log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        logs_path = self.log_dir / f"run_{stamp}.json"
        payload = {"status": "running", "started_at": stamp, "input": str(input_path), "plugin_commit": EXPECTED_PLANX_COMMIT, "commands": [], "steps": []}
        result = RunResult("running", logs_path)
        try:
            self.check_plugin(); self.validate_qgis()
        except PrerequisiteError as exc:
            result.status = "blocked"; result.failed = str(exc); payload.update(status=result.status, error=str(exc)); logs_path.write_text(json.dumps(payload, indent=2)); return result
        available = self._available_layers(input_path)
        selected = [
            e for e in MANIFEST
            if (e.enabled_by_default if not only else e.name in only or e.stage in only)
        ]
        required = set().union(*(set(e.required_layers) for e in selected)) if selected else set()
        missing = sorted(required - available)
        if missing:
            result.status = "blocked"; result.missing_layers = missing; payload.update(status=result.status, missing_layers=missing); logs_path.write_text(json.dumps(payload, indent=2)); return result
        completed = set()
        for entry in selected:
            missing = sorted(set(entry.required_layers) - available)
            if missing:
                result.status="blocked"; result.missing_layers=missing; result.failed=f"{entry.name}: missing {', '.join(missing)}"; break
            if any(dep not in completed and not self._output_exists(next(x for x in MANIFEST if x.name == dep)) for dep in entry.dependencies):
                result.status="blocked"; result.failed=f"{entry.name}: dependency output missing"; break
            if reuse and self._output_exists(entry): result.skipped.append(entry.name); completed.add(entry.name); continue
            command = build_qgis_command(self.qgis_process, entry.algorithm, entry.parameters(input_path, self.output_dir)); result.commands.append(command); payload["commands"].append(command)
            if dry_run: completed.add(entry.name); continue
            proc = self._run(command, env=self.environment(), capture_output=True, text=True, check=False)
            step = {"name": entry.name, "returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}; payload["steps"].append(step)
            if proc.returncode != 0: result.status="failed"; result.failed=entry.name; break
            completed.add(entry.name)
        else: result.status = "dry-run" if dry_run else "ok"
        payload.update(status=result.status, skipped=result.skipped, missing_layers=result.missing_layers, error=result.failed)
        logs_path.write_text(json.dumps(payload, indent=2)); result.logs_path = logs_path; return result
