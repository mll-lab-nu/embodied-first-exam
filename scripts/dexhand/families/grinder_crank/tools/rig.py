"""Authoring helpers (not shipped to task dirs): wrist-stage orientation and named finger targets."""

from __future__ import annotations

import numpy as np
from scipy.spatial.transform import Rotation

# Native Wave frame: fingers +z, palm normal +x, thumb +y (right) / -y (mirrored left).
MOUNT = np.array([[0.0, 0.0, 1.0], [0.0, -1.0, 0.0], [1.0, 0.0, 0.0]])  # stage <- native (quat 0 .707 0 .707)


def stage_angles(palm_normal, fingers):
    """Serial XYZ wrist angles that put the native palm normal / finger direction on the given world vectors."""
    x = np.asarray(palm_normal, float)
    x /= np.linalg.norm(x)
    z = np.asarray(fingers, float)
    z = z - x * (z @ x)
    z /= np.linalg.norm(z)
    y = np.cross(z, x)
    H = np.column_stack([x, y, z])
    R = H @ MOUNT.T
    return Rotation.from_matrix(R).as_euler("XYZ")


def world_of_native(angles, native):
    R = Rotation.from_euler("XYZ", angles).as_matrix() @ MOUNT
    return R @ np.asarray(native, float)


class Layout:
    """Index helper for a Session's actuator layout."""

    # Sharpa-style finger keys -> Wuji Hand 2.2 actuator suffixes (authoring convenience for the wuji rig; the
    # joint angle conventions differ, so Wuji values are searched separately).
    WUJI = {"thumb_CMC_FE": "THJ0", "thumb_CMC_AA": "THJ1", "thumb_MCP_FE": "THJ2", "thumb_IP": "THJ3"}
    for _f, _w in (("index", "FF"), ("middle", "MF"), ("ring", "RF"), ("pinky", "LF")):
        WUJI.update({f"{_f}_MCP_FE": _w + "J0", f"{_f}_MCP_AA": _w + "J1", f"{_f}_PIP": _w + "J2", f"{_f}_DIP": _w + "J3"})

    def __init__(self, session):
        self.names = session.actuator_names
        self.index = {n: i for i, n in enumerate(self.names)}
        self.lo, self.hi = session.lo, session.hi
        if any("_wuji_" in n for n in self.names):
            for side, s in (("right", "r"), ("left", "l")):
                for key, suffix in self.WUJI.items():
                    self.index[f"{side}_{key}"] = self.index[f"{s}_wuji_{s}_{suffix}"]

    def wrist(self, side):
        return [self.index[f"{side}_wrist_{a}_act"] for a in ("x", "y", "z", "rx", "ry", "rz")]

    def fingers(self, side):
        return [i for i, n in enumerate(self.names) if n.startswith(side + "_") and "wrist" not in n] + \
               [i for i, n in enumerate(self.names) if n.startswith(side[0] + "_wuji_")]

    def set(self, row, values: dict):
        row = np.array(row, dtype=float)
        for k, v in values.items():
            if k in self.index:  # keys without a counterpart on this hand model are ignored
                row[self.index[k]] = v
        return np.clip(row, self.lo, self.hi)
