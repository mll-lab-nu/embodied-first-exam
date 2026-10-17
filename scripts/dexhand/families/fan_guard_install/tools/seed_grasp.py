"""Authoring: solve the hub-cap grasp seeds (grasp, squeeze, open) for one hand and save them under tools/seeds/.

Thumb on the cap's near (-x) edge, index and middle on its far (+x) edge, fingertip pads just below the cap top, palm
down; collision margins against the nearby dish wires and the worktop. Kinematics only (no simulation step).
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from fanplan import Kinematics, hand_frame, stage_angles  # noqa: E402
from geometry import CAP_AXIAL, CAP_HALF, CAP_RADIUS, GUARD_REST  # noqa: E402
from runtime import Session  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--hand", default="sharpa")
    p.add_argument("--pad", type=float, default=0.0085, help="fingertip pad half-thickness (m)")
    p.add_argument("--below-top", type=float, default=0.006)
    p.add_argument("--squeeze", type=float, default=0.006)
    p.add_argument("--open", type=float, default=0.014)
    p.add_argument("--init", help="optional initial row (.npy) for the wrist guess")
    p.add_argument("--out-dir", default="")
    p.add_argument("--corner", action="store_true")
    p.add_argument("--yaw", type=float, default=0.0, help="grasp layout yaw about the vertical (deg)")
    p.add_argument("--corner-gap", type=float, default=0.0066)
    p.add_argument("--margin", type=float, default=0.002)
    args = p.parse_args()
    s = Session(hand=args.hand)
    m = s.model
    k = Kinematics(s)
    cap = GUARD_REST + np.array([0, 0, CAP_AXIAL])
    zc = cap[2] + CAP_HALF - args.below_top
    r = CAP_RADIUS + args.pad
    if args.corner:
        # Source 6 mm badge: the fingertip pads rest on the dish spokes just outside the badge and press on its
        # top edge (contact normal ~35 deg above horizontal; fingertip friction carries the guard).
        r = CAP_RADIUS + args.corner_gap
        spoke_z = GUARD_REST[2] + 0.047 * (1 - r / 0.1845) ** 0.70
        zc = spoke_z + args.pad
    yaw = np.radians(args.yaw)
    Rz = np.array([[np.cos(yaw), -np.sin(yaw), 0], [np.sin(yaw), np.cos(yaw), 0], [0, 0, 1]])
    layout = {"thumb": (-r - 0.001, 0.0), "index": (r, 0.014), "middle": (r, -0.012)}
    targets = {n: cap + Rz @ np.array([dx, dy, zc - cap[2]]) for n, (dx, dy) in layout.items()}
    q0 = np.array(s.initial_targets)
    q0[3:6] = stage_angles(Rz @ hand_frame([1, 0, -0.05], [0, 0.05, -1]))
    q0[:3] = cap + Rz @ np.array([-0.03, 0.0, 0.09])
    if args.init:
        q0[:6] = np.load(args.init)[:6]
    sl = k.slices
    lo, hi = m.actuator_ctrlrange.T
    q0[6:] = np.clip(0.3 * (lo[6:] + hi[6:]) / 2 + 0.3, lo[6:], hi[6:])
    for name in ("ring", "pinky"):
        for j in sl[name]:
            q0[j] = lo[j] + 0.8 * (hi[j] - lo[j]) if hi[j] > 1.0 else 0.0
    avoid = [g for g in range(m.ngeom) if s.checker.guard_geom[g] and np.linalg.norm(s.data.geom_xpos[g] - cap) < 0.11
             and m.geom(g).name != "front_badge"] + [m.geom("table_top").id]
    var = list(range(6)) + [j for n in ("thumb", "index", "middle") for j in sl[n]]
    if args.corner:  # the pads rest on the spokes next to the badge: avoid only the rim, hoops and worktop
        avoid = [g for g in avoid if "spoke" not in (m.geom(g).name or "")]
    q, cost = k.solve(q0, targets, var, avoid=avoid, reg=0.02, max_nfev=400, margin=args.margin)
    tips = k.fk(q)
    print("grasp cost", cost, {n: np.round((tips[n] - t) * 1000, 1).tolist() for n, t in targets.items()})
    fingers = [j for n in ("thumb", "index", "middle") for j in sl[n]]

    def shifted(delta):
        tt = {}
        for n in ("thumb", "index", "middle"):
            v = tips[n] - cap
            v[2] = 0
            v /= np.linalg.norm(v)
            tt[n] = tips[n] + v * delta
        out, c = k.solve(q, tt, fingers, reg=0.001)
        return out, c

    squeeze, c1 = shifted(-args.squeeze)
    opened, c2 = shifted(args.open)
    print("squeeze cost", c1, "open cost", c2)
    out = Path(args.out_dir) if args.out_dir else HERE / "seeds"
    out.mkdir(exist_ok=True)
    prefix = "" if args.hand == "sharpa" else args.hand + "_"
    np.save(out / f"{prefix}grasp.npy", q)
    np.save(out / f"{prefix}squeeze.npy", squeeze)
    np.save(out / f"{prefix}open.npy", opened)
    print("saved", [str(out / f"{prefix}{n}.npy") for n in ("grasp", "squeeze", "open")])


if __name__ == "__main__":
    main()
