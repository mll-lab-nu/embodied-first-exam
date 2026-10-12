"""Build the YAMLab assets of one fiber_bundling tier from the old RoboTangle STL package.

Run with the Isaac venv python (needs pxr):  python build_assets.py --tier very_easy --out ../assets

Inputs (old package, table frame, mm): cable_*_centerline(s).csv, layout.json, *.stl.
Outputs in <out>/<tier>/:
  cable.usda      fixed-base articulation: root link `terminal` (terminal box colliders + lead_00,
                  welded as in the old MJCF), lead_01..lead_NN, trunk_00..05, fiber_SS_KK; every
                  bend is a free 3-DoF ball joint (D6 with translations locked) with the old
                  viscous damping and armature, zero stiffness; gravity disabled (old gravcomp 1).
  fixtures.usda   static colliders + visuals: ring (64 capsules, exact radii), cradle, ring mount.
  layout_world.json  transform, ring frame, link list, strand/trunk dimensions for env + oracle.

Re-layout: p_world = Rz(yaw) @ p_table_mm / 1000 + t, yaw = +90 deg (old +x, terminal -> ring, becomes
world +y; old +y becomes world -x). Geometry is unchanged (rigid transform of the whole scene).
"""
import argparse, csv, json, math, struct
from pathlib import Path

import numpy as np
from pxr import Usd, UsdGeom, UsdPhysics, Gf, Sdf, Vt


def physx(prim, schema, attrs):
    """Apply a PhysX API schema by name and author its attributes (the PhysX schema python module is Kit-only)."""
    prim.AddAppliedSchema(schema)
    for name, (typ, val) in attrs.items():
        prim.CreateAttribute(name, typ).Set(val)
VT = Sdf.ValueTypeNames

OLD = Path(__import__("os").environ.get("FB_OLD_PKG", str(Path(__file__).resolve().parents[3] / "robotangle_v1_stl" / "fiber_bundling")))
TABLE_Z = 0.7517

# --- old layout constants (topogym/assets/geometry/fiber_bundling.py @ 2dafa5f) ---
TRUNK_RADIUS = 0.012
TRUNK_SEG = 0.04
FIBER_RADIUS = 0.0012
FIBER_SEG = 0.008
FIBER_ROOT_INSET = 2.5 * FIBER_RADIUS
RING_INNER = 0.0135
RING_TUBE = 0.004
RING_SEGMENTS = 64
DENSITY = 1100.0
FIBER_DAMPING_OLD = 2e-5  # N m s / rad (old MJCF joint damping)
# PhysX: with the old 2e-5 the strands drift ~30 mm (in the trunk frame) while the friction grasp holds the
# jacket (out/lift_d0 vs lift_d2e3), and with 2e-3 combed strands still creep apart (easier: 9 -> 18 mm while
# re-centring/holding, run ea3); 2e-2 keeps them combed (ea4). Zero stiffness as before. Override with --fiber_damping.
FIBER_DAMPING = 2e-2
TRUNK_DAMPING = 0.02
FIBER_ARMATURE = 1e-8     # kg m^2 (old MJCF armature)
TRUNK_ARMATURE = 1e-6
AXIS_HEIGHT = 0.24
# terminal colliders in the old working-trunk frame (AnchoredLayout.terminal_parts, collision=True)
H = AXIS_HEIGHT
TERMINAL_PARTS = [
    ("terminal_case", "box", [-.44, -.16, -H/2+.016], [.21, .18, H+.016]),
    ("terminal_gland", "cylinder", [-.338, -.16, 0., -.298, -.16, 0.], [.018]),
] + [(f"terminal_foot_{i}{j}", "box", [x, y, -H+.004], [.045, .035, .008])
     for i, x in enumerate((-.515, -.365)) for j, y in enumerate((-.222, -.098))] + [
    (f"terminal_handle_{i}", "box", [x, -.16, .032], [.015, .028, .045]) for i, x in enumerate((-.49, -.39))
] + [("terminal_handle_top", "box", [-.44, -.16, .055], [.115, .028, .014])]

COLORS = [(.62, .045, .035), (.045, .23, .58), (.08, .34, .12), (.25, .10, .045),
          (.82, .81, .74), (.83, .60, .045), (.035, .038, .043), (.36, .39, .42)]
JACKET = (.026, .029, .032)
COPPER = (.86, .60, .20)


