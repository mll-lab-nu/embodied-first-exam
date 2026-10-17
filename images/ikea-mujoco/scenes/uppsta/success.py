"""UPPSTA hammering block success check on the current state. The source tree has no end-state grader (its
direct-force run logs per-step measurements); this check compares the end state with the scene's own 'assembled'
keyframe (every part in its assembled pose, pegs up), in the board frame, with the STEGESUND thresholds:
  - both screws' seat welds engaged (seat_weld.py), and each screw in its own hole: axial and lateral error < 0.6 mm,
    axis tilt < 2 deg (spin free);
  - end blocks a and b: position error < 0.6 mm, rotation error < 1 deg;
  - the four dowels (identical, any dowel in any dowel hole): each assembled dowel position holds a distinct dowel
    within 0.6 mm, its axis within 2 deg (either way round);
  - the eight pegs (identical, any peg in any hole): each peg hole holds a distinct peg within 1 mm laterally, its
    axis within 2 deg, and at most 0.5 mm above the up position (the source pushes a peg until it reaches it);
  - the block stands on its feet: the board's assembled up direction within 1 deg of world +z;
  - released: no robot body touches any part.
"""
import math
import numpy as np
import mujoco

SCREWS = ("screw_a", "screw_b")
BLOCKS = ("end_block_a", "end_block_b")
DOWELS = tuple(f"dowel_{i}" for i in range(4))
PEGS = tuple(f"peg_{i}" for i in range(8))


def _T(d, b):
    M = np.eye(4)
    M[:3, :3] = d.xmat[b].reshape(3, 3)
    M[:3, 3] = d.xpos[b]
    return M


def _angle_deg(R):
    q = np.zeros(4)
    mujoco.mju_mat2Quat(q, np.ascontiguousarray(R).reshape(-1))
    return math.degrees(2 * math.atan2(float(np.linalg.norm(q[1:])), abs(float(q[0]))))


def _axis_deg(u, v, either_way=False):
    c = float(np.dot(u, v)) / (np.linalg.norm(u) * np.linalg.norm(v))
    c = abs(c) if either_way else c
    return math.degrees(math.acos(min(max(c, -1.0), 1.0)))


