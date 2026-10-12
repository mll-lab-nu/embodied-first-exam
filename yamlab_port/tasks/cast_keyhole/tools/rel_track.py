"""Relative configuration (silver in the gold plate frame) along a run vs the route: bar point (plate units)
and rotation from nominal, every N steps.  usage: python rel_track.py <tier> <run_dir> [from] [every]"""
import json, sys
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
sys.path.insert(0, str(Path(__file__).resolve().parent))
import keyhole_geometry as kg
import plan2 as pl
from layout import Scene, T_from
from route_check import Checker
tier, run = sys.argv[1], Path(sys.argv[2])
a = int(sys.argv[3]) if len(sys.argv) > 3 else 0
ev = int(sys.argv[4]) if len(sys.argv) > 4 else 10
sc = Scene(tier); REL = pl.Relative(sc.record, tier); ch = Checker(sc.record)
z = np.load(run / "states.npz")
ph = {p["start_step"]: p["name"] for p in json.load(open(run / "metrics.json"))["phases"]}
for i in range(a, len(z["keyhole_gold"]), ev):
    T = {}
    for n in kg.NAMES:
        st = z[f"keyhole_{n}"][i]
        T[n] = T_from(Rotation.from_quat(st[[4, 5, 6, 3]]), st[:3]) @ sc.T_part_plate[n]
    r, c = REL.measured(T["gold"], T["silver"])
    rel = (r * REL.r0.inv())
    names = [v for k, v in ph.items() if k <= i]
    print(i, names[-1] if names else "", "bar(units)", (c * 1000 / 3).round(2), "rot vs nominal (deg)",
          np.degrees(rel.as_rotvec()).round(1), "clear mm", round(ch.distance(r, c) * 1000, 2))
