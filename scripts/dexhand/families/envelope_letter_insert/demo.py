"""Authoring controller (Sharpa Wave): press-and-slide the letter to the envelope mouth, feed it in by fingertip
friction, finish with a fingertip push on the trailing edge, then withdraw the hand.

Closed loop at authoring time only (it reads the letter/envelope poses to place its waypoints); the recorded rows
are plain motor targets that replay open loop. Usage:
    python demo.py --out solution/trajectory.npz [--hand sharpa]
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")
import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

from runtime import Session

FINGERS = ("index", "middle", "ring", "pinky")


def smooth(r):
    return r * r * (3 - 2 * r)


class Controller:
    def __init__(self, session, posture, beta, log=print, ref=(0, 2)):
        self.s = session
        self.m, self.d = session.model, session.data
        self.log = log
        self.phases = []
        self.dofs = self.m.jnt_dofadr[self.m.actuator_trnid[:, 0]]
        self.gains = self.m.actuator_gainprm[:, 0].copy()
        self.lo, self.hi = self.m.actuator_ctrlrange.T
        self.origin = self.m.body("wrist_stage").pos.copy()
        self.posture = np.asarray(posture, dtype=float)
        self.beta = beta
        self.wuji = session.hand == "wuji"
        if self.wuji:
            # Wuji Hand 2.2: fingertip = collision meshes of the distal link and the tip sensor frame
            self.tips = []
            for f in ("index_finger", "middle_finger", "ring_finger", "pinky"):
                bodies = {self.m.body(f"r_wuji_r_{f}_{part}").id for part in ("distal", "tip_sensor_frame")}
                self.tips.append([g for g in range(self.m.ngeom) if self.m.geom_bodyid[g] in bodies
                                  and self.m.geom_contype[g] and self.m.geom_type[g] == mujoco.mjtGeom.mjGEOM_MESH])
        else:
            self.tips = [self.m.geom(f"right_{f}_fingertip_collision").id for f in FINGERS]
        self.ref = tuple(ref)
        self.offsets = self._tip_offsets()
        self.target = self.s.hold_action().copy()
        self.yaw = 0.0

    # -------------------------------------------------------------- kinematics
    def _hand_rotation(self, yaw):
        """Wrist stage rotation: fingers tilted by beta towards -X (palm facing -X), then yawed about world Z."""
        b = self.beta
        f = np.array([-np.sin(b), 0, -np.cos(b)])
        n = np.array([-np.cos(b), 0, np.sin(b)])
        y = np.cross(f, n)
        desired = Rotation.from_euler("z", yaw).as_matrix() @ np.c_[n, y, f]
        w, x, y_, z = self.m.body("right_hand_C_MC").quat
        hand_mount = Rotation.from_quat([x, y_, z, w]).as_matrix()
        return desired @ hand_mount.T

    def _tip_offsets(self):
        """Fingertip capsule centres and axes in the wrist-stage frame for the fixed finger posture."""
        d = mujoco.MjData(self.m)
        q = self.s.hold_action().copy()
        q[:6] = 0
        q[6:] = self.posture
        d.qpos[self.s.qadr] = q
        mujoco.mj_kinematics(self.m, d)
        if self.wuji:
            points = []
            for geoms in self.tips:
                pts = []
                for g in geoms:
                    mid = self.m.geom_dataid[g]
                    v = self.m.mesh_vert[self.m.mesh_vertadr[mid]: self.m.mesh_vertadr[mid] + self.m.mesh_vertnum[mid]]
                    pts.append(d.geom_xpos[g] + v @ d.geom_xmat[g].reshape(3, 3).T - self.origin)
                points.append(np.concatenate(pts))
            return points, None
        centres = np.array([d.geom_xpos[g] - self.origin for g in self.tips])
        axes = np.array([d.geom_xmat[g].reshape(3, 3)[:, 2] for g in self.tips])
        return centres, axes

    def set_posture(self, posture, ref, beta=None):
        """Switch the finger posture (reached smoothly by the next `run`), the reference fingertips and the tilt."""
        if beta is not None:
            self.beta = beta
        self.posture = np.asarray(posture, dtype=float)
        self.ref = tuple(ref)
        self.offsets = self._tip_offsets()

    def lowest_points(self, yaw):
        """Lowest point of each fingertip capsule, relative to the wrist-stage position, in world axes."""
        rw = self._hand_rotation(yaw)
        if self.wuji:
            out = []
            for pts in self.offsets[0]:
                p = pts @ rw.T
                out.append(p[np.argmin(p[:, 2])])
            return np.array(out)
        centres, axes = self.offsets
        c = centres @ rw.T
        a = axes @ rw.T
        radius, half = self.m.geom_size[self.tips[0], 0], self.m.geom_size[self.tips[0], 1]
        end = c - half * np.sign(a[:, 2])[:, None] * a
        return end - np.array([0, 0, radius])

    def tip_geometry(self, yaw):
        """(reference point offset, lowest-point z offset) in world axes for the posture at this yaw."""
        if self.wuji:
            low = self.lowest_points(yaw)
            return low, low[:, 2]
        rw = self._hand_rotation(yaw)
        centres, axes = self.offsets
        c = centres @ rw.T
        a = axes @ rw.T
        radius, half = self.m.geom_size[self.tips[0], 0], self.m.geom_size[self.tips[0], 1]
        low = c[:, 2] - radius - half * np.abs(a[:, 2])
        return c, low

    def wrist_targets(self, point, yaw, z_low):
        """Wrist targets that put the fingertip line's centre at `point` (x, y) with the lowest fingertip at z_low."""
        rw = self._hand_rotation(yaw)
        c, low = self.tip_geometry(yaw)
        i, j = self.ref
        ref = 0.5 * (c[i] + c[j])  # between the two reference fingertips
        pos = np.array([point[0] - ref[0], point[1] - ref[1], z_low - low[list(self.ref)].min()]) - self.origin
        euler = Rotation.from_matrix(rw).as_euler("XYZ")
        return np.r_[pos, euler]

    def check_kinematics(self):
        q = self.s.hold_action().copy()
        q[:6] = self.wrist_targets((0.5, 0.0), 0.2, 0.8)
        q[6:] = self.posture
        d = mujoco.MjData(self.m)
        d.qpos[self.s.qadr] = q
        mujoco.mj_kinematics(self.m, d)
        mid = 0.5 * (d.geom_xpos[self.tips[0]] + d.geom_xpos[self.tips[2]])
        return mid

    # -------------------------------------------------------------- execution
    def row(self):
        action = self.target.copy()
        action[:6] += self.d.qfrc_bias[self.dofs[:6]] / self.gains[:6]
        return np.clip(action, self.lo, self.hi)

    def run(self, goal, count, phase, until=None):
        start = self.target.copy()
        goal = np.asarray(goal, dtype=float)
        for i in range(1, count + 1):
            if self.s.done:
                break
            self.target = start + (goal - start) * smooth(i / count)
            self.s.step(self.row())
            self.phases.append(phase)
            if until is not None and until():
                break
        return self.s.features()

    def hold(self, count, phase):
        return self.run(self.target.copy(), count, phase)

    def pose(self, point, yaw, z_low):
        q = self.target.copy()
        q[:6] = self.wrist_targets(point, yaw, z_low)
        q[6:] = self.posture
        return q

    # -------------------------------------------------------------- state
    def letter(self):
        b = self.m.body("letter").id
        r = self.d.xmat[b].reshape(3, 3)
        return self.d.xpos[b].copy(), float(np.arctan2(r[1, 0], r[0, 0]))

    def envelope(self):
        b = self.m.body("envelope").id
        r = self.d.xmat[b].reshape(3, 3)
        return self.d.xpos[b].copy(), float(np.arctan2(r[1, 0], r[0, 0])), r


