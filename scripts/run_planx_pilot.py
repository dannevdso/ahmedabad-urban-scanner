#!/usr/bin/env python3
"""Run the Navrangpura PlanX pilot with resumable, logged QGIS steps."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ahmedabad_scanner.planx_runner import PlanXRunner


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/derived/planx/navrangpura-planx-inputs.gpkg"))
    parser.add_argument("--only", help="Comma-separated algorithm names or stages")
    parser.add_argument("--reuse", action="store_true", help="Skip steps whose stable outputs already exist")
    parser.add_argument("--dry-run", action="store_true", help="Validate prerequisites and print commands without running analyses")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    only = {item.strip() for item in args.only.split(",") if item.strip()} if args.only else None
    input_path = args.input if args.input.is_absolute() else REPO_ROOT / args.input
    result = PlanXRunner(REPO_ROOT).run(input_path, only=only, reuse=args.reuse, dry_run=args.dry_run)
    print(f"status={result.status}")
    print(f"log={result.logs_path}")
    for command in result.commands:
        print("COMMAND", " ".join(command))
    if result.skipped:
        print("skipped=" + ",".join(result.skipped))
    if result.missing_layers:
        print("missing_layers=" + ",".join(result.missing_layers), file=sys.stderr)
    if result.failed:
        print(result.failed, file=sys.stderr)
    return 0 if result.status in {"ok", "dry-run"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
