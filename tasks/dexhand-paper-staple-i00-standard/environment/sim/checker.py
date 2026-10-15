"""Strict paper_staple verdict from simulator state only (ordered stages, terminal hold, fail-fast)."""

from __future__ import annotations

import mujoco
import numpy as np

from scene import STAPLE_LOCAL, _arm_rig_module

CORNERS = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]], dtype=float)
STAGE_NAMES = ["aligned", "in_throat", "pressed", "released_hold"]


class Checker:
    """Stages (each latched in order; a later stage needs every earlier predicate true at the same control step):

    1. ``aligned``: every corner of sheets 1 and 2 lies within ``align_tolerance_m`` (in the plane of sheet 0) of the
       matching corner of sheet 0, the sheets are stacked in index order (sheet i+1 above sheet i by 0.5-3 sheet
       thicknesses along sheet 0's normal) and sheets 0-1 and 1-2 are in physical contact.
    2. ``in_throat``: (1) and the stapler's staple point (on its anvil, under the driver blade) lies inside every
       sheet, between ``staple_margin_min_m`` and ``staple_margin_max_m`` from both edges of one sheet corner, and
       every sheet's mid-plane passes between 0 and ``throat_height_max_m`` above that point (the corner rests on the
       anvil inside the throat).
    3. ``pressed``: (1), (2), the head hinge within ``stroke_tolerance_rad`` of its bottom stop and the driver blade
       touching the top sheet.
    4. ``released_hold``: after (3): (1), (2), head hinge back up (<= ``head_up_rad``), no hand contact with any sheet
       or the stapler, every sheet slower than 0.02 m/s, for ``hold_steps`` consecutive controls -> success.
    """

    def __init__(self, model, config, stop_angle):
        self.m = model
        self.c = config
        self.stop = float(stop_angle)
        self.n = len(config["sheets"])
        self.sheet_ids = [model.body(f"sheet_{i}").id for i in range(self.n)]
        self.sheet_geoms = [model.geom(f"sheet_{i}_plate").id for i in range(self.n)]
        self.half = np.asarray(config["sheet"]["half"], dtype=float)
        self.t = float(config["sheet"]["thickness"])
        self.base = model.body("stapler_base").id
        self.head = model.body("stapler_head").id
        self.hinge = int(model.joint("head_hinge").qposadr[0])
        self.blade = model.geom("driver_blade").id
        # every body that is not the world, a sheet or the stapler belongs to the robot (stand, both arms, both
        # hands): any robot contact counts as "hand contact" for the released hold
        owner = np.full(model.nbody, "hand", dtype=object)
        owner[0] = ""
        for i, b in enumerate(self.sheet_ids):
            owner[b] = f"sheet_{i}"
        owner[self.base] = "stapler"
        owner[self.head] = "stapler"
        self.geom_owner = np.array([owner[int(model.geom_bodyid[g])] for g in range(model.ngeom)], dtype=object)
        self.is_hand = self.geom_owner == "hand"
        # the Marvin stand and arm links (not the hands): touching the desk, the stapler or a sheet ends the episode
        arm_bodies = _arm_rig_module().robot_body_ids(model)
        self.is_arm = np.array([int(model.geom_bodyid[g]) in arm_bodies for g in range(model.ngeom)])
        self.is_sheet = np.array([str(o).startswith("sheet_") for o in self.geom_owner])
        self.is_stapler = self.geom_owner == "stapler"
        self.ground = np.zeros(model.ngeom, dtype=bool)
        for g in range(model.ngeom):
            name = model.geom(g).name or ""
            if name == "floor" or name.startswith("desk_leg"):
                self.ground[g] = True
        self.floor = model.geom("floor").id
        self.geom_body = np.array([f"body:{int(model.geom_bodyid[g])}" for g in range(model.ngeom)], dtype=object)
        # sheets by owner name; the stapler counts as supported when its base or head touches anything
        self.drop_bodies = [(b, f"sheet_{i}") for i, b in enumerate(self.sheet_ids)] + [(self.base, f"body:{self.base}")]
        self._v = np.empty(6)
        self.desk_lo = np.asarray(config["desk"]["center"]) - np.asarray(config["desk"]["half"])
        self.desk_hi = np.asarray(config["desk"]["center"]) + np.asarray(config["desk"]["half"])
        self.ws_lo = np.asarray(config["workspace"]["min"], dtype=float)
        self.ws_hi = np.asarray(config["workspace"]["max"], dtype=float)
        self.reset(None)

    # ------------------------------------------------------------------ state
    def reset(self, data):
        self.stage = 0
        self.hold = 0
        self.success = False
        self.failure = None
        self.failure_detail = None
        self.stapler_home = None if data is None else data.xpos[self.base].copy()
        self.stage_steps = {}

    # ------------------------------------------------------------------ geometry
    def corners(self, data, i):
        b = self.sheet_ids[i]
        R = data.xmat[b].reshape(3, 3)
        local = np.c_[CORNERS * self.half, np.zeros(4)]
        return data.xpos[b] + local @ R.T

    def staple_point(self, data):
        R = data.xmat[self.base].reshape(3, 3)
        return data.xpos[self.base] + R @ STAPLE_LOCAL

    # ------------------------------------------------------------------ fail-fast
    def violation(self, data):
        """First broken invariant as (reason, detail) or None; checked after every physics substep."""
        if not np.isfinite(data.qpos).all() or not np.isfinite(data.qvel).all():
            return "unstable_physics", "non-finite state"
        for w in (mujoco.mjtWarning.mjWARN_BADQPOS, mujoco.mjtWarning.mjWARN_BADQVEL, mujoco.mjtWarning.mjWARN_BADQACC):
            if data.warning[w].number:
                return "unstable_physics", "simulator warning"
        top = self.c["table_z"]
        for i, b in enumerate(self.sheet_ids):
            p = data.xpos[b]
            if p[2] < top + self.t / 2 - 0.001:
                return "sheet_below_table", f"sheet_{i}"
            if np.any(p[:2] < self.desk_lo) or np.any(p[:2] > self.desk_hi):
                return "sheet_off_desk", f"sheet_{i}"
            if np.any(p < self.ws_lo) or np.any(p > self.ws_hi):
                return "sheet_left_workspace", f"sheet_{i}"
            if np.min(self.corners(data, i)[:, 2]) < top - 0.015:
                return "sheet_below_table", f"sheet_{i} corner"
        home = self.stapler_home
        if home is not None and np.linalg.norm(data.xpos[self.base][:2] - home[:2]) > self.c["stapler_max_shift_m"]:
            return "stapler_displaced", "base moved more than the allowed distance"
        tilt = float(np.arccos(np.clip(data.xmat[self.base][8], -1, 1)))
        if tilt > self.c["stapler_max_tilt_rad"]:
            return "stapler_tipped", f"tilt {tilt:.3f} rad"
        # Mid-air drop (no catch window): an object with no contact at all whose COM falls faster than
        # ``drop_speed_m_s`` fails at the first such substep, even if it would land or be caught later.
        v = self._v
        falling = []
        for b, name in self.drop_bodies:
            mujoco.mj_objectVelocity(self.m, data, mujoco.mjtObj.mjOBJ_BODY, b, v, 0)
            if v[5] < -self.c["drop_speed_m_s"]:
                falling.append(name)
        if falling:
            touched = set()
            for k in range(data.ncon):
                a, b = data.contact.geom[k]
                touched.add(self.geom_owner[a])
                touched.add(self.geom_owner[b])
                touched.add(self.geom_body[a])
                touched.add(self.geom_body[b])
            for name in falling:
                if name not in touched:
                    return "object_dropped", f"{name} unsupported and falling"
        n = data.ncon
        if n:
            g = data.contact.geom[:n]
            g1, g2 = g[:, 0], g[:, 1]
            arm = (self.is_arm[g1] & ~self.is_hand[g2]) | (self.is_arm[g2] & ~self.is_hand[g1])
            if arm.any():
                k = int(np.flatnonzero(arm)[0])
                a, b = int(g1[k]), int(g2[k])
                if not self.is_arm[a]:
                    a, b = b, a
                return "arm_collision", f"{self.m.geom(a).name or 'arm link'} touched {self.m.geom(b).name or 'world'}"
            objects = self.is_sheet | self.is_stapler
            hit = (objects[g1] & self.ground[g2]) | (objects[g2] & self.ground[g1])
            if hit.any():
                k = int(np.flatnonzero(hit)[0])
                obj = int(g1[k] if objects[g1[k]] else g2[k])
                return "object_dropped", str(self.geom_owner[obj])
        return None

    # ------------------------------------------------------------------ predicates
    def features(self, data):
        n = self.n
        R0 = data.xmat[self.sheet_ids[0]].reshape(3, 3)
        normal = R0[:, 2]
        c0 = self.corners(data, 0)
        offsets = []
        for i in range(1, n):
            ci = self.corners(data, i)
            diff = ci - c0
            diff -= np.outer(diff @ normal, normal)
            offsets.append(float(np.max(np.linalg.norm(diff, axis=1))))
        heights = [float((data.xpos[b] - data.xpos[self.sheet_ids[0]]) @ normal) for b in self.sheet_ids]
        gaps = [heights[i + 1] - heights[i] for i in range(n - 1)]
        pairs = set()
        hand_sheet = hand_stapler = 0
        blade_top = False
        top_geom = self.sheet_geoms[-1]
        for k in range(data.ncon):
            con = data.contact[k]
            if con.efc_address < 0:
                continue
            a, b = int(con.geom1), int(con.geom2)
            oa, ob = self.geom_owner[a], self.geom_owner[b]
            if self.is_sheet[a] and self.is_sheet[b] and oa != ob:
                pairs.add(frozenset((oa, ob)))
            if (self.is_hand[a] and self.is_sheet[b]) or (self.is_hand[b] and self.is_sheet[a]):
                hand_sheet += 1
            if (self.is_hand[a] and self.is_stapler[b]) or (self.is_hand[b] and self.is_stapler[a]):
                hand_stapler += 1
            if {a, b} == {self.blade, top_geom}:
                blade_top = True
        adjacent = all(frozenset((f"sheet_{i}", f"sheet_{i + 1}")) in pairs for i in range(n - 1))
        aligned = (
            max(offsets) <= self.c["align_tolerance_m"]
            and all(0.5 * self.t <= g <= 3.0 * self.t for g in gaps)
            and adjacent
        )
        S = self.staple_point(data)
        margins, lifts, inside = [], [], True
        for i, b in enumerate(self.sheet_ids):
            R = data.xmat[b].reshape(3, 3)
            local = R.T @ (S - data.xpos[b])
            ex, ey = self.half[0] - abs(local[0]), self.half[1] - abs(local[1])
            margins.append((float(ex), float(ey)))
            lifts.append(float(-local[2]))  # mid-plane height above the staple point
            lo, hi = self.c["staple_margin_min_m"], self.c["staple_margin_max_m"]
            if not (lo <= ex <= hi and lo <= ey <= hi and 0.0 <= -local[2] <= self.c["throat_height_max_m"]):
                inside = False
        angle = float(data.qpos[self.hinge])
        pressed = angle >= self.stop - self.c["stroke_tolerance_rad"]
        speeds = []
        v = np.empty(6)
        for b in self.sheet_ids:
            mujoco.mj_objectVelocity(self.m, data, mujoco.mjtObj.mjOBJ_BODY, b, v, 0)
            speeds.append(float(np.linalg.norm(v[3:])))
        return {
            "corner_offsets_m": offsets,
            "stack_gaps_m": gaps,
            "adjacent_contacts": adjacent,
            "aligned": bool(aligned),
            "staple_point": S.tolist(),
            "staple_margins_m": margins,
            "sheet_height_above_staple_m": lifts,
            "in_throat": bool(inside),
            "head_angle_rad": angle,
            "head_stop_rad": self.stop,
            "pressed": bool(pressed),
            "blade_on_stack": bool(blade_top),
            "hand_sheet_contacts": hand_sheet,
            "hand_stapler_contacts": hand_stapler,
            "max_sheet_speed_m_s": max(speeds),
            "stapler_shift_m": float(np.linalg.norm(data.xpos[self.base][:2] - self.stapler_home[:2]))
            if self.stapler_home is not None else 0.0,
        }

    def update(self, data, step):
        """Advance the ordered stages after a control step; returns the features."""
        f = self.features(data)
        a, t = f["aligned"], f["aligned"] and f["in_throat"]
        if self.stage == 0 and a:
            self.stage = 1
            self.stage_steps["aligned"] = step
        if self.stage == 1 and t:
            self.stage = 2
            self.stage_steps["in_throat"] = step
        if self.stage == 2 and t and f["pressed"] and f["blade_on_stack"]:
            self.stage = 3
            self.stage_steps["pressed"] = step
        if self.stage >= 3:
            ok = (
                t
                and f["head_angle_rad"] <= self.c["head_up_rad"]
                and f["hand_sheet_contacts"] == 0
                and f["hand_stapler_contacts"] == 0
                and f["max_sheet_speed_m_s"] <= 0.02
            )
            self.hold = self.hold + 1 if ok else 0
            if self.hold >= self.c["hold_steps"]:
                self.stage = 4
                self.success = True
                self.stage_steps["released_hold"] = step
        f["stage"] = self.stage
        f["hold_steps"] = self.hold
        return f
