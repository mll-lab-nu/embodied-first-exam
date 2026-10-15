"""Strict, state-only verdict for tray_glass_carry (ordered stages, terminal hold, fail-fast).

Liquid is not simulated. A glass counts as spilled when its axis tilts more than ``spill_tilt_deg`` (15 deg) from
vertical. Every quantity below is read from the MuJoCo state (body poses/velocities and the active contact list).

Stages (in order; each counts only after the previous one):
  1 lifted   - the tray touches neither counter and its base is >= ``lift_height_m`` above the counter top, with both
               glasses seated on the tray.
  2 placed   - the tray rests on the receiving counter only, its centre within ``target_tolerance_xy`` of
               ``target_xy``, tilted <= ``placed_tilt_deg``, yawed <= ``placed_yaw_deg`` from its start orientation,
               both glasses seated.
  3 released - stage-2 conditions, no hand contact with the tray or a glass, both glasses within
               ``glass_upright_hold_deg`` of vertical, tray and glasses at rest; held for ``hold_steps`` consecutive
               controls (success; the episode ends).
Fail-fast (checked after every physics substep; permanent): spill (glass tilt), glass outside the tray footprint or
lifted off the tray (base height in the tray frame above floor top + ``glass_lifted_m`` or below -10 mm), an unsupported tray or glass (tray: no hand or counter contact; glass: no tray, glass, hand or
counter contact) moving downward faster than ``unsupported_fall_speed_m_s``, the tray touching the source counter again after lift-off, the tray touching the receiving
counter while its centre is more than ``drag_margin_m`` outside the target tolerance (no sliding/dragging),
contact of the bottle with the tray / a glass / a hand, a dropping tray or glass (downward speed
above ``drop_speed_m_s``), tray tipped beyond ``tray_tip_deg``, any task object below the counter tops or touching the
floor, any task object outside the workspace box, unstable physics, episode budget exhausted.
"""

from __future__ import annotations

import mujoco
import numpy as np

GLASSES = ("cup_0", "cup_1")
OBJECTS = ("tray",) + GLASSES
UNSTABLE = (mujoco.mjtWarning.mjWARN_BADQPOS, mujoco.mjtWarning.mjWARN_BADQVEL, mujoco.mjtWarning.mjWARN_BADQACC)


