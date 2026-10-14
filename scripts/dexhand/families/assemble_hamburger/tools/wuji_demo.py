"""Wuji Hand 2.2 authoring controller for assemble_hamburger (motor targets only).

Port of the family's Sharpa authoring controller (scripts/dexhand/families/assemble_hamburger/demo.py): robot
kinematics (least-squares IK over the wrist stage, thumb and index joints) -> motor targets, side pinches between
the thumb and index fingertips, contact-driven placement. No object pose is written, no weld, no external force:
the session only receives actuator target rows through `Session.step`.

Checkpoints: after every placed layer the rows so far and the controller state are saved, so a later run can
resume (`--resume`) by replaying the recorded rows (deterministic) and continue with new parameters.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")
import mujoco
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

from runtime import Session
from scene import LAYER_HALF_HEIGHT

TIP = {"index": "r_wuji_r_index_finger_tip_sensor_frame_collision1", "thumb": "r_wuji_r_thumb_tip_sensor_frame_collision1"}
# Wuji finger order: THJ0..3 (6:10), FFJ0..3 (10:14), MFJ0..3 (14:18), RFJ0..3 (18:22), LFJ0..3 (22:26).
VARIABLE = np.r_[0:14]


def default_params():
    return {
        "pad": 0.0075,
        "open_clear": 0.006,
        "close_clear": -0.004,
        "curl": [1.2, 0.0, 1.6, 1.2],  # middle/ring/pinky MCP flex, abd, PIP, DIP (kept out of the way)
        "thumb_seed": [0.6, 0.0, 0.3, 0.3],
        "index_seed": [0.2, 0.0, 0.3, 0.2],
        "boost": 2.0,
        "lift": 0.16,
        "place_gap": 0.024,
        "per_layer": {},
        "food_exempt": ["r_wuji_r_index_finger_distal_collision1", "r_wuji_r_thumb_distal_collision1"],
    }


THUMB_PRESETS = ([0.0, -1.4, 0.0, 0.0], [1.0, -0.5, 0.3, 0.3], [0.5, -1.2, 0.2, 0.2])


def pinch_pose(session, name, clearance, seed, params, grasp_z=0.0, multistart=True):
    """Least-squares pinch IK; falls back to a few thumb/wrist seeds when the given seed does not converge."""
    best = None
    seeds = [seed]
    if multistart:
        direction = 0 if name in ("cheese", "lettuce") else 1
        for thumb in THUMB_PRESETS:
            for rx in (seed[3], -1.57):
                alt = seed.copy()
                alt[6:10] = thumb
                alt[3] = rx
                seeds.append(alt)
    for k, candidate in enumerate(seeds):
        try:
            q, cost = _pinch_pose(session, name, clearance, candidate, params, grasp_z)
        except mujoco.FatalError as exc:
            print("  ik error", exc, flush=True)
            continue
        if best is None or cost < best[1]:
            best = (q, cost)
        if cost <= params.get("max_cost", 0.002):
            return q
    raise RuntimeError(f"Unreachable pinch for {name}: {best[1] if best else None}")


def _pinch_pose(session, name, clearance, seed, params, grasp_z=0.0):
    m = session.model
    d = mujoco.MjData(m)
    q = seed.copy()
    center = session.data.xpos[session.bodies[name]].copy()
    center[2] += grasp_z
    direction = 0 if name in ("cheese", "lettuce") else 1
    radius = {"patty": 0.048, "tomato": 0.046, "cheese": 0.049, "lettuce": 0.052, "top_bun": 0.051}[name]
    gids = [m.geom(TIP["index"]).id, m.geom(TIP["thumb"]).id]
    lo, hi = m.actuator_ctrlrange[VARIABLE].T.copy()
    lo[2] = center[2] + 0.025
    initial = q[VARIABLE].copy()
    collisions = [
        g
        for g in range(m.ngeom)
        if m.geom_contype[g] and session.owner.get(int(m.geom_bodyid[g])) == "hand" and g not in gids
    ]
    # The distal pads next to the pinching tips may touch the food edge; every other hand geom must stay clear.
    exempt = {m.geom(n).id for n in params.get("food_exempt", [])}
    food_check = [g for g in collisions if g not in exempt]
    food = (
        m.geom(name + "_collision").id if name not in ("cheese", "lettuce") else m.geom(name + "_center_collision").id
    )
    obstacles = [m.geom("table").id, m.geom(name + "_prep_support").id]
    pad = params["pad"]

    def residual(values):
        q[VARIABLE] = values
        d.qpos[:] = session.data.qpos
        d.qpos[session.qadr] = q
        mujoco.mj_kinematics(m, d)
        mujoco.mj_collision(m, d)
        errors = []
        for gid, sign in zip(gids, (1, -1)):
            target = center.copy()
            target[direction] += sign * (radius + pad + clearance)
            errors.extend((d.geom_xpos[gid] - target) * 100)
        for gid in food_check:
            distance = mujoco.mj_geomDistance(m, d, gid, food, 0.012, None)
            errors.append(min(0, distance - 0.001) * 250)
        for gid in collisions + gids:
            for obstacle in obstacles:
                distance = mujoco.mj_geomDistance(m, d, gid, obstacle, 0.012, None)
                errors.append(min(0, distance - 0.001) * 250)
        self_penetration = np.zeros(m.ngeom)
        for c in d.contact[: d.ncon]:
            if (
                session.owner.get(int(m.geom_bodyid[c.geom1])) == "hand"
                and session.owner.get(int(m.geom_bodyid[c.geom2])) == "hand"
            ):
                names = (m.geom(c.geom1).name or "") + (m.geom(c.geom2).name or "")
                if "thumb" in names or "index" in names:
                    self_penetration[c.geom1] += min(0, float(c.dist) + 0.0001) * 300
        errors.extend(self_penetration)
        errors.extend((values - initial) * 0.012)
        return np.asarray(errors)

    fit = least_squares(residual, np.clip(initial, lo + 1e-6, hi - 1e-6), bounds=(lo + 1e-8, hi - 1e-8), max_nfev=350)
    residual(fit.x)
    tips = [d.geom_xpos[g].copy() for g in gids]
    print(f"  ik {name} clear={clearance:+.3f} cost={fit.cost:.5f} tips={np.round(tips, 3).tolist()}", flush=True)
    return q.copy(), fit.cost


class Demo:
    def __init__(self, params):
        self.p = params
        self.session = Session(hand="wuji")
        s = self.session
        self.phases = []
        self.joint_target = s.hold_action()
        self.dofs = s.model.jnt_dofadr[s.model.actuator_trnid[:, 0]]
        self.gains = s.model.actuator_gainprm[:, 0]
        self.log = []

    def execute(self, target, count, phase):
        s = self.session
        start = self.joint_target.copy()
        for ratio in np.linspace(0, 1, count + 1)[1:]:
            if s.done:
                break
            blend = ratio * ratio * (3 - 2 * ratio)
            self.joint_target = start + (target - start) * blend
            action = self.joint_target + s.data.qfrc_bias[self.dofs] / self.gains
            action[6:] += self.p["boost"] * (self.joint_target[6:] - s.data.qpos[s.qadr[6:]])
            action = np.clip(action, *s.model.actuator_ctrlrange.T)
            s.step(action)
            self.phases.append(phase)
        f = s.features()
        line = {k: f[k] for k in ("aligned_layers", "hand_contacts", "finger_contacts", "peak_bend_rad", "failure")}
        print(f"[{s.steps}] {phase} {json.dumps(line)}", flush=True)

    def checkpoint(self, path, extra):
        s = self.session
        np.savez_compressed(path, actions=np.asarray(s.actions), phases=np.asarray(self.phases),
                            joint_target=self.joint_target, state=json.dumps(extra))


def run(args):
    params = default_params()
    if args.params:
        params.update(json.loads(Path(args.params).read_text()))
    demo = Demo(params)
    s = demo.session
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    ctrl = {"previous_opened": None, "previous_center": None, "previous_direction": 1, "next_layer": 1}
    if args.resume:
        with np.load(args.resume, allow_pickle=False) as z:
            rows = z["actions"]
            demo.phases = list(z["phases"])
            jt = z["joint_target"]
            ctrl = json.loads(str(z["state"]))
        for row in rows:
            s.step(row)
        demo.joint_target = jt.copy()
        print(f"resumed {len(rows)} rows, next layer {ctrl['next_layer']}, status {s.status()['reason']}", flush=True)
    else:
        base = s.hold_action()
        curled = base.copy()
        curled[6:10] = params["thumb_seed"]
        curled[10:14] = params["index_seed"]
        for k in (14, 18, 22):
            curled[k:k + 4] = params["curl"]
        demo.execute(base, 10, "settle ingredients")
        demo.execute(curled, 40, "shape hand")
    for layer, name in list(enumerate(s.names[1:], 1))[ctrl["next_layer"] - 1:]:
        lp = dict(params)
        lp.update(params["per_layer"].get(name, {}))
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
        if "seed_wrist" in lp:
            seed[:6] = lp["seed_wrist"]
        opened = pinch_pose(s, name, lp["open_clear"], seed, lp, lp.get("grasp_z", 0.0))
        closed = pinch_pose(s, name, lp["close_clear"], opened, {**lp, "max_cost": lp.get("max_cost_closed", 0.5)},
                            lp.get("grasp_z", 0.0), multistart=False)
        ctrl.update(previous_opened=opened.tolist(), previous_center=original.tolist(), previous_direction=direction)
        above = opened.copy()
        above[2] += 0.15
        demo.execute(above, 65, "approach " + name)
        demo.execute(above, lp.get("prepare", 150), "prepare pinch posture")
        demo.execute(opened, 65, "align beside " + name)
        demo.execute(opened, 65, "reach edge of " + name)
        demo.execute(closed, 50, "pinch " + name)
        demo.execute(closed, 100, "stabilize grasp")
        lift = closed.copy()
        lift[2] += lp["lift"]
        demo.execute(lift, 95, "lift " + name)
        carried = s.data.xpos[s.bodies[name]].copy()
        print("carried", name, np.round(carried, 4).tolist(), "delta", np.round(carried - original, 4).tolist(), flush=True)
        if carried[2] < original[2] + 0.08 or s.done:
            print("Physical pickup failed: " + name, s.status()["reason"], flush=True)
            break
        target = lift.copy()
        target[:2] += np.asarray(s.config["target_xy"]) - carried[:2]
        demo.execute(target, 120, "center " + name + " over plate")
        carried = s.data.xpos[s.bodies[name]].copy()
        height = s.stack_top(layer - 1) + LAYER_HALF_HEIGHT[name] + lp["place_gap"]
        lowered = target.copy()
        lowered[2] += height - carried[2]
        lowered[:2] += np.asarray(s.config["target_xy"]) - carried[:2]
        demo.execute(lowered, 95, "lower " + name)
        carried = s.data.xpos[s.bodies[name]].copy()
        if lp.get("recenter", True):
            fix = lowered.copy()
            fix[:2] += np.asarray(s.config["target_xy"]) - carried[:2]
            demo.execute(fix, 60, "stabilize above stack")
            lowered = fix
        else:
            demo.execute(lowered, 60, "stabilize above stack")
        release = opened.copy()
        release[:3] += lowered[:3] - closed[:3]
        demo.execute(release, 90, "open side pinch")
        demo.execute(release, 50, "wait for free release")
        retreat = release.copy()
        retreat[2] += 0.15
        demo.execute(retreat, 65, "withdraw from " + name)
        retreat[0] += 0.13
        demo.execute(retreat, 45, "clear stack")
        demo.execute(retreat, 70, "settle " + name)
        f = s.features()
        print("placed", name, np.round(f["positions"][name], 4).tolist(), "align_err",
              {k: round(v * 1000, 1) for k, v in f["alignment_errors_m"].items()}, "aligned", f["aligned_layers"],
              "adjacent", f["adjacent_contacts"], "reason", s.status()["reason"], flush=True)
        ctrl["next_layer"] = layer + 1
        demo.checkpoint(out.with_name(out.stem + f".ckpt{layer}.npz"), ctrl)
        if s.done or name == args.stop_after:
            break
    if not s.done:
        demo.execute(demo.joint_target, 130, "hands clear; stability check")
    np.savez_compressed(out, actions=np.asarray(s.actions), phases=np.asarray(demo.phases))
    st = s.status()
    summary = {k: st[k] for k in ("success", "reason", "steps", "stage", "aligned_layers", "adjacent_contacts",
                                   "max_alignment_error_m", "max_tilt_rad", "hand_contacts", "released_hold_steps",
                                   "peak_bend_rad", "failure_detail")}
    summary["state_sha"] = s.state_sha()
    out.with_suffix(".live.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--params")
    parser.add_argument("--resume")
    parser.add_argument("--stop-after")
    run(parser.parse_args())
