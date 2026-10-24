#!/usr/bin/env python3
"""Run bounded non-space-syntax PlanX stages on current Ahmedabad–Gandhinagar inputs."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ahmedabad_scanner.planx_runner import PlanXRunner

DEFAULT_STAGES = ",".join(
    [
        "preparenetwork",
        "networkcentrality",
        "streetmorphology",
        "deadends",
        "buildingmetrics",
        "greenconnectivity",
        "heatriskgrid",
        "serviceareas",
        "accessscore",
        "greenaccess",
        "facilitylocation",
        "extractinterventionsites",
        "mergeinterventioncivic",
        "accessscoreintervention",
        "scenariosnapshotbaseline",
        "scenariosnapshotintervention",
        "scenariocompare",
        "scenariorank",
        "performancereport",
    ]
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/derived/planx/ahmedabad-gandhinagar-planx-inputs.gpkg"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/derived/planx/ahmedabad-gandhinagar-outputs"))
    parser.add_argument("--log-dir", type=Path, default=Path("data/derived/planx/ahmedabad-gandhinagar-logs"))
    parser.add_argument("--only", default=DEFAULT_STAGES, help="Comma-separated stages; space syntax is never included by default.")
    parser.add_argument("--reuse", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    input_path = args.input if args.input.is_absolute() else ROOT / args.input
    output_dir = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    log_dir = args.log_dir if args.log_dir.is_absolute() else ROOT / args.log_dir
    only = {value.strip() for value in args.only.split(",") if value.strip()}
    if "spacesyntax" in only:
        raise SystemExit("spacesyntax is intentionally excluded from this current-study runner")
    result = PlanXRunner(ROOT, output_dir=output_dir, log_dir=log_dir).run(
        input_path, only=only, reuse=args.reuse, dry_run=args.dry_run
    )
    print(json.dumps({
        "status": result.status,
        "log": str(result.logs_path),
        "output_dir": str(output_dir),
        "commands": result.commands,
        "skipped": result.skipped,
        "missing_layers": result.missing_layers,
        "failed": result.failed,
    }, indent=2))
    return 0 if result.status in {"ok", "dry-run"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
