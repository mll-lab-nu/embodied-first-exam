"""Authoring controller (not shipped to tasks): closed-loop pinch, transport and insertion, recorded as rows.

The controller reads the simulator state (plug, hub and hand poses) to choose actuator targets; only the recorded
actuator rows form the trajectory, and replay.py re-executes them open loop from the frozen reset.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("MUJOCO_GL", "egl")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import mujoco
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

from runtime import Session
from scene import USB

LAYOUTS = {
    # actuator index groups (after the six wrist targets) and the free fingers' curled / straight targets
    "sharpa": dict(THUMB=list(range(6, 11)), INDEX=list(range(11, 15)), MIDDLE=list(range(15, 19)),
                   OTHERS=list(range(19, 28)), CURLED=np.array([1.2, 0.0, 1.4, 0.9, 0.1, 1.2, 0.0, 1.4, 0.9]),
                   EXTENDED=np.array([0.15, 0.0, 0.2, 0.1, 0.0, 0.15, 0.0, 0.2, 0.1])),
    "wuji": dict(THUMB=list(range(6, 10)), INDEX=list(range(10, 14)), MIDDLE=list(range(14, 18)),
                 OTHERS=list(range(18, 26)), CURLED=np.array([1.2, 0.0, 1.4, 0.9, 1.2, 0.0, 1.4, 0.9]),
                 EXTENDED=np.array([0.15, 0.0, 0.2, 0.1, 0.15, 0.0, 0.2, 0.1])),
}
THUMB = INDEX = MIDDLE = OTHERS = CURLED = EXTENDED = None


def use_layout(hand):
    globals().update(LAYOUTS[hand])


def frame(R, p):
    T = np.eye(4)
    T[:3, :3], T[:3, 3] = R, p
    return T


class Controller:
    def __init__(self, session, log=print):
        self.s = session
        m = self.m = session.model
        self.d = session.data
        self.scratch = mujoco.MjData(m)
        self.hand_root = m.body("right_hand_C_MC").id
        self.Rq0 = Rotation.from_quat(m.body_quat[self.hand_root][[1, 2, 3, 0]]).as_matrix()
        self.B = Rotation.from_quat(m.body_quat[m.body("wrist_gimbal").id][[1, 2, 3, 0]]).as_matrix()
        self.plug = m.body("plug").id
        self.hub = m.body("hub").id
        self.hand = session.hand
        use_layout(self.hand)
        if self.hand == "sharpa":
            self.tips = {f: m.geom(f"right_{f}_fingertip_collision").id for f in ("thumb", "index", "middle")}
        else:
            names = {"thumb": "thumb", "index": "index_finger", "middle": "middle_finger"}
            self.tips = {f: m.geom(f"r_wuji_r_{n}_tip_sensor_frame_collision1").id for f, n in names.items()}
            self.tip_sites = {f: m.site(f"r_wuji_r_{n}_tip").id for f, n in names.items()}
            self.distal = {f: m.body(f"r_wuji_r_{n}_distal").id for f, n in names.items()}
        self.housing = m.geom("plug_housing").id
        owner = session.checker.owner
        self.hand_geoms = [g for g in range(m.ngeom) if owner[int(m.geom_bodyid[g])] == "hand" and m.geom_contype[g]]
        self.obstacles = [m.geom("counter").id] + [g for g in range(m.ngeom) if owner[int(m.geom_bodyid[g])] == "hub"
                                                  and m.geom_contype[g]]
        self.plug_geoms = [g for g in range(m.ngeom) if int(m.geom_bodyid[g]) == self.plug and m.geom_contype[g]]
        self.dofs = m.jnt_dofadr[m.actuator_trnid[:, 0]]
        self.gains = m.actuator_gainprm[:, 0].copy()
        self.lo, self.hi = m.actuator_ctrlrange.T
        self.target = session.hold_action()
        self.phases = []
        self.log = log
        self.axis_weight = 0.3
        self.max_step = 0.0015
        self.debug = False
        self.max_rot = 0.015
        self.nfev = 600

    # ------------------------------------------------------------------ kinematics
    def stage_from_hand(self, R_hand, p_hand, near):
        R_stage = self.B.T @ R_hand @ self.Rq0.T
        a = Rotation.from_matrix(R_stage).as_euler("XYZ")
        candidates = [a, np.array([a[0] + np.pi, np.pi - a[1], a[2] + np.pi])]
        best = None
        for c in candidates:
            c = near + (c - near + np.pi) % (2 * np.pi) - np.pi
            if best is None or np.linalg.norm(c - near) < np.linalg.norm(best - near):
                best = c
        return np.r_[p_hand, best]

    def hand_pose(self, d=None):
        d = d or self.d
        return frame(d.xmat[self.hand_root].reshape(3, 3), d.xpos[self.hand_root])

    def plug_pose(self, d=None):
        d = d or self.d
        return frame(d.xmat[self.plug].reshape(3, 3), d.xpos[self.plug])

    def port_frame(self, k=None):
        k = self.s.config["target_port"] if k is None else k
        R = self.d.xmat[self.hub].reshape(3, 3)
        mouth = self.d.xpos[self.hub] + R @ np.array([USB["hub"]["ports_x"][k], USB["hub"]["mouth_y"], 0.0])
        return R, mouth

    def pinch(self, R_hand_goal, clearance, seed, contact_x=0.0045, ys=(-0.0215, -0.0295, -0.0135), weight_rot=0.3,
              tilt=1.0, yaw=0.0):
        """Least-squares wrist + thumb/index targets: the fingertip end spheres press the housing's broad faces.

        Thumb on the +z_p (polarity) face, index on the -z_p face; contact ``contact_x`` along x_p (toward the hand),
        each distal pad tilted back toward -x_p by ``tilt`` (tip->base direction = n + tilt * (-x_p)).
        """
        m, d = self.m, self.scratch
        variable = np.r_[0:6, THUMB, INDEX, MIDDLE]
        q = seed.copy()
        P = self.plug_pose()
        Rp, pp = P[:3, :3], P[:3, 3]
        # The thumb presses the -z_p face, index and middle the +z_p (polarity) face; ``up`` is the side of x_p
        # pointing away from the counter while the plug lies on its side (the fingers' base side).
        up = 1.0 if Rp[2, 0] >= 0 else -1.0
        faces = {"thumb": (np.array([up * contact_x, ys[0], -0.004]), -Rp[:, 2]),
                 "index": (np.array([up * contact_x, ys[1], 0.004]), Rp[:, 2]),
                 "middle": (np.array([up * contact_x, ys[2], 0.004]), Rp[:, 2])}
        others = [g for g in self.hand_geoms if g not in self.tips.values()]
        lo, hi = self.lo[variable] + 1e-6, self.hi[variable] - 1e-6
        x0 = np.clip(q[variable], lo, hi)

        def residual(x):
            q[variable] = x
            d.qpos[:] = self.d.qpos
            d.qpos[self.s.qadr] = q
            mujoco.mj_forward(m, d)
            err = []
            for f, gid in self.tips.items():
                local, normal = faces[f]
                want = normal + tilt * (up * np.cos(yaw) * Rp[:, 0] - np.sin(yaw) * Rp[:, 1])
                want /= np.linalg.norm(want)
                if self.hand == "sharpa":
                    axis = d.geom_xmat[gid].reshape(3, 3)[:, 2]
                    end = d.geom_xpos[gid] + axis * m.geom_size[gid, 1]
                    goal = pp + Rp @ local + normal * (m.geom_size[gid, 0] + clearance)
                    err.extend((end - goal) * 300)
                else:
                    # Mesh fingertip: signed distance to the housing and where the nearest housing point lies.
                    fromto = np.zeros(6)
                    dist = mujoco.mj_geomDistance(m, d, gid, self.housing, 1.0, fromto)
                    err.append((dist - clearance) * 300)
                    err.extend((fromto[3:] - (pp + Rp @ local)) * 300)
                    axis = d.site_xpos[self.tip_sites[f]] - d.xpos[self.distal[f]]
                    axis /= np.linalg.norm(axis)
                err.extend((-axis - want) * self.axis_weight)
            R = d.xmat[self.hand_root].reshape(3, 3)
            err.extend((R - R_hand_goal).ravel() * weight_rot)
            for g in others:
                for o in self.obstacles + self.plug_geoms:
                    dist = mujoco.mj_geomDistance(m, d, g, o, 0.01, None)
                    err.append(min(0.0, dist - 0.003) * 300)
            for g in self.tips.values():
                for o in self.obstacles:
                    dist = mujoco.mj_geomDistance(m, d, g, o, 0.01, None)
                    err.append(min(0.0, dist - 0.0015) * 300)
            err.extend((x - x0) * 0.01)
            return np.asarray(err)

        fit = least_squares(residual, x0, bounds=(lo, hi), max_nfev=self.nfev)
        residual(fit.x)
        return q.copy(), fit.cost

    # ------------------------------------------------------------------ execution
    def command(self, target, boost=2.0):
        action = target + self.d.qfrc_bias[self.dofs] / self.gains
        action[6:] += boost * (target[6:] - self.d.qpos[self.s.qadr[6:]])
        return np.clip(action, self.lo, self.hi)

    def execute(self, goal, count, phase, boost=2.0):
        start = self.target.copy()
        for ratio in np.linspace(0, 1, count + 1)[1:]:
            if self.s.done:
                break
            blend = ratio * ratio * (3 - 2 * ratio)
            self.target = start + (goal - start) * blend
            self.s.step(self.command(self.target, boost))
            self.phases.append(phase)
        self.report(phase)

    def hand_counter(self):
        counter = self.m.geom("counter").id
        owner = self.s.checker.geom_owner
        names = []
        for i in range(self.d.ncon):
            g1, g2 = int(self.d.contact[i].geom1), int(self.d.contact[i].geom2)
            for a, b in ((g1, g2), (g2, g1)):
                if owner[a] == "hand" and (b == counter or owner[b] == "hub"):
                    names.append(self.m.body(int(self.m.geom_bodyid[a])).name.replace("right_", "") + ("@hub" if b != counter else ""))
        return ",".join(sorted(set(names))) or "0"

    def report(self, phase):
        f = self.s.status()
        phase = f"{phase} [hc={self.hand_counter()}]"
        self.log(f"{phase:28s} step={f['steps']:4d} stage={f['stage']} reason={f['reason']!r} "
                 f"depth={f['target_depth_m']*1000:.2f}mm lat={f['target_lateral_m']*1000:.2f} "
                 f"vert={f['target_vertical_m']*1000:.2f} axis={f['axis_error_deg']:.2f} fingers={f['fingers_on_plug']} "
                 f"touch={f['plug_touch']} hub_disp={f['hub_displacement_m']*1000:.2f}mm plug_z={f['plug_pos'][2]:.4f}")

    def track_plug(self, goal_fn, count, phase, finger_fn=None, gain=1.0):
        """Closed loop: each control, place the hand so the measured plug-in-hand pose reaches goal_fn(i)."""
        integ = np.zeros(3)
        for i in range(count):
            if self.s.done:
                break
            Rg, pg = goal_fn(i)
            H, P = self.hand_pose(), self.plug_pose()
            T_hp = np.linalg.inv(H) @ P
            H_goal = frame(Rg, pg) @ np.linalg.inv(T_hp)
            integ += (pg - P[:3, 3]) * 0.05 * gain
            integ = np.clip(integ, -0.004, 0.004)
            tgt = self.target.copy()
            want = self.stage_from_hand(H_goal[:3, :3], H_goal[:3, 3] + integ, self.target[3:6])
            # Rate limit: at most max_step metres / max_rot radians of wrist-target change per control.
            tgt[:3] += np.clip(want[:3] - tgt[:3], -self.max_step, self.max_step)
            tgt[3:6] += np.clip(want[3:6] - tgt[3:6], -self.max_rot, self.max_rot)
            if finger_fn is not None:
                tgt[6:] = finger_fn(i)
            self.target = tgt
            self.s.step(self.command(self.target))
            self.phases.append(phase)
            if self.debug:
                P2 = self.plug_pose()
                ang = np.degrees(Rotation.from_matrix(Rg.T @ P2[:3, :3]).magnitude())
                self.log(f"  {phase[:12]} i={i} perr={np.round((P2[:3, 3] - pg) * 1000, 1)} ang={ang:.1f} "
                         f"want-tgt={np.round(want - tgt[:6], 3)} tgt={np.round(tgt[:6], 3)} "
                         f"q={np.round(self.d.qpos[self.s.qadr[:6]], 3)} f={self.s.status()['fingers_on_plug']}")
        self.report(phase)


def run(out=None, verbose=True, params=None):
    params = dict(params or {})
    s = Session(hand=params.get("hand", "sharpa"))
    c = Controller(s, log=print if verbose else (lambda *a: None))
    c.debug = params.get("debug", False)
    top = s.config["counter_top_z"]
    c.execute(s.hold_action(), 10, "settle")
    # --- pickup pinch on the housing's broad faces (plug lying on its side)
    P = c.plug_pose()
    Rp = P[:3, :3]
    up = 1.0 if Rp[2, 0] >= 0 else -1.0
    yaw = params.get("yaw", 0.0)
    # Fingers point down and toward the shell end by ``yaw`` (so the hand stays in front of the counter edge later).
    zf = Rp @ np.array([-up * np.cos(yaw), np.sin(yaw), 0.0])
    yt = -Rp[:, 2]
    R_pick = np.column_stack([np.cross(yt, zf), yt, zf])
    seed = c.target.copy()
    seed[OTHERS] = CURLED
    above = seed.copy()
    above[:6] = c.stage_from_hand(R_pick, P[:3, 3] + np.array([0.04, 0, 0.30]), seed[3:6])
    c.execute(above, 60, "approach above plug")
    kw = {"yaw": yaw}
    if "ys" in params:
        kw["ys"] = tuple(params["ys"])
    opened, cost_o = c.pinch(R_pick, 0.012, above, **kw)
    closed, cost_c = c.pinch(R_pick, params.get("squeeze", -0.004), opened, **kw)
    touching, _ = c.pinch(R_pick, 0.0, closed, **kw)
    c.log(f"pinch fit costs open={cost_o:.4f} closed={cost_c:.4f}")
    hover = opened.copy()
    hover[2] += 0.08
    c.execute(hover, 50, "hover over plug")
    c.execute(opened, 50, "descend to open pinch")
    c.execute(closed, 40, "close pinch")
    c.execute(closed, 20, "stabilize grasp")
    lift = closed.copy()
    lift[2] += 0.06
    c.execute(lift, 50, "lift plug")
    # --- transport: rotate the plug to the port axis (polarity up) in front of the counter edge
    Rport, mouth = c.port_frame(params.get("port"))
    fingers = c.target[6:].copy()
    fingers_t = fingers.copy()
    fingers_t[np.asarray(OTHERS) - 6] = EXTENDED
    standoff = params.get("standoff", 0.012)
    # Joint-space wrist rotation (no Euler branch flips), hand position chosen so the plug follows a straight path.
    H, P = c.hand_pose(), c.plug_pose()
    T_hp = np.linalg.inv(H) @ P
    p0 = P[:3, 3].copy()
    p1 = mouth + Rport @ np.array([0, -0.10, 0.05])
    H1 = frame(Rport, p1) @ np.linalg.inv(T_hp)
    th0 = c.target[3:6].copy()
    th1 = c.stage_from_hand(H1[:3, :3], H1[:3, 3], th0)[3:]
    f0 = c.target[6:].copy()
    n_tr = params.get("transport_rows", 180)
    for i in range(n_tr):
        if s.done:
            break
        u = (i + 1) / n_tr
        u = u * u * (3 - 2 * u)
        th = th0 + (th1 - th0) * u
        Rh = c.B @ Rotation.from_euler("XYZ", th).as_matrix() @ c.Rq0
        pp = p0 + (p1 - p0) * u + np.array([0, 0, 0.03 * np.sin(np.pi * u)])
        tgt = c.target.copy()
        tgt[:3] = pp - Rh @ T_hp[:3, 3]
        tgt[3:6] = th
        tgt[6:] = f0 + (fingers_t - f0) * u
        c.target = tgt
        s.step(c.command(c.target))
        c.phases.append("transport and rotate")
    c.report("transport and rotate")
    c.track_plug(lambda i: (Rport, p1), params.get("correct_rows", 60), "correct orientation in front")
    c.track_plug(lambda i: (Rport, mouth + Rport @ np.array([0, -0.10, 0.05 * (1 - min(1, (i + 1) / 50))])), 60,
                 "lower in front of edge")
    # The middle finger (front, top) is not needed once the plug is aligned: straighten it away from the counter/hub.
    mid_free = c.target[6:].copy()
    mid_free[np.asarray(MIDDLE) - 6] = params.get("middle_free", [0.0, 0.0, 0.0, 0.0])
    f_hold = c.target[6:].copy()
    c.track_plug(lambda i: (Rport, mouth + Rport @ np.array([0, -0.10, 0])), 25, "free middle finger",
                 finger_fn=lambda i: f_hold + (mid_free - f_hold) * min(1, (i + 1) / 20))
    c.track_plug(lambda i: (Rport, mouth + Rport @ np.array([0, -0.10 + (0.10 - standoff) * min(1, (i + 1) / 50), 0])),
                 60, "approach port mouth")
    c.track_plug(lambda i: (Rport, mouth + Rport @ np.array([0, -standoff, 0.0])), 30, "settle alignment")
    depth = params.get("depth", 0.0118)
    n_ins = params.get("insert_rows", 70)
    c.track_plug(lambda i: (Rport, mouth + Rport @ np.array([0, -standoff + (depth + standoff) * min(1, (i + 1) / n_ins), 0.0])),
                 n_ins + 20, "insert")
    # --- release: open thumb and index, keep the wrist, then back away
    # Release: relax to a zero-squeeze touch, then open while the wrist presses 1 mm further along the port axis.
    release = c.target.copy()
    release[:3] += Rport[:, 1] * params.get("release_push", 0.001)
    for idx in (THUMB, INDEX, MIDDLE):
        release[idx] = touching[idx]
    c.execute(release, 25, "relax pinch")
    for idx in (INDEX, MIDDLE):
        release[idx] = opened[idx]
    c.execute(release, 40, "lift index off the plug")
    release[2] -= params.get("thumb_drop", 0.004)  # the thumb leaves the housing along its face normal (no drag)
    c.execute(release, 30, "drop thumb off the plug")
    release[THUMB] = opened[THUMB]
    c.execute(release, 40, "open thumb away")
    back = release.copy()
    back[0] += 0.05  # sideways first, clear of the cable hanging behind the plug
    c.execute(back, 40, "move hand aside")
    back[1] -= 0.06
    back[2] += 0.04
    c.execute(back, 50, "withdraw hand")
    c.execute(back, params.get("hold_rows", 120), "hold released plug")
    f = s.status()
    if out:
        outp = Path(out)
        outp.parent.mkdir(parents=True, exist_ok=True)
        # Slack: the episode ends at success; append hold rows so success comes well before the last row.
        rows = np.asarray(s.actions)
        extra = params.get("slack_rows", 60)
        rows = np.concatenate([rows, np.repeat(rows[-1:], extra, axis=0)])
        phases = np.asarray(c.phases[: len(s.actions)] + ["hold (slack)"] * extra)
        s.save_trajectory(rows, outp)
        np.savez_compressed(outp.with_suffix(".phases.npz"), phases=phases)
        outp.with_suffix(".live.json").write_text(json.dumps({k: v for k, v in f.items()}, indent=1, default=str) + "\n")
    return s, c, f


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out")
    parser.add_argument("--params", default="{}")
    args = parser.parse_args()
    s, c, f = run(args.out, params=json.loads(args.params))
    print(json.dumps({k: f[k] for k in ("success", "reason", "stage", "steps", "failure_detail")}, default=str))
