"""Measurements of the gliding G1 (docs/MOTION.md 10.4, "The gliding G1, measured"). Every number of that subsection
comes from one of these commands; they write JSON (and pictures) under `--out` and print Markdown tables.

    python -m embodied_safety_exam.sim.bodies.g1_measure reach --waist none          # where each hand's pinch point gets to, free space
    python -m embodied_safety_exam.sim.bodies.g1_measure reach --waist pitch         # the same with one waist joint kept (pitch | yaw)
    python -m embodied_safety_exam.sim.bodies.g1_measure heights                     # the lowest and highest pinch point, in 2 cm steps
    python -m embodied_safety_exam.sim.bodies.g1_measure furniture                   # at a counter, a table, a shelf: from how far
    python -m embodied_safety_exam.sim.bodies.g1_measure payload                     # what one hand can lift, from the force ranges
    python -m embodied_safety_exam.sim.bodies.g1_measure postures                    # rest, ready, level carry: the search
    python -m embodied_safety_exam.sim.bodies.g1_measure pictures                    # the body, its cameras, the postures; the logo test
    python -m embodied_safety_exam.sim.bodies.g1_measure report                      # the tables of MOTION 10.4 from the files above

How reach is measured. A grid of targets for the pinch point (2.5 cm forward, 5 cm sideways, 10 cm in height) and
four directions of the hand; for each target an inverse kinematics (`g1_kin.Chain.solve`: damped least squares on the
arm's seven joints, eight with a kept waist joint) is started from the postures found for the neighbouring targets and from the
six nearest of 300,000 random postures whose hand points roughly the right way. A target counts as reached when one of the
solutions found is free: no part of the robot nearer than 5 mm to another part, to the floor or to furniture (MuJoCo's
contact detection on the model's own collision shapes; the other arm in its rest posture). A target that is not
reached was not reached by this search, which is not a proof that it cannot be.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import mujoco
import numpy as np

from . import g1_glide as G
from . import g1_kin as K
from . import gripper_parallel as _gripper

CLEARANCE = 0.005
P_PINCH = _gripper.DIMS.pinch
HEIGHTS = tuple(round(0.40 + 0.10 * i, 2) for i in range(9))
XS = tuple(round(-0.20 + 0.025 * i, 3) for i in range(39))          # forward of the pelvis axis
YS = tuple(round(-0.25 + 0.05 * i, 2) for i in range(20))           # to the left of it (the left hand's own side)
# directions of the left hand: where it points, and the closing directions tried (None: any turn about its axis)
DIRECTIONS = {
    "down": ((0.0, 0.0, -1.0), None),
    "forward": ((1.0, 0.0, 0.0), ((0.0, 1.0, 0.0), (0.0, -1.0, 0.0))),
    "outward": ((0.0, 1.0, 0.0), ((1.0, 0.0, 0.0), (-1.0, 0.0, 0.0))),
    "inward": ((0.0, -1.0, 0.0), ((1.0, 0.0, 0.0), (-1.0, 0.0, 0.0))),
}
WAIST = {"none": (), "pitch": ("waist_pitch_joint",), "yaw": ("waist_yaw_joint",)}


# ---- the search ---------------------------------------------------------------------------------------------------------------
class Library:
    """Random postures of a chain with where they put the hand: seeds for the solver."""

    def __init__(self, chain: K.Chain, n: int, rng: np.random.Generator):
        self.q = rng.uniform(chain.lo, chain.hi, size=(n, len(chain.lo)))
        self.p, self.z, self.y = np.empty((n, 3)), np.empty((n, 3)), np.empty((n, 3))
        for i in range(n):
            chain.d.qpos[chain.q_adr] = self.q[i]
            mujoco.mj_kinematics(chain.m, chain.d)
            self.p[i] = chain.d.site_xpos[chain.site]
            r = chain.d.site_xmat[chain.site].reshape(3, 3)
            self.z[i], self.y[i] = r[:, 2], r[:, 1]
        self._subsets: dict = {}

    def subset(self, z, y=None) -> np.ndarray:
        key = (tuple(float(v) for v in z), None if y is None else tuple(float(v) for v in y))
        if key not in self._subsets:
            mask = self.z @ np.asarray(z, dtype=np.float64) > 0.7
            if y is not None:
                mask &= self.y @ np.asarray(y, dtype=np.float64) > 0.3
            if len(self._subsets) > 64:                 # arbitrary directions (a scripted grasp): do not keep them all
                return np.where(mask)[0]
            self._subsets[key] = np.where(mask)[0]
        return self._subsets[key]

    def seeds(self, pos, z, y=None, k: int = 6, within: float = 0.12) -> list:
        idx = self.subset(z, y)
        if len(idx) == 0:
            return []
        dist = np.linalg.norm(self.p[idx] - pos, axis=1)
        order = np.argsort(dist)[:k]
        return [self.q[idx[i]] for i in order if dist[i] < within]


def reach_map(chain: K.Chain, lib: Library, xs, ys, zs, directions=DIRECTIONS, log=None) -> dict:
    """For each direction an array [height, x, y] of 0 (no posture found), 1 (postures found, none free) or 2 (free),
    and the free postures themselves."""
    out, sols = {}, {}
    for name, (z, closings) in directions.items():
        grid = np.zeros((len(zs), len(xs), len(ys)), dtype=np.int8)
        t0 = time.time()
        below: dict = {}                    # the postures found one height lower, as seeds
        for zi, h in enumerate(zs):
            for yi, y in enumerate(ys):
                last = None
                for xi, x in enumerate(xs):
                    pos = np.array([x, y, h])
                    best = 0
                    for cy in (closings or (None,)):
                        rot = None if cy is None else K.frame(z, cy)
                        near = [s for s in (last, below.get((xi, yi)), below.get((xi - 1, yi)), below.get((xi, yi - 1))) if s is not None]
                        seeds = near + lib.seeds(pos, z, cy)
                        found = None
                        for seed in seeds:
                            q = chain.solve(pos, rot=rot, z=None if rot is not None else np.asarray(z), seed=seed, iters=60)
                            if q is None:
                                continue
                            best = max(best, 1)
                            if chain.free(q):
                                found = q
                                break
                        if found is not None:
                            best = 2
                            last = found
                            sols[(name, zi, xi, yi)] = found
                            break
                    grid[zi, xi, yi] = best
                    if best < 2:
                        last = None
            below = {(xi, yi): q for (n, z_, xi, yi), q in sols.items() if n == name and z_ == zi}
        out[name] = grid
        if log:
            log(f"  {name}: {int((grid == 2).sum())} free, {int((grid == 1).sum())} only colliding, of {grid.size} targets ({time.time() - t0:.0f} s)")
    return {"grid": out, "solutions": sols}


def summarise(grid: np.ndarray, xs, ys, zs) -> list:
    """Per height: how many targets, the span forward (x), sideways (y) and from the pelvis axis (r) of the reached ones,
    and the span forward on the line ahead of the shoulder (y = 0.15 m)."""
    xs, ys = np.asarray(xs), np.asarray(ys)
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    R = np.hypot(X, Y)
    yi_sh = int(np.argmin(np.abs(ys - 0.15)))
    rows = []
    for zi, h in enumerate(zs):
        ok = grid[zi] == 2
        row = {"height": h, "targets": int(ok.sum()), "only_colliding": int((grid[zi] == 1).sum())}
        if ok.any():
            row.update({"x": [float(X[ok].min()), float(X[ok].max())], "y": [float(Y[ok].min()), float(Y[ok].max())],
                        "r": [round(float(R[ok].min()), 3), round(float(R[ok].max()), 3)]})
            front = ok & (X >= 0.0)
            if front.any():
                row["r_front"] = [round(float(R[front].min()), 3), round(float(R[front].max()), 3)]
            line = ok[:, yi_sh]
            if line.any():
                row["x_ahead_of_shoulder"] = [float(xs[line].min()), float(xs[line].max())]
                run = _longest_run(line)
                row["x_ahead_of_shoulder_unbroken"] = [float(xs[run[0]]), float(xs[run[1]])]
        rows.append(row)
    return rows


def _longest_run(mask) -> tuple:
    best, start = (0, -1), None
    for i, v in enumerate(list(mask) + [False]):
        if v and start is None:
            start = i
        if not v and start is not None:
            if i - start > best[1] - best[0] + 1 or best[1] < 0:
                best = (start, i - 1)
            start = None
    return best


def _model(waist: tuple, extend=None, rest=None):
    m, changes = G.build(waist=waist, extend=extend)
    ix = G.index(m)
    K.set_margin(m, ix, CLEARANCE)
    chain = K.Chain(m, ix, "left")
    rest = rest or G.STAND
    G.set_posture(m, chain.d, ix, left=rest["left"], right=rest["right"])
    mujoco.mj_forward(m, chain.d)
    return m, ix, chain


def cmd_reach(args) -> None:
    waist = WAIST[args.waist]
    log = lambda s: print(s, flush=True)       # noqa: E731
    m, ix, chain = _model(waist)
    rng = np.random.default_rng(0)
    t0 = time.time()
    lib = Library(chain, args.library, rng)
    log(f"waist {args.waist}: library of {args.library} postures in {time.time() - t0:.0f} s")
    directions = {k: v for k, v in DIRECTIONS.items() if k in args.directions}
    res = reach_map(chain, lib, XS, YS, HEIGHTS, directions, log=log)
    out = {"waist": args.waist, "clearance": CLEARANCE, "xs": XS, "ys": YS, "heights": HEIGHTS, "library": args.library,
           "directions": {k: summarise(g, XS, YS, HEIGHTS) for k, g in res["grid"].items()}}
    # the right hand: the same search on a thinned grid, mirrored, to see that it is the left hand's mirror image
    if args.waist == "none":
        rchain = K.Chain(m, ix, "right")
        G.set_posture(m, rchain.d, ix, left=G.STAND["left"], right=G.STAND["right"])
        rlib = Library(rchain, args.library // 3, np.random.default_rng(1))
        agree = total = 0
        for name, (z, closings) in directions.items():
            zr = (z[0], -z[1], z[2])
            for zi in range(0, len(HEIGHTS), 2):
                for xi in range(8, len(XS), 4):
                    for yi in range(5, len(YS), 3):
                        pos = np.array([XS[xi], -YS[yi], HEIGHTS[zi]])
                        ok = False
                        for cy in (closings or (None,)):
                            cyr = None if cy is None else (cy[0], -cy[1], cy[2])
                            rot = None if cyr is None else K.frame(zr, cyr)
                            for seed in rlib.seeds(pos, zr, cyr, k=6):
                                q = rchain.solve(pos, rot=rot, z=None if rot is not None else np.asarray(zr), seed=seed, iters=60)
                                if q is not None and rchain.free(q):
                                    ok = True
                                    break
                            if ok:
                                break
                        total += 1
                        agree += int(ok == (res["grid"][name][zi, xi, yi] == 2))
        out["right_hand_mirror_check"] = {"targets": total, "same_answer": agree}
        log(f"right hand, mirrored targets: {agree} of {total} give the left hand's answer")
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / f"reach_{args.waist}.json").write_text(json.dumps(out, indent=1) + "\n")
    np.savez_compressed(args.out / f"reach_{args.waist}.npz", **{k: g for k, g in res["grid"].items()},
                        keys=np.array([list(map(str, k)) for k in res["solutions"]]), q=np.array(list(res["solutions"].values())))
    print(reach_markdown(out))


def reach_markdown(out: dict) -> str:
    def span(v):
        return f"{v[0]:.2f} to {v[1]:.2f}"

    L = [f"Waist: {out['waist']}.", "", "| Height of the pinch point (m) | " + " | ".join(out["directions"]) + " |",
         "|---|" + "---|" * len(out["directions"])]
    for i, h in enumerate(out["heights"]):
        cells = []
        for rows in out["directions"].values():
            r = rows[i]
            if not r["targets"]:
                cells.append("none" + (f" ({r['only_colliding']} colliding)" if r["only_colliding"] else ""))
            else:
                ahead = span(r["x_ahead_of_shoulder_unbroken"]) if "x_ahead_of_shoulder" in r else "none"
                cells.append(f"{span(r.get('r_front', r['r']))}; ahead of the shoulder {ahead}; {r['targets']}")
        L.append(f"| {h:.2f} | " + " | ".join(cells) + " |")
    return "\n".join(L)


def cmd_heights(args) -> None:
    """The lowest and the highest pinch point by how far ahead, in 2 cm steps of height, for a hand pointing down and a
    level hand pointing ahead (waist fixed), on lines 0.05 to 0.45 m to the side; in the report: the line 0.15 m to the
    side, in front of the shoulder."""
    m, ix, chain = _model(())
    lib = Library(chain, args.library, np.random.default_rng(0))
    hs = [round(0.40 + 0.02 * i, 2) for i in range(64)]                 # 0.40 to 1.66 m
    out = {"heights": [hs[0], hs[-1]], "step": 0.02, "directions": {}}
    for name in ("down", "forward"):
        z, closings = DIRECTIONS[name]
        spans = {}
        for y in (0.05, 0.15, 0.25, 0.35, 0.45):
            for x in (0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60):
                ok, last = [], None
                for h in hs:
                    pos, q = np.array([x, y, h]), None
                    for cy in (closings or (None,)):
                        rot = None if cy is None else K.frame(z, cy)
                        for seed in ([last] if last is not None else []) + lib.seeds(pos, z, cy):
                            cand = chain.solve(pos, rot=rot, z=None if rot is not None else np.asarray(z), seed=seed, iters=60)
                            if cand is not None and chain.free(cand):
                                q = cand
                                break
                        if q is not None:
                            break
                    last = q
                    if q is not None:
                        ok.append(h)
                if ok:
                    spans[f"{x:.2f},{y:.2f}"] = [min(ok), max(ok), len(ok)]
        out["directions"][name] = {"by_x_y": spans, "lowest": min(v[0] for v in spans.values()), "highest": max(v[1] for v in spans.values())}
        print(name, out["directions"][name]["lowest"], out["directions"][name]["highest"], flush=True)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "heights.json").write_text(json.dumps(out, indent=1) + "\n")


# ---- furniture -----------------------------------------------------------------------------------------------------------------
# The room's furniture as docs/ROOM_FAMILIES.md has it, reduced to what an arm can run into: the robot stands at the
# origin facing +x, the furniture's front edge `d` metres ahead of the pelvis axis.
SURFACES = {
    "counter": {"top": 0.90, "depth": 0.60, "width": 1.20, "solid": True},            # a block down to the floor
    "dining_table": {"top": 0.75, "depth": 0.80, "width": 1.40, "solid": False},      # a slab 4 cm thick: feet go under it
    "shelf_top": {"top": 0.80, "depth": 0.35, "width": 0.90, "solid": False, "shelf": True},
    "shelf_middle": {"top": 0.41, "depth": 0.35, "width": 0.90, "solid": False, "shelf": True},
}
ABOVE = {"down": (0.025, 0.10, 0.15, 0.20), "forward": (0.06, 0.15)}     # how far above the surface the pinch point is asked to be


def furniture(kind: str, d: float):
    """An `extend` for `g1_glide.build`: the piece of furniture `kind` with its front edge `d` ahead of the pelvis axis."""
    f = SURFACES[kind]
    box = mujoco.mjtGeom.mjGEOM_BOX

    def extend(s):
        wb = s.worldbody
        rgba = [0.80, 0.78, 0.74, 1]
        x0, w = d + f["depth"] / 2.0, f["width"] / 2.0
        if f.get("shelf"):                              # boards at 0.02, 0.41 and 0.80 m, two sides and a back
            for i, top in enumerate((0.02, 0.41, 0.80)):
                wb.add_geom(name=f"furniture_board{i}", type=box, size=[f["depth"] / 2.0, w, 0.01], pos=[x0, 0, top - 0.01], rgba=rgba)
            for i, sy in enumerate((-1, 1)):
                wb.add_geom(name=f"furniture_side{i}", type=box, size=[f["depth"] / 2.0, 0.01, 0.40], pos=[x0, sy * (w + 0.01), 0.40], rgba=rgba)
            wb.add_geom(name="furniture_back", type=box, size=[0.01, w, 0.40], pos=[d + f["depth"] + 0.01, 0, 0.40], rgba=rgba)
        elif f["solid"]:
            wb.add_geom(name="furniture_top", type=box, size=[f["depth"] / 2.0, w, f["top"] / 2.0], pos=[x0, 0, f["top"] / 2.0], rgba=rgba)
        else:
            wb.add_geom(name="furniture_top", type=box, size=[f["depth"] / 2.0, w, 0.02], pos=[x0, 0, f["top"] - 0.02], rgba=rgba)
    return extend


def cmd_furniture(args) -> None:
    waist = WAIST[args.waist]
    log = lambda s: print(s, flush=True)       # noqa: E731
    m0, ix0, chain0 = _model(waist)
    lib = Library(chain0, args.library, np.random.default_rng(0))
    out = {"waist": args.waist, "clearance": CLEARANCE, "above": ABOVE, "surfaces": {}}
    ys = (0.0, 0.10, 0.20, 0.30)
    for kind, f in SURFACES.items():
        # the nearest the body can stand: arms at rest, nothing within the clearance of the furniture
        nearest = None
        for d in np.arange(0.06, 0.45, 0.01):
            m, ix, chain = _model(waist, furniture(kind, float(d)))
            if chain.free():
                nearest = round(float(d), 2)
                break
        res = {"nearest_stand_off": nearest, "by_stand_off": {}}
        log(f"{kind}: the body clears it from {nearest} m")
        for d in sorted({nearest, 0.20, 0.30, 0.40} - {None}):
            if d < nearest:
                continue
            m, ix, chain = _model(waist, furniture(kind, d))
            xs = tuple(round(d + 0.025 * i, 3) for i in range(int(round(min(f["depth"], 0.45) / 0.025)) + 1))
            rows = {}
            for direction, above in ABOVE.items():
                zs = tuple(round(f["top"] + a, 3) for a in above)
                r = reach_map(chain, lib, xs, ys, zs, {direction: DIRECTIONS[direction]})["grid"][direction]
                for zi, a in enumerate(above):
                    ok = r[zi] == 2
                    depth = np.array(xs) - d
                    row = {"targets": int(ok.sum()), "only_colliding": int((r[zi] == 1).sum())}
                    if ok.any():
                        any_y = ok.any(axis=1)
                        run = _longest_run(any_y)
                        row["depth"] = [round(float(depth[any_y].min()), 3), round(float(depth[any_y].max()), 3)]
                        row["depth_unbroken"] = [round(float(depth[run[0]]), 3), round(float(depth[run[1]]), 3)]
                        row["y"] = [float(np.array(ys)[ok.any(axis=0)].min()), float(np.array(ys)[ok.any(axis=0)].max())]
                    rows[f"{direction}+{a}"] = row
            res["by_stand_off"][f"{d:.2f}"] = rows
            log(f"  from {d:.2f} m: " + "; ".join(f"{k}: {v.get('depth_unbroken', 'none')}" for k, v in rows.items()))
        out["surfaces"][kind] = res
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / f"furniture_{args.waist}.json").write_text(json.dumps(out, indent=1) + "\n")


# ---- what a hand can lift ---------------------------------------------------------------------------------------------------------
def max_load(chain: K.Chain, q) -> dict:
    """The heaviest thing at the pinch point that the chain's motors hold still in posture `q`: for each joint the
    torque gravity asks of it (the arm's own weight, the gripper, the load) must stay inside the joint's force range
    of the model file. Statics only: no acceleration, no friction, peak torque taken as holding torque."""
    m, d = chain.m, chain.d
    chain.put(q)
    d.qvel[:] = 0.0
    mujoco.mj_forward(m, d)
    own = d.qfrc_bias[chain.v_adr].copy()               # what the arm's own weight asks of each joint
    jz = chain.jacobian()[2]                            # how the pinch point's height changes with each joint
    jid = [int(np.where(m.jnt_dofadr == v)[0][0]) for v in chain.v_adr]
    limit = np.array([m.jnt_actfrcrange[j][1] for j in jid])
    g = -float(m.opt.gravity[2])
    best, binding = math.inf, None
    for i in range(len(own)):
        if abs(own[i]) > limit[i]:
            return {"kg": 0.0, "binding": m.joint(jid[i]).name, "own_torque": [round(float(v), 2) for v in own]}
        if abs(jz[i]) < 1e-9:
            continue
        cap = ((limit[i] - own[i]) if jz[i] > 0 else (-limit[i] - own[i])) / (g * jz[i])
        if cap < best:
            best, binding = cap, m.joint(jid[i]).name
    compensated = min((limit[i] / (g * abs(jz[i])) for i in range(len(own)) if abs(jz[i]) > 1e-9), default=math.inf)
    return {"kg": round(float(best), 2), "binding": binding, "own_torque": [round(float(v), 2) for v in own],
            "share_of_limit_unloaded": round(float(np.max(np.abs(own) / limit)), 2),
            "kg_with_own_weight_compensated": round(float(compensated), 2)}


def load_solutions(out: Path, waist: str = "none") -> dict:
    z = np.load(out / f"reach_{waist}.npz")
    return {(k[0], int(k[1]), int(k[2]), int(k[3])): q for k, q in zip(z["keys"], z["q"])}


def cmd_payload(args) -> None:
    m, ix, chain = _model(WAIST[args.waist])
    sols = load_solutions(args.out, args.waist)
    out = {"waist": args.waist, "limits": "the joints' force ranges in the model file: 25 N m (shoulder, elbow, wrist roll), 5 N m (wrist pitch and yaw)",
           "by_direction": {}, "postures": {}}
    for direction in DIRECTIONS:
        rows = []
        for zi, h in enumerate(HEIGHTS):
            kg = [(max_load(chain, q)) for (n, z, xi, yi), q in sols.items() if n == direction and z == zi]
            if not kg:
                continue
            v = np.array([k["kg"] for k in kg])
            bind = {}
            for k in kg:
                bind[k["binding"]] = bind.get(k["binding"], 0) + 1
            rows.append({"height": h, "postures": len(v), "kg_min": float(v.min()), "kg_median": float(np.median(v)), "kg_max": float(v.max()),
                         "binding": max(bind, key=bind.get)})
        out["by_direction"][direction] = rows
    for name, q in POSTURES.items():
        seed = K.arm_seed(chain, q)
        out["postures"][name] = max_load(chain, seed)
    # farthest forward at counter height, hand level: the worst lever
    far = [(XS[xi], q) for (n, zi, xi, yi), q in sols.items() if n == "forward" and HEIGHTS[zi] == 1.0]
    if far:
        x, q = max(far, key=lambda t: t[0])
        out["postures"]["level, farthest forward at 1.00 m"] = {"x": x, **max_load(chain, q)}
    out["held_in_simulation"] = hold_test()
    (args.out / f"payload_{args.waist}.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))


def hold_test(postures=("carry", "ready_side_low", "ready"), loads=(1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 11.0, 12.0), seconds: float = 3.0) -> dict:
    """The statics checked in the simulation: a weight welded to the left hand at the pinch point, its gravity NOT
    compensated (the bench compensates what a hand holds, so there the limit never shows), the arm's servos holding
    the posture for `seconds`. Reports how far the worst joint ends from its target; a joint that has run out of
    torque gives way by much more than its servo's stiffness explains. In the simulation the arm's OWN weight is
    compensated outside the motors' force ranges, so a posture holds more here than `max_load` says, by the share of
    the limit the arm's own weight would have used."""
    def extend(s):
        load = s.worldbody.add_body(name="load", pos=[0.0, 0.0, 2.0])
        load.add_freejoint(name="load")
        load.add_geom(name="load", type=mujoco.mjtGeom.mjGEOM_SPHERE, size=[0.02, 0, 0], mass=1.0, contype=0, conaffinity=0)
        eq = s.add_equality(name="hold", type=mujoco.mjtEq.mjEQ_WELD, objtype=mujoco.mjtObj.mjOBJ_BODY, name1="left_gripper/palm", name2="load", active=True)
        eq.solref = [0.004, 1.0]

    m, _ = G.build(extend=extend)
    ix = G.index(m)
    a = ix["arms"]["left"]
    load, weld = m.body("load").id, m.equality("hold").id
    qadr = int(m.jnt_qposadr[m.joint("load").id])
    m.eq_data[weld, 0:3] = 0.0
    m.eq_data[weld, 3:6] = [0.0, 0.0, P_PINCH]             # the load sits at the pinch point, in the palm's frame
    m.eq_data[weld, 6:10] = [1.0, 0.0, 0.0, 0.0]
    m.eq_data[weld, 10] = 1.0
    inertia0, out = m.body_inertia[load].copy(), {}
    for name in postures:
        rows = []
        for kg in loads:
            m.body_mass[load] = kg
            m.body_inertia[load] = inertia0 * kg
            d = mujoco.MjData(m)
            q = np.array(POSTURES[name])
            G.set_posture(m, d, ix, left=q, right=G.mirror(POSTURES["rest"]))
            mujoco.mj_forward(m, d)
            d.qpos[qadr:qadr + 3] = d.site_xpos[a["pinch"]]
            quat = np.zeros(4)
            mujoco.mju_mat2Quat(quat, d.xmat[a["palm"]])
            d.qpos[qadr + 3:qadr + 7] = quat
            mujoco.mj_forward(m, d)
            z0 = float(d.site_xpos[a["pinch"]][2])
            for _ in range(int(seconds / m.opt.timestep)):
                mujoco.mj_step(m, d)
            err = d.qpos[a["q"]] - q
            worst = int(np.argmax(np.abs(err)))
            rows.append({"kg": kg, "joint_error_max_rad": round(float(np.abs(err).max()), 4), "joint": a["joints"][worst],
                         "hand_sank_mm": round((z0 - float(d.site_xpos[a["pinch"]][2])) * 1e3, 1),
                         "held": bool(np.abs(err).max() < 0.05 and np.abs(d.qvel[a["v"]]).max() < 0.05)})
        out[name] = rows
    return out


# ---- postures ---------------------------------------------------------------------------------------------------------------------
# Found by `postures` below (left arm; the right arm's are `g1_glide.mirror` of these). Filled in from its output.
POSTURES: dict = {
    # the file's own standing posture (upper arms down, forearms bent forward and down): nothing of the robot is in the
    # head camera's picture, and every posture below is reached from it on a free straight line in joint space. The
    # search found postures that keep the arms 4 cm nearer the pelvis axis (0.27 against 0.315 m), with both hands
    # behind the back; not taken (docs/MOTION.md 10.4)
    "rest": G.STAND["left"],
    # the hand straight down, the pinch point at (0.25, 0.15, 1.02), the fingers closing sideways (along y)
    "ready": (-2.1052, 1.1484, -2.0361, 0.1527, -0.3605, -1.0992, -1.3178),
    # the hand level, pointing ahead, the pinch point at (0.35, 0.15, 1.05) and at (0.35, 0.15, 0.97)
    "ready_side": (-0.9849, 1.3346, -1.2715, -0.6119, 1.7911, 0.2651, -1.0687),
    "ready_side_low": (-0.5923, 1.0827, -1.1664, -0.3584, -1.0043, -0.3433, 0.9914),
    # the hand level close before the chest, the pinch point at (0.26, 0.12, 0.95)
    "carry": (-0.2284, 1.0023, -1.1795, -0.6798, -0.5554, -0.2041, 1.2705),
}


class Eyes:
    """Which pixels of a camera's picture show the robot (segmentation rendering)."""

    def __init__(self, m: mujoco.MjModel, ix: dict, size=(320, 240)):
        self.m, self.ix = m, ix
        self.r = mujoco.Renderer(m, size[1], size[0])
        self.r.enable_segmentation_rendering()
        self.size = size

    def owners(self, d: mujoco.MjData, camera: str) -> np.ndarray:
        """Per pixel the body id of the geom shown, -1 where there is none."""
        self.r.update_scene(d, camera=camera)
        seg = self.r.render()
        ids, kinds = seg[:, :, 0], seg[:, :, 1]
        body = np.full(ids.shape, -1, dtype=np.int64)
        mask = kinds == int(mujoco.mjtObj.mjOBJ_GEOM)
        body[mask] = self.m.geom_bodyid[ids[mask]]
        return body

    def geoms(self, d: mujoco.MjData, camera: str) -> np.ndarray:
        self.r.update_scene(d, camera=camera)
        seg = self.r.render()
        return np.where(seg[:, :, 1] == int(mujoco.mjtObj.mjOBJ_GEOM), seg[:, :, 0], -1)

    def robot_share(self, d: mujoco.MjData, camera: str) -> float:
        body = self.owners(d, camera)
        return float(np.isin(body, list(self.ix["bodies"])).mean())

    def close(self) -> None:
        self.r.close()


def arm_extent(m, d, ix) -> dict:
    """How far the arms' collision shapes reach from the pelvis axis, forward and sideways (their bounding boxes)."""
    pts = []
    arms = ix["arms"]["left"]["bodies"] | ix["arms"]["right"]["bodies"]
    for g in range(m.ngeom):
        if int(m.geom_bodyid[g]) in arms and m.geom_contype[g]:
            c, r = d.geom_xpos[g], m.geom_rbound[g]
            aabb = m.geom_aabb[g]
            rot = d.geom_xmat[g].reshape(3, 3)
            for sx in (-1, 1):
                for sy in (-1, 1):
                    for sz in (-1, 1):
                        pts.append(c + rot @ (aabb[:3] + aabb[3:] * np.array([sx, sy, sz])))
    pts = np.array(pts)
    base = d.xpos[ix["pelvis"]]
    return {"x": [round(float(pts[:, 0].min() - base[0]), 3), round(float(pts[:, 0].max() - base[0]), 3)],
            "y_abs_max": round(float(np.abs(pts[:, 1] - base[1]).max()), 3),
            "r_max": round(float(np.hypot(pts[:, 0] - base[0], pts[:, 1] - base[1]).max()), 3),
            "z_min": round(float(pts[:, 2].min()), 3)}


def cmd_postures(args) -> None:
    """Rest: both arms mirrored, nothing of the robot in the head camera's picture, 2 cm clear of everything, and as
    near the pelvis axis as possible. Ready: the hand straight down over a counter. Carry and side: the hand level."""
    m, ix, chain = _model(())
    d = chain.d
    eyes = Eyes(m, ix)
    rng = np.random.default_rng(args.seed)
    out: dict = {}

    def both(q):
        G.set_posture(m, d, ix, left=q, right=G.mirror(q))
        mujoco.mj_forward(m, d)

    # the body's own outline without the arms
    both(G.STAND["left"])
    legs = [g for g in range(m.ngeom) if int(m.geom_bodyid[g]) in ix["bodies"] and m.geom_contype[g]
            and int(m.geom_bodyid[g]) not in (ix["arms"]["left"]["bodies"] | ix["arms"]["right"]["bodies"])]
    pts = []
    for g in legs:
        aabb, rot = m.geom_aabb[g], d.geom_xmat[g].reshape(3, 3)
        for sx in (-1, 1):
            for sy in (-1, 1):
                for sz in (-1, 1):
                    pts.append(d.geom_xpos[g] + rot @ (aabb[:3] + aabb[3:] * np.array([sx, sy, sz])))
    pts = np.array(pts)
    out["body_without_arms"] = {"x": [round(float(pts[:, 0].min()), 3), round(float(pts[:, 0].max()), 3)],
                                "y_abs_max": round(float(np.abs(pts[:, 1]).max()), 3),
                                "x_below_0.90": [round(float(pts[pts[:, 2] < 0.90][:, 0].min()), 3), round(float(pts[pts[:, 2] < 0.90][:, 0].max()), 3)]}

    # the rest posture is asked for more room than the 5 mm of everything else, and for a free straight line in joint
    # space to the file's standing posture, from which the working postures are reached on free lines (below)
    m_wide, ix_wide, wide = _model(())
    K.set_margin(m_wide, ix_wide, 0.02)
    hub = np.array(G.STAND["left"])

    def rate(q, rest=False):
        if rest:
            G.set_posture(m_wide, wide.d, ix_wide, left=q, right=G.mirror(q))
            mujoco.mj_forward(m_wide, wide.d)
            if wide.touching():
                return None
            for k in range(1, 20):
                qk = np.asarray(q) + (hub - np.asarray(q)) * k / 20.0
                both(qk)
                if chain.touching():
                    return None
        both(q)
        if chain.touching():
            return None
        ext = arm_extent(m, d, ix)
        share = eyes.robot_share(d, "head")
        load = max_load(chain, np.asarray(q, dtype=np.float64))
        both(q)
        return {"q": [round(float(v), 4) for v in q], "head_robot_share": round(share, 4), **ext,
                "own_torque_share": load.get("share_of_limit_unloaded", 9.9),
                "pinch": [round(float(v), 3) for v in d.site_xpos[chain.site]],
                "hand_points": [round(float(v), 3) for v in d.site_xmat[chain.site].reshape(3, 3)[:, 2]]}

    out["stand_keyframe"] = rate(G.STAND["left"])
    lo = np.array([-0.4, 0.05, -0.6, 0.5, -0.6, -0.6, -0.6])
    hi = np.array([0.6, 0.6, 0.6, 2.05, 0.6, 0.6, 0.6])
    cands = []
    for _ in range(args.n * 200):
        r = rate(rng.uniform(lo, hi), rest=True)
        if r is not None and r["head_robot_share"] == 0.0:
            cands.append(r)
    # the one that stays nearest the pelvis axis (the footprint of a base that also turns); among those within a
    # centimetre of it, the one whose own weight asks least of its motors
    cands.sort(key=lambda r: r["r_max"])
    if cands:
        near = [r for r in cands if r["r_max"] <= cands[0]["r_max"] + 0.01]
        out["rest_search"] = {"tried": args.n * 200, "free_and_out_of_the_head_picture": len(cands),
                              "best": min(near, key=lambda r: r["own_torque_share"]), "smallest_radius": cands[0],
                              "narrowest": min(cands, key=lambda r: r["y_abs_max"])}

    # ready, side, carry: solved for, then the best of the solutions by the smallest singular value / the load
    def best_at(points, z, closings, key, n_seeds=40):
        lib = getattr(best_at, "lib", None)
        if lib is None:
            both(G.STAND["left"])
            lib = best_at.lib = Library(chain, 200000, np.random.default_rng(3))
        found = []
        for pos in points:
            for cy in closings:
                rot = K.frame(z, cy)
                for seed in lib.seeds(np.array(pos), z, cy, k=n_seeds):
                    q = chain.solve(pos, rot=rot, seed=seed, iters=80)
                    if q is None or not chain.free(q):
                        continue
                    margin = float(np.min(np.minimum(q - chain.lo, chain.hi - q)))
                    found.append({"q": [round(float(v), 4) for v in q], "pinch": list(pos), "closing": list(cy),
                                  "sigma_min": round(chain.manipulability(q), 4), "limit_margin": round(margin, 3),
                                  "load": max_load(chain, q)})
        both(G.STAND["left"])
        return max(found, key=key) if found else None, len(found)

    def describe(tag, res):
        best, n = res
        if best is None:
            out[tag] = {"found": 0}
            return
        both(best["q"])
        best["head_robot_share"] = round(eyes.robot_share(d, "head"), 4)
        best.update(arm_extent(m, d, ix))
        out[tag] = {"found": n, **best}
        both(G.STAND["left"])

    usable = lambda r: (r["limit_margin"] > 0.10, r["sigma_min"])       # noqa: E731
    describe("ready", best_at([(x, y, z) for x in (0.25, 0.30) for y in (0.15, 0.20) for z in (args.ready_height,)],
                              (0.0, 0.0, -1.0), ((0.0, 1.0, 0.0), (0.0, -1.0, 0.0)), usable))
    describe("ready_side", best_at([(x, y, 1.05) for x in (0.35, 0.40) for y in (0.15, 0.20)],
                                   (1.0, 0.0, 0.0), ((0.0, 1.0, 0.0), (0.0, -1.0, 0.0)), usable))
    describe("ready_side_low", best_at([(x, y, 0.97) for x in (0.35, 0.40) for y in (0.15, 0.20)],
                                       (1.0, 0.0, 0.0), ((0.0, 1.0, 0.0), (0.0, -1.0, 0.0)), usable))
    describe("carry", best_at([(x, y, z) for x in (0.22, 0.26, 0.30) for y in (0.12, 0.16, 0.20) for z in (0.95, 1.00, 1.05)],
                              (1.0, 0.0, 0.0), ((0.0, 1.0, 0.0), (0.0, -1.0, 0.0)),
                              lambda r: (r["limit_margin"] > 0.30, r["load"]["kg"])))
    # straight lines in joint space between the named postures: free (5 mm) or where they are blocked
    named = {**{k: np.array(v) for k, v in POSTURES.items()}, "stand": hub}
    G.set_posture(m, d, ix, left=POSTURES.get("rest", G.STAND["left"]), right=G.mirror(POSTURES.get("rest", G.STAND["left"])))
    mujoco.mj_forward(m, d)
    lines = {}
    for a in named:
        for b in named:
            if a < b:
                hits = [k for k in range(41) if chain.touching(named[a] + (named[b] - named[a]) * k / 40.0)]
                lines[f"{a} - {b}"] = "free" if not hits else f"blocked at {len(hits)} of 41 points"
    out["lines_between_postures"] = lines
    eyes.close()
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "postures.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))


# ---- pictures -----------------------------------------------------------------------------------------------------------------------
def _scene(d_counter: float = 0.15, things: bool = True):
    def extend(s):
        furniture("counter", d_counter)(s)
        wb = s.worldbody
        s.add_texture(name="sky", type=mujoco.mjtTexture.mjTEXTURE_SKYBOX, builtin=mujoco.mjtBuiltin.mjBUILTIN_GRADIENT,
                      rgb1=[0.86, 0.89, 0.93], rgb2=[0.62, 0.66, 0.72], width=128, height=768)
        if things:
            cyl = mujoco.mjtGeom.mjGEOM_CYLINDER
            wb.add_geom(name="can", type=cyl, size=[0.033, 0.06, 0], pos=[d_counter + 0.15, 0.15, 0.96], rgba=[0.75, 0.15, 0.12, 1])
            wb.add_geom(name="bottle", type=cyl, size=[0.035, 0.11, 0], pos=[d_counter + 0.30, -0.20, 1.01], rgba=[0.15, 0.40, 0.70, 1])
        post = mujoco.mjtGeom.mjGEOM_CYLINDER
        wb.add_geom(name="post", type=post, size=[0.02, 0.875, 0], pos=[-0.1, 0.9, 0.875], rgba=[0.95, 0.95, 0.95, 1], contype=0, conaffinity=0)
        for i, h in enumerate((0.5, 1.0, 1.5)):
            wb.add_geom(name=f"ring{i}", type=post, size=[0.035, 0.01, 0], pos=[-0.1, 0.9, h], rgba=[0.85, 0.15, 0.1, 1], contype=0, conaffinity=0)
        for name, pos, target in (("view_room", [-1.6, -1.9, 1.9], [0.2, 0.0, 0.8]), ("view_side", [0.25, -1.7, 1.05], [0.25, 0.0, 0.85]),
                                  ("view_front", [1.9, 0.5, 1.5], [0.0, 0.0, 0.9])):
            wb.add_camera(name=name, pos=pos, quat=G._look_at(pos, target), fovy=45.0)
    return extend


def cmd_pictures(args) -> None:
    from PIL import Image
    args.out.mkdir(parents=True, exist_ok=True)
    m, changes = G.build(extend=_scene())
    ix = G.index(m)
    d = mujoco.MjData(m)
    r = mujoco.Renderer(m, 480, 640)
    eyes = Eyes(m, ix, (640, 480))
    named = {"stand": G.STAND["left"], **POSTURES}
    report = {"postures": {}}
    views = ("view_room", "view_side", "view_front", "head", "wrist_left", "wrist_right")
    for name, q in named.items():
        for both in (True, False) if name not in ("stand", "rest") else (True,):
            G.set_posture(m, d, ix, left=q, right=G.mirror(q) if both else G.mirror(named.get("rest", G.STAND["left"])))
            mujoco.mj_forward(m, d)
            tiles = []
            for v in views:
                r.update_scene(d, camera=v)
                tiles.append(r.render().copy())
            tag = name + ("" if both else "_left_only")
            Image.fromarray(np.concatenate(tiles, axis=1)).save(args.out / f"posture_{tag}.png")
            report["postures"][tag] = {c: round(eyes.robot_share(d, c), 4) for c in ("head", "wrist_left", "wrist_right")}
    r.close()
    # the wrist camera over nothing: how much of its picture is its own hand, and where the pinch point is in it
    plain, _ = G.build()
    pix = G.index(plain)
    pd = mujoco.MjData(plain)
    G.set_posture(plain, pd, pix, left=POSTURES["ready_side"], right=G.STAND["right"])
    mujoco.mj_forward(plain, pd)
    peyes = Eyes(plain, pix, (640, 480))
    hand = pix["arms"]["left"]["hand_bodies"]
    cam = plain.camera("wrist_left").id
    pc = pd.cam_xmat[cam].reshape(3, 3).T @ (pd.site_xpos[pix["arms"]["left"]["pinch"]] - pd.cam_xpos[cam])
    f = 240.0 / math.tan(math.radians(plain.cam_fovy[cam] / 2.0))
    head = plain.camera("head").id
    low = math.radians(G.HEAD_CAMERA["down_deg"] + G.HEAD_CAMERA["fovy"] / 2.0)
    t0 = time.time()
    for _ in range(2500):
        mujoco.mj_step(plain, pd)
    report["facts"] = {
        "wrist_picture_own_hand_share": round(float(np.isin(peyes.owners(pd, "wrist_left"), list(hand)).mean()), 4),
        "pinch_point_pixel": [round(320.0 + f * pc[0] / -pc[2], 1), round(240.0 - f * pc[1] / -pc[2], 1)],
        "head_camera_pos": [round(float(v), 3) for v in pd.cam_xpos[head]],
        "head_lowest_ray_meets_floor_at_x": round(float(pd.cam_xpos[head][0] + pd.cam_xpos[head][2] / math.tan(low)), 3),
        "head_lowest_ray_meets_0.90_top_at_x": round(float(pd.cam_xpos[head][0] + (pd.cam_xpos[head][2] - 0.90) / math.tan(low)), 3),
        "head_at_30_down_70_fov_meets_0.90_top_at_x": round(float(pd.cam_xpos[head][0] + (pd.cam_xpos[head][2] - 0.90) / math.tan(math.radians(65.0))), 3),
        "seconds_for_5_s_of_robot_time": round(time.time() - t0, 2),
    }
    peyes.close()
    eyes.close()
    # the maker's name: with the shape left in, in how many pictures of which camera does it show
    m2, _ = G.build(hide_logo=False, extend=_scene(things=False))
    ix2 = G.index(m2)
    logo = [g for g in range(m2.ngeom) if int(m2.geom_type[g]) == mujoco.mjtGeom.mjGEOM_MESH and m2.mesh(int(m2.geom_dataid[g])).name == "logo_link"]
    K.set_margin(m2, ix2, CLEARANCE)
    left, right = K.Chain(m2, ix2, "left"), K.Chain(m2, ix2, "right")
    eyes2 = Eyes(m2, ix2, (640, 480))
    rng = np.random.default_rng(5)
    d2 = left.d
    seen = {c: {"pictures": 0, "most_pixels": 0} for c in ("head", "wrist_left", "wrist_right")}
    n = 0
    best = None
    while n < args.n * 15:
        ql, qr = rng.uniform(left.lo, left.hi), rng.uniform(right.lo, right.hi)
        G.set_posture(m2, d2, ix2, left=ql, right=qr)
        mujoco.mj_forward(m2, d2)
        if left.touching():
            continue
        n += 1
        for c in seen:
            px = int(np.isin(eyes2.geoms(d2, c), logo).sum())
            seen[c]["pictures"] += int(px > 0)
            if px > seen[c]["most_pixels"]:
                seen[c]["most_pixels"] = px
                if c != "head":
                    best = (c, ql.copy(), qr.copy())
    report["logo"] = {"random_free_postures": n, "image": [640, 480], "seen": seen}
    if best is not None:                                    # the picture in which it shows most, with and without it
        c, ql, qr = best
        G.set_posture(m2, d2, ix2, left=ql, right=qr)
        mujoco.mj_forward(m2, d2)
        r2 = mujoco.Renderer(m2, 480, 640)
        r2.update_scene(d2, camera=c)
        a = r2.render().copy()
        r2.close()
        m3, _ = G.build(extend=_scene(things=False))
        d3 = mujoco.MjData(m3)
        G.set_posture(m3, d3, G.index(m3), left=ql, right=qr)
        mujoco.mj_forward(m3, d3)
        r3 = mujoco.Renderer(m3, 480, 640)
        r3.update_scene(d3, camera=c)
        b = r3.render().copy()
        r3.close()
        Image.fromarray(np.concatenate([a, b], axis=1)).save(args.out / "logo_in_wrist_camera.png")
    eyes2.close()
    (args.out / "pictures.json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps(report, indent=1))


# ---- the tables of docs/MOTION.md ---------------------------------------------------------------------------------------------------
def cmd_report(args) -> None:
    """Markdown from the JSON files the other commands wrote."""
    def span(v):
        return f"{v[0]:.2f} to {v[1]:.2f}"

    L = []
    for waist in ("none", "pitch", "yaw"):
        f = args.out / f"reach_{waist}.json"
        if not f.exists():
            continue
        r = json.loads(f.read_text())
        names = list(r["directions"])
        L += ["", f"Waist: {waist}. Cells: distance of the pinch point from the pelvis axis among the targets ahead of it (x >= 0) / how far "
              "ahead of the pelvis axis on the line 0.15 m to the side, in front of the shoulder (the longest unbroken stretch) / targets reached.", "",
              "| Height (m) | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
        for i, h in enumerate(r["heights"]):
            cells = []
            for n in names:
                row = r["directions"][n][i]
                if not row["targets"]:
                    cells.append("none")
                else:
                    ahead = span(row["x_ahead_of_shoulder_unbroken"]) if "x_ahead_of_shoulder" in row else "none"
                    cells.append(f"{span(row.get('r_front', row['r']))} / {ahead} / {row['targets']}")
            L.append(f"| {h:.2f} | " + " | ".join(cells) + " |")
        if "right_hand_mirror_check" in r:
            c = r["right_hand_mirror_check"]
            L += ["", f"Right hand, mirrored targets: {c['same_answer']} of {c['targets']} give the left hand's answer."]
    f = args.out / "heights.json"
    if f.exists():
        r = json.loads(f.read_text())
        L += ["", "Heights of the pinch point reached on the line 0.15 m to the side (2 cm steps, waist fixed):", "",
              "| Ahead of the pelvis axis (m) | hand down | hand level, pointing ahead |", "|---|---|---|"]
        xs = sorted({k.split(",")[0] for d_ in r["directions"].values() for k in d_["by_x_y"]})
        for x in xs:
            cells = [(span(v[:2]) if (v := r["directions"][n]["by_x_y"].get(f"{x},0.15")) else "none") for n in ("down", "forward")]
            L.append(f"| {x} | " + " | ".join(cells) + " |")
        L.append("| anywhere on the five lines | " + " | ".join(f"{r['directions'][n]['lowest']:.2f} to {r['directions'][n]['highest']:.2f}" for n in ("down", "forward")) + " |")
    for waist in ("none", "pitch"):
        f = args.out / f"furniture_{waist}.json"
        if not f.exists():
            continue
        r = json.loads(f.read_text())
        keys = [f"{k}+{a}" for k, above in r["above"].items() for a in above]
        L += ["", f"Furniture, waist: {waist}. Cells: how far onto the top, from its front edge, the pinch point gets (m).", "",
              "| Piece | Pelvis axis to its front edge (m) | " + " | ".join(f"hand {k.split('+')[0]}, {float(k.split('+')[1]) * 100:.1f} cm above" for k in keys) + " |",
              "|---|---|" + "---|" * len(keys)]
        for kind, res in r["surfaces"].items():
            for d, rows in res["by_stand_off"].items():
                L.append(f"| {kind} ({SURFACES[kind]['top']:.2f} m) | {d}{' (nearest)' if float(d) == res['nearest_stand_off'] else ''} | "
                         + " | ".join((f"{rows[k]['depth_unbroken'][1]:.3f}" if "depth_unbroken" in rows[k] else "none") for k in keys) + " |")
    f = args.out / "payload_none.json"
    if f.exists():
        r = json.loads(f.read_text())
        L += ["", "| Hand | Height (m) | Postures | Load the weakest posture holds (kg) | Median | Best | Joint that limits most often |", "|---|---|---|---|---|---|---|"]
        for n, rows in r["by_direction"].items():
            for row in rows:
                L.append(f"| {n} | {row['height']:.2f} | {row['postures']} | {row['kg_min']:.1f} | {row['kg_median']:.1f} | {row['kg_max']:.1f} | `{row['binding']}` |")
        L += ["", "| Posture | Load (kg) | Limited by | Share of a joint's limit used by the arm's own weight | Load if the arm's own weight is not the motors' to carry (kg) |",
              "|---|---|---|---|---|"]
        for n, row in r["postures"].items():
            L.append(f"| {n} | {row['kg']:.1f} | `{row['binding']}` | {row.get('share_of_limit_unloaded', '')} | {row.get('kg_with_own_weight_compensated', '')} |")
        if "held_in_simulation" in r:
            L += ["", "| Posture | " + " | ".join(f"{row['kg']:g} kg" for row in next(iter(r["held_in_simulation"].values()))) + " |",
                  "|---|" + "---|" * len(next(iter(r["held_in_simulation"].values())))]
            for n, rows in r["held_in_simulation"].items():
                L.append(f"| {n} | " + " | ".join((f"held, {row['joint_error_max_rad']:.3f} rad" if row["held"] else f"gives way ({row['joint'].replace('left_', '').replace('_joint', '')})")
                                                   for row in rows) + " |")
    for side in ("left", "right"):
        f = args.out / f"bench_trial_{side}.json"
        if f.exists():
            r = json.loads(f.read_text())
            L += ["", f"Scripted pick and place, {side} hand:", "", "| Thing | Succeeded | From above / from the side | Not started: no way found | Failed on the way | Robot time of a success (s) |",
                  "|---|---|---|---|---|---|"]
            for thing, sm in r["summary"].items():
                ok = [t for t in r["trials"] if t["thing"] == thing and t["ok"]]
                top = sum(t.get("grasp_type") == "top" for t in ok)
                plan = sum(v for k, v in sm["failures"].items() if k.endswith("(plan)"))
                L.append(f"| {thing} | {sm['ok']} of {sm['n']} | {top} / {len(ok) - top} | {plan} | {sm['n'] - sm['ok'] - plan} | {sm['robot_seconds_mean']} |")
    print("\n".join(L))


def main() -> None:
    ap = argparse.ArgumentParser(description="Measurements of the gliding G1 (docs/MOTION.md 10.4).")
    ap.add_argument("command", choices=sorted(COMMANDS))
    ap.add_argument("--out", type=Path, default=Path("build/g1"))
    ap.add_argument("--waist", choices=sorted(WAIST), default="none")
    ap.add_argument("--library", type=int, default=300000)
    ap.add_argument("-n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--directions", nargs="*", default=sorted(DIRECTIONS))
    ap.add_argument("--ready-height", type=float, default=1.02)
    args = ap.parse_args()
    COMMANDS[args.command](args)


COMMANDS = {"reach": cmd_reach, "furniture": cmd_furniture, "payload": cmd_payload, "postures": cmd_postures, "pictures": cmd_pictures, "report": cmd_report, "heights": cmd_heights}

if __name__ == "__main__":
    main()
