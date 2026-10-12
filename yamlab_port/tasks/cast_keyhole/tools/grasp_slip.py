"""In-hand slip: pose of each plate relative to its holding link_6 over time, vs the value at a reference step.

usage: python grasp_slip.py <run_dir> [ref_step]   (default ref: start of the 'lift' phase)
"""
import json
import sys

import numpy as np
from scipy.spatial.transform import Rotation

run = sys.argv[1]
z = np.load(f"{run}/states.npz")
ph = json.load(open(f"{run}/metrics.json"))["phases"]
starts = {p["name"]: p["start_step"] for p in ph}
ref = int(sys.argv[2]) if len(sys.argv) > 2 else starts.get("lift", 0)


def T(st):
    M = np.eye(4); M[:3, :3] = Rotation.from_quat(st[[4, 5, 6, 3]]).as_matrix(); M[:3, 3] = st[:3]
    return M


for plate, arm in (("keyhole_gold", "left_arm"), ("keyhole_silver", "right_arm")):
    rel = [np.linalg.inv(T(z[arm + "_link6"][i])) @ T(z[plate][i]) for i in range(len(z[plate]))]
    r0 = rel[min(ref, len(rel) - 1)]
    print(plate, "relative to", arm, "link_6, from step", ref)
    for name, s in sorted(starts.items(), key=lambda kv: kv[1]) + [("end", len(rel) - 1)]:
        s = min(s, len(rel) - 1)
        if s < ref:
            continue
        d = np.linalg.inv(r0) @ rel[s]
        print(f"   {name:10s} step {s:5d}: slip {np.linalg.norm(d[:3, 3]) * 1000:7.2f} mm "
              f"{np.degrees(Rotation.from_matrix(d[:3, :3]).magnitude()):6.2f} deg")
