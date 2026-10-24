#!/usr/bin/env python3
"""Run the height-independent PlanX isovist pilot without touching legacy outputs."""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

QGIS_PROCESS = Path("/Applications/QGIS.app/Contents/MacOS/bin/qgis_process")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["isovistfield"], required=True)
    parser.add_argument("--input", type=Path, required=True, help="Projected GPKG containing a buildings layer")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cell", type=float, default=25.0)
    parser.add_argument("--rays", type=int, default=36)
    parser.add_argument("--max-dist", type=float, default=200.0)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if not args.input.exists():
        raise SystemExit(f"input not found: {args.input}")
    if args.output.exists() and not args.overwrite:
        raise SystemExit(f"refusing to overwrite existing output: {args.output}; use --overwrite explicitly")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(QGIS_PROCESS), "run", "planx:isovistfield",
        f"--BUILDINGS={args.input}|layername=buildings",
        f"--CELL={args.cell:g}", f"--N_RAYS={args.rays}", f"--MAX_DIST={args.max_dist:g}",
        f"--OUT_POINTS={args.output}",
    ]
    print("COMMAND", " ".join(command))
    result = subprocess.run(command, check=False, text=True)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
