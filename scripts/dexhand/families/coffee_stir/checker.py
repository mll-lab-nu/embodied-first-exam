"""Strict, state-only verdict for the coffee stirring task.

Ordered stages (evaluated once per control step, after the physics substeps):

1. ``in_hand_submerged``: the bowl is submerged in the coffee (bowl centre, tip and neck below the coffee surface,
   all three inside the cup radius) while the spoon is in the hand (thumb and at least one other finger touch it).
2. ``stirred``: the bowl has revolved at least ``stir_revolutions`` times about the cup axis. The unwrapped angle of
   the bowl centre about the cup's vertical axis line (world frame) accumulates only while the bowl is submerged, at
   least ``stir_min_radius_m`` from the axis and the spoon is in the hand (thumb + another finger); per-control
   increments above ``stir_max_step_rad`` are not counted. If the bowl leaves the coffee before the stage completes,
   the count restarts from zero.
3. ``rested``: the spoon is released (no hand contact), its bowl rests in the coffee inside the cup, spoon and cup
   are still (speed limits), continuously for ``rest_hold_steps`` controls. Success ends the episode.

Fail-fast invariants are checked after every physics substep and end the episode permanently (no grace window: a
spoon that touches neither the hand nor the mug while its centre of mass falls faster than ``drop_speed_m_s`` is
dropped at that substep).
"""

from __future__ import annotations

import mujoco
import numpy as np

from scene import BOWL_HALF_LENGTH, COFFEE_Z, CUP_FLOOR_Z, CUP_INNER_R

STAGES = ("in_hand_submerged", "stirred", "rested")