def read_csv(path):
    rows = [r for r in csv.reader(open(path)) if r and not r[0].startswith("#")]
    head, body = rows[0], rows[1:]
    return head, np.array([[float(v) for v in r] for r in body])


def read_stl(path):
    data = Path(path).read_bytes()
    n = struct.unpack("<I", data[80:84])[0]
    if 84 + 50 * n == len(data):
        arr = np.frombuffer(data[84:], dtype=np.dtype([("n", "<3f4"), ("v", "<9f4"), ("a", "<u2")]), count=n)
        tri = arr["v"].reshape(-1, 3, 3).astype(float)
    else:  # ascii
        v = [list(map(float, l.split()[1:4])) for l in data.decode().splitlines() if l.strip().startswith("vertex")]
        tri = np.array(v).reshape(-1, 3, 3)
    return tri


def quat_to_mat(q):  # wxyz
    q = np.asarray(q, float)/np.linalg.norm(q)
    w, x, y, z = q
    return np.array([[1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)],
                     [2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)],
                     [2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)]])


def mat_to_quat(R):
    tr = np.trace(R)
    if tr > 0:
        s = math.sqrt(tr+1.0)*2; w = .25*s; x = (R[2, 1]-R[1, 2])/s; y = (R[0, 2]-R[2, 0])/s; z = (R[1, 0]-R[0, 1])/s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = math.sqrt(1+R[0, 0]-R[1, 1]-R[2, 2])*2; w = (R[2, 1]-R[1, 2])/s; x = .25*s; y = (R[0, 1]+R[1, 0])/s; z = (R[0, 2]+R[2, 0])/s
    elif R[1, 1] > R[2, 2]:
        s = math.sqrt(1+R[1, 1]-R[0, 0]-R[2, 2])*2; w = (R[0, 2]-R[2, 0])/s; x = (R[0, 1]+R[1, 0])/s; y = .25*s; z = (R[1, 2]+R[2, 1])/s
    else:
        s = math.sqrt(1+R[2, 2]-R[0, 0]-R[1, 1])*2; w = (R[1, 0]-R[0, 1])/s; x = (R[0, 2]+R[2, 0])/s; y = (R[1, 2]+R[2, 1])/s; z = .25*s
    q = np.array([w, x, y, z]); return q/np.linalg.norm(q)


def frame(direction):
    """Old topogym `frame`: x along the segment, y = up x x, z = x x y."""
    x = direction/np.linalg.norm(direction)
    y = np.cross([0., 0., 1.], x); y /= np.linalg.norm(y)
    return np.column_stack((x, y, np.cross(x, y)))


class Layout:
    """Old table frame (mm) -> YAMLab world (m)."""
    def __init__(self, yaw_deg, t):
        self.yaw = math.radians(yaw_deg)
        c, s = math.cos(self.yaw), math.sin(self.yaw)
        self.R = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.]])
        self.t = np.asarray(t, float)

    def p(self, mm):
        return (np.asarray(mm, float)/1000.) @ self.R.T + self.t

    def rot(self, R_table):
        return self.R @ R_table


def xform(prim, pos, R=None, scale=None):
    x = UsdGeom.Xformable(prim)
    x.ClearXformOpOrder()
    x.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(*map(float, pos)))
    if R is not None:
        q = mat_to_quat(R)
        x.AddOrientOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Quatd(float(q[0]), Gf.Vec3d(*map(float, q[1:]))))
    if scale is not None:
        x.AddScaleOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(*map(float, scale)))


def collider(prim, contact_offset, rest_offset=0.0):
    UsdPhysics.CollisionAPI.Apply(prim)
    physx(prim, "PhysxCollisionAPI", {"physxCollision:contactOffset": (VT.Float, float(contact_offset)),
                                      "physxCollision:restOffset": (VT.Float, float(rest_offset))})


def color(prim, rgb):
    UsdGeom.Gprim(prim).CreateDisplayColorAttr(Vt.Vec3fArray([Gf.Vec3f(*rgb)]))


