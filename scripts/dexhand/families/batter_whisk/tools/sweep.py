"""Authoring only: run author_arm phases for many parameter sets in one process (snapshot/restore).

    python tools/sweep.py --until left_hold --grid '{"l_tip_in": [0.009, 0.011], "l_tip_below": [0.012, 0.02]}'
"""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tools"))

import author_arm  # noqa: E402
from runtime import Session  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hand", default="sharpa")
    ap.add_argument("--until", default=None)
    ap.add_argument("--base", default="{}")
    ap.add_argument("--grid", default="{}")
    ap.add_argument("--extra", type=int, default=50, help="hold steps after the phase")
    args = ap.parse_args()
    s = Session(hand=args.hand)
    snap = s.snapshot()
    base = json.loads(args.base)
    grid = json.loads(args.grid)
    keys = list(grid)
    for values in itertools.product(*[grid[k] for k in keys]) if keys else [()]:
        params = {**base, **dict(zip(keys, values))}
        s.restore(snap)
        c = author_arm.Controller(s, params)
        c.run(args.until)
        if not s.done:
            c.hold(args.extra, "extra")
        st = s.status()
        f = s.checker.f
        print(json.dumps({"params": dict(zip(keys, values)), "reason": st["reason"], "stage": st["stage"],
                          "steps": s.steps, "rev": round(st["revolutions"], 2), "tilt": round(st["max_bowl_tilt_deg"], 2),
                          "slide": round(st["max_bowl_slide_m"], 4), "holder_bowl": f["holder_bowl"],
                          "hand_whisk": f["hand_whisk"], "detail": st["failure_detail"]}, default=str), flush=True)


if __name__ == "__main__":
    main()
