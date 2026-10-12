"""Offline unit test of the ported goal check (pure numpy, no simulator).

Rigidly translates the start cable along the ring axis (strands straightened toward the axis or left
fanned) and checks the predicate: combed + pushed through -> reached; fanned -> never reached.
"""
import json, os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "yamlab_task", "envs", "tasks"))
from fiber_bundling_goal import FiberGoal
tier = sys.argv[1] if len(sys.argv) > 1 else "very_easy"
lay = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", tier, "layout_world.json")))
succ = dict(maximum_bend_deg=60., ring_plane_half_thickness_m=1e-6, below_table_margin_m=0.1)
n = np.array(lay["ring"]["normal"]); c = np.array(lay["ring"]["center"])
start = {k: (np.array(v["origin"]), np.array(v["R"])) for k, v in lay["links"].items()}


def combed(pose, radius):
    """Re-lay every strand straight along the axis at the given radial offset (keeps segment lengths)."""
    out = dict(pose)
    p5, R5 = pose["trunk_05"]; front = p5+R5[:, 0]*0.04
    for names in lay["fibers"]["names"]:
        root = pose[names[0]][0]; rad = root-front; rad -= (rad @ n)*n; u = rad/np.linalg.norm(rad)
        for j, nm in enumerate(names):
            L = lay["links"][nm]["length"]
            o = front+u*radius+n*(j*L)
            out[nm] = (o, pose[nm][1]*0+np.column_stack([n, np.cross([0, 0, 1], n), np.cross(n, np.cross([0, 0, 1], n))]))
    return out


def run(pose0, shift_to, steps=300):
    g = FiberGoal(lay, succ); g.reset(start)
    s0 = (pose0["trunk_05"][0]+pose0["trunk_05"][1][:, 0]*0.04-c) @ n
    res = None
    for k in range(steps+1):
        d = (shift_to-s0)*k/steps
        pose = {nm: (p+n*d, R) for nm, (p, R) in pose0.items()}
        zs = np.array([p[2] for p, _ in pose.values()])
        res = g.evaluate(pose, zs)
    return res


for name, pose, to in [("combed r=9mm, front to +21mm", combed(start, 0.009), 0.021),
                       ("combed r=9mm, front to +12mm (not clear)", combed(start, 0.009), 0.012),
                       ("start fan (31 mm), front to +21mm", start, 0.021),
                       ("combed r=15mm (guided band), front +21", combed(start, 0.015), 0.021),
                       ("combed r=19mm (outside hole), front +21", combed(start, 0.019), 0.021)]:
    reached, fail, m = run(pose, to)
    print(f"{name:45s} reached={reached} fail={fail} complete={m.get('strands_complete')} front_clear={m.get('front_sheath_clear')} "
          f"bend={m.get('maximum_bend_deg', 0):.1f}")
