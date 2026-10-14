"""Layer-by-layer Wuji controller with a greedy per-layer parameter search (motor targets only).

The controller for one layer is the Sharpa authoring routine (approach, side pinch, lift, carry over the plate,
lower, open, withdraw) with Wuji kinematics (`wuji_demo.pinch_pose`) and tunable timing/offsets. For each layer the
search forks the simulator after the accepted prefix, runs several parameter variants in parallel children (each a
deterministic continuation of the same state) and keeps the variant whose released stack is best aligned. The
accepted rows are then executed in the parent, so the final trajectory is one continuous actuator replay.
"""

from __future__ import annotations

import argparse
import itertools
import json
import multiprocessing as mp
import os
import time
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")
import numpy as np
from scipy.spatial.transform import Rotation

import wuji_demo as wd
from scene import LAYER_HALF_HEIGHT

BASE = {
    "prepare": 60, "align": 65, "reach": 65, "pinch": 50, "stab": 60, "lift_n": 95, "transport": 160,
    "lower_n": 95, "hold": 60, "open_n": 90, "wait": 50, "withdraw": 65, "clear": 45, "settle": 50,
    "open_clear": 0.006, "close_clear": -0.004, "lift": 0.16, "place_gap": 0.024, "release_dx": 0.0,
    "release_dy": 0.0, "open_frac": 1.0, "grasp_z": 0.0, "recenter": True, "withdraw_dx": 0.13, "min_lift": 0.04,
}


def layer_routine(demo, layer, name, lp, ctrl):
    """Run one layer from the current state. Returns the updated controller state (does not modify ``ctrl``)."""
    s = demo.session
    ctrl = dict(ctrl)
    original = s.data.xpos[s.bodies[name]].copy()
    direction = 0 if name in ("cheese", "lettuce") else 1
    if ctrl["previous_opened"] is not None:
        seed = np.asarray(ctrl["previous_opened"]).copy()
        seed[:3] += original - np.asarray(ctrl["previous_center"])
        if direction != ctrl["previous_direction"]:
            rotation = Rotation.from_euler("z", -np.pi / 2 if direction == 0 else np.pi / 2).as_matrix()
            seed[:3] = original + rotation @ (seed[:3] - original)
            seed[3:6] = Rotation.from_matrix(rotation @ Rotation.from_euler("XYZ", seed[3:6]).as_matrix()).as_euler("XYZ")
    else:
        seed = demo.joint_target.copy()
        seed[3] = 0.0
    ik = {**wd.default_params(), **lp}
    opened = wd.pinch_pose(s, name, lp["open_clear"], seed, ik, lp["grasp_z"])
    closed = wd.pinch_pose(s, name, lp["close_clear"], opened, {**ik, "max_cost": 0.5}, lp["grasp_z"], multistart=False)
    ctrl.update(previous_opened=opened.tolist(), previous_center=original.tolist(), previous_direction=direction)
    above = opened.copy()
    above[2] += 0.15
    demo.execute(above, 65, "approach " + name)
    demo.execute(above, lp["prepare"], "prepare pinch posture")
    demo.execute(opened, lp["align"], "align beside " + name)
    demo.execute(opened, lp["reach"], "reach edge of " + name)
    demo.execute(closed, lp["pinch"], "pinch " + name)
    demo.execute(closed, lp["stab"], "stabilize grasp")
    lift = closed.copy()
    lift[2] += lp["lift"]
    demo.execute(lift, lp["lift_n"], "lift " + name)
    carried = s.data.xpos[s.bodies[name]].copy()
    if carried[2] < original[2] + lp["min_lift"] or s.done:
        return ctrl, "pickup_failed"
    target = lift.copy()
    target[:2] += np.asarray(s.config["target_xy"]) - carried[:2]
    demo.execute(target, lp["transport"], "center " + name + " over plate")
    carried = s.data.xpos[s.bodies[name]].copy()
    height = s.stack_top(layer - 1) + LAYER_HALF_HEIGHT[name] + lp["place_gap"]
    lowered = target.copy()
    lowered[2] += height - carried[2]
    lowered[:2] += np.asarray(s.config["target_xy"]) - carried[:2]
    demo.execute(lowered, lp["lower_n"], "lower " + name)
    if lp["recenter"]:
        carried = s.data.xpos[s.bodies[name]].copy()
        lowered = lowered.copy()
        lowered[:2] += np.asarray(s.config["target_xy"]) - carried[:2]
    lowered[0] += lp["release_dx"]
    lowered[1] += lp["release_dy"]
    demo.execute(lowered, lp["hold"], "stabilize above stack")
    release = closed + (opened - closed) * lp["open_frac"]
    release[:3] = opened[:3] + lowered[:3] - closed[:3]
    demo.execute(release, lp["open_n"], "open side pinch")
    demo.execute(release, lp["wait"], "wait for free release")
    retreat = release.copy()
    retreat[6:] = opened[6:]
    retreat[2] += 0.15
    demo.execute(retreat, lp["withdraw"], "withdraw from " + name)
    retreat[0] += lp["withdraw_dx"]
    demo.execute(retreat, lp["clear"], "clear stack")
    demo.execute(retreat, lp["settle"], "settle " + name)
    return ctrl, "ok"


