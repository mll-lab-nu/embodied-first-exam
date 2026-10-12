"""Clearance along the 'align' motion (silver relative to gold, measured settled configuration -> nominal start
configuration) for a logged state.  Prints the min signed distance per strategy.

usage: python align_check.py <tier> <states.npz> <step>
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation, Slerp

sys.path.insert(0, str(Path(__file__).resolve().parent))
import keyhole_geometry as kg
import plan2 as pl
import route as rt
from layout import Scene, T_from
from route_check import Checker

tier, path, k = sys.argv[1], sys.argv[2], int(sys.argv[3])
sc = Scene(tier)
z = np.load(path)
Tp = {}
for n in kg.NAMES:
    st = z[f"keyhole_{n}"][k]
    Tp[n] = T_from(Rotation.from_quat(st[[4, 5, 6, 3]]), st[:3]) @ sc.T_part_plate[n]
REL = pl.Relative(sc.record, tier)
ch = Checker(sc.record)
r_m, c_m = REL.measured(Tp["gold"], Tp["silver"])
r0, c0 = REL.r0, REL.c0
print("measured relative: rot from nominal (deg)", round(np.degrees((r_m * r0.inv()).magnitude()), 1),
      "rotvec(gold frame)", (r_m * r0.inv()).as_rotvec().round(3), "bar offset (mm)", ((c_m - c0) * 1000).round(1))
print("clearance at measured (mm)", round(ch.distance(r_m, c_m) * 1000, 2))
sl = Slerp([0, 1], Rotation.from_quat([r_m.as_quat(), r0.as_quat()]))
strategies = {
    "simultaneous": lambda u: (sl(u), c_m + u * (c0 - c0 + c0 - c_m)),
    "translate_then_rotate": lambda u: (r_m, c_m + 2 * u * (c0 - c_m)) if u < .5 else (sl(2 * u - 1), c0),
    "rotate_then_translate": lambda u: (sl(2 * u), c_m) if u < .5 else (r0, c_m + (2 * u - 1) * (c0 - c_m)),
}
for name, f in strategies.items():
    d = [ch.distance(*f(u)) for u in np.linspace(0, 1, 81)]
    i = int(np.argmin(d))
    print(f"{name:24s} min {min(d)*1000:7.2f} mm at u={i/80:.3f}")