def wuji_posture(s, beta, pip=0.35, dip=0.25, mcp=0.25):
    """Wuji Hand 2.2 pressing posture: four fingertips level (lowest points at one height), thumb neutral."""
    from scipy.optimize import least_squares

    names = s.actuator_names[6:]
    q = np.zeros(len(names))
    keys = []
    for f in ("FF", "MF", "RF", "LF"):
        q[names.index(f"r_wuji_r_{f}J2")] = pip
        q[names.index(f"r_wuji_r_{f}J3")] = dip
        keys.append(names.index(f"r_wuji_r_{f}J0"))
    c = Controller(s, q, beta)

    def residual(v):
        q[keys] = v
        c.set_posture(q, (0, 2))
        low = c.lowest_points(0.0)
        return np.r_[(low[:, 2] - low[1, 2]) * 100, (v[1] - mcp) * 2.0]

    fit = least_squares(residual, np.full(4, mcp), bounds=(np.full(4, -0.5), np.full(4, 1.5)))
    q[keys] = fit.x
    return q.copy()


def make_demo(output, hand="sharpa", params=None):
    p = dict(
        beta=0.55,
        press_local_x=0.030,
        press_depth=0.0015,
        preinsert_gap=0.010,
        feed_stop=0.012,
        push_depth=0.0055,
        push_height=0.0011,
        push_back=0.013,
        contact_offset=0.006,
        align_iters=4,
        feed_increment=0.008,
        feed_steps=12,
        lateral_gain=0.8,
        yaw_gain=0.8,
        push_increment=0.005,
        push_steps=10,
        slack_rows=100,
        transport_correct=hand == "wuji",
        follow_wedge=hand == "wuji",
    )
    if hand == "wuji":
        p.update(press_depth=0.0025)
    p.update(params or {})
    # Authored on the wave-2 floating wrist stage; tools/arm_port.py moves the result onto the Marvin arm.
    s = Session(hand=hand, config=json.loads((Path(__file__).resolve().parent / "tools/floating_task.json").read_text()))
    cfg = s.config
    top = cfg["desk_top_z"]
    letter_t = cfg["letter"]["thickness_m"]
    half_depth = cfg["letter"]["depth_m"] / 2
    env_half_depth = cfg["envelope"]["depth_m"] / 2
    posture = np.zeros(s.action_dim - 6)
    names = s.actuator_names[6:]
    if s.hand == "wuji":
        posture = wuji_posture(s, p["beta"], pip=p.get("wuji_pip", 0.35), dip=p.get("wuji_dip", 0.25),
                               mcp=p.get("wuji_mcp", 0.25))
    else:
        for name, value in dict(
            right_thumb_CMC_FE=0.2, right_thumb_MCP_FE=0.2, right_thumb_IP=0.2,
            right_index_MCP_FE=0.211648, right_index_PIP=0.35, right_index_DIP=0.2,
            right_middle_MCP_FE=0.25007, right_middle_PIP=0.35, right_middle_DIP=0.2,
            right_ring_MCP_FE=0.175592, right_ring_PIP=0.35, right_ring_DIP=0.2,
            right_pinky_MCP_FE=0.096823, right_pinky_PIP=0.35, right_pinky_DIP=0.2,
        ).items():
            posture[names.index(name)] = value
    c = Controller(s, posture, p["beta"])
    log = []

    def note(tag):
        f = s.features()
        lp, ly = c.letter()
        ep, ey, _ = c.envelope()
        entry = dict(tag=tag, step=s.steps, letter=lp.round(4).tolist(), letter_yaw=round(ly, 4),
                     envelope=ep.round(4).tolist(), envelope_yaw=round(ey, 4), stage=f["stage_completed"],
                     fraction=round(f["inserted_fraction"], 3), outside=round(f["outside_m"], 4),
                     contacts=[f["hand_letter_contacts"], f["hand_envelope_contacts"]], failure=f["failure"])
        log.append(entry)
        print(json.dumps(entry), flush=True)

    def rot2(a):
        return np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])

    def rel():
        """Letter centre (x, y) and yaw in the envelope frame."""
        lp, ly = c.letter()
        ep, ey, _ = c.envelope()
        xy = rot2(-ey) @ (lp[:2] - ep[:2])
        return xy, ly - ey, lp, ly, ep, ey

    def letter_point(local_x):
        lp, ly = c.letter()
        return lp[:2] + rot2(ly) @ np.array([local_x, 0.0])

    surface = top + letter_t
    press_z = surface - p["press_depth"]
    # 1. approach and press on the letter centre (no drag torque while transporting)
    press = letter_point(0.0)
    c.run(c.pose(press, 0.0, surface + 0.06), 60, "approach letter")
    c.run(c.pose(press, 0.0, surface + 0.01), 40, "descend")
    c.run(c.pose(press, 0.0, press_z), 30, "press letter")
    c.hold(15, "press letter")
    note("pressed")
    # 2. slide to the pre-insertion pose in front of the mouth: +X first (clear of the flap), then +Y
    _, _, lp, ly, ep, ey = rel()
    pre_x = env_half_depth + cfg["envelope"]["flap_depth_m"] + half_depth + p["preinsert_gap"]
    goal = ep[:2] + rot2(ey) @ np.array([pre_x, 0.0])
    via = np.array([goal[0], press[1]])
    if not p["transport_correct"]:
        c.run(c.pose(via, 0.0, press_z), 110, "slide letter towards the mouth")
        c.run(c.pose(goal, 0.0, press_z), 170, "slide letter to the mouth")
        press = goal
    else:
        # closed-loop legs (authoring only): compensate the letter's slip under the fingertips after each leg
        hand_at = via.copy()
        c.run(c.pose(hand_at, 0.0, press_z), 130, "slide letter towards the mouth")
        for _ in range(3):
            lp, _ = c.letter()
            err = goal[0] - lp[0]
            if abs(err) < 0.002:
                break
            hand_at = hand_at + np.array([err, 0.0])
            c.run(c.pose(hand_at, 0.0, press_z), 40, "slide letter towards the mouth")
        target = hand_at + np.array([0.0, goal[1] - via[1]])
        c.run(c.pose(target, 0.0, press_z), 200, "slide letter to the mouth")
        for _ in range(3):
            lp, _ = c.letter()
            err = goal - lp[:2]
            if np.abs(err).max() < 0.002:
                break
            target = target + err
            c.run(c.pose(target, 0.0, press_z), 40, "slide letter to the mouth")
        press = target
    c.hold(15, "settle")
    note("preinsert")
    # 3. align: translate/rotate about the pressed centre until the letter is square to the mouth
    for attempt in range(p["align_iters"]):
        xy, dyaw, lp, ly, ep, ey = rel()
        err = np.array([pre_x, 0.0]) - xy
        press = press + rot2(ey) @ err
        c.yaw = c.yaw - dyaw
        c.run(c.pose(press, c.yaw, press_z), 40, "square the letter to the mouth")
        c.hold(10, "settle")
        note(f"align-{attempt}")
    # 4. re-grip on the trailing half
    c.run(c.pose(press, c.yaw, surface + 0.008), 25, "lift fingertips")
    press = letter_point(p["press_local_x"])
    c.run(c.pose(press, c.yaw, surface + 0.008), 30, "move to the trailing half")
    c.run(c.pose(press, c.yaw, press_z), 25, "press trailing half")
    c.hold(10, "settle")
    # 5. feed in by fingertip friction, in closed-loop increments
    feed_goal_x = env_half_depth + p["feed_stop"] - p["press_local_x"]  # letter-centre x_e at the end of feeding
    step = p["feed_increment"]
    for k in range(60):
        xy, dyaw, lp, ly, ep, ey = rel()
        if xy[0] <= feed_goal_x + 1e-4:
            break
        dx = -min(step, xy[0] - feed_goal_x)
        corr = np.array([dx, -xy[1] * p["lateral_gain"]])
        press = press + rot2(ey) @ corr
        c.yaw = c.yaw - dyaw * p["yaw_gain"]
        z = press_z + (cfg["envelope"]["wall_m"] if xy[0] < pre_x - 0.03 else 0.0)
        c.run(c.pose(press, c.yaw, z), p["feed_steps"], "feed letter into the mouth")
        f = s.features()
        print("feed", k, "rel", xy.round(4).tolist(), round(dyaw, 4), "env", c.envelope()[0][:2].round(4).tolist(),
              "hc", f["hand_letter_contacts"], f["hand_envelope_contacts"], f["envelope_fingers"], "frac",
              round(f["inserted_fraction"], 3), "seams", f["corners_in_seams"], "walls", f["corners_between_walls"])
        if s.done:
            break
        if f["hand_envelope_contacts"]:
            # a fingertip reached the parted mouth lip: back off slightly and stop feeding
            press = press + rot2(ey) @ np.array([0.003, 0.0])
            c.run(c.pose(press, c.yaw, z), 10, "feed letter into the mouth")
            break
    c.hold(15, "settle")
    note("fed")
    # 6. lift the fingertips, move behind the trailing edge and push it in
    c.run(c.pose(press, c.yaw, surface + 0.012), 30, "lift fingertips")
    xy, dyaw, lp, ly, ep, ey = rel()
    trailing = lp[:2] + rot2(ly) @ np.array([half_depth, 0.0])
    behind = trailing + rot2(ey) @ np.array([p["push_back"], 0.0])
    c.run(c.pose(behind, c.yaw, surface + 0.012), 40, "move behind the trailing edge")
    c.run(c.pose(behind, c.yaw, top + p["push_height"]), 40, "lower behind the trailing edge")
    note("behind")
    # push in closed-loop increments until the trailing edge is `push_depth` inside the mouth line
    target = behind.copy()
    cen, _ = c.tip_geometry(c.yaw)
    low_offset = c.lowest_points(c.yaw)[list(c.ref)].mean(axis=0)[:2] - 0.5 * (cen[c.ref[0]] + cen[c.ref[1]])[:2]
    wall, flap = cfg["envelope"]["wall_m"], cfg["envelope"]["flap_depth_m"]

    def push_z(point):
        """Fingertip height for the push; optionally following the flap wedge / back wall under the fingertips."""
        if not p["follow_wedge"]:
            return top + p["push_height"]
        ep_, ey_, _ = c.envelope()
        xe = (rot2(-ey_) @ (point + low_offset - ep_[:2]))[0]
        return top + p["push_height"] + wall * float(np.clip((env_half_depth + flap - xe) / flap, 0.0, 1.0))

    for k in range(80):
        f = s.features()
        corners = np.asarray(f["corners_envelope_frame"])
        trailing_x = corners[:, 0].max()
        remaining = trailing_x - (env_half_depth - p["push_depth"])
        print("push", k, "trail", round(trailing_x, 4), "yc", round(float(corners[:, 1].mean()), 4), "hc",
              f["hand_letter_contacts"], f["hand_envelope_contacts"], "env", c.envelope()[0][:2].round(4).tolist(),
              "frac", round(f["inserted_fraction"], 3), "outside", round(f["outside_m"], 4))
        if f["hand_envelope_contacts"] and p.get("debug"):
            pairs = []
            for i in range(s.data.ncon):
                con = s.data.contact[i]
                n1, n2 = s.model.geom(con.geom1).name, s.model.geom(con.geom2).name
                if "envelope" in n1 + n2 and ("right_" in n1 + n2 or "wuji" in n1 + n2):
                    pairs.append((n1, n2, round(con.dist * 1000, 2), s.data.geom_xpos[con.geom1].round(4).tolist()))
            print("  env contacts", pairs, "lip angle", round(float(s.data.qpos[s.model.jnt_qposadr[s.model.joint("envelope_lip_fold").id]]), 3))
            from PIL import Image
            Image.fromarray(s.render_frame(p["debug"], 960, 540)).save(Path(output).with_name(f"debug_push_{k}.png"))
        if remaining <= 0 or s.done:
            break
        if s.status()["stage"] >= 2 and f["outside_m"] <= p.get("stop_outside_m", -1.0):
            break  # inserted with margin: stop before the fingertip drags the envelope along
        ep, ey, _ = c.envelope()
        lateral = -float(corners[:, 1].mean()) * p["lateral_gain"]
        target = target + rot2(ey) @ np.array([-min(p["push_increment"], remaining + 0.004), lateral])
        c.run(c.pose(target, c.yaw, push_z(target)), p["push_steps"], "push the trailing edge in")
    c.hold(20, "settle")
    note("pushed")
    # 7. withdraw the hand and wait for the released hold
    c.run(c.pose(target + rot2(ey) @ np.array([0.03, 0.0]), c.yaw, top + 0.03), 50, "withdraw")
    c.run(c.pose(target + rot2(ey) @ np.array([0.10, 0.0]), c.yaw, top + 0.12), 60, "withdraw")
    c.hold(120, "released hold")
    note("end")
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    actions = np.asarray(s.actions)
    phases = list(c.phases[: len(actions)])
    # Slack: hold rows after the last executed row (the episode ends at success, so they are never executed).
    pad = int(p["slack_rows"])
    actions = np.vstack([actions, np.repeat(actions[-1:], pad, axis=0)])
    phases += ["hold"] * pad
    s.save_trajectory(actions, out)
    np.savez_compressed(out.with_name(out.stem + ".phases.npz"), actions=actions, phases=np.asarray(phases),
                        hand=np.array(s.hand), task=np.array(s.task))
    status = {k: v for k, v in s.status().items() if k != "corners_envelope_frame"}
    out.with_suffix(".live.json").write_text(json.dumps(dict(status=status, log=log, params=p, rows=len(actions),
                                                             final_sha=s.state_sha()), indent=1) + "\n")
    print(json.dumps({k: s.status()[k] for k in ("success", "reason", "stage", "steps")}))
    return s, c


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--hand", default="sharpa")
    parser.add_argument("--params", default="{}")
    args = parser.parse_args()
    make_demo(args.out, args.hand, json.loads(args.params))