def capsule(stage, path, a, b, radius, rgb=None, coll=None, guide=False):
    """Capsule whose segment runs from a to b (in the parent frame)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = b-a; L = float(np.linalg.norm(d))
    cap = UsdGeom.Capsule.Define(stage, path)
    cap.CreateAxisAttr("X"); cap.CreateHeightAttr(L); cap.CreateRadiusAttr(float(radius))
    xform(cap.GetPrim(), (a+b)/2, frame(d) if abs(d[2]) < .999*L or L == 0 else None)
    if rgb: color(cap.GetPrim(), rgb)
    if coll is not None: collider(cap.GetPrim(), coll)
    if guide: cap.CreatePurposeAttr("guide")
    return cap


def prism_mesh(stage, path, a, b, radius, sides=64, rgb=None, coll=None):
    """Convex cylinder (regular prism, vertices on the true radius) from a to b."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    F = frame(b-a); L = float(np.linalg.norm(b-a))
    ang = 2*np.pi*np.arange(sides)/sides
    ring = np.c_[np.zeros(sides), radius*np.cos(ang), radius*np.sin(ang)]
    pts = np.vstack([ring, ring+[L, 0, 0]])
    faces, counts = [], []
    for i in range(sides):
        j = (i+1) % sides
        faces += [i, j, sides+j, sides+i]; counts.append(4)
    faces += list(range(sides))[::-1]; counts.append(sides)
    faces += list(range(sides, 2*sides)); counts.append(sides)
    m = UsdGeom.Mesh.Define(stage, path)
    m.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(*map(float, p)) for p in pts]))
    m.CreateFaceVertexIndicesAttr(Vt.IntArray(faces)); m.CreateFaceVertexCountsAttr(Vt.IntArray(counts))
    xform(m.GetPrim(), a, F)
    if rgb: color(m.GetPrim(), rgb)
    if coll is not None:
        collider(m.GetPrim(), coll)
        UsdPhysics.MeshCollisionAPI.Apply(m.GetPrim()).CreateApproximationAttr("convexHull")
        physx(m.GetPrim(), "PhysxConvexHullCollisionAPI", {"physxConvexHullCollision:hullVertexLimit": (VT.Int, 2*sides)})
    return m


def box(stage, path, center, size, R=None, rgb=None, coll=None, guide=False):
    c = UsdGeom.Cube.Define(stage, path)
    c.CreateSizeAttr(1.0)
    xform(c.GetPrim(), center, R, size)
    if rgb: color(c.GetPrim(), rgb)
    if coll is not None: collider(c.GetPrim(), coll)
    if guide: c.CreatePurposeAttr("guide")
    return c


def stl_visual(stage, path, stl, pos_world, R_world, rgb):
    tri = read_stl(stl)/1000.
    pts = tri.reshape(-1, 3)
    m = UsdGeom.Mesh.Define(stage, path)
    m.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(*map(float, p)) for p in pts]))
    m.CreateFaceVertexIndicesAttr(Vt.IntArray(list(range(len(pts)))))
    m.CreateFaceVertexCountsAttr(Vt.IntArray([3]*len(tri)))
    m.CreateSubdivisionSchemeAttr("none")
    xform(m.GetPrim(), pos_world, R_world)
    color(m.GetPrim(), rgb)
    return m