class Checker:
    def __init__(self, model, config):
        self.m = model
        self.c = config
        self.cup = model.body("cup").id
        self.spoon = model.body("spoon").id
        self.sites = {n: model.site(n).id for n in ("bowl_center", "bowl_tip", "bowl_neck", "spoon_top")}
        stage_root = model.body("wrist_stage").id
        hand_bodies = set()
        for b in range(model.nbody):
            p = b
            while p:
                if p == stage_root:
                    hand_bodies.add(b)
                    break
                p = int(model.body_parentid[p])
        self.hand_bodies = np.asarray(sorted(hand_bodies), dtype=int)
        body = model.geom_bodyid
        self.hand_geom = np.isin(body, self.hand_bodies)
        self.spoon_geom = body == self.spoon
        self.cup_geom = body == self.cup
        self.ground_geom = np.zeros(model.ngeom, dtype=bool)
        self.ground_geom[[model.geom("worktop").id, model.geom("floor").id]] = True
        self.floor = model.geom("floor").id
        tips = [model.site(i).name for i in range(model.nsite)]
        self.fingertip_sites = np.asarray(
            [model.site(n).id for n in tips if n and (n.endswith("_fingertip") or n.endswith("_tip"))
             and model.site_bodyid[model.site(n).id] in hand_bodies],
            dtype=int,
        )
        ws = config["workspace"]
        self.ws_lo = np.asarray(ws["min"], dtype=float)
        self.ws_hi = np.asarray(ws["max"], dtype=float)
        self.reset(None)

    # ------------------------------------------------------------------ state
    def reset(self, data):
        self.stage = 0
        self.theta = 0.0
        self.prev_angle = None
        self.hold = 0
        self.success = False
        self.failure = None
        self.failure_detail = None
        self.max_theta = 0.0
        self.cup_xy0 = None if data is None else data.xpos[self.cup, :2].copy()
        self.cup_z0 = None if data is None else float(data.xpos[self.cup, 2])

    def get_state(self):
        return np.array([self.stage, self.theta, np.nan if self.prev_angle is None else self.prev_angle, self.hold,
                         float(self.success), self.max_theta], dtype=np.float64)

    def snapshot(self):
        return {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in vars(self).items()
                if k in ("stage", "theta", "prev_angle", "hold", "success", "failure", "failure_detail", "max_theta",
                         "cup_xy0", "cup_z0")}

    def restore(self, snap):
        for k, v in snap.items():
            setattr(self, k, v.copy() if isinstance(v, np.ndarray) else v)

    # --------------------------------------------------------------- geometry
    def cup_frame(self, data, point):
        return data.xmat[self.cup].reshape(3, 3).T @ (point - data.xpos[self.cup])

    def cup_tilt(self, data):
        return float(np.arccos(np.clip(data.xmat[self.cup, 8], -1.0, 1.0)))

    def bowl(self, data):
        pts = {n: self.cup_frame(data, data.site_xpos[self.sites[n]]) for n in ("bowl_center", "bowl_tip", "bowl_neck")}
        radial = {n: float(np.hypot(p[0], p[1])) for n, p in pts.items()}
        submerged = all(p[2] <= COFFEE_Z and p[2] >= CUP_FLOOR_Z - 0.004 for p in pts.values()) and all(
            r <= CUP_INNER_R for r in radial.values()
        )
        return pts, radial, submerged

    def contacts(self, data):
        hand_spoon = 0
        fingers = set()
        spoon_cup = 0
        import hands  # noqa: PLC0415 - shared module (scene.py registers it)

        for i in range(data.ncon):
            c = data.contact[i]
            if c.efc_address < 0:
                continue
            g1, g2 = int(c.geom1), int(c.geom2)
            if (self.hand_geom[g1] and self.spoon_geom[g2]) or (self.hand_geom[g2] and self.spoon_geom[g1]):
                hand_spoon += 1
                hg = g1 if self.hand_geom[g1] else g2
                name = self.m.geom(hg).name or self.m.body(int(self.m.geom_bodyid[hg])).name
                finger = hands.finger_of(name) or hands.finger_of(self.m.body(int(self.m.geom_bodyid[hg])).name)
                fingers.add(finger or "palm")
            if (self.cup_geom[g1] and self.spoon_geom[g2]) or (self.cup_geom[g2] and self.spoon_geom[g1]):
                spoon_cup += 1
        return hand_spoon, sorted(fingers), spoon_cup

    def com_velocity(self, data, body):
        """Linear velocity of the body's centre of mass, world frame (mjOBJ_BODY reports it at xipos)."""
        v = np.empty(6)
        mujoco.mj_objectVelocity(self.m, data, mujoco.mjtObj.mjOBJ_BODY, body, v, 0)
        return v[3:].copy()

    def speeds(self, data, body):
        """(COM linear speed, angular speed), world frame."""
        v = np.empty(6)
        mujoco.mj_objectVelocity(self.m, data, mujoco.mjtObj.mjOBJ_BODY, body, v, 0)
        return float(np.linalg.norm(v[3:])), float(np.linalg.norm(v[:3]))

    # -------------------------------------------------------------- fail-fast
    def violation(self, data):
        """First broken invariant as (reason, detail) or None. Checked after every physics substep."""
        table_z = self.c["table_z"]
        tilt = self.cup_tilt(data)
        if tilt > np.radians(self.c["cup_max_tilt_deg"]):
            return "cup_tipped", {"tilt_deg": float(np.degrees(tilt))}
        slide = float(np.linalg.norm(data.xpos[self.cup, :2] - self.cup_xy0))
        if slide > self.c["cup_max_slide_m"]:
            return "cup_moved", {"slide_m": slide}
        lift = float(data.xpos[self.cup, 2] - self.cup_z0)
        if lift > self.c["cup_max_lift_m"]:
            return "cup_lifted", {"lift_m": lift}
        spoon_supported = False
        for i in range(data.ncon):
            c = data.contact[i]
            if c.efc_address < 0:
                continue
            g1, g2 = int(c.geom1), int(c.geom2)
            if (self.spoon_geom[g1] and self.ground_geom[g2]) or (self.spoon_geom[g2] and self.ground_geom[g1]):
                return "spoon_dropped", {"geom": self.m.geom(g2 if self.spoon_geom[g1] else g1).name}
            if (self.cup_geom[g1] and g2 == self.floor) or (self.cup_geom[g2] and g1 == self.floor):
                return "cup_dropped", {}
            if (self.spoon_geom[g1] and (self.hand_geom[g2] or self.cup_geom[g2])) or (
                self.spoon_geom[g2] and (self.hand_geom[g1] or self.cup_geom[g1])
            ):
                spoon_supported = True
        if not spoon_supported:
            # No drop-and-catch window: a spoon touching neither the hand nor the mug while its centre of mass falls
            # faster than the threshold has been dropped, at this substep.
            vz = self.com_velocity(data, self.spoon)[2]
            if vz < -self.c["drop_speed_m_s"]:
                return "spoon_dropped", {"unsupported_fall_speed_m_s": float(-vz)}
        for name, sid in self.sites.items():
            if data.site_xpos[sid, 2] < table_z - 0.001:
                return "below_table", {"site": name, "z": float(data.site_xpos[sid, 2])}
        if data.xpos[self.cup, 2] < table_z - 0.005:
            return "below_table", {"body": "cup", "z": float(data.xpos[self.cup, 2])}
        for name in ("bowl_center", "spoon_top"):
            p = data.site_xpos[self.sites[name]]
            if np.any(p < self.ws_lo) or np.any(p > self.ws_hi):
                return "spoon_left_workspace", {"site": name, "pos": p.tolist()}
        for sid in self.fingertip_sites:
            p = self.cup_frame(data, data.site_xpos[sid])
            if np.hypot(p[0], p[1]) < CUP_INNER_R and p[2] < COFFEE_Z:
                return "hand_in_coffee", {"site": self.m.site(int(sid)).name}
        return None

    # ----------------------------------------------------------------- stages
    def update(self, data):
        """Advance the ordered stages once per control step; returns the feature dict."""
        pts, radial, submerged = self.bowl(data)
        hand_spoon, fingers, spoon_cup = self.contacts(data)
        held = hand_spoon > 0
        # Stages 1-2 need the spoon in the hand: the thumb and at least one other finger touch it (a single finger
        # pushing the handle does not count as holding the spoon).
        grasped = "thumb" in fingers and any(f in fingers for f in ("index", "middle", "ring", "pinky"))
        c = pts["bowl_center"]
        if self.stage == 0 and submerged and grasped:
            self.stage = 1
            self.prev_angle = None
        elif self.stage == 1:
            if not submerged:
                self.theta = 0.0
                self.prev_angle = None
            elif grasped and radial["bowl_center"] >= self.c["stir_min_radius_m"]:
                # Revolution about the cup's vertical axis line in the world frame: turning the cup under a still
                # spoon does not count as stirring.
                offset = data.site_xpos[self.sites["bowl_center"], :2] - data.xpos[self.cup, :2]
                angle = float(np.arctan2(offset[1], offset[0]))
                if self.prev_angle is not None:
                    delta = (angle - self.prev_angle + np.pi) % (2 * np.pi) - np.pi
                    if abs(delta) <= self.c["stir_max_step_rad"]:
                        self.theta += delta
                self.prev_angle = angle
            else:
                self.prev_angle = None
            self.max_theta = max(self.max_theta, abs(self.theta))
            if abs(self.theta) >= 2 * np.pi * self.c["stir_revolutions"]:
                self.stage = 2
        lin, ang = self.speeds(data, self.spoon)
        cup_lin, cup_ang = self.speeds(data, self.cup)
        rested = (
            self.stage == 2
            and not held
            and submerged
            and spoon_cup > 0
            and lin <= self.c["rest_linear_speed_m_s"]
            and ang <= self.c["rest_angular_speed_rad_s"]
            and cup_lin <= self.c["rest_linear_speed_m_s"]
            and cup_ang <= self.c["rest_angular_speed_rad_s"]
            and self.failure is None
        )
        self.hold = self.hold + 1 if rested else 0
        if self.hold >= self.c["rest_hold_steps"]:
            self.stage = 3
            self.success = True
        return {
            "stage": self.stage,
            "stage_name": STAGES[self.stage - 1] if self.stage else "",
            "revolutions": abs(self.theta) / (2 * np.pi),
            "max_revolutions": self.max_theta / (2 * np.pi),
            "bowl_cup_frame": c.tolist(),
            "bowl_radius_m": radial["bowl_center"],
            "bowl_submerged": bool(submerged),
            "hand_spoon_contacts": hand_spoon,
            "spoon_fingers": fingers,
            "spoon_grasped": bool(grasped),
            "spoon_cup_contacts": spoon_cup,
            "spoon_speed_m_s": lin,
            "spoon_angular_speed_rad_s": ang,
            "cup_tilt_deg": float(np.degrees(self.cup_tilt(data))),
            "cup_slide_m": float(np.linalg.norm(data.xpos[self.cup, :2] - self.cup_xy0)),
            "rest_hold_steps": self.hold,
        }
