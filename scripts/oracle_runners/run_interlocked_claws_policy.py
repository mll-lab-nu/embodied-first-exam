#!/usr/bin/env python3
"""Claws medium geometry and friction-pregrasp policy manager entry point."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.oracle_runners.run_rigid_reference_policy import main

if __name__ == "__main__":
    main("interlocked_claws")
