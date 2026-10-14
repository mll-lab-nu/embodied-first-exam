"""Authoring controller: native side pinches and contact-driven placement."""

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


def pinch_pose(session, name, clearance, seed=None):
    m = session.model
    d = mujoco.MjData(m)
    q = np.asarray(session.config["initial_targets"]["sharpa"]).copy() if seed is None else seed.copy()
    if seed is None:
        q[3] = 0.0
    center = session.data.xpos[session.bodies[name]].copy()
    direction = 0 if name in ("cheese", "lettuce") else 1
    radius = {"patty": 0.048, "tomato": 0.046, "cheese": 0.049, "lettuce": 0.052, "top_bun": 0.051}[name]
    gids = [m.geom("right_index_fingertip_collision").id, m.geom("right_thumb_fingertip_collision").id]
    variable = np.r_[0:6, 6:15]
    lo, hi = m.actuator_ctrlrange[variable].T.copy()
    lo[2] = center[2] + 0.025
    initial = q[variable].copy()
    collisions = [
        g
        for g in range(m.ngeom)
        if m.geom_contype[g] and session.owner.get(int(m.geom_bodyid[g])) == "hand" and g not in gids
    ]
    food = (
        m.geom(name + "_collision").id if name not in ("cheese", "lettuce") else m.geom(name + "_center_collision").id
    )
    obstacles = [m.geom("table").id, m.geom(name + "_prep_support").id]

    def residual(values):
        q[variable] = values
        d.qpos[:] = session.data.qpos
        d.qpos[session.qadr] = q
        mujoco.mj_forward(m, d)
        errors = []
        for gid, sign in zip(gids, (1, -1)):
            axis = d.geom_xmat[gid].reshape(3, 3)[:, 2]
            pad_radius = m.geom_size[gid, 0] + m.geom_size[gid, 1] * abs(axis[direction])
            target = center.copy()
            target[direction] += sign * (radius + pad_radius + clearance)
            errors.extend((d.geom_xpos[gid] - target) * 100)
        for gid in collisions:
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
    if fit.cost > 0.002:
        raise RuntimeError(f"Unreachable pinch for {name}: {fit.cost}")
    return q.copy()


def make_demo(output, stop_after=None):
    session = Session()
    phases = []
    joint_target = session.hold_action()
    dofs = session.model.jnt_dofadr[session.model.actuator_trnid[:, 0]]
    gains = session.model.actuator_gainprm[:, 0]

    def execute(target, count, phase):
        nonlocal joint_target
        start = joint_target.copy()
        for ratio in np.linspace(0, 1, count + 1)[1:]:
            if session.done:
                break  # the episode ended (success or failure); later rows would not be executed
            # Smooth acceleration avoids throwing a freely grasped ingredient.
            blend = ratio * ratio * (3 - 2 * ratio)
            joint_target = start + (target - start) * blend
            action = joint_target + session.data.qfrc_bias[dofs] / gains
            action[6:] += 2.0 * (joint_target[6:] - session.data.qpos[session.qadr[6:]])
            action = np.clip(action, *session.model.actuator_ctrlrange.T)
            session.step(action)
            phases.append(phase)
        f = session.features()
        print(
            phase,
            json.dumps({k: f[k] for k in ("aligned_layers", "hand_contacts", "finger_contacts", "peak_bend_rad")}),
            flush=True,
        )

    execute(session.hold_action(), 35, "settle ingredients")
    previous_opened = None
    previous_center = None
    previous_direction = 1
    for layer, name in enumerate(session.names[1:], 1):
        original = session.data.xpos[session.bodies[name]].copy()
        seed = None
        if previous_opened is not None:
            seed = previous_opened.copy()
            seed[:3] += original - previous_center
            direction = 0 if name in ("cheese", "lettuce") else 1
            if direction != previous_direction:
                rotation = Rotation.from_euler("z", -np.pi / 2 if direction == 0 else np.pi / 2).as_matrix()
                seed[:3] = original + rotation @ (seed[:3] - original)
                seed[3:6] = Rotation.from_matrix(rotation @ Rotation.from_euler("XYZ", seed[3:6]).as_matrix()).as_euler(
                    "XYZ"
                )
        opened = pinch_pose(session, name, 0.006, seed)
        closed = pinch_pose(session, name, -0.004, opened)
        previous_opened, previous_center = opened.copy(), original.copy()
        previous_direction = 0 if name in ("cheese", "lettuce") else 1
        outside = opened.copy()
        above = outside.copy()
        above[2] += 0.15
        execute(above, 65, "approach " + name)
        execute(above, 150, "prepare pinch posture")
        execute(outside, 65, "align beside " + name)
        execute(opened, 65, "reach edge of " + name)
        execute(closed, 50, "pinch " + name)
        execute(closed, 100, "stabilize grasp")
        lift = closed.copy()
        lift[2] += 0.16
        execute(lift, 95, "lift " + name)
        carried = session.data.xpos[session.bodies[name]].copy()
        print("carried", name, carried.tolist(), "delta", (carried - original).tolist(), flush=True)
        if carried[2] < original[2] + 0.08:
            print("Physical pickup failed: " + name, flush=True)
            break
        target = lift.copy()
        target[:2] += np.asarray(session.config["target_xy"]) - carried[:2]
        execute(target, 120, "center " + name + " over plate")
        carried = session.data.xpos[session.bodies[name]].copy()
        height = session.stack_top(layer - 1) + LAYER_HALF_HEIGHT[name] + 0.024
        lowered = target.copy()
        lowered[2] += height - carried[2]
        lowered[:2] += np.asarray(session.config["target_xy"]) - carried[:2]
        execute(lowered, 95, "lower " + name)
        execute(lowered, 60, "stabilize above stack")
        release = opened.copy()
        release[:3] += lowered[:3] - closed[:3]
        execute(release, 90, "open side pinch")
        execute(release, 50, "wait for free release")
        retreat = release.copy()
        retreat[2] += 0.15
        execute(retreat, 65, "withdraw from " + name)
        retreat[0] += 0.13
        execute(retreat, 45, "clear stack")
        execute(retreat, 70, "settle " + name)
        print("placed", name, session.features()["positions"][name], flush=True)
        if name == stop_after:
            break
    execute(joint_target, 130, "hands clear; stability check")
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, actions=np.asarray(session.actions), phases=np.asarray(phases))
    out.with_suffix(".live.json").write_text(
        json.dumps(
            {"initial_sha": session.initial_sha, "final_sha": session.state_sha(), "verdict": session.features()},
            indent=2,
        )
        + "\n"
    )
    from PIL import Image

    Image.fromarray(session.render_frame(width=1280, height=720)).save(out.with_suffix(".png"))
    print(json.dumps(session.features(), indent=2), flush=True)
    session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--stop-after")
    args = parser.parse_args()
    make_demo(args.out, args.stop_after)
