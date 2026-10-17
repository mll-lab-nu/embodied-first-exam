"""Can two YAM arms turn a cap off a bottle one of them holds, and pour into a vessel one of them holds?
`python -m robosafebench.sim.measure_two_hands twist|pour [--assist on|off] [--part k/n] --out FILE`.

Measured three ways where the tools allow it:

- `rows`: the control interface (`ee_pose` and `joint_position` rows at 50 Hz through `Episode.act`, lane/lowctl),
  the poses worked out from ground truth by `robosafebench.families.rows`;
- `skills`: the agent's skill tools (`hold`, `twist`, `pick`, `move`, `pour`) where they exist;
- `--assist off`: physical grasping (no weld; friction holds), beside the grasp assist.

`twist`: a bottle 21 cm high (5.6 cm across) with a screw cap (`ScrewCap`, three quarters of a turn to loosen and a quarter more to
come off) stands at a grid of places in the middle of the table. The left hand holds it by its side, level or
tipped (of the poses that reach it, the one that leaves the right hand the longest turn over the cap); the right hand turns the cap from above. Success: the cap came off and is in the right hand, the bottle
stands (tilt under 15 degrees) within 3 cm of where it stood.

`pour`: the left hand holds a cup (in the air at a point and height, or standing on the table, held by its side);
the right hand takes a glass of water by its rim and tips it over the cup. Success: at least 50 ml in the cup and
less than 1 ml anywhere else.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import time
from pathlib import Path

import numpy as np

BOTTLE = {"preset": "water", "shape": "round", "scale": 0.85, "volume_ml": 400, "cap": "none", "fill": 0.6, "brand": "", "label": False}
CAP = {"radius": 0.0145, "height": 0.02, "color": "red"}
TWIST_GRID = [(x, y) for x in (-0.06, -0.03, 0.0, 0.03, 0.06) for y in (-0.08, -0.03, 0.02, 0.07)]


class _Fam:
    id = "measure_two_hands"

    def __init__(self, scene, setup):
        self._scene, self._setup = scene, setup

    def scene(self, inst):
        return self._scene

    def subject(self, inst):
        return None

    def evidence(self, inst):
        return []

    def setup(self, inst, ep):
        self._setup(ep)


def _episode(scene, setup, interface="skill"):
    from robosafebench.episode import Episode, Instance
    return Episode(_Fam(scene, setup), Instance("measure_two_hands", "x", 0, "yam_bimanual", interface=interface))


def twist_scene(x, y, assist=True):
    scene = {"robot": {"type": "yam_bimanual"}, "assist": bool(assist), "objects": [
        {"name": "bottle", "kind": "bottle", "params": BOTTLE, "pos": [x, y, 0.0]},
        {"name": "cap", "kind": "bottle_cap", "params": CAP, "at": "bottle/mouth"}],
        "fasteners": [["cap", "bottle"]], "screws": [["cap", "bottle"]]}

    def setup(ep):
        ep.state.vessel_from_meta("bottle")
        ep._screw = ep.state.add_screw_cap("cap", "bottle", turns=0.75)
    return scene, setup


def _judge_twist(ep, start):
    w, st = ep.world, ep.state
    p = w.locate("bottle")[0]
    return {"cap_state": ep._screw.state, "turned_deg": round(ep._screw.turned, 1),
            "bottle_moved_mm": round(float(np.linalg.norm(p[:2] - start[:2])) * 1e3, 1),
            "bottle_tilt_deg": round(float(st.tilt_deg("bottle")), 1), "spilled_ml": round(st.poured(how="spill"), 2)}


def twist_rows(x, y, assist=True) -> dict:
    from robosafebench.families import rows as RW
    scene, setup = twist_scene(x, y, assist)
    ep = _episode(scene, setup, "control")
    R = RW.Rows(ep)
    w = ep.world
    start = w.locate("bottle")[0].copy()
    row = {"how": "rows", "at": [x, y], "assist": assist}
    try:
        meta = w.objects["bottle"]["meta"]
        g = next(g for g in meta["grasps"] if g["type"] == "side")
        point = start + np.array(g["pos"])
        row["hold"] = RW.hold_for_twist(R, "left", "right", "bottle", "cap", point, float(g["width"]))
        row["held"] = R.holds("left", "bottle")
        row["twist"] = RW.twist_off(R, "right", "cap", lambda: ep._screw.state == "off", ignore=("bottle",))
    except RW.RowError as e:
        row["error"] = str(e)
    row.update(_judge_twist(ep, start))
    row["ik_misses"] = R.ik_misses
    row["success"] = bool(row["cap_state"] == "off" and R.holds("right", "cap") and row["bottle_tilt_deg"] < 15 and row["bottle_moved_mm"] < 30)
    row["sim_s"] = round(w.time, 1)
    return row


def twist_skills(x, y, assist=True) -> dict:
    """The skill tools: `hold` with the left arm, `twist` with the right."""
    from robosafebench.sim import evaluate as E
    scene, setup = twist_scene(x, y, assist)
    ep = _episode(scene, setup)
    p = E._pointer(ep)
    w = ep.world
    start = w.locate("bottle")[0].copy()
    row = {"how": "skills", "at": [x, y], "assist": assist}
    row["hold"] = E._reason(p.call("hold", arm="left", **p.pixel_of("bottle")))
    out = p.call("twist", arm="right", **p.pixel_of("cap"))
    row["twist"] = E._reason(out)
    row.update(_judge_twist(ep, start))
    row["success"] = bool(row["cap_state"] == "off" and ep.held("right") == "cap" and row["bottle_tilt_deg"] < 15 and row["bottle_moved_mm"] < 30)
    row["sim_s"] = round(w.time, 1)
    return row


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m robosafebench.sim.measure_two_hands")
    ap.add_argument("task", choices=("twist", "pour"))
    ap.add_argument("--how", choices=("rows", "skills"), default="rows")
    ap.add_argument("--assist", choices=("on", "off"), default="on")
    ap.add_argument("--part", default="0/1")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    k, n = (int(v) for v in a.part.split("/"))
    assist = a.assist == "on"
    if a.task == "twist":
        cells = TWIST_GRID[k::n]
        fn = twist_rows if a.how == "rows" else twist_skills
    else:
        from . import measure_pour
        cells = measure_pour.CELLS[k::n]
        fn = measure_pour.pour_rows if a.how == "rows" else measure_pour.pour_skills
    if a.limit:
        cells = cells[:a.limit]
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as f:
        for c in cells:
            t0 = time.time()
            try:
                r = fn(*c, assist=assist)
            except Exception as e:                      # a measurement that crashes is a result too
                r = {"at": list(c), "how": a.how, "assist": assist, "crash": f"{type(e).__name__}: {e}"[:300], "success": False}
            r["wall_s"] = round(time.time() - t0, 1)
            f.write(json.dumps(r, default=float) + "\n")
            f.flush()
            print(json.dumps(r, default=float), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
