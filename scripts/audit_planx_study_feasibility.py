"""Audit PlanX stage feasibility for the current study-area input package."""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", type=Path, default=Path("data/derived/planx/ahmedabad-gandhinagar-planx-inputs.json"))
    parser.add_argument("--output", type=Path, default=Path("reports/ahmedabad_gandhinagar_planx_feasibility.json"))
    args = parser.parse_args()
    root = args.inputs.resolve().parent.parent.parent.parent
    summary = json.loads(args.inputs.read_text(encoding="utf-8"))
    counts = summary["counts"]
    source = summary["source_counts"]
    free_gb = shutil.disk_usage(root).free / (1024**3)
    stages = {
        "preparenetwork": {"decision": "attempt", "reason": "full current OSM highway line source is 58,824 exploded lines; PlanX noding is the required first network stage"},
        "networkcentrality": {"decision": "attempt", "reason": "sampled betweenness is configured at 500 sources; network remains the full current-study graph"},
        "streetmorphology": {"decision": "attempt", "reason": "network-only output with no building cardinality"},
        "deadends": {"decision": "attempt", "reason": "network-only output"},
        "buildingmetrics": {"decision": "attempt", "reason": "bounded to 30,000 selected footprints rather than 1,077,523"},
        "tessellation": {"decision": "skip", "reason": "30,000-building Voronoi seed construction is not accepted as a safe first full-area run; it is disabled in config"},
        "greenconnectivity": {"decision": "attempt", "reason": f"only {counts['green_spaces']} current OSM green polygons"},
        "heatriskgrid": {"decision": "attempt", "reason": "bounded building and green inputs; proxy only"},
        "serviceareas": {"decision": "attempt", "reason": f"{counts['civic_facilities']} mapped civic facilities and prepared network"},
        "accessscore": {"decision": "attempt", "reason": f"{counts['representative_origins']} deterministic origins and {source['osm_points'] + source['osm_polygons']} saved OSM point/polygon source features"},
        "greenaccess": {"decision": "attempt", "reason": f"{counts['representative_origins']} deterministic origins and {counts['green_spaces']} green polygons"},
        "facilitylocation": {"decision": "attempt", "reason": f"{counts['candidate_sites']} deterministic network-node candidates; exact audit disabled"},
        "scenario": {"decision": "attempt_if_dependencies_complete", "reason": "scenario stages reuse bounded access and facility-location outputs"},
        "spacesyntax": {"decision": "excluded", "reason": "explicit user exclusion; no space-syntax command is generated"},
    }
    report = {
        "generated_utc": datetime.now(UTC).isoformat(),
        "inputs": str(args.inputs),
        "study_area": summary["study_area"],
        "boundary": summary["boundary"],
        "source_counts": source,
        "input_counts": counts,
        "free_disk_gib_at_audit": round(free_gb, 3),
        "policy": "Use full current-study OSM network; use deterministic 30,000-footprint building subset; sample origins and candidate sites; stop or skip stages that exceed safe runtime or require unavailable amenity completeness.",
        "stages": stages,
        "limitations": summary["limitations"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
