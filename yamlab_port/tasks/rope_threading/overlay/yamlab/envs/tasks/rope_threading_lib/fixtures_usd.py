"""Author the static ring fixtures (rings, stands, bases) as one USD of static colliders (needs pxr).

Ring = exact torus approximated like the old collision mesh (64 major sections): 64 capsules of radius
= tube radius along the chords of the ring centreline circle (caps overlap their neighbours; max deviation
from the torus R (1 - cos(pi/64)) = 0.09 mm, as the old 64-section mesh). Stand = capsule r 5 mm, base =
50 x 80 x 8 mm box. No rigid-body API: PhysX treats them as static colliders.
"""
from __future__ import annotations

import numpy as np

from .threading_geom import ring_basis, stand_length, BASE_SIZE_OLD, STAND_RADIUS, rot2

COLORS = {"R1": (0.20, 0.70, 0.80), "R2": (0.35, 0.80, 0.40), "R3": (0.85, 0.35, 0.30)}
STAND_COLOR = (0.60, 0.60, 0.60)
BASE_COLOR = (0.45, 0.48, 0.50)
N_SEG = 64


def _quat_x_to(d):
    """wxyz quaternion rotating +X onto unit vector d."""
    from scipy.spatial.transform import Rotation as Rot
    d = np.asarray(d, float) / np.linalg.norm(d)
    x = np.array([1.0, 0.0, 0.0])
    v = np.cross(x, d)
    s = np.linalg.norm(v)
    if s < 1e-12:
        return (1.0, 0.0, 0.0, 0.0) if d[0] > 0 else (0.0, 0.0, 0.0, 1.0)
    q = Rot.from_rotvec(v / s * np.arctan2(s, x @ d)).as_quat()
    return (q[3], q[0], q[1], q[2])


def ring_segments(ring, n_seg=N_SEG):
    u, v = ring_basis(ring["normal"])
    th = np.arange(n_seg + 1) * 2 * np.pi / n_seg
    pts = ring["center"] + ring["radius"] * (np.cos(th)[:, None] * u + np.sin(th)[:, None] * v)
    return pts[:-1], pts[1:]


def write_fixtures_usd(path, scene, yaw_deg, *, friction=0.3, contact_offset=0.002, rest_offset=0.0):
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, UsdShade, PhysxSchema

    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    root = UsdGeom.Xform.Define(stage, "/Fixtures")
    stage.SetDefaultPrim(root.GetPrim())
    mat = UsdShade.Material.Define(stage, "/Fixtures/Looks/fixture_phys")
    mapi = UsdPhysics.MaterialAPI.Apply(mat.GetPrim())
    mapi.CreateStaticFrictionAttr(float(friction))
    mapi.CreateDynamicFrictionAttr(float(friction))
    mapi.CreateRestitutionAttr(0.0)
    pm = PhysxSchema.PhysxMaterialAPI.Apply(mat.GetPrim())
    pm.CreateFrictionCombineModeAttr("average")

    def collider(prim):
        UsdPhysics.CollisionAPI.Apply(prim)
        pc = PhysxSchema.PhysxCollisionAPI.Apply(prim)
        pc.CreateContactOffsetAttr(float(contact_offset))
        pc.CreateRestOffsetAttr(float(rest_offset))
        UsdShade.MaterialBindingAPI.Apply(prim).Bind(mat, UsdShade.Tokens.weakerThanDescendants, "physics")

    def place(xf, pos, quat):
        xf.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(*map(float, pos)))
        xf.AddOrientOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Quatd(*map(float, quat)))

    for ring in scene["rings"]:
        name = ring["name"]
        UsdGeom.Xform.Define(stage, f"/Fixtures/{name}")
        a, b = ring_segments(ring)
        for k in range(len(a)):
            cap = UsdGeom.Capsule.Define(stage, f"/Fixtures/{name}/seg_{k:02d}")
            place(cap, 0.5 * (a[k] + b[k]), _quat_x_to(b[k] - a[k]))
            cap.CreateAxisAttr("X")
            cap.CreateRadiusAttr(float(ring["tube"]))
            cap.CreateHeightAttr(float(np.linalg.norm(b[k] - a[k])))
            cap.CreateDisplayColorAttr([Gf.Vec3f(*COLORS.get(name, (0.8, 0.8, 0.2)))])
            collider(cap.GetPrim())
        sc = ring["stand_center"]
        L = stand_length(sc[2])
        st = UsdGeom.Capsule.Define(stage, f"/Fixtures/{name}_stand")
        place(st, sc, (1.0, 0.0, 0.0, 0.0))
        st.CreateAxisAttr("Z")
        st.CreateRadiusAttr(STAND_RADIUS)
        st.CreateHeightAttr(float(L - 2 * STAND_RADIUS))
        st.CreateDisplayColorAttr([Gf.Vec3f(*STAND_COLOR)])
        collider(st.GetPrim())
        bc = ring["base_center"]
        bx = UsdGeom.Cube.Define(stage, f"/Fixtures/{name}_base")
        yaw = np.radians(yaw_deg)
        place(bx, bc, (np.cos(yaw / 2), 0.0, 0.0, np.sin(yaw / 2)))
        bx.CreateSizeAttr(1.0)
        bx.AddScaleOp().Set(Gf.Vec3f(*map(float, BASE_SIZE_OLD)))
        bx.CreateDisplayColorAttr([Gf.Vec3f(*BASE_COLOR)])
        collider(bx.GetPrim())
    stage.GetRootLayer().Save()
    return str(path)