def build(tier, out_dir, yaw_deg, t, contact_offset):
    src = OLD/tier
    lay = Layout(yaw_deg, t)
    layout_json = json.load(open(src/"layout.json"))
    parts = {p["name"]: p for p in layout_json["parts"]}
    npm = layout_json["non_printable"][0]
    _, lead = read_csv(src/"cable_lead_start_centerline.csv")
    _, trunk = read_csv(src/"cable_trunk_start_centerline.csv")
    _, fib = read_csv(src/"cable_fibers_start_centerlines.csv")
    nf = int(fib[:, 0].max())+1
    fibers = [fib[fib[:, 0] == i, 1:] for i in range(nf)]
    assert nf == npm["fiber_count"], (nf, npm)
    trunk_origin_mm = trunk[0]  # working-trunk frame origin in the table frame
    W = lambda mm: lay.p(mm)
    out = Path(out_dir)/tier
    out.mkdir(parents=True, exist_ok=True)

    # ---------------- cable articulation ----------------
    st = Usd.Stage.CreateNew(str(out/"cable.usda"))
    UsdGeom.SetStageUpAxis(st, UsdGeom.Tokens.z); UsdGeom.SetStageMetersPerUnit(st, 1.0)
    root = UsdGeom.Xform.Define(st, "/cable")
    st.SetDefaultPrim(root.GetPrim())
    UsdPhysics.ArticulationRootAPI.Apply(root.GetPrim())
    physx(root.GetPrim(), "PhysxArticulationAPI", {"physxArticulation:enabledSelfCollisions": (VT.Bool, True),
          "physxArticulation:solverPositionIterationCount": (VT.Int, 16), "physxArticulation:solverVelocityIterationCount": (VT.Int, 1)})
    UsdGeom.Scope.Define(st, "/cable/joints")

    links = {}  # name -> (origin world, R world, length, kind)

    def add_link(name, origin, R):
        p = UsdGeom.Xform.Define(st, f"/cable/{name}").GetPrim()
        xform(p, origin, R)
        UsdPhysics.RigidBodyAPI.Apply(p)
        physx(p, "PhysxRigidBodyAPI", {"physxRigidBody:disableGravity": (VT.Bool, True),
              "physxRigidBody:linearDamping": (VT.Float, 0.0), "physxRigidBody:angularDamping": (VT.Float, 0.0),
              "physxRigidBody:maxDepenetrationVelocity": (VT.Float, 0.1)})
        UsdPhysics.MassAPI.Apply(p).CreateDensityAttr(DENSITY)
        return p

    def to_local(name_or_none, pts):
        o, R = links[name_or_none][:2]
        return (np.asarray(pts, float)-o) @ R

    def ball(name, parent, child, damping, armature):
        j = UsdPhysics.Joint.Define(st, f"/cable/joints/{name}")
        j.CreateBody0Rel().SetTargets([f"/cable/{parent}"]); j.CreateBody1Rel().SetTargets([f"/cable/{child}"])
        po, pR = links[parent][:2]; co, cR = links[child][:2]
        lp0 = (co-po) @ pR; lr0 = mat_to_quat(pR.T @ cR)
        j.CreateLocalPos0Attr(Gf.Vec3f(*map(float, lp0)))
        j.CreateLocalRot0Attr(Gf.Quatf(float(lr0[0]), Gf.Vec3f(*map(float, lr0[1:]))))
        j.CreateLocalPos1Attr(Gf.Vec3f(0, 0, 0)); j.CreateLocalRot1Attr(Gf.Quatf(1, Gf.Vec3f(0, 0, 0)))
        prim = j.GetPrim()
        for ax in ("transX", "transY", "transZ"):
            lim = UsdPhysics.LimitAPI.Apply(prim, ax); lim.CreateLowAttr(1.0); lim.CreateHighAttr(-1.0)
        for ax in ("rotX", "rotY", "rotZ"):
            d = UsdPhysics.DriveAPI.Apply(prim, ax)
            d.CreateTypeAttr("force"); d.CreateStiffnessAttr(0.0)
            d.CreateDampingAttr(float(damping)*math.pi/180.)  # USD angular drive units are per degree
            d.CreateTargetPositionAttr(0.0); d.CreateTargetVelocityAttr(0.0)
        physx(prim, "PhysxJointAPI", {"physxJoint:armature": (VT.Float, float(armature)),
              "physxJoint:maxJointVelocity": (VT.Float, 1e4)})
        return j

    # root link: terminal box colliders + lead_00 (welded in the old MJCF: no joint on lead_00)
    lead_w = W(lead)
    a, b = lead_w[0], lead_w[1]
    R0 = frame(b-a)
    term = add_link("terminal", a, R0)
    links["terminal"] = (a, R0, float(np.linalg.norm(b-a)), "terminal")
    capsule(st, "/cable/terminal/lead_00_jacket", [0, 0, 0], [np.linalg.norm(b-a), 0, 0], TRUNK_RADIUS, JACKET, contact_offset)
    for name, kind, pos, size in TERMINAL_PARTS:
        if kind == "box":
            c = W(trunk_origin_mm+np.array(pos)*1000.)
            box(st, f"/cable/terminal/{name}", to_local("terminal", c), size, R0.T @ lay.R, None, contact_offset, guide=True)
        else:
            pa_, pb_ = W(trunk_origin_mm+np.array(pos[:3])*1000.), W(trunk_origin_mm+np.array(pos[3:])*1000.)
            m = prism_mesh(st, f"/cable/terminal/{name}", to_local("terminal", pa_), to_local("terminal", pb_), size[0], 32, None, contact_offset)
            m.CreatePurposeAttr("guide")
    p = parts["cable_terminal_box"]["pose"]["table"]
    vis = stl_visual(st, "/cable/terminal/visual_box", src/"cable_terminal_box.stl",
                     to_local("terminal", W(p["position_mm"])), R0.T @ lay.rot(quat_to_mat(p["quaternion_wxyz"])), (.075, .16, .18))
    fixed = UsdPhysics.FixedJoint.Define(st, "/cable/joints/root_fixed")
    fixed.CreateBody1Rel().SetTargets(["/cable/terminal"])
    fixed.CreateLocalPos0Attr(Gf.Vec3f(*map(float, a))); q = mat_to_quat(R0)
    fixed.CreateLocalRot0Attr(Gf.Quatf(float(q[0]), Gf.Vec3f(*map(float, q[1:]))))
    fixed.CreateLocalPos1Attr(Gf.Vec3f(0, 0, 0)); fixed.CreateLocalRot1Attr(Gf.Quatf(1, Gf.Vec3f(0, 0, 0)))

    chain = []  # ordered link names along the cable
    prev = "terminal"
    for i in range(1, len(lead_w)-1):
        a, b = lead_w[i], lead_w[i+1]
        name = f"lead_{i:02d}"; R = frame(b-a); L = float(np.linalg.norm(b-a))
        add_link(name, a, R); links[name] = (a, R, L, "lead")
        capsule(st, f"/cable/{name}/jacket", [0, 0, 0], [L, 0, 0], TRUNK_RADIUS, JACKET, contact_offset)
        ball(f"{name}_bend", prev, name, TRUNK_DAMPING, TRUNK_ARMATURE)
        chain.append(name); prev = name
    trunk_w = W(trunk)
    nt = len(trunk_w)-1
    for i in range(nt):
        a, b = trunk_w[i], trunk_w[i+1]
        name = f"trunk_{i:02d}"; R = frame(b-a); L = float(np.linalg.norm(b-a))
        add_link(name, a, R); links[name] = (a, R, L, "trunk")
        if i < nt-1:
            capsule(st, f"/cable/{name}/jacket", [0, 0, 0], [L, 0, 0], TRUNK_RADIUS, JACKET, contact_offset)
        else:  # flat front face: sphere at the joint + 64-gon cylinder (old: cylinder + sphere geoms)
            s = UsdGeom.Sphere.Define(st, f"/cable/{name}/joint_cover"); s.CreateRadiusAttr(TRUNK_RADIUS)
            color(s.GetPrim(), JACKET); collider(s.GetPrim(), contact_offset)
            prism_mesh(st, f"/cable/{name}/jacket", [0, 0, 0], [L, 0, 0], TRUNK_RADIUS, 64, JACKET, contact_offset)
        ball(f"{name}_bend", prev, name, TRUNK_DAMPING, TRUNK_ARMATURE)
        chain.append(name); prev = name
    last_trunk = prev
    fiber_names = []
    for k, pts_mm in enumerate(fibers):
        pw = W(pts_mm)
        parent = last_trunk; names = []
        for j in range(len(pw)-1):
            a, b = pw[j], pw[j+1]
            name = f"fiber_{k:02d}_{j:02d}"; R = frame(b-a); L = float(np.linalg.norm(b-a))
            add_link(name, a, R); links[name] = (a, R, L, "fiber")
            inset = FIBER_ROOT_INSET if j == 0 else 0.
            capsule(st, f"/cable/{name}/strand", [inset, 0, 0], [L, 0, 0], FIBER_RADIUS,
                    COPPER if j == len(pw)-2 else COLORS[k % len(COLORS)], contact_offset)
            ball(f"{name}_bend", parent, name, FIBER_DAMPING, FIBER_ARMATURE)
            names.append(name); parent = name
        fiber_names.append(names)
    st.GetRootLayer().Save()

    # ---------------- static fixtures ----------------
    fs = Usd.Stage.CreateNew(str(out/"fixtures.usda"))
    UsdGeom.SetStageUpAxis(fs, UsdGeom.Tokens.z); UsdGeom.SetStageMetersPerUnit(fs, 1.0)
    froot = UsdGeom.Xform.Define(fs, "/fixtures"); fs.SetDefaultPrim(froot.GetPrim())
    rp = parts["bundling_ring"]["pose"]["table"]
    ring_c = W(rp["position_mm"]); ring_R = lay.rot(quat_to_mat(rp["quaternion_wxyz"]))
    ring_n = ring_R[:, 2]
    UsdGeom.Xform.Define(fs, "/fixtures/ring")
    Rr = RING_INNER+RING_TUBE
    ang = 2*np.pi*np.arange(RING_SEGMENTS)/RING_SEGMENTS
    loc = np.c_[Rr*np.cos(ang), Rr*np.sin(ang), np.zeros_like(ang)]
    vw = loc @ ring_R.T + ring_c
    for i in range(RING_SEGMENTS):
        capsule(fs, f"/fixtures/ring/seg_{i:02d}", vw[i], vw[(i+1) % RING_SEGMENTS], RING_TUBE, None, contact_offset, guide=True)
    stl_visual(fs, "/fixtures/ring/visual", src/"bundling_ring.stl", ring_c, ring_R, COPPER)
    for name, rgb in [("cable_cradle_base", (.14, .19, .23)), ("cable_cradle_post", (.39, .44, .47)),
                      ("cable_cradle_pad", (.09, .10, .11)), ("cable_cradle_left", (.27, .33, .37)),
                      ("cable_cradle_right", (.27, .33, .37)), ("ring_mount_base", (.13, .19, .25)),
                      ("ring_mount_post", (.38, .43, .49))]:
        pp = parts[name]["pose"]["table"]
        tri = read_stl(src/f"{name}.stl")/1000.
        size = tri.reshape(-1, 3).max(0)-tri.reshape(-1, 3).min(0)
        Rw = lay.rot(quat_to_mat(pp["quaternion_wxyz"]))
        box(fs, f"/fixtures/{name}", W(pp["position_mm"]), size, Rw, rgb, 0.002)
    fs.GetRootLayer().Save()

    aperture = Rr*math.cos(math.pi/RING_SEGMENTS)-RING_TUBE
    trunk_front = links[last_trunk][0]+links[last_trunk][1][:, 0]*links[last_trunk][2]
    info = dict(
        tier=tier, source=str(src), units="SI metres", table_z=TABLE_Z,
        transform=dict(description="p_world = Rz(yaw) @ (p_table_mm / 1000) + t", yaw_deg=yaw_deg, t=list(map(float, t)),
                       R=lay.R.tolist()),
        ring=dict(center=ring_c.tolist(), normal=ring_n.tolist(), R=ring_R.tolist(), centerline_radius=Rr, tube_radius=RING_TUBE,
                  inner_radius=RING_INNER, segments=RING_SEGMENTS, min_aperture_radius=aperture,
                  trunk_radial_clearance=aperture-TRUNK_RADIUS),
        trunk=dict(names=[n for n in chain if n.startswith("trunk")], radius=TRUNK_RADIUS, segment=TRUNK_SEG,
                   front_world=trunk_front.tolist()),
        lead=dict(names=["terminal"]+[n for n in chain if n.startswith("lead")]),
        fibers=dict(names=fiber_names, radius=FIBER_RADIUS, segment=FIBER_SEG, count=nf,
                    tips_world=[W(f)[-1].tolist() for f in fibers]),
        links={n: dict(origin=v[0].tolist(), R=v[1].tolist(), length=v[2], kind=v[3]) for n, v in links.items()},
        contact_offset=contact_offset, rest_offset=0.0,
        damping=dict(fiber=FIBER_DAMPING, fiber_old=FIBER_DAMPING_OLD, trunk_lead=TRUNK_DAMPING), armature=dict(fiber=FIBER_ARMATURE, trunk_lead=TRUNK_ARMATURE),
        gravity="disabled on all cable links (old model: gravity compensation 1.0)",
        old_start_clearances_mm=dict(fiber_min_initial_surface_clearance=13.60, trunk_radial_clearance=1.48),
    )
    json.dump(info, open(out/"layout_world.json", "w"), indent=1)
    print(json.dumps(dict(ring=info["ring"], trunk_front=info["trunk"]["front_world"], tips=info["fibers"]["tips_world"],
                          nlinks=len(links)), indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", default="very_easy")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent/"assets"))
    ap.add_argument("--yaw", type=float, default=90.0)
    ap.add_argument("--tx", type=float, default=0.25)
    ap.add_argument("--ty", type=float, default=0.0)
    ap.add_argument("--contact_offset", type=float, default=0.0005)
    ap.add_argument("--fiber_damping", type=float, default=FIBER_DAMPING)
    a = ap.parse_args()
    FIBER_DAMPING = a.fiber_damping
    build(a.tier, a.out, a.yaw, (a.tx, a.ty, TABLE_Z), a.contact_offset)
