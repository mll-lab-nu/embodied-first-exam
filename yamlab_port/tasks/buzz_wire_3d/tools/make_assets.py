"""Build the buzz-wire USD assets (plain pxr, no Isaac app needed).

Per tier writes <out>/<tier>/{wand,rail,stops,deck}.usda:
  wand  : dynamic rigid body, frame at the loop centre (old URDF link frame). Colliders = the old
          collision model 1:1 (64 ring capsules r 1.26 mm on R 15.4 mm, stem capsule, grip box
          30.52 x 9.8 x 7 mm); mass/inertia from the old densities (grip 650, metal 7800 kg/m3);
          visual = wand.stl.
  rail  : one rigid body (made kinematic by the task cfg) of capsules r 1.47 mm between consecutive
          centreline points of buzz_wire_centerline.csv (old table frame, metres); visual = the
          reference tube STL.
  stops : the two 8 x 8 x 12 mm wood end blocks (separate body: they are wood, not wire).
  deck  : top plate + rim + four 45 mm feet as boxes (from wire_base.stl), visual = wire_base.stl.
Fixed parts are authored in the old table frame (m); the task places each asset with the re-layout
transform (pos = translation, rot = yaw). PhysX-specific settings (contact offsets, kinematic flag,
contact reporting) are applied by the Isaac Lab spawn cfg in the task.
"""
import json
import os
import sys
import numpy as np
import trimesh
from pxr import Usd, UsdGeom, UsdPhysics, UsdShade, Gf, Sdf, Vt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bw_geom import (OLD_GRIP_LEN, OLD_GRIP_HALF_W, OLD_GRIP_HALF_T, STL_ROOT, LOOP_R, TUBE_R, LOOP_SEGMENTS, STEM_LEN, GRIP_LEN, GRIP_HALF_W, GRIP_HALF_T,
                     WIRE_R, GRIP_X0, GRIP_XC, STL_ORIGIN_IN_BODY, RHO_WOOD, RHO_METAL, DECK_CENTER_OLD,
                     DECK_BOXES_LOCAL_MM, STOP_HALF_MM, load_rail_old_mm, stop_centers_old_mm, wand_capsules)

FRICTION = dict(wood=0.8, metal=0.3, deck=0.5)


def new_stage(path, root):
    if os.path.exists(path):
        os.remove(path)
    st = Usd.Stage.CreateNew(path)
    UsdGeom.SetStageUpAxis(st, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(st, 1.0)
    UsdPhysics.SetStageKilogramsPerUnit(st, 1.0)
    prim = UsdGeom.Xform.Define(st, root).GetPrim()
    st.SetDefaultPrim(prim)
    return st, prim


def material(st, path, mu, color=None):
    mat = UsdShade.Material.Define(st, path)
    api = UsdPhysics.MaterialAPI.Apply(mat.GetPrim())
    api.CreateStaticFrictionAttr(mu)
    api.CreateDynamicFrictionAttr(mu)
    api.CreateRestitutionAttr(0.0)
    return mat


def bind_phys(prim, mat):
    UsdShade.MaterialBindingAPI.Apply(prim).Bind(mat, UsdShade.Tokens.weakerThanDescendants, "physics")


def xform(prim, t, q_wxyz=(1, 0, 0, 0), s=None):
    x = UsdGeom.Xformable(prim)
    x.ClearXformOpOrder()
    x.AddTranslateOp().Set(Gf.Vec3d(*map(float, t)))
    x.AddOrientOp().Set(Gf.Quatf(float(q_wxyz[0]), Gf.Vec3f(*map(float, q_wxyz[1:]))))
    if s is not None:
        x.AddScaleOp().Set(Gf.Vec3f(*map(float, s)))


def quat_z_to(v):
    """Quaternion (wxyz) rotating +z onto unit vector v."""
    v = v / np.linalg.norm(v)
    z = np.array([0.0, 0.0, 1.0])
    c = float(np.dot(z, v))
    if c < -0.999999:
        return (0.0, 1.0, 0.0, 0.0)
    a = np.cross(z, v)
    w = 1.0 + c
    q = np.array([w, *a])
    return tuple(q / np.linalg.norm(q))


def capsule(st, path, a, b, r, mat=None):
    a, b = np.asarray(a, float), np.asarray(b, float)
    L = float(np.linalg.norm(b - a))
    g = UsdGeom.Capsule.Define(st, path)
    g.CreateAxisAttr("Z")
    g.CreateRadiusAttr(float(r))
    g.CreateHeightAttr(max(L, 1e-6))
    xform(g.GetPrim(), (a + b) / 2, quat_z_to(b - a) if L > 1e-9 else (1, 0, 0, 0))
    UsdPhysics.CollisionAPI.Apply(g.GetPrim())
    UsdGeom.Imageable(g.GetPrim()).CreatePurposeAttr("guide")  # collider only; visuals are meshes
    if mat is not None:
        bind_phys(g.GetPrim(), mat)
    return g


def box(st, path, centre, half, mat=None, visible=False):
    g = UsdGeom.Cube.Define(st, path)
    g.CreateSizeAttr(1.0)
    xform(g.GetPrim(), centre, (1, 0, 0, 0), 2 * np.asarray(half, float))
    UsdPhysics.CollisionAPI.Apply(g.GetPrim())
    if not visible:
        UsdGeom.Imageable(g.GetPrim()).CreatePurposeAttr("guide")
    if mat is not None:
        bind_phys(g.GetPrim(), mat)
    return g


def mesh_from_stl(st, path, stl, scale=1e-3, offset=(0, 0, 0), color=(0.7, 0.7, 0.7)):
    m = trimesh.load(stl)
    g = UsdGeom.Mesh.Define(st, path)
    pts = m.vertices * scale + np.asarray(offset)
    g.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(*p) for p in pts.astype(float)]))
    g.CreateFaceVertexCountsAttr(Vt.IntArray([3] * len(m.faces)))
    g.CreateFaceVertexIndicesAttr(Vt.IntArray(m.faces.reshape(-1).astype(int).tolist()))
    g.CreateSubdivisionSchemeAttr("none")
    g.CreateDisplayColorAttr(Vt.Vec3fArray([Gf.Vec3f(*color)]))
    return g


