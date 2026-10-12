"""Build the YAMLab assets of one Cast Keyhole tier (run on vast: needs pxr from the Isaac venv).

Output: <out>/<tier>/keyhole_{gold,silver}/keyhole_{gold,silver}.usd + asset_size.json, and
<out>/<tier>/layout.json (world start poses, masses, goal region, re-layout transform, vertices for the goal
check, plate frames for the oracle).

Each plate is ONE dynamic rigid body (RigidBodyAPI on the default prim = the part/STL frame) with
 - a visual mesh (the STL geometry, 1:1, no collision), and
 - one convex collider per slab prism of the old generator (exact, non-overlapping convex cells; the slots and
   the 4.8 mm start clearance are preserved exactly, see check_colliders.py).
Mass comes from the task YAML; PhysX derives COM and inertia from the colliders (= the exact solid).

usage: python build_assets.py <tier> <out_dir>
"""
import json
import sys
from pathlib import Path

import numpy as np
import trimesh
from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, Vt

sys.path.insert(0, str(Path(__file__).resolve().parent))
import keyhole_geometry as kg
from layout import Scene

COLORS = {"gold": (0.61, 0.43, 0.12), "silver": (0.56, 0.61, 0.66)}


def add_mesh(stage, path, mesh, color=None):
    m = UsdGeom.Mesh.Define(stage, path)
    m.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(*map(float, v)) for v in mesh.vertices]))
    m.CreateFaceVertexCountsAttr(Vt.IntArray([3] * len(mesh.faces)))
    m.CreateFaceVertexIndicesAttr(Vt.IntArray([int(i) for i in mesh.faces.ravel()]))
    m.CreateSubdivisionSchemeAttr("none")
    lo, hi = mesh.bounds
    m.CreateExtentAttr(Vt.Vec3fArray([Gf.Vec3f(*map(float, lo)), Gf.Vec3f(*map(float, hi))]))
    if color is not None:
        m.CreateDisplayColorAttr(Vt.Vec3fArray([Gf.Vec3f(*color)]))
    return m


def write_plate(folder, name, plate):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"keyhole_{name}.usd"
    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    root = UsdGeom.Xform.Define(stage, f"/keyhole_{name}")
    stage.SetDefaultPrim(root.GetPrim())
    UsdPhysics.RigidBodyAPI.Apply(root.GetPrim())
    UsdPhysics.MassAPI.Apply(root.GetPrim())
    vis = plate.visual_part()
    add_mesh(stage, f"/keyhole_{name}/visual", vis, COLORS[name])
    UsdGeom.Xform.Define(stage, f"/keyhole_{name}/collisions")
    for i, cell in enumerate(plate.cells_part()):
        hull = trimesh.convex.convex_hull(cell.vertices)
        m = add_mesh(stage, f"/keyhole_{name}/collisions/cell_{i:03d}", hull)
        m.CreatePurposeAttr(UsdGeom.Tokens.guide)
        UsdPhysics.CollisionAPI.Apply(m.GetPrim())
        mc = UsdPhysics.MeshCollisionAPI.Apply(m.GetPrim())
        mc.CreateApproximationAttr(UsdPhysics.Tokens.convexHull)
    stage.GetRootLayer().Save()
    ext = vis.bounds[1] - vis.bounds[0]
    (folder / "asset_size.json").write_text(json.dumps({"size": {"x": float(ext[0]), "y": float(ext[1]),
                                                                  "z": float(ext[2])}}, indent=1))
    return path


def main(tier, out):
    out = Path(out) / tier
    sc = Scene(tier)
    for n in kg.NAMES:
        write_plate(out / f"keyhole_{n}", n, sc.plates[n])
    lay = sc.to_json()
    lay["vertices_part_m"] = {f"keyhole_{n}": np.asarray(sc.part_vertices(n)).round(7).tolist() for n in kg.NAMES}
    lay["T_part_plate"] = {f"keyhole_{n}": sc.T_part_plate[n].tolist() for n in kg.NAMES}
    lay["source"] = {"record": f"records/{tier}.json (verbatim copy of topogym variations/cast_keyhole)",
                     "generator": "topogym/assets/geometry/cast_keyhole.py (ported in tools/keyhole_geometry.py)"}
    (out / "layout.json").write_text(json.dumps(lay))
    print("wrote", out, {k: v["pos"] for k, v in lay["parts"].items()})


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
