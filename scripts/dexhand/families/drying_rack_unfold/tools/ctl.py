"""Authoring controller helpers for drying_rack_unfold (Sharpa): pinch kinematics + waypoint interpolation.

Pinch families (finger joint targets per thumb-index separation) were found by kinematic search:
pinch_unfold.json (pinch axis along the hand's lateral axis) and pinch_low.json (low pinch whose fingertips reach a
tube 11 mm above the counter with every other hand geom clear of the counter)."""
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from runtime import Session  # noqa: E402,F401

FAMS = {"A": {float(k): np.asarray(v) for k, v in json.loads((HERE / "pinch_unfold.json").read_text()).items()}}
CURL = {15: 1.5, 17: 1.6, 18: 1.2, 19: 1.5, 21: 1.6, 22: 1.2, 23: 0.2, 24: 1.5, 26: 1.6, 27: 1.2}
JIDX = [6, 7, 8, 9, 10, 11, 12, 13, 14]  # thumb 5 + index 4


def rot(rx, ry, rz):
    cx, sx, cy, sy, cz, sz = np.cos(rx), np.sin(rx), np.cos(ry), np.sin(ry), np.cos(rz), np.sin(rz)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Rx @ Ry @ Rz


class Kin:
    """Pinch-midpoint offsets in the hand frame (zero wrist rotation), measured by forward kinematics."""

    def __init__(self, s, fam="A"):
        import mujoco

        self.s = s
        self.P = FAMS[fam]
        self.SEPS = np.array(sorted(self.P))
        SEPS = self.SEPS
        m, d = s.model, mujoco.MjData(s.model)
        self.origin = np.asarray(s.config["wrist_stage"]["origin"], float)
        self.table = {}
        for sep in SEPS:
            row = self.fingers(sep)
            d.qpos[:] = m.qpos0
            d.qpos[s.qadr] = np.r_[np.zeros(6), row]
            mujoco.mj_kinematics(m, d)
            t = d.geom_xpos[m.geom("right_thumb_fingertip_collision").id]
            i = d.geom_xpos[m.geom("right_index_fingertip_collision").id]
            self.table[sep] = ((t + i) / 2 - self.origin, t - i)

    def fingers(self, sep):
        SEPS, PINCH = self.SEPS, self.P
        sep = float(np.clip(sep, SEPS[0], SEPS[-1]))
        k = np.searchsorted(SEPS, sep)
        k = int(np.clip(k, 1, len(SEPS) - 1))
        a, b = SEPS[k - 1], SEPS[k]
        w = (sep - a) / (b - a)
        x = (1 - w) * PINCH[a] + w * PINCH[b]
        row = np.zeros(22)
        for j, v in CURL.items():
            row[j - 6] = v
        row[np.array(JIDX) - 6] = x
        return row

    def offset(self, sep):
        SEPS = self.SEPS
        sep = float(np.clip(sep, SEPS[0], SEPS[-1]))
        k = int(np.clip(np.searchsorted(SEPS, sep), 1, len(SEPS) - 1))
        a, b = SEPS[k - 1], SEPS[k]
        w = (sep - a) / (b - a)
        return (1 - w) * self.table[a][0] + w * self.table[b][0]

    def row(self, mid, sep, rz=0.0, rx=0.0, ry=0.0, wrist_sep=None):
        """Row placing the pinch midpoint at world ``mid`` (for the hand geometry at ``wrist_sep``)."""
        R = rot(rx, ry, rz)
        off = self.offset(sep if wrist_sep is None else wrist_sep)
        p = np.asarray(mid, float) - self.origin - R @ off
        return np.r_[p, rx, ry, rz, self.fingers(sep)]


def lerp_rows(a, b, n):
    return [a + (b - a) * (k + 1) / n for k in range(n)]


def smooth_rows(a, b, n):
    out = []
    for k in range(n):
        t = (k + 1) / n
        t = t * t * (3 - 2 * t)
        out.append(a + (b - a) * t)
    return out


def euler_xyz(R):
    """Serial wrist angles (rx, ry, rz) with Rx(rx) Ry(ry) Rz(rz) = R."""
    ry = np.arcsin(np.clip(R[0, 2], -1, 1))
    rx = np.arctan2(-R[1, 2], R[2, 2])
    rz = np.arctan2(-R[0, 1], R[0, 0])
    return rx, ry, rz


def Rax(axis, a):
    axis = np.asarray(axis, float) / np.linalg.norm(axis)
    K = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    return np.eye(3) + np.sin(a) * K + (1 - np.cos(a)) * K @ K


class Kin2:
    """Pinch family from a json {'rx','ry','dir','family'}: hand orientation = Rworld @ Rbase."""

    def __init__(self, s, path):
        import mujoco

        spec = json.loads(Path(path).read_text())
        self.Rbase = rot(spec["rx"], spec["ry"], 0.0)
        self.dir = np.asarray(spec["dir"])  # pinch axis (thumb - index) in the world frame of Rbase
        self.P = {float(k): np.asarray(v) for k, v in spec["family"].items()}
        self.SEPS = np.array(sorted(self.P))
        m, d = s.model, mujoco.MjData(s.model)
        self.origin = np.asarray(s.config["wrist_stage"]["origin"], float)
        self.table = {}
        for sep in self.SEPS:
            d.qpos[:] = m.qpos0
            d.qpos[s.qadr] = np.r_[np.zeros(6), self.fingers(sep)]
            mujoco.mj_kinematics(m, d)
            t = d.geom_xpos[m.geom("right_thumb_fingertip_collision").id]
            i = d.geom_xpos[m.geom("right_index_fingertip_collision").id]
            self.table[sep] = (t + i) / 2 - self.origin  # hand frame (zero wrist rotation)

    def _interp(self, sep):
        S = self.SEPS
        sep = float(np.clip(sep, S[0], S[-1]))
        k = int(np.clip(np.searchsorted(S, sep), 1, len(S) - 1))
        a, b = S[k - 1], S[k]
        return a, b, (sep - a) / (b - a)

    def fingers(self, sep):
        a, b, w = self._interp(sep)
        x = (1 - w) * self.P[a] + w * self.P[b]
        row = np.zeros(22)
        for j, v in CURL.items():
            row[j - 6] = v
        row[np.array(JIDX) - 6] = x
        return row

    def offset(self, sep):
        a, b, w = self._interp(sep)
        return (1 - w) * self.table[a] + w * self.table[b]

    def yaw_for(self, axis_world):
        """Yaw that maps the pinch direction onto +axis_world (horizontal)."""
        return np.arctan2(axis_world[1], axis_world[0]) - np.arctan2(self.dir[1], self.dir[0])

    def row(self, mid, sep, Rw, wrist_sep=None):
        R = Rw @ self.Rbase
        rx, ry, rz = euler_xyz(R)
        off = self.offset(sep if wrist_sep is None else wrist_sep)
        p = np.asarray(mid, float) - self.origin - R @ off
        return np.r_[p, rx, ry, rz, self.fingers(sep)]
