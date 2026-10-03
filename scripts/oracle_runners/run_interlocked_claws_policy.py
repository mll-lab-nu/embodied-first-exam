#!/usr/bin/env python3
"""Claws manager: assisted low-tier references and legacy tier diagnostics."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.oracle_runners.run_rigid_reference_policy import main

if __name__ == "__main__":
    import argparse
    selector = argparse.ArgumentParser(add_help=False)
    selector.add_argument("--variant", default="medium")
    selected, _ = selector.parse_known_args()
    if selected.variant in {"very_easy", "easier"}:
        from scripts.oracle_runners.run_interlocked_claws_simplified_policy import main as simplified_main
        simplified_main()
    else:
        main("interlocked_claws")
