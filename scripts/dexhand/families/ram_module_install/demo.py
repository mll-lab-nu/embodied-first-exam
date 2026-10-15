"""Authoring controller (not shipped to agents): closed-loop scripted pinch, transport, keyed insertion, release.

The controller reads the Session state, but every command it issues is an ordinary actuator-target row; the rows are
recorded and replayed open-loop by ``replay.py``.
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

PCB_HALF = 0.00064
CORNER = np.array([-0.066675, 0.0, 0.0])  # lower corner of the fixed-retainer end (module frame)
PINCH = (0.004, 0.0, 0.030)  # pinch point in the module frame (m): centre of the upper PCB band


class Controller:
    def __init__(self, session, log=print):
        self.s = session
        self.m, self.d = session.model, session.data
        self.kin = mujoco.MjData(self.m)
        self.rows, self.phases = [], []
        self.target = session.hold_action()
        self.dofs = self.m.jnt_dofadr[self.m.actuator_trnid[:, 0]]
        self.gain = self.m.actuator_gainprm[:, 0]
        self.mount = Rotation.from_quat(np.roll(np.asarray(session.config["hand_mount_quat"], float), -1))
        self.base = np.asarray(session.config["wrist_base"], float)
        self.hand_body = self.m.body("right_hand_C_MC").id if session.hand == "sharpa" else self.m.body("right_hand_C_MC").id
        self.log = log
        self.verbose = bool(os.environ.get("DEMO_VERBOSE"))
        self.use_middle = False
        self.upright_weight = 0.0
        self.pad_terms = True
        self.length_axis = np.array([1.0, 0, 0])
        self.spread = 0.011
        if session.hand == "sharpa":
            self.tips = {
                "thumb": self.m.geom("right_thumb_fingertip_collision").id,
                "index": self.m.geom("right_index_fingertip_collision").id,
                "middle": self.m.geom("right_middle_fingertip_collision").id,
            }
            self.pinch_cols, self.middle_cols, self.tip_radius = np.r_[6:15], np.r_[15:19], None
        else:  # Wuji Hand 2.2: thumb 6:10, index 10:14, middle 14:18 (vendor mesh fingertips)
            self.tips = {
                "thumb": self.m.geom("r_wuji_r_thumb_tip_sensor_frame_collision1").id,
                "index": self.m.geom("r_wuji_r_index_finger_tip_sensor_frame_collision1").id,
                "middle": self.m.geom("r_wuji_r_middle_finger_tip_sensor_frame_collision1").id,
            }
            self.pinch_cols, self.middle_cols, self.tip_radius = np.r_[6:14], np.r_[14:18], 0.0075
            self.pad_terms = False

    # ------------------------------------------------------------------ kinematics helpers
    def fk(self, q):
        k = self.kin
        k.qpos[:] = self.d.qpos
        k.qpos[self.s.qadr] = q
        mujoco.mj_kinematics(self.m, k)
        return k

    def wrist_from_hand_pose(self, pos, rot):
        """Wrist joint targets that put the hand root body at world ``pos`` with rotation ``rot`` (Rotation)."""
        stage = rot * self.mount.inv()
        angles = stage.as_euler("XYZ")
        return np.r_[pos - self.base, angles]

    def hand_pose(self):
        b = self.hand_body
        return self.d.xpos[b].copy(), Rotation.from_matrix(self.d.xmat[b].reshape(3, 3))

    def module_pose(self):
        b = self.s.checker.dimm
        return self.d.xpos[b].copy(), Rotation.from_matrix(self.d.xmat[b].reshape(3, 3))

    def pinch_ik(self, center, normal, clearance, seed, height_axis=(0, 0, 1), fingers_only=False, thumb_side=1.0):
        """Thumb pad on +normal face, index pad on -normal face of the PCB at ``center``."""
        m = self.m
        q = seed.copy()
        var = self.pinch_cols if fingers_only else np.r_[0:6, self.pinch_cols]
        if self.use_middle:
            var = np.r_[var, self.middle_cols]
        lo, hi = m.actuator_ctrlrange[var].T
        normal = np.asarray(normal, float)
        module_geoms = [g for g in np.flatnonzero(self.s.checker.module_geom & (m.geom_contype > 0))
                        if (m.geom(g).name or "").startswith("pcb_band")]
        hand_geoms = [g for g in np.flatnonzero(self.s.checker.hand_geom & (m.geom_contype > 0))
                      if g not in (self.tips["thumb"], self.tips["index"], self.tips["middle"])]
        init = q[var].copy()

        def residual(x):
            q[var] = x
            k = self.fk(q)
            err = []
            for name, sign in (("thumb", thumb_side), ("index", -thumb_side)) + ((("middle", -thumb_side),) if self.use_middle else ()):
                g = self.tips[name]
                r = m.geom_size[g, 0] if self.tip_radius is None else self.tip_radius
                target = center + sign * normal * (PCB_HALF + r + clearance)
                if name != "thumb" and self.use_middle:
                    target = target + self.length_axis * (self.spread if name == "middle" else -self.spread)
                err.extend((k.geom_xpos[g] - target) * 300)
                axis = k.geom_xmat[g].reshape(3, 3)[:, 2]
                if not fingers_only and self.pad_terms:
                    err.append(float(axis @ normal) * 2.0)  # pad axis parallel to the face
                    err.append((1.0 - abs(float(axis @ np.asarray(height_axis, float)))) * 1.0)  # fingertip points down
            for g in ([] if fingers_only else hand_geoms):
                for mg in module_geoms:
                    dist = mujoco.mj_geomDistance(m, k, int(g), int(mg), 0.01, None)
                    err.append(min(0.0, dist - 0.002) * 300)
            err.extend((x - init) * 0.01)
            if not fingers_only and self.upright_weight:
                err.extend(np.asarray(x[3:5]) * self.upright_weight)
            return np.asarray(err)

        fit = least_squares(residual, np.clip(init, lo + 1e-6, hi - 1e-6), bounds=(lo, hi), max_nfev=200)
        q[var] = fit.x
        return q, fit.cost

    def tip_ik(self, tip, target, seed, avoid=(), weight=300.0):
        """Wrist + finger joints placing fingertip ``tip`` at ``target`` while other hand geoms keep clear of ``avoid``."""
        m = self.m
        q = seed.copy()
        var = np.r_[0:6, self.pinch_cols]
        lo, hi = m.actuator_ctrlrange[var].T
        g_tip = self.tips[tip]
        hand_geoms = [g for g in np.flatnonzero(self.s.checker.hand_geom & (m.geom_contype > 0)) if g != g_tip]
        init = q[var].copy()

        def residual(x):
            q[var] = x
            k = self.fk(q)
            err = list((k.geom_xpos[g_tip] - target) * weight)
            for g in hand_geoms:
                for a in avoid:
                    dist = mujoco.mj_geomDistance(m, k, int(g), int(a), 0.02, None)
                    err.append(min(0.0, dist - 0.006) * 300)
            for a in avoid:
                dist = mujoco.mj_geomDistance(m, k, int(g_tip), int(a), 0.02, None)
                err.append(min(0.0, dist - 0.001) * 300)
            err.extend((x - init) * 0.02)
            return np.asarray(err)

        fit = least_squares(residual, np.clip(init, lo + 1e-6, hi - 1e-6), bounds=(lo, hi), max_nfev=200)
        q[var] = fit.x
        return q, fit.cost

    # ------------------------------------------------------------------ execution
    def command(self, joint_target):
        action = joint_target.copy()
        action[:6] += self.d.qfrc_bias[self.dofs[:6]] / self.gain[:6]
        lo, hi = self.m.actuator_ctrlrange.T
        action = np.clip(action, lo, hi)
        # Rows are recorded at float32 precision (what the public client sends), kept inside the native bounds.
        rounded = action.astype(np.float32)
        rounded = np.where(rounded > hi, np.nextafter(hi.astype(np.float32), np.float32(-np.inf)), rounded)
        rounded = np.where(rounded < lo, np.nextafter(lo.astype(np.float32), np.float32(np.inf)), rounded)
        return rounded.astype(np.float64)

    def move(self, target, count, phase, hold_fingers=None):
        start = self.target.copy()
        for ratio in np.linspace(0, 1, count + 1)[1:]:
            if self.s.done:
                return
            blend = ratio * ratio * (3 - 2 * ratio)
            self.target = start + (target - start) * blend
            action = self.command(self.target)
            self.s.step(action)
            self.rows.append(action)
            self.phases.append(phase)
        f = self.s.features()
        info = {k: f[k] for k in ("stage", "module_pos", "fingers_on_module", "end_depths_m", "lateral_m",
                                  "latch_rad", "failure")}
        if self.verbose:
            m, d, ck = self.m, self.d, self.s.checker
            info["hand_world"] = sorted({(m.geom(int(a)).name, m.geom(int(b)).name) for a, b in d.contact.geom[:d.ncon]
                                         if ck.hand_geom[a] != ck.hand_geom[b] and not (ck.module_geom[a] or ck.module_geom[b])})
            info["module_socket"] = sorted({(m.geom(int(a)).name, m.geom(int(b)).name) for a, b in d.contact.geom[:d.ncon]
                                            if (ck.module_geom[a] and ck.socket_geom[b]) or (ck.module_geom[b] and ck.socket_geom[a])})
        self.log(phase, json.dumps(info))

    def hold(self, count, phase):
        self.move(self.target.copy(), count, phase)


def curled(q, hand="sharpa"):
    q = q.copy()
    if hand == "sharpa":
        q[15:19] = [1.2, 0.0, 1.2, 1.0]
        q[19:23] = [1.55, 0.0, 1.7, 1.3]
        q[23:28] = [0.25, 1.55, 0.0, 1.7, 1.3]
    else:  # Wuji: middle, ring and little fingers folded into the palm (mcp_flex, abd, pip, dip)
        for start in (14, 18, 22):
            q[start : start + 4] = [1.45, 0.0, 1.9, 1.4]
    return q


def run(session, params=None, log=print):
    p = dict(stop_slide=0.0, stop_backoff=0.0012, stop_press=0.003, press_x=0.05, edge_press=0.006, reseat_iters=1, reseat_lift=0.004, reseat_press=0.002, level_extra=0.004, level_rows=100, corner_inset=0.0003, carry_rows=110, level_touch=True, level_offset=0.005, level_press=0.0015, grasp_yaw=np.pi / 2, thumb_side=-1.0, squeeze=-0.010, insert_mode="pinch", lift=0.06, pre_insert=0.0185, enter=0.0075, regrip_up=0.010, press_h=0.004, press_clear=-0.004, press_down=0.012, pinch_press=0.0)
    p.update(params or {})
    c = Controller(session, log=log)
    s = session
    c.hold(10, "settle")
    pos, rot = c.module_pose()
    center = pos + rot.apply(PINCH)
    normal = rot.apply([0, 1, 0])
    seed = curled(s.hold_action(), s.hand)
    seed[5] = p["grasp_yaw"]  # index flexes towards the chip face, thumb on the back face
    q_pre, cost = c.pinch_ik(center, normal, 0.006, seed, thumb_side=p["thumb_side"])
    q_above = q_pre.copy()
    q_above[2] += 0.05
    c.move(q_above, 60, "approach above the module")
    c.move(q_pre, 40, "lower around the module")
    q_grip, cost2 = c.pinch_ik(center, normal, p["squeeze"], q_pre, fingers_only=True, thumb_side=p["thumb_side"])
    c.move(q_grip, 30, "pinch the upper PCB edge")
    c.hold(10, "pinch")
    q_lift = c.target.copy()
    q_lift[2] += p["lift"]
    c.move(q_lift, 50, "lift out of the foam holder")
    c.hold(10, "lifted")
    if p["level_touch"]:
        # Level the module in the pinch: set its lower edge down on the top of one foam jaw (beside the slit),
        # pressing lightly so it pivots level about the pads, then lift again.
        mp, mr = c.module_pose()
        side = mr.apply([0, -1, 0]) * p["level_offset"]
        q = c.target.copy()
        q[:2] += side[:2]
        c.move(q, 30, "move beside the slit")
        jaw_top = s.config["bench_top_z"] + 0.016
        q = c.target.copy()
        q[2] -= (mp[2] - jaw_top) + p["level_press"]
        c.move(q, 50, "level the module on the foam jaw")
        c.hold(10, "levelled")
        q = c.target.copy()
        q[2] += 0.05
        c.move(q, 40, "lift again")
    # hand-to-module transform measured in the grasp
    hp, hr = c.hand_pose()
    mp, mr = c.module_pose()
    rel_p = hr.inv().apply(mp - hp)
    rel_r = hr.inv() * mr
    sock = s.checker
    sock.module_pose_in_socket(s.data)
    s_pos, s_rot = sock.socket_pos, Rotation.from_matrix(sock.socket_mat)

    def hand_for_module(module_pos, module_rot):
        hand_rot = module_rot * rel_r.inv()
        hand_pos = module_pos - hand_rot.apply(rel_p)
        return hand_rot, hand_pos

    def wrist_target(module_pos, module_rot):
        hand_rot, hand_pos = hand_for_module(module_pos, module_rot)
        q = c.target.copy()
        q[:6] = c.wrist_from_hand_pose(hand_pos, hand_rot)
        # keep the yaw continuous with the current command
        q[3:6] = c.target[3:6] + (q[3:6] - c.target[3:6] + np.pi) % (2 * np.pi) - np.pi
        return q

    def align(desired_pos, desired_rot, iters, phase, rows=25, settle=8, rotate=True):
        for _ in range(iters):
            c.hold(settle, phase)
            mp, mr = c.module_pose()
            # Control the lower corner of the fixed-retainer end. The pinch sits 4 mm towards the latch end of the
            # centre of mass, so the module hangs with this end slightly low: it enters first, rests on the socket
            # floor, and the module then pivots level about it while the latch end pushes the latch foot down.
            mp = mp + mr.apply(CORNER)
            desired_pos_pivot = desired_pos + desired_rot.apply(CORNER + np.array([p["corner_inset"], 0, 0]))
            err_r = desired_rot * mr.inv()
            # A two-pad pinch is a pivot about the face normal: never try to correct that component (the module
            # hangs from the pads); the end guides level it when it is pressed in.
            rv = err_r.as_rotvec()
            n = mr.apply([0, 1, 0])
            err_r = Rotation.from_rotvec(rv - n * (rv @ n)) if rotate else Rotation.identity()
            cmd_pos = c.base + c.target[:3]
            cmd_rot = Rotation.from_euler("XYZ", c.target[3:6]) * c.mount
            new_rot = err_r * cmd_rot
            new_pos = desired_pos_pivot + err_r.apply(cmd_pos - mp)
            q = c.target.copy()
            q[:6] = c.wrist_from_hand_pose(new_pos, new_rot)
            q[3:6] = c.target[3:6] + (q[3:6] - c.target[3:6] + np.pi) % (2 * np.pi) - np.pi
            c.move(q, rows, phase)
            if s.done:
                return

    def at(height):
        return s_pos + s_rot.apply([0, 0, 0.002 + height])

    c.move(wrist_target(at(0.06), s_rot), p["carry_rows"], "carry and turn to match the socket key")
    align(at(0.06), s_rot, 1, "align over the outer socket", rotate=True)
    align(at(0.06), s_rot, 2, "align over the outer socket")
    align(at(0.03), s_rot, 2, "lower over the slot", rows=40)
    align(at(p["pre_insert"]), s_rot, 5, "align just above the end guides", rows=25)
    align(at(0.010), s_rot, 2, "enter the end guides", rows=40)
    align(at(p["enter"]), s_rot, 2, "insert into the slot throat", rows=40)
    if p["insert_mode"] == "pinch":
        align(at(0.003), s_rot, 1, "set the fixed end on the socket floor", rows=40)
        align(at(p["pinch_press"]), s_rot, 1, "set the fixed end on the socket floor", rows=30)
        # pivot the module level about its seated end: lower the pads along the arc
        # The pads move along the arc about the seated corner (no along-slot drag on the module).
        mp, mr = c.module_pose()
        corner = mp + mr.apply(CORNER)
        pinch_now = mp + mr.apply(PINCH)
        pinch_level = corner + s_rot.apply(np.asarray(PINCH) - CORNER)
        delta = pinch_level - pinch_now
        delta[2] -= p["level_extra"]
        q = c.target.copy()
        q[:3] += delta
        c.move(q, p["level_rows"], "lower the latch end: the latch snaps closed")
        c.hold(10, "pressed")
        # Optionally locate the module along the slot against the fixed-end stop, then press home.
        q = c.target.copy()
        if p["stop_slide"] > 0:
            q[:3] += s_rot.apply([-p["stop_slide"], 0.0, -0.001])
            c.move(q, 40, "slide the module against the fixed-end stop")
            q[:3] += s_rot.apply([p["stop_backoff"], 0.0, 0.0])
            c.move(q, 20, "ease off the stop")
            q[:3] += s_rot.apply([0.0, 0.0, -p["stop_press"]])
            c.move(q, 40, "press home: the latch snaps closed")
        c.hold(10, "pressed")
        for _ in range(p["reseat_iters"]):
            f = s.features()
            if f["latched"] or s.done:
                break
            # not home yet: lift the module a little, centre it along the slot, press again
            along = f["module_origin_in_socket_m"][0]
            lateral = f["module_origin_in_socket_m"][1]
            shift = s_rot.apply([-along, -lateral, 0.0])
            q = c.target.copy()
            q[2] += p["reseat_lift"]
            c.move(q, 30, "lift slightly to re-centre")
            q[:2] += shift[:2]
            c.move(q, 30, "re-centre along the slot")
            q[2] -= p["reseat_lift"] + p["reseat_press"]
            c.move(q, 60, "press home again")
            c.hold(15, "pressed")
    # let go of the faces, then press the upper edge down between the thumb and index pads
    mp, mr = c.module_pose()
    if p["insert_mode"] == "pinch":
        if not s.features()["latched"] and not s.done:
            # Finish like a person: let go and press the latch end of the upper edge down with the index tip.
            normal = mr.apply([0, 1, 0])
            q_open, _ = c.pinch_ik(mp + mr.apply(PINCH), normal, 0.008, c.target, fingers_only=True,
                                   thumb_side=p["thumb_side"])
            c.move(q_open, 30, "let go of the module")
            q = q_open.copy()
            q[2] += 0.04
            c.move(q, 40, "lift the hand")
            m = s.model
            avoid = [m.geom("atx_24pin").id, m.geom("pcb_band_4").id]
            names = {p["press_x"]: "press the latch end down: the latch snaps closed",
                     -p["press_x"]: "press the fixed end down", 0.0: "press the middle of the upper edge"}
            for xloc in (p["press_x"], -p["press_x"], 0.0, p["press_x"]):
                f = s.features()
                if s.done or (f["latched"] and f["seated"]):
                    break
                mp, mr = c.module_pose()
                point = mp + mr.apply([xloc, 0, 0.03125])
                q_above, cost = c.tip_ik("index", point + np.array([0, 0, 0.012 + 0.008]), c.target, avoid=avoid)
                c.move(q_above, 60, "index tip over the upper edge")
                q = q_above.copy()
                q[2] -= 0.012 + p["edge_press"]
                c.move(q, 70, names[xloc])
                c.hold(20, "pressed")
                q[2] += 0.03
                c.move(q, 40, "lift the finger")
        else:
            normal = mr.apply([0, 1, 0])
            q_open, _ = c.pinch_ik(mp + mr.apply(PINCH), normal, 0.008, c.target, fingers_only=True,
                                   thumb_side=p["thumb_side"])
            c.move(q_open, 30, "let go of the module")
    else:
        normal = mr.apply([0, 1, 0])
        q_open, _ = c.pinch_ik(mp + mr.apply(PINCH), normal, 0.004, c.target, fingers_only=True, thumb_side=p["thumb_side"])
        c.move(q_open, 25, "release the faces")
        q = q_open.copy()
        q[2] += p["regrip_up"]
        c.move(q, 25, "move the pads above the upper edge")
        mp, mr = c.module_pose()
        top = mp + mr.apply([PINCH[0], 0, 0.03125 + p["press_h"]])
        q_v, _ = c.pinch_ik(top, normal, p["press_clear"], c.target, fingers_only=True, thumb_side=p["thumb_side"])
        c.move(q_v, 25, "close the pads over the upper edge")
        q = q_v.copy()
        q[2] -= p["press_down"]
        c.move(q, 80, "press home: the latch snaps closed")
        c.hold(20, "pressed")
        q[2] += 0.004
        c.move(q, 20, "ease off")
    c.hold(20, "pressed")
    mp, mr = c.module_pose()
    normal = mr.apply([0, 1, 0])
    center = mp + mr.apply(PINCH)
    q_open, _ = c.pinch_ik(center, normal, 0.008, c.target, fingers_only=True, thumb_side=p["thumb_side"])
    c.move(q_open, 60, "release the module")
    q_up = q_open.copy()
    q_up[2] += 0.08
    c.move(q_up, 60, "withdraw the hand")
    c.hold(80, "hold")
    return c


def recovery_rows(session, c, p=None):
    """Open-loop recovery rows appended after the nominal success (never executed when the nominal run succeeds).

    The recorded oracle replays bit-exactly, but if a perturbed replay leaves the module resting on the key (fixed end
    on the floor, latch end raised, along-slot offset of a few mm), these rows press the upper edge with the index tip,
    drag the module along the slot both ways so its notch drops over the key, press both ends home (the latch snaps
    closed) and withdraw. Targets are planned kinematically from the nominal seated pose; nothing is simulated here.
    """
    p = dict(edge_x=0.03, press=0.003, drag=0.003, latch_x=0.055, fixed_x=-0.05, approach=0.02)
    p.update(p or {})
    m = session.model
    ck = session.checker
    ck.module_pose_in_socket(session.data)
    s_pos, s_rot = ck.socket_pos, Rotation.from_matrix(ck.socket_mat)
    top = 0.002 + 0.03125
    avoid = [m.geom("atx_24pin").id]
    rows, phases = [], []
    target = c.target.copy()

    def go(q, count, phase):
        nonlocal target
        start = target.copy()
        for ratio in np.linspace(0, 1, count + 1)[1:]:
            blend = ratio * ratio * (3 - 2 * ratio)
            target = start + (q - start) * blend
            rows.append(c.command(target))
            phases.append(phase)

    def tip_target(x_local, dz):
        point = s_pos + s_rot.apply([x_local, 0.0, top + dz])
        q, _ = c.tip_ik("index", point, target, avoid=avoid)
        return q

    seq = []
    q_above = tip_target(p["edge_x"], p["approach"])
    go(q_above, 60, "recovery: index tip over the upper edge")
    q_press = q_above.copy()
    q_press[2] -= p["approach"] + p["press"] + 0.003
    go(q_press, 50, "recovery: press the upper edge")
    for along in (-p["drag"], p["drag"], 0.0):
        q = q_press.copy()
        q[:3] += s_rot.apply([along, 0.0, 0.0])
        go(q, 60, "recovery: drag along the slot until the notch drops over the key")
    for x_local, label in ((p["latch_x"], "recovery: press the latch end"), (p["fixed_x"], "recovery: press the fixed end")):
        q = q_press.copy()
        q[2] += 0.02
        go(q, 30, "recovery: lift the finger")
        q_above = tip_target(x_local, p["approach"])
        go(q_above, 40, "recovery: index tip over the upper edge")
        q = q_above.copy()
        q[2] -= p["approach"] + p["press"] + 0.003
        go(q, 50, label)
        q_press = q
    q = q_press.copy()
    q[2] += 0.08
    go(q, 60, "recovery: withdraw the hand")
    go(q, 80, "recovery: hold")
    return np.asarray(rows), phases


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--hand", default="sharpa")
    parser.add_argument("--params", default="{}")
    parser.add_argument("--slack", type=int, default=150)
    parser.add_argument("--recovery", type=int, default=0)
    args = parser.parse_args()
    s = Session(hand=args.hand)
    c = run(s, json.loads(args.params))
    st = s.status()
    print(json.dumps({k: st[k] for k in ("success", "reason", "stage", "steps", "failure_detail")}))
    rows = np.asarray(c.rows)
    phases = list(c.phases)
    if args.recovery:
        extra, extra_phases = recovery_rows(s, c)
        rows = np.vstack([rows, extra])
        phases += extra_phases
    # Slack: the episode ends at success; extra hold rows keep the oracle robust to tiny perturbations.
    rows = np.vstack([rows, np.repeat(rows[-1:], args.slack, axis=0)])
    phases += ["hold (after success)"] * args.slack
    s.save_trajectory(rows, args.out)
    np.save(Path(args.out).with_suffix(".phases.npy"), np.asarray(phases))
    print(json.dumps({"rows": len(rows), "success_step": st["steps"]}))