def wand_mass():
    """Old generator: mass/inertia from capsule meshes (metal 7800) + exact grip box (wood 650)."""
    mass, first, I0 = 0.0, np.zeros(3), np.zeros((3, 3))
    parts = [(a, b, r) for a, b, r, _ in wand_capsules()]
    for a, b, r in parts:
        L = np.linalg.norm(b - a)
        m = trimesh.creation.capsule(height=L, radius=r, count=[16, 16])
        T = np.eye(4)
        from scipy.spatial.transform import Rotation
        q = quat_z_to(b - a)
        T[:3, :3] = Rotation.from_quat([q[1], q[2], q[3], q[0]]).as_matrix()
        T[:3, 3] = (a + b) / 2
        m.apply_transform(T)
        m.density = RHO_METAL
        mass += m.mass
        first += m.mass * m.center_mass
        I0 += m.moment_inertia + m.mass * ((m.center_mass @ m.center_mass) * np.eye(3) - np.outer(m.center_mass, m.center_mass))
    g = trimesh.creation.box((GRIP_LEN, 2 * GRIP_HALF_W, 2 * GRIP_HALF_T))
    g.apply_translation([GRIP_XC, 0, 0])
    g.density = RHO_WOOD
    mass += g.mass
    first += g.mass * g.center_mass
    I0 += g.moment_inertia + g.mass * ((g.center_mass @ g.center_mass) * np.eye(3) - np.outer(g.center_mass, g.center_mass))
    com = first / mass
    I = I0 - mass * ((com @ com) * np.eye(3) - np.outer(com, com))
    return mass, com, I


def build_wand(out, tier):
    st, root = new_stage(os.path.join(out, "wand.usda"), "/wand")
    UsdPhysics.RigidBodyAPI.Apply(root)
    mass, com, I = wand_mass()
    w, V = np.linalg.eigh(I)
    if np.linalg.det(V) < 0:
        V[:, 0] *= -1
    from scipy.spatial.transform import Rotation
    qx = Rotation.from_matrix(V).as_quat()
    mapi = UsdPhysics.MassAPI.Apply(root)
    mapi.CreateMassAttr(float(mass))
    mapi.CreateCenterOfMassAttr(Gf.Vec3f(*com.astype(float)))
    mapi.CreateDiagonalInertiaAttr(Gf.Vec3f(*w.astype(float)))
    mapi.CreatePrincipalAxesAttr(Gf.Quatf(float(qx[3]), Gf.Vec3f(*qx[:3].astype(float))))
    metal = material(st, "/wand/Looks/metal", FRICTION["metal"])
    wood = material(st, "/wand/Looks/wood", FRICTION["wood"])
    UsdGeom.Scope.Define(st, "/wand/collisions")
    for i, (a, b, r, role) in enumerate(wand_capsules()):
        name = f"ring_{i:02d}" if role == "loop" else "stem"
        capsule(st, f"/wand/collisions/{name}", a, b, r, metal)
    box(st, "/wand/collisions/grip", (GRIP_XC, 0, 0), (GRIP_LEN / 2, GRIP_HALF_W, GRIP_HALF_T), wood)
    # visual = the port's tool (old loop + stem, enlarged grip; the old wand.stl has the old grip)
    tor = trimesh.creation.torus(major_radius=LOOP_R, minor_radius=TUBE_R, major_sections=96, minor_sections=16)
    stem = trimesh.creation.cylinder(radius=TUBE_R, segment=[[LOOP_R, 0, 0], [GRIP_X0, 0, 0]], sections=16)
    metal_vis = trimesh.util.concatenate([tor, stem])
    grip_vis = trimesh.creation.box((GRIP_LEN, 2 * GRIP_HALF_W, 2 * GRIP_HALF_T))
    grip_vis.apply_translation([GRIP_XC, 0, 0])
    for name, m, col in (("visual_metal", metal_vis, (0.85, 0.62, 0.22)), ("visual_grip", grip_vis, (0.55, 0.36, 0.2))):
        tmp = os.path.join(out, f"_{name}.stl")
        m.export(tmp)
        mesh_from_stl(st, f"/wand/{name}", tmp, scale=1.0, color=col)
        os.remove(tmp)
    st.GetRootLayer().Save()
    return dict(mass_kg=float(mass), com_m=com.tolist(), inertia_kg_m2=I.tolist())