class Monitor:
    def __init__(self, model, data, task, scene=None):
        self.m, self.d, self.task = model, data, task
        self.mech = scene.mech if scene is not None else None
        m = model
        self.bid = {n: m.body(n).id for n in ("board",) + SCREWS + BLOCKS + DOWELS + PEGS}
        # the long axis (body frame) of a dowel / peg: its smallest principal inertia axis
        self.long_axis = {}
        for n in DOWELS + PEGS:
            b = self.bid[n]
            R = np.zeros(9); mujoco.mju_quat2Mat(R, m.body_iquat[b]); R = R.reshape(3, 3)
            self.long_axis[n] = R[:, int(np.argmin(m.body_inertia[b]))]
        kd = mujoco.MjData(m)
        mujoco.mj_resetDataKeyframe(m, kd, m.key("assembled").id)
        mujoco.mj_kinematics(m, kd)
        Tb = _T(kd, self.bid["board"])
        self.want = {n: np.linalg.inv(Tb) @ _T(kd, self.bid[n]) for n in self.bid if n != "board"}
        self.up_board = Tb[:3, :3].T @ np.array([0, 0, 1.0])
        self.robot = np.array([m.body(i).name.startswith(("left/", "right/")) for i in range(m.nbody)])
        self.part_ids = {m.jnt_bodyid[j] for j in range(m.njnt) if m.jnt_type[j] == mujoco.mjtJoint.mjJNT_FREE}

    def reset(self): pass
    def update(self): pass
    def state(self): return {}
    def set_state(self, s): pass

    def _set_match(self, names, tol_mm, have, extra):
        """each assembled slot (the keyframe poses of `names`) gets the nearest distinct part of `names`"""
        free, rep, ok = set(names), {}, True
        for slot in names:
            w = self.want[slot]
            best = min(free, key=lambda n: float(np.linalg.norm(have[n][:3, 3] - w[:3, 3])))
            free.discard(best)
            r = extra(slot, best, w, have[best])
            rep[slot] = dict(part=best, **r)
            ok = ok and r["ok"]
        return rep, ok

    def report(self):
        m, d = self.m, self.d
        Tb = _T(d, self.bid["board"])
        have = {n: np.linalg.inv(Tb) @ _T(d, b) for n, b in self.bid.items() if n != "board"}
        rep, ok = {}, True
        welds = self.mech.status() if self.mech is not None else {}
        for s in SCREWS:
            err = np.linalg.inv(self.want[s]) @ have[s]
            ax, lat = float(err[2, 3]) * 1e3, float(np.hypot(err[0, 3], err[1, 3])) * 1e3
            tilt = math.degrees(math.acos(min(max(float(err[2, 2]), -1.0), 1.0)))
            welded = bool(welds.get(s, {}).get("welded"))
            good = welded and abs(ax) < 0.6 and lat < 0.6 and tilt < 2
            rep[s] = dict(welded=welded, axial_mm=round(ax, 3), lateral_mm=round(lat, 3), tilt_deg=round(tilt, 3),
                          ok=bool(good))
            ok = ok and good
        for n in BLOCKS:
            err = np.linalg.inv(self.want[n]) @ have[n]
            dp, da = float(np.linalg.norm(err[:3, 3])) * 1e3, _angle_deg(err[:3, :3])
            good = dp < 0.6 and da < 1.0
            rep[n] = dict(pos_mm=round(dp, 3), rot_deg=round(da, 3), ok=bool(good))
            ok = ok and good

        def dowel(slot, part, w, h):
            dp = float(np.linalg.norm(h[:3, 3] - w[:3, 3])) * 1e3
            da = _axis_deg(h[:3, :3] @ self.long_axis[part], w[:3, :3] @ self.long_axis[slot], either_way=True)
            return dict(pos_mm=round(dp, 3), axis_deg=round(da, 3), ok=bool(dp < 0.6 and da < 2))
        rep["dowels"], good = self._set_match(DOWELS, 0.6, have, dowel)
        ok = ok and good
        up = self.up_board

        def peg(slot, part, w, h):
            dv = h[:3, 3] - w[:3, 3]
            rise = float(dv @ up) * 1e3                      # above the up position, along the board's up direction
            lat = float(np.linalg.norm(dv - (dv @ up) * up)) * 1e3
            da = _axis_deg(h[:3, :3] @ self.long_axis[part], w[:3, :3] @ self.long_axis[slot], either_way=True)
            return dict(lateral_mm=round(lat, 3), above_up_mm=round(rise, 3), axis_deg=round(da, 3),
                        ok=bool(lat < 1.0 and rise <= 0.5 and da < 2))
        rep["pegs"], good = self._set_match(PEGS, 1.0, have, peg)
        ok = ok and good
        tilt = _axis_deg(Tb[:3, :3] @ up, np.array([0, 0, 1.0]))
        rep["on_its_feet_tilt_deg"] = round(tilt, 3)
        ok = ok and tilt < 1.0
        touch = []
        for c in d.contact[: d.ncon]:
            b1, b2 = m.geom_bodyid[c.geom1], m.geom_bodyid[c.geom2]
            if (self.robot[b1] and b2 in self.part_ids) or (self.robot[b2] and b1 in self.part_ids):
                touch.append((m.body(b1).name, m.body(b2).name))
        rep["robot_part_contacts"] = sorted(set(touch))
        ok = ok and not touch
        failed = [k for k, v in rep.items() if isinstance(v, dict) and (v.get("ok") is False or
                  any(isinstance(x, dict) and x.get("ok") is False for x in v.values()))]
        return {"success": bool(ok), "assembled": rep, "failed": failed, "fasteners": welds}