def score(session, layer):
    """Lower is better. Hard failures are large; otherwise the worst alignment error (mm) of the placed layers."""
    f = session.features()
    if session.failure:
        return 1e6, f
    names = session.names[: layer + 1]
    errors = [f["alignment_errors_m"][n] * 1000 for n in names]
    heights = [f["positions"][n][2] for n in names]
    ordered = all(a < b for a, b in zip(heights, heights[1:]))
    tilt = max(np.arccos(np.clip(session.data.xmat[session.bodies[n], 8], -1, 1)) for n in names)
    penalty = 0.0
    if not ordered:
        penalty += 1e4
    if f["hand_contacts"]:
        penalty += 1e3
    adjacent = sum(
        1 for a, b in zip(names, names[1:]) if b in _contacts_of(session, a)
    )
    if adjacent < layer:
        penalty += 500 * (layer - adjacent)
    if tilt > 0.15:
        penalty += 300
    return max(errors) + penalty, f


def _contacts_of(session, name):
    m, d = session.model, session.data
    out = set()
    for c in d.contact[: d.ncon]:
        if c.efc_address < 0:
            continue
        a = session.owner.get(int(m.geom_bodyid[c.geom1]), "world")
        b = session.owner.get(int(m.geom_bodyid[c.geom2]), "world")
        if a == name and b != name:
            out.add(b)
        if b == name and a != name:
            out.add(a)
    return out


_STATE = {}


def _child(args):
    variant, idx = args
    demo, layer, name, ctrl, base_lp = _STATE["demo"], _STATE["layer"], _STATE["name"], _STATE["ctrl"], _STATE["lp"]
    import contextlib, io
    lp = {**base_lp, **variant}
    n0 = len(demo.session.actions)
    buf = io.StringIO()
    t = time.time()
    try:
        with contextlib.redirect_stdout(buf):
            new_ctrl, status = layer_routine(demo, layer, name, lp, ctrl)
    except Exception as exc:  # unreachable IK etc.
        return {"idx": idx, "variant": variant, "score": 2e6, "status": repr(exc), "log": buf.getvalue()[-2000:]}
    sc, f = score(demo.session, layer)
    if status != "ok":
        sc = max(sc, 1e6)
    return {
        "idx": idx, "variant": variant, "score": float(sc), "status": status, "ctrl": new_ctrl,
        "rows": np.asarray(demo.session.actions[n0:]).tolist(), "phases": demo.phases[n0:],
        "joint_target": demo.joint_target.tolist(), "errors": {k: round(v * 1000, 2) for k, v in f["alignment_errors_m"].items()},
        "failure": demo.session.failure, "failure_detail": demo.session.failure_detail, "hand_contacts": f["hand_contacts"],
        "steps": demo.session.steps, "seconds": round(time.time() - t, 1), "log": buf.getvalue()[-1500:],
    }


def search_layer(demo, layer, name, ctrl, base_lp, variants, workers):
    _STATE.update(demo=demo, layer=layer, name=name, ctrl=ctrl, lp=base_lp)
    ctx = mp.get_context("fork")
    with ctx.Pool(min(workers, len(variants)), maxtasksperchild=1) as pool:
        results = pool.map(_child, [(v, i) for i, v in enumerate(variants)], chunksize=1)
    results.sort(key=lambda r: r["score"])
    return results


