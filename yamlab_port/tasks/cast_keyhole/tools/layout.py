"""Re-layout of the Cast Keyhole scene for the YAM workstation, plus frames used by the task and oracle.

Transform (old table frame, mm -> YAMLab world, m):  p_world = Rz(YAW) p_old/1000 + (X0, Y0, TABLE_Z).
YAW = 0: old +x -> world +X, old +y -> world +Y (pure translation).  The old table frame has its origin at the tabletop
centre, +z up.
Parts keep their old poses relative to each other and to the goal square.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

import keyhole_geometry as kg

TABLE_Z = 0.7500   # physical tabletop: top of the workstation's table_surface collider (yam.yaml's 0.7517 is the
                   # calibration/visual top; plates resting on the table have their bottom at 0.7500)
X0, Y0 = 0.52, -0.10          # old table origin in YAMLab world (m); chosen by measured YAM reach
YAW_DEG = 0.0                 # scene yaw: gold's free (+x) band faces the left arm, silver's -x edge the right arm
PKG_GOAL = {                  # old goal_region from the STL package layout.json (mm, old table frame)
    "very_easy": ((-128.3, 114.8), (128.3, 371.3)),
    "easier": ((-128.3, 114.8), (128.3, 371.3)),
}


# per-tier re-layout (X0, Y0, yaw_deg); tiers not listed use the module defaults above
TIER_LAYOUT = {
    # easier: 8 cm further from the robot than very_easy, so the left arm can hold the gold band near its
    # fork end (the only part of the +x band the easier silver legs never sweep, gold y -105..-65 mm)
    "easier": (0.54, -0.10, 0.0),
}
_CUR = {"tier": None}


def layout_offset(tier=None):
    x0, y0, _ = TIER_LAYOUT.get(tier or _CUR["tier"], (X0, Y0, YAW_DEG))
    return np.array([x0, y0, TABLE_Z])


def R_yaw(tier=None):
    return Rotation.from_euler("z", TIER_LAYOUT.get(tier or _CUR["tier"], (X0, Y0, YAW_DEG))[2], degrees=True)


def T_from(R, p):
    T = np.eye(4)
    T[:3, :3] = R.as_matrix() if isinstance(R, Rotation) else R
    T[:3, 3] = p
    return T


class Scene:
    """World frames of one tier: part frames (= STL/USD frames), plate frames, goal region."""

    def __init__(self, tier, pkg_dir=None):
        self.tier = tier
        _CUR["tier"] = tier
        self.record = kg.load_record(tier)
        self.plates = kg.build_plates(self.record)
        old = kg.old_start_poses(self.plates)   # part frames in the old table frame (m)
        off = layout_offset()
        Ry = R_yaw()
        self.T_part0 = {n: T_from(Ry * r, Ry.apply(p) + off) for n, (p, r) in old.items()}
        # part frame -> plate frame:  T_part_plate = Trans(-bbox_c) * plate_to_asm
        self.T_part_plate = {}
        for n, pl in self.plates.items():
            A = np.eye(4); A[:3, 3] = -pl.bbox_center_asm
            self.T_part_plate[n] = A @ pl.plate_to_asm
        self.T_plate0 = {n: self.T_part0[n] @ self.T_part_plate[n] for n in kg.NAMES}
        # goal region (old package numbers, mm) -> world
        if pkg_dir is not None:
            lay = json.loads((Path(pkg_dir) / tier / "layout.json").read_text())
            lo, hi = lay["markers"][0]["table_xy_min_mm"], lay["markers"][0]["table_xy_max_mm"]
        else:
            lo, hi = PKG_GOAL[tier]
        lo, hi = np.asarray(lo) / 1000, np.asarray(hi) / 1000
        half = float((hi[0] - lo[0]) / 2)
        sep_old = float(lo[1] - max(.03, .02))      # old: gold all y <= sep_old (old table frame)
        corners = np.array([[lo[0], lo[1], 0], [hi[0], hi[1], 0]])
        cw = Ry.apply(corners)[:, :2] + off[:2]
        lo_w, hi_w = cw.min(0), cw.max(0)
        n_w = Ry.apply([0, 1, 0])[:2]               # old +y in world: the goal side of the separator
        rigid_size = 2 * (half - .015)          # placement.choose_region: half = rigid_size/2 + 0.015
        margin = max(.03, .02)                   # separation_margin = max(.03, minimum_separation_m)
        axis = int(np.argmax(np.abs(n_w)))
        sign = float(np.sign(n_w[axis]))
        # gold (remainder) must satisfy: sign * p[axis] <= sign_offset   (old: y_old <= sep_old)
        self.goal = dict(
            xy_min=lo_w.tolist(), xy_max=hi_w.tolist(),
            table_z=TABLE_Z, height=max(.15, rigid_size + .02),
            separator_axis=axis, separator_sign=sign,
            separator_offset=float(sep_old + sign * off[axis]),
            boundary_margin=.001, penetration_tolerance=.001)

    def part_vertices(self, name):
        return self.plates[name].visual_part().vertices

    def to_json(self):
        d = {"tier": self.tier, "transform": {"old_table_mm_to_world_m": "p_world = Rz(yaw) p_old/1000 + offset",
                                             "yaw_deg": float(R_yaw(self.tier).as_euler("xyz", degrees=True)[2]),
                                             "offset_m": layout_offset(self.tier).tolist()},
             "parts": {}, "goal_region": self.goal}
        for n in kg.NAMES:
            T = self.T_part0[n]
            q = Rotation.from_matrix(T[:3, :3]).as_quat()[[3, 0, 1, 2]]
            d["parts"][f"keyhole_{n}"] = {"pos": T[:3, 3].tolist(), "quat_wxyz": q.tolist(),
                                          "mass_kg": float(sum(c.volume for c in self.plates[n].cells)
                                                           * self.record["density_kg_m3"])}
        return d


if __name__ == "__main__":
    import sys
    s = Scene(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    print(json.dumps(s.to_json(), indent=1))
