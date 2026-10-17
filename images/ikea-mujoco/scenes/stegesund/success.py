"""STEGESUND roll stand success check: the source tree's assembled_report (assembly.py) on the current state, ported
to numpy only (rotation angles from quaternions instead of scipy rotation vectors; same values, same thresholds).

Every part except half_A and the hex key, relative to its reference body, against its assembled relative pose
(task.json['assembled_poses_world']; reference = the shelf for a bolt, half_A otherwise):
  - bolt_1..4 (checked in their bore, spin free): axial error < 0.6 mm, lateral error < 0.6 mm, axis tilt < 2 deg;
  - half_B, shelf: position error < 0.6 mm, rotation error < 1 deg; rod: position error < 3 mm, rotation < 1 deg;
  - the stand is upright: half_A's z axis within 1 deg of world +z.
One addition to the source check: the rod's rotation error is taken up to the rod's own symmetry (task.json
'symmetric_parts': a centred 32-facet prism along its local y axis, so a spin by 360/32 deg about that axis or an
end-for-end flip leaves the same solid in the same place). The source check, written for the direct-force run that put
the rod down unturned, counted an end-for-end flipped rod as 180 deg off.
"""
import math
import numpy as np
import mujoco


def _T(d, b):
    M = np.eye(4)
    M[:3, :3] = d.xmat[b].reshape(3, 3)
    M[:3, 3] = d.xpos[b]
    return M


def _angle_deg(R):
    q = np.zeros(4)
    mujoco.mju_mat2Quat(q, np.ascontiguousarray(R).reshape(-1))
    return math.degrees(2 * math.atan2(float(np.linalg.norm(q[1:])), abs(float(q[0]))))


def _rot(axis, ang):
    axis = np.asarray(axis, float) / np.linalg.norm(axis)
    K = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    return np.eye(3) + math.sin(ang) * K + (1 - math.cos(ang)) * K @ K


def _symmetries(task, part):
    """the rotations (part frame) that map the part onto itself: identity, or for a centred regular n-facet prism along
    a local axis, the n spins about it and the n end-for-end flips about the perpendicular axes at multiples of pi/n"""
    sym = task.get("symmetric_parts", {}).get(part)
    if sym is None:
        return [np.eye(3)]
    n, a = int(sym["facets"]), np.eye(3)["xyz".index(sym["axis"])]
    u, w = np.eye(3)[[i for i in range(3) if a[i] == 0]]
    return ([_rot(a, 2 * math.pi * k / n) for k in range(n)] +
            [_rot(math.cos(math.pi * j / n) * u + math.sin(math.pi * j / n) * w, math.pi) for j in range(n)])


def assembled_report(m, d, task):
    asm = {k: np.array(v) for k, v in task["assembled_poses_world"].items()}
    rep, ok = {}, True
    for n in task["part_types"]:
        if n in ("half_A", "hex_key"):
            continue
        ref = "shelf" if n.startswith("bolt") else "half_A"
        want = np.linalg.inv(asm[ref]) @ asm[n]
        have = np.linalg.inv(_T(d, m.body(ref).id)) @ _T(d, m.body(n).id)
        err = np.linalg.inv(want) @ have
        dp = float(np.linalg.norm(err[:3, 3])) * 1e3
        if n.startswith("bolt"):
            da = math.degrees(math.acos(min(max(float(err[2, 2]), -1.0), 1.0)))
            dp_ax = float(err[2, 3]) * 1e3
            lat = float(np.hypot(err[0, 3], err[1, 3])) * 1e3
            good = abs(dp_ax) < 0.6 and lat < 0.6 and da < 2
            rep[n] = dict(axial_mm=round(dp_ax, 3), lateral_mm=round(lat, 3), tilt_deg=round(da, 3), ok=bool(good))
        else:
            da = min(_angle_deg(err[:3, :3] @ S) for S in _symmetries(task, n))
            tol = 3.0 if n == "rod" else 0.6
            good = dp < tol and da < 1.0
            rep[n] = dict(pos_mm=round(dp, 3), rot_deg=round(da, 3), ok=bool(good))
        ok = ok and rep[n]["ok"]
    up = d.xmat[m.body("half_A").id].reshape(3, 3)[:, 2]
    rep["stand_upright_tilt_deg"] = round(math.degrees(math.acos(min(max(float(up[2]), -1.0), 1.0))), 3)
    ok = ok and rep["stand_upright_tilt_deg"] < 1.0
    rep["all_ok"] = bool(ok)
    return rep


class Monitor:
    def __init__(self, model, data, task, scene=None):
        self.m, self.d, self.task = model, data, task
        self.mech = scene.mech if scene is not None else None

    def reset(self): pass
    def update(self): pass
    def state(self): return {}
    def set_state(self, s): pass

    def report(self):
        rep = assembled_report(self.m, self.d, self.task)
        out = {"success": rep["all_ok"], "assembled": rep}
        if self.mech is not None:
            out["fasteners"] = self.mech.status()
        return out