def apply_rows(demo, result):
    s = demo.session
    for row in result["rows"]:
        s.step(np.asarray(row))
    demo.phases.extend(result["phases"])
    demo.joint_target = np.asarray(result["joint_target"])


def grid(spec):
    keys = list(spec)
    return [dict(zip(keys, values)) for values in itertools.product(*(spec[k] for k in keys))]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--plan", required=True, help="JSON: {layer name: {base: {...}, grid: {key: [values]}}}")
    parser.add_argument("--resume")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--layers", default="patty,cheese,tomato,lettuce,top_bun")
    parser.add_argument("--accept", type=float, default=9.0, help="stop searching a layer once a score below this exists")
    args = parser.parse_args()
    plan = json.loads(Path(args.plan).read_text())
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    demo = wd.Demo({**wd.default_params(), **plan.get("_demo", {})})
    s = demo.session
    ctrl = {"previous_opened": None, "previous_center": None, "previous_direction": 1, "next_layer": 1}
    if args.resume:
        with np.load(args.resume, allow_pickle=False) as z:
            rows, phases, jt, ctrl = z["actions"], list(z["phases"]), z["joint_target"], json.loads(str(z["state"]))
        for row in rows:
            s.step(row)
        demo.phases, demo.joint_target = phases, jt.copy()
        print(f"resumed {len(rows)} rows; next layer {ctrl['next_layer']}", flush=True)
    else:
        base = s.hold_action()
        curled = base.copy()
        dp = demo.p
        curled[6:10] = dp["thumb_seed"]
        curled[10:14] = dp["index_seed"]
        for k in (14, 18, 22):
            curled[k:k + 4] = dp["curl"]
        demo.execute(base, 10, "settle ingredients")
        demo.execute(curled, 40, "shape hand")
    wanted = args.layers.split(",")
    for layer, name in enumerate(s.names[1:], 1):
        if layer < ctrl["next_layer"] or name not in wanted:
            continue
        cfg = plan.get(name, {})
        base_lp = {**BASE, **plan.get("_all", {}), **cfg.get("base", {})}
        stages = cfg.get("stages") or [cfg.get("grid", {})]
        best = None
        for stage in stages:
            variants = grid(stage) if stage else [{}]
            t = time.time()
            results = search_layer(demo, layer, name, ctrl, base_lp, variants, args.workers)
            print(f"== {name}: {len(variants)} variants in {time.time() - t:.0f}s", flush=True)
            for r in results[:6]:
                print(f"   score={r['score']:.2f} {r['variant']} status={r['status']} fail={r.get('failure')} "
                      f"err={r.get('errors')} steps={r.get('steps')}", flush=True)
            if best is None or results[0]["score"] < best["score"]:
                best = results[0]
            if best["score"] < args.accept:
                break
        if best["score"] >= 1e5:
            print(f"!! no feasible variant for {name}; last log:\n{best.get('log', '')}", flush=True)
            (out.with_suffix(f".{name}.fail.json")).write_text(json.dumps(results[:3], indent=1, default=str))
            break
        apply_rows(demo, best)
        ctrl = dict(best["ctrl"], next_layer=layer + 1)
        sc, f = score(s, layer)
        assert abs(sc - best["score"]) < 1e-9, (sc, best["score"])
        print(f">> accepted {name} {best['variant']} score={sc:.2f} steps={s.steps}", flush=True)
        demo.checkpoint(out.with_name(out.stem + f".ckpt{layer}.npz"), ctrl)
    if ctrl["next_layer"] == 6 and not s.done:
        # Hands are clear; hold still until the released-stack condition has held for 100 controls.
        demo.execute(demo.joint_target, 400, "stability check")
    np.savez_compressed(out, actions=np.asarray(s.actions), phases=np.asarray(demo.phases))
    st = s.status()
    summary = {k: st[k] for k in ("success", "reason", "steps", "stage", "aligned_layers", "adjacent_contacts",
                                   "max_alignment_error_m", "max_tilt_rad", "hand_contacts", "released_hold_steps",
                                   "peak_bend_rad", "failure_detail", "alignment_errors_m")}
    summary["state_sha"] = s.state_sha()
    out.with_suffix(".live.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
