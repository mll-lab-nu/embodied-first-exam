"""Authoring only (not shipped): build the frozen start state of the source film (spoon held upright above the mug)
on the Marvin rig, physically.

The approved T11 film starts with the teaspoon held upright (bowl down) above the mug, its bowl just above the rim
(source trajectory ``initial = (0.48, 0, 0.885)``; hands omitted in the kinematic demo). That held state is produced
here by a physical authoring run on the task model: the spoon leans in the mug (the wave-2 start), the right Sharpa
hand takes the wave-2 thumb-over / index-under pinch near the handle top (wave-2 GRASP pose converted to the arm by
IK), raises the pinch over the mug axis so the spoon swings upright like a pendulum below the pinch, and holds it
with the bowl centre at the source's start point. The settled ``qpos`` and the held actuator targets become
``initial_qpos`` / ``initial_targets`` in task.json (a contact grasp, no weld; the authoring rows are discarded).
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
FAMILY = HERE.parent
sys.path.insert(0, str(FAMILY))
sys.path.insert(1, str(HERE))
os.environ.setdefault("MUJOCO_GL", "egl")
import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

from runtime import Session
from armctl import ArmCtl, smooth
from rigtools import Rig

# Wave-2 reference (floating six-axis stage; see git history of this family): the spoon leaning in the mug and the
# kinematic pinch (thumb pad above, index pad below the handle, 150 mm from the bowl centre) as stage targets.
LEAN_SPOON = [0.479962, 0.043053, 0.777461, 0.92169, 0.387925, -0.000559, 0.001025]
GRASP = [0.36135, -0.06433, 0.96667, -1.98548, 0.58991, 1.1555, 1.65046, 0.08041, -0.5236, 0.3491, 0.0, 1.39493,
         -0.09912, 0.0, 0.0, 1.3, 0.0, 1.4, 1.0, 1.4, 0.0, 1.5, 1.1, 0.0, 1.4, 0.0, 1.5, 1.1]
THUMB_CLOSE = {"right_thumb_CMC_FE": 0.25, "right_thumb_IP": 0.25}
INDEX_CLOSE = {"right_index_MCP_FE": 0.18, "right_index_PIP": 0.15}
THUMB_OPEN = {"right_thumb_CMC_FE": -0.45}
INDEX_OPEN = {"right_index_MCP_FE": -0.55}
HAND_QUAT = (0.0, 0.7071067811865476, 0.0, 0.7071067811865476)  # wave-2 hand mount under the stage (w, x, y, z)


def stage_pose(w6):
    """World pose of the wave-2 hand root for stage targets (x, y, z, rx, ry, rz): slides along world axes, then
    serial X-Y-Z hinges, then the fixed hand mount quaternion."""
    R = Rotation.from_euler("XYZ", w6[3:6]).as_matrix() @ Rotation.from_quat(
        [HAND_QUAT[1], HAND_QUAT[2], HAND_QUAT[3], HAND_QUAT[0]]).as_matrix()
    return np.asarray(w6[:3], float), R


def fingers_of(session, base, *changes):
    """Right-hand finger targets: the wave-2 finger vector (22, right_hand order) plus named deltas."""
    names = [session.model.actuator(i).name for i in range(session.model.nu)]
    rig_f = [n for n in names if n.startswith("right_")]
    f = np.asarray(base[6:], float).copy()
    for ch in changes:
        for k, v in ch.items():
            f[rig_f.index(k)] += v
    return f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--render")
    ap.add_argument("--approach", type=float, default=0.04)
    ap.add_argument("--squeeze", type=float, default=1.0)
    ap.add_argument("--start-bowl", type=float, nargs=3, default=[0.48, 0.0, 0.885])
    ap.add_argument("--hold", type=int, default=100)
    ap.add_argument("--grip-shift", type=float, default=0.03)
    ap.add_argument("--hand", default="sharpa")
    ap.add_argument("--grip-z", type=float, default=0.125, help="wuji: pinch point along the spoon (m from the bowl)")
    ap.add_argument("--wuji-squeeze", type=float, default=-0.004)
    a = ap.parse_args()
    path = FAMILY / "task.json"
    cfg = json.loads(path.read_text())
    cfg_auth = json.loads(json.dumps(cfg))
    cfg_auth["spoon_pos"] = LEAN_SPOON
    # Authoring session: the spoon leans in the mug (scene default pose), the arm starts parked + open hand.
    import scene
    from scene import arm_rig
    m, _ = scene.build(cfg_auth, hand=a.hand)
    d = mujoco.MjData(m)
    target = arm_rig.default_targets(m)
    qadr = m.jnt_qposadr[m.actuator_trnid[:, 0]]
    d.qpos[qadr] = target
    mujoco.mj_forward(m, d)
    # Start the authoring run with the right hand already above the handle (IK), fingers open (no swing from park).
    from armctl import arm_ik
    gp0, gR0 = stage_pose(GRASP[:6])
    lean_axis0 = Rotation.from_quat([LEAN_SPOON[4], LEAN_SPOON[5], LEAN_SPOON[6], LEAN_SPOON[3]]).as_matrix()[:, 2]
    gp0 = gp0 - lean_axis0 * a.grip_shift
    high0 = gp0 - a.approach * np.array([1.0, 0, 0]) + np.array([0, 0, 0.06])
    q_hi, ep, er = arm_ik.ArmIK(m, "right").solve_best(high0, gR0, qpos=d.qpos)
    lay = arm_rig.layout(m)
    target[lay["arm"]["right"]] = q_hi
    d.qpos[qadr] = target
    mujoco.mj_forward(m, d)
    print(f"start IK err {ep:.4f} m {er:.4f} rad")
    # A Session-like object around this model for ArmCtl / the checker.
    s = Session(config={**cfg_auth, "initial_qpos": {a.hand: d.qpos.tolist()},
                        "initial_targets": {a.hand: target.tolist()}}, hand=a.hand)
    m, d = s.model, s.data
    rig = Rig(m, d, a.hand)
    c = ArmCtl(s, sides=("right",), ki=0.2)
    # Wave-2 grasp pose -> arm IK (the mount frame equals the old hand-root frame).
    e1 = np.array([1.0, 0, 0])
    gp, gR = stage_pose(GRASP[:6])
    # Grip further down the handle than wave-2 (more shaft above the pinch: the hanging spoon creeps slowly through
    # a two-finger pinch while it is stirred).
    lean_axis = Rotation.from_quat([LEAN_SPOON[4], LEAN_SPOON[5], LEAN_SPOON[6], LEAN_SPOON[3]]).as_matrix()[:, 2]
    gp = gp - lean_axis * a.grip_shift
    if a.hand == "sharpa":
        f_pre = fingers_of(s, GRASP, THUMB_OPEN, INDEX_OPEN)
        f_closed = fingers_of(s, GRASP, {k: v * a.squeeze for k, v in THUMB_CLOSE.items()},
                              {k: v * a.squeeze for k, v in INDEX_CLOSE.items()})
    else:
        # Wuji: the same mount orientation as the Sharpa reference; thumb pad on the handle's upper side, index pad
        # under it, fitted by least squares (arm + finger targets) at clearance +12 mm (open) and squeezed.
        sp_b = m.body("spoon").id
        Rs, ps = d.xmat[sp_b].reshape(3, 3), d.xpos[sp_b]
        axis = Rs[:, 2]
        pt = ps + axis * a.grip_z
        up = np.array([0, 0, 1.0]) - axis * axis[2]
        up /= np.linalg.norm(up)
        faces = {"thumb": (pt + up * 0.0027, up), "index": (pt - up * 0.0027, -up)}
        obs = [g for g in range(m.ngeom) if int(m.geom_bodyid[g]) in (sp_b, m.body("cup").id) and m.geom_contype[g]]
        seed = target.copy()
        seed[rig.groups["right"]["thumb"]] = [0.3, 0.0, 0.3, 0.3]
        seed[rig.groups["right"]["index"]] = [0.5, 0.0, 0.5, 0.3]
        for g_, v in (("middle", [1.2, 0.0, 1.4, 0.9]), ("ring", [1.2, 0.0, 1.4, 0.9]), ("pinky", [1.2, 0.0, 1.4, 0.9])):
            seed[rig.groups["right"][g_]] = v
        q0, _, _ = arm_ik.ArmIK(m, "right").solve_best(gp, gR, qpos=d.qpos)
        seed[rig.arm["right"]] = q0
        kw = dict(fingers=("thumb", "index"), rot_weight=0.2, nfev=300)
        touch, c1 = rig.grasp("right", gR, faces, seed, 0.0, obstacles=obs, **kw)
        opened, c2 = rig.grasp("right", gR, faces, touch, 0.012, obstacles=obs, **kw)
        closed, c3 = rig.grasp("right", gR, faces, touch, a.wuji_squeeze, **kw)
        print(f"wuji grasp fit costs touch {c1:.4f} open {c2:.4f} closed {c3:.4f}")
        f_pre, f_closed = opened[rig.fing["right"]], closed[rig.fing["right"]]
        ik_ = arm_ik.ArmIK(m, "right")
        gp, _ = ik_.fk(opened[rig.arm["right"]], qpos=d.qpos)
        gp_closed, _ = ik_.fk(closed[rig.arm["right"]], qpos=d.qpos)
    approach = gp - a.approach * e1
    high = approach + np.array([0, 0, 0.06])
    ok = c.move("open the fingers above the spoon", 40, {"right": (high, gR)}, {"right": f_pre})
    if s.failure:
        print("failure", s.failure, s.failure_detail)
    ok = ok and c.move("lower beside the handle", 50, {"right": (approach, gR)})
    ok = ok and c.move("slide fingers around the handle", 50, {"right": (gp, gR)})
    if a.hand != "sharpa":
        ok = ok and c.move("pinch the handle", 35, {"right": (gp_closed, gR)}, {"right": f_closed})
    else:
        ok = ok and c.move("pinch the handle", 35, fingers={"right": f_closed})
    ok = ok and c.hold("pinch the handle", 20)
    f = s.features()
    print("pinched", f["spoon_fingers"], "failure", s.failure)
    # Pendulum: raise the pinch over the cup axis; the spoon swings upright below it.
    tips = [rig.tips["right"][x] for x in ("thumb", "index")]
    pinch = lambda: d.geom_xpos[tips].mean(axis=0)
    bowl = lambda: d.site_xpos[m.site("bowl_center").id].copy()
    p0 = pinch()
    L = float(np.linalg.norm(p0 - bowl()))
    goal_bowl = np.asarray(a.start_bowl, float)
    hp, hR = c.goal["right"]
    rel = hp - p0
    top = np.array([goal_bowl[0], goal_bowl[1], goal_bowl[2] + L])
    n = 100
    for i in range(1, n + 1):
        u = smooth(i / n)
        lift = np.array([0, 0, 0.05 * np.sin(np.pi * u)])
        if not c.step("raise the spoon upright over the mug", {"right": (p0 + (top - p0) * u + lift + rel, hR)}):
            break
    c.hold("let the spoon settle", 60)
    # Closed loop on the hanging bowl: bring its centre to the source start point.
    for _ in range(4):
        err = goal_bowl - bowl()
        g = c.goal["right"]
        c.move("place the bowl at the start point", 30, {"right": (g[0] + err, g[1])})
    c.hold("hold", a.hold)
    sp = m.body("spoon").id
    v = np.zeros(6)
    mujoco.mj_objectVelocity(m, d, mujoco.mjtObj.mjOBJ_BODY, sp, v, 0)
    tilt = np.degrees(np.arccos(np.clip(d.xmat[sp][8], -1, 1)))
    f = s.features()
    print(f"held: bowl {np.round(bowl(), 4).tolist()} (goal {goal_bowl.tolist()}), tilt {tilt:.2f} deg, spoon speed "
          f"{np.linalg.norm(v[3:]):.4f} m/s, fingers {f['spoon_fingers']}, failure {s.failure}, controls {len(c.rows)}")
    if a.render:
        import imageio
        r = mujoco.Renderer(m, 360, 480)
        cam = mujoco.MjvCamera()
        imgs = []
        for az, el in ((200, -20), (290, -10)):
            cam.lookat[:] = d.xpos[sp] + np.array([0, 0, 0.08])
            cam.distance, cam.azimuth, cam.elevation = 0.5, az, el
            r.update_scene(d, cam)
            imgs.append(r.render())
        imageio.imwrite(a.render, np.concatenate(imgs, axis=1))
    if a.write and not s.failure:
        cfg = json.loads(path.read_text())
        q = d.qpos.copy()
        if a.hand == "sharpa":
            cfg["spoon_pos"] = [float(x) for x in np.r_[q[m.jnt_qposadr[m.body_jntadr[sp]]:][:7]]]
        cfg.setdefault("initial_qpos", {})[a.hand] = [float(x) for x in q]
        cfg.setdefault("initial_targets", {})[a.hand] = [float(x) for x in d.ctrl]
        path.write_text(json.dumps(cfg, indent=1) + "\n")
        print("wrote", path)


if __name__ == "__main__":
    main()
