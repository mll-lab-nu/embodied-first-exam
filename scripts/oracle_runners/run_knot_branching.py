#!/usr/bin/env python3
"""Search knot decisions with checkpoints, upstream backtracking and replay-based resume."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from topogym.planning.knot_untying.cli import main

if __name__ == "__main__":
    raise SystemExit(main(branching=True))