class Checker:
    def __init__(self, model, config):
        self.m, self.c = model, config
        self.body = {name: model.body(name).id for name in OBJECTS}
        owner = np.full(model.nbody, "world", dtype=object)
        for b in range(1, model.nbody):
            p, name = b, "world"
            while p:
                n = model.body(p).name
                if n in OBJECTS or n == "bottle":
                    name = n
                    break
                if n.endswith("_wrist_stage"):
                    name = "hand"
                    break
                p = int(model.body_parentid[p])
            owner[b] = name
        self.geom_owner = owner[model.geom_bodyid]
        self.is_object = np.isin(self.geom_owner, OBJECTS)
        self.is_hand = self.geom_owner == "hand"
        self.is_bottle = self.geom_owner == "bottle"
        self.floor = model.geom("floor").id
        self.counter = [model.geom("counter_0").id, model.geom("counter_1").id]
        self.top = float(config["table_top_z"])
        self.ws_lo = np.asarray(config["workspace"]["min"], float)
        self.ws_hi = np.asarray(config["workspace"]["max"], float)
        self.cos_spill = np.cos(np.radians(config["spill_tilt_deg"]))
        self.cos_tip = np.cos(np.radians(config["tray_tip_deg"]))
        self.reset()

    def reset(self):
        self.stage = 0
        self.hold = 0
        self.success = False
        self.failure = None
        self.detail = None
        self.max_glass_tilt_deg = 0.0

    # ------------------------------------------------------------------ geometry
    def _tilt_cos(self, d, name):
        return float(d.xmat[self.body[name], 8])

    def glass_local(self, d, name):
        """Glass base centre in the tray frame (tray origin = bottom centre of the tray floor)."""
        t = self.body["tray"]
        R = d.xmat[t].reshape(3, 3)
        return R.T @ (d.xpos[self.body[name]] - d.xpos[t])

    def _contacts(self, d):
        n = d.ncon
        if not n:
            return np.zeros((0, 2), int)
        pairs = d.contact.geom[:n]
        active = d.contact.efc_address[:n] >= 0
        return pairs[active]

    # ------------------------------------------------------------------ fail-fast (every substep)
    def violation(self, d):
        if any(d.warning[w].number for w in UNSTABLE) or not np.isfinite(d.qpos).all():
            return "unstable_physics", ""
        for name in GLASSES:
            if self._tilt_cos(d, name) < self.cos_spill:
                return "glass_spilled", name
        for name in GLASSES:
            p = self.glass_local(d, name)
            a, b = self.c["glass_footprint_semi_axes"]
            if (p[0] / a) ** 2 + (p[1] / b) ** 2 > 1.0:
                return "glass_left_tray", name
            if p[2] > 0.002 + self.c["glass_lifted_m"] or p[2] < -0.01:
                return "glass_off_tray", name
        if self._tilt_cos(d, "tray") < self.cos_tip:
            return "tray_tipped", "tray"
        for name in OBJECTS:
            b = self.body[name]
            p = d.xpos[b]
            if p[2] < self.top - self.c["below_table_margin_m"]:
                return "object_below_table", name
            if np.any(p < self.ws_lo) or np.any(p > self.ws_hi):
                return "object_left_workspace", name
            if d.cvel[b, 5] < -self.c["drop_speed_m_s"]:
                return "object_dropped", name
        pairs = self._contacts(d)
        # A falling object without support fails at once (no drop-and-catch window): the tray is supported only by a
        # hand or a counter, a glass by the tray, the other glass, a hand or a counter.
        supported = set()
        for a, b in pairs:
            for x, y in ((a, b), (b, a)):
                ox, oy = self.geom_owner[x], self.geom_owner[y]
                if ox in OBJECTS and (oy == "hand" or y in self.counter or (ox != "tray" and oy in OBJECTS and oy != ox)):
                    supported.add(ox)
        for name in OBJECTS:
            if name not in supported and d.cvel[self.body[name], 5] < -self.c["unsupported_fall_speed_m_s"]:
                return "object_dropped", name
        if len(pairs):
            g1, g2 = pairs[:, 0], pairs[:, 1]
            bottle = (self.is_bottle[g1] & (self.is_object[g2] | self.is_hand[g2])) | (
                self.is_bottle[g2] & (self.is_object[g1] | self.is_hand[g1]))
            if bottle.any():
                i = int(np.flatnonzero(bottle)[0])
                other = g2[i] if self.is_bottle[g1[i]] else g1[i]
                return "obstacle_contact", str(self.geom_owner[other])
            tray_on = lambda geom: ((g1 == geom) & (self.geom_owner[g2] == "tray")) | (
                (g2 == geom) & (self.geom_owner[g1] == "tray"))
            if self.stage >= 1 and tray_on(self.counter[0]).any():
                return "tray_back_on_source", "tray"
            if tray_on(self.counter[1]).any():
                offset = np.abs(d.xpos[self.body["tray"], :2] - np.asarray(self.c["target_xy"]))
                if np.any(offset > np.asarray(self.c["target_tolerance_xy"]) + self.c["drag_margin_m"]):
                    return "tray_dragged", "tray"
            floor = ((g1 == self.floor) & self.is_object[g2]) | ((g2 == self.floor) & self.is_object[g1])
            if floor.any():
                i = int(np.flatnonzero(floor)[0])
                return "object_on_floor", str(self.geom_owner[g2[i] if g1[i] == self.floor else g1[i]])
        return None

    # ------------------------------------------------------------------ predicate features (every control)
    def features(self, d):
        t = self.body["tray"]
        pairs = self._contacts(d)
        tray_counter = [False, False]
        hand_contact = False
        for g1, g2 in pairs:
            for a, b in ((g1, g2), (g2, g1)):
                if self.geom_owner[a] == "tray" and b in self.counter:
                    tray_counter[self.counter.index(b)] = True
                if self.is_hand[a] and self.is_object[b]:
                    hand_contact = True
        glass = {}
        for name in GLASSES:
            p = self.glass_local(d, name)
            tilt = float(np.degrees(np.arccos(np.clip(self._tilt_cos(d, name), -1, 1))))
            glass[name] = {"local": p.round(5).tolist(), "tilt_deg": tilt,
                           "seated": bool(-0.003 <= p[2] <= 0.002 + self.c["glass_seat_tolerance_m"])}
        speeds, spins = [], []
        for name in OBJECTS:
            v = d.cvel[self.body[name]]
            # cvel = (angular, linear) at the subtree COM of the root body; every task object is a root free body
            # without children, so this is the object's own COM velocity (world axes)
            spins.append(float(np.linalg.norm(v[:3])))
            speeds.append(float(np.linalg.norm(v[3:])))
        tray_xy = d.xpos[t, :2]
        offset = tray_xy - np.asarray(self.c["target_xy"])
        tray_tilt = float(np.degrees(np.arccos(np.clip(d.xmat[t, 8], -1, 1))))
        tray_yaw = float(np.degrees(np.arctan2(d.xmat[t, 3], d.xmat[t, 0])))
        return {
            "tray_pos": d.xpos[t].round(5).tolist(),
            "tray_tilt_deg": tray_tilt,
            "tray_yaw_deg": tray_yaw,
            "tray_on_source": tray_counter[0],
            "tray_on_target_counter": tray_counter[1],
            "target_offset_xy": offset.round(5).tolist(),
            "hand_contact": hand_contact,
            "glasses": glass,
            "max_speed_m_s": max(speeds),
            "max_spin_rad_s": max(spins),
        }

    def update(self, d):
        """Advance the ordered stages after one control; returns the features used."""
        f = self.features(d)
        c = self.c
        seated = all(g["seated"] for g in f["glasses"].values())
        lifted = (not f["tray_on_source"] and not f["tray_on_target_counter"]
                  and f["tray_pos"][2] >= self.top + c["lift_height_m"] and seated)
        tol = np.asarray(c["target_tolerance_xy"])
        placed = (f["tray_on_target_counter"] and not f["tray_on_source"]
                  and bool(np.all(np.abs(f["target_offset_xy"]) <= tol))
                  and f["tray_tilt_deg"] <= c["placed_tilt_deg"] and abs(f["tray_yaw_deg"]) <= c["placed_yaw_deg"]
                  and seated)
        released = (placed and not f["hand_contact"]
                    and all(g["tilt_deg"] <= c["glass_upright_hold_deg"] for g in f["glasses"].values())
                    and f["max_speed_m_s"] <= c["rest_speed_m_s"] and f["max_spin_rad_s"] <= c["rest_angular_speed_rad_s"])
        if self.stage == 0 and lifted:
            self.stage = 1
        if self.stage == 1 and placed:
            self.stage = 2
        if self.stage >= 2 and released:
            self.hold += 1
        else:
            self.hold = 0
        if self.hold >= c["hold_steps"]:
            self.stage = 3
            self.success = True
        f.update({"lifted": lifted, "placed": placed, "released": released, "hold_steps": self.hold})
        return f

    def state(self):
        return [self.stage, self.hold, int(self.success), self.failure or ""]
