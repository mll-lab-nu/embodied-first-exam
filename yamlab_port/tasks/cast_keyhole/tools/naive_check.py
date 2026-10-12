"""Naive disassembly check: pull the silver straight along the gold's -y (no key turn) from the nominal start
and report the first penetration (fcl signed distance on the exact convex cells).  usage: python naive_check.py <tier>"""
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import keyhole_geometry as kg
import route as rt
from route_check import Checker

tier = sys.argv[1]
rec = kg.load_record(tier)
ch = Checker(rec)
r0, c0 = rt.nominal_relative(rec)
for name, direction in (("pull_-y", np.array([0, -1, 0])), ("pull_+y", np.array([0, 1, 0])),
                        ("pull_-x", np.array([-1, 0, 0])), ("pull_+x", np.array([1, 0, 0])),
                        ("pull_+z", np.array([0, 0, 1])), ("pull_-z", np.array([0, 0, -1]))):
    hit = None
    for s in np.arange(0, 0.25, 0.0005):
        d = ch.distance(r0, c0 + direction * s)
        if d < 0:
            hit = (s, d); break
    print(f"{name}: " + (f"blocked after {hit[0]*1000:.1f} mm (penetration {-hit[1]*1000:.2f} mm)" if hit else "free for 250 mm"))
