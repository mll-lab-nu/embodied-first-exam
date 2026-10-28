#!/usr/bin/env python3
"""Losslessly bundle NPY artifacts in explicitly inactive experiment runs."""

import argparse
import json
from pathlib import Path

from humanclaw_bench.experiments.artifacts import compact_arrays


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--inactive", action="store_true", help="Confirm all selected runs have no active writers")
    parser.add_argument("--remove-loose", action="store_true", help="Remove redundant NPY files only after committed copies are verified")
    args = parser.parse_args()
    if not args.inactive:
        parser.error("Check that jobs are stopped, then pass --inactive")
    runs = [args.root] if (args.root / "run.json").is_file() else sorted(path.parent for path in args.root.rglob("run.json") if path.parent.name.startswith("run_"))
    for directory in runs:
        # Idempotent reruns retain the earlier migration receipt.
        if not next((directory / "artifacts").glob("*.npy"), None):
            continue
        result = compact_arrays(directory, inactive=True, remove_loose=args.remove_loose)
        print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
