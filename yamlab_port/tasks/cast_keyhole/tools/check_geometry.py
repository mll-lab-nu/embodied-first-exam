"""Check the ported geometry against the STL package: meshes, start poses, goal region, start gap.

usage: python check_geometry.py <tier> [stl_package_dir]
"""
import json, sys
from pathlib import Path
import numpy as np
import trimesh
from scipy.spatial.transform import Rotation
sys.path.insert(0, str(Path(__file__).resolve().parent))
import keyhole_geometry as kg

tier = sys.argv[1]
pkg = Path(sys.argv[2] if len(sys.argv) > 2 else
           str(Path(__file__).resolve().parents[3] / "robotangle_v1_stl" / "cast_keyhole")) / tier
rec = kg.load_record(tier)
plates = kg.build_plates(rec)
layout = json.loads((pkg / "layout.json").read_text())
out = {}
for n, p in plates.items():
    stl = trimesh.load(pkg / f"keyhole_{n}.stl")
    mine = p.visual_part()
    # compare as point sets (mm)
    d1 = trimesh.proximity.signed_distance(mine, stl.vertices / 1000.) if False else None
    a = np.sort(np.round(stl.vertices, 3).view([("", float)] * 3), axis=0)
    b = np.sort(np.round(mine.vertices * 1000, 3).view([("", float)] * 3), axis=0)
    bounds_err = np.abs(stl.bounds - mine.bounds * 1000).max()
    vol = (stl.volume, mine.volume * 1e9, sum(c.volume for c in p.cells) * 1e9)
    out[n] = dict(stl_vertices=len(stl.vertices), mine_vertices=len(mine.vertices), bounds_err_mm=float(bounds_err),
                  volume_mm3=vol, extent_mm=(p.extent * 1000).round(2).tolist(), cells=len(p.cells),
                  mass_kg=sum(c.volume for c in p.cells) * rec["density_kg_m3"])
    # nearest-point check of STL vertices onto my mesh
    q = trimesh.proximity.ProximityQuery(mine)
    _, dist, _ = q.on_surface(stl.vertices / 1000.)
    out[n]["stl_to_mine_max_mm"] = float(dist.max() * 1000)
poses = kg.old_start_poses(plates)
for part in layout["parts"]:
    n = part["name"].split("_")[1]
    pos, rot = poses[n]
    ref = np.asarray(part["pose"]["table"]["position_mm"])
    q = rot.as_quat()[[3, 0, 1, 2]]
    out[n]["start_pos_err_mm"] = float(np.abs(pos * 1000 - ref).max())
    out[n]["start_quat"] = q.round(6).tolist()
    out[n]["ref_quat"] = part["pose"]["table"]["quaternion_wxyz"]
# goal region
world = {n: poses[n][1].apply(plates[n].visual_part().vertices) + poses[n][0] for n in plates}
g = kg.choose_goal_region(world["gold"][:, :2], world["silver"])
lo = [-g["half"], g["center_y"] - g["half"]]; hi = [g["half"], g["center_y"] + g["half"]]
mk = layout["markers"][0]
out["goal"] = dict(mine_min_mm=(np.array(lo) * 1000).round(2).tolist(), mine_max_mm=(np.array(hi) * 1000).round(2).tolist(),
                   pkg_min=mk["table_xy_min_mm"], pkg_max=mk["table_xy_max_mm"], height_mm=g["height"] * 1000,
                   separator_offset_mm=g["offset"] * 1000, rigid_size_mm=g["rigid_size"] * 1000)
# start gap between the two (collision cells and visual)
cm = trimesh.collision.CollisionManager
try:
    a, b = cm(), cm()
    a.add_object("g", trimesh.Trimesh(world["gold"], plates["gold"].visual.faces))
    b.add_object("s", trimesh.Trimesh(world["silver"], plates["silver"].visual.faces))
    out["start_gap_mm"] = float(a.min_distance_other(b) * 1000)
except Exception as e:  # fcl missing
    out["start_gap_mm"] = repr(e)
print(json.dumps(out, indent=1, default=float))