def build_rail(out, tier):
    st, root = new_stage(os.path.join(out, "rail.usda"), "/rail")
    UsdPhysics.RigidBodyAPI.Apply(root)
    metal = material(st, "/rail/Looks/metal", FRICTION["metal"])
    rail = load_rail_old_mm(tier) / 1000.0
    UsdGeom.Scope.Define(st, "/rail/collisions")
    for i in range(len(rail) - 1):
        capsule(st, f"/rail/collisions/seg_{i:03d}", rail[i], rail[i + 1], WIRE_R, metal)
    d = json.load(open(os.path.join(STL_ROOT, tier, "layout.json")))
    tube = [p for p in d["parts"] if p["name"] == "wire_rail_REFERENCE_tube"][0]
    mesh_from_stl(st, "/rail/visual", os.path.join(STL_ROOT, tier, "wire_rail_REFERENCE_tube.stl"),
                  offset=np.array(tube["pose"]["table"]["position_mm"]) / 1000.0, color=(0.72, 0.33, 0.16))
    st.GetRootLayer().Save()
    return dict(segments=len(rail) - 1, length_m=float(np.linalg.norm(np.diff(rail, axis=0), axis=1).sum()))


def build_stops(out, tier):
    st, root = new_stage(os.path.join(out, "stops.usda"), "/stops")
    UsdPhysics.RigidBodyAPI.Apply(root)
    wood = material(st, "/stops/Looks/wood", FRICTION["deck"])
    for i, c in enumerate(stop_centers_old_mm(tier)):
        box(st, f"/stops/block_{i}", c / 1000.0, np.array(STOP_HALF_MM) / 1000.0, wood, visible=True)
    st.GetRootLayer().Save()


def build_deck(out, tier):
    st, root = new_stage(os.path.join(out, "deck.usda"), "/deck")
    UsdPhysics.RigidBodyAPI.Apply(root)
    wood = material(st, "/deck/Looks/wood", FRICTION["deck"])
    UsdGeom.Scope.Define(st, "/deck/collisions")
    for i, (c, h) in enumerate(DECK_BOXES_LOCAL_MM):
        box(st, f"/deck/collisions/box_{i}", (DECK_CENTER_OLD + np.array(c)) / 1000.0, np.array(h) / 1000.0, wood)
    mesh_from_stl(st, "/deck/visual", os.path.join(STL_ROOT, tier, "wire_base.stl"),
                  offset=DECK_CENTER_OLD / 1000.0, color=(0.78, 0.62, 0.42))
    st.GetRootLayer().Save()


def write_geometry(out, tier):
    """Task-side geometry in the OLD table frame (metres); the task applies the re-layout."""
    from bw_geom import start_pose_old, finish_pose_old, DECK_TOP_OLD_MM, APERTURE
    rail = load_rail_old_mm(tier) / 1000.0
    sp, sR = start_pose_old(tier)
    fp, fR = finish_pose_old(tier)
    q = lambda R: R.as_quat()[[3, 0, 1, 2]].tolist()
    json.dump(dict(tier=tier, frame="old table frame, metres; wand frame = loop centre",
                   rail_m=rail.tolist(), start_p=sp.tolist(), start_q_wxyz=q(sR),
                   finish_p=fp.tolist(), finish_q_wxyz=q(fR), deck_top_m=DECK_TOP_OLD_MM / 1000.0,
                   aperture_m=APERTURE, loop_radius_m=LOOP_R, tube_radius_m=TUBE_R, wire_radius_m=WIRE_R,
                   stem_end_m=GRIP_X0, grip_center_m=GRIP_XC, grip_size_m=[GRIP_LEN, 2 * GRIP_HALF_W, 2 * GRIP_HALF_T],
                   old_grip_size_m=[OLD_GRIP_LEN, 2 * OLD_GRIP_HALF_W, 2 * OLD_GRIP_HALF_T],
                   note="start/finish = old endpoint_pose formula (deck rest) with the port's grip; start yaw deviation applied in the task cfg"),
              open(os.path.join(out, "geometry.json"), "w"))


if __name__ == "__main__":
    out_root = sys.argv[1]
    tiers = sys.argv[2:] or ["very_easy", "easier"]
    report = {}
    for t in tiers:
        out = os.path.join(out_root, t)
        os.makedirs(out, exist_ok=True)
        report[t] = dict(wand=build_wand(out, t), rail=build_rail(out, t))
        build_stops(out, t)
        build_deck(out, t)
        write_geometry(out, t)
    json.dump(report, open(os.path.join(out_root, "assets_report.json"), "w"), indent=1)
    print(json.dumps(report, indent=1))
