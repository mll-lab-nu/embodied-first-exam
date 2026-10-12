"""Author the capsule-chain rope as one PhysX articulation in a USD file (needs pxr, i.e. a running Kit app).

Layout of the asset (all link poses authored in the asset frame = YAMLab env frame):
  /Rope                      Xform, PhysicsArticulationRootAPI (+ PhysxArticulationAPI)
  /Rope/link_000 ...         Xform + RigidBodyAPI + MassAPI, child capsule collider (axis X)
  /Rope/joints/j_000 ...     SphericalJoint link_i -> link_i+1 at the shared end point
  /Rope/Looks/rope_phys      physics material (rope friction)
Joint frames coincide when the two links are collinear and untwisted (rest shape = straight),
so the knotted start pose carries non-zero joint coordinates.
"""
from __future__ import annotations

import numpy as np


def write_rope_usd(path, centres, quats, d, radius, mass_per_link, *, friction=0.3,
                   contact_offset=0.002, rest_offset=0.0, linear_damping=0.0, angular_damping=0.0,
                   max_depenetration_velocity=0.5, pos_iters=32, vel_iters=4, sleep_threshold=0.0, color=(0.95, 0.45, 0.1),
                   capsule_height=None, joint_type="d6"):
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, UsdShade, PhysxSchema

    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    root = UsdGeom.Xform.Define(stage, "/Rope")
    stage.SetDefaultPrim(root.GetPrim())
    UsdPhysics.ArticulationRootAPI.Apply(root.GetPrim())
    art = PhysxSchema.PhysxArticulationAPI.Apply(root.GetPrim())
    art.CreateEnabledSelfCollisionsAttr(True)
    art.CreateSolverPositionIterationCountAttr(int(pos_iters))
    art.CreateSolverVelocityIterationCountAttr(int(vel_iters))
    art.CreateSleepThresholdAttr(float(sleep_threshold))
    art.CreateStabilizationThresholdAttr(0.0)

    mat = UsdShade.Material.Define(stage, "/Rope/Looks/rope_phys")
    mapi = UsdPhysics.MaterialAPI.Apply(mat.GetPrim())
    mapi.CreateStaticFrictionAttr(float(friction))
    mapi.CreateDynamicFrictionAttr(float(friction))
    mapi.CreateRestitutionAttr(0.0)
    pm = PhysxSchema.PhysxMaterialAPI.Apply(mat.GetPrim())
    pm.CreateFrictionCombineModeAttr("average")
    pm.CreateRestitutionCombineModeAttr("average")

    h = d if capsule_height is None else capsule_height
    n = len(centres)
    for i in range(n):
        lp = f"/Rope/link_{i:03d}"
        x = UsdGeom.Xform.Define(stage, lp)
        x.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(*map(float, centres[i])))
        w, qx, qy, qz = map(float, quats[i])
        x.AddOrientOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Quatd(w, qx, qy, qz))
        prim = x.GetPrim()
        UsdPhysics.RigidBodyAPI.Apply(prim)
        rb = PhysxSchema.PhysxRigidBodyAPI.Apply(prim)
        rb.CreateLinearDampingAttr(float(linear_damping))
        rb.CreateAngularDampingAttr(float(angular_damping))
        rb.CreateMaxDepenetrationVelocityAttr(float(max_depenetration_velocity))
        rb.CreateSleepThresholdAttr(0.0)
        rb.CreateStabilizationThresholdAttr(0.0)
        UsdPhysics.MassAPI.Apply(prim).CreateMassAttr(float(mass_per_link))
        cap = UsdGeom.Capsule.Define(stage, lp + "/collision")
        cap.CreateAxisAttr("X")
        cap.CreateRadiusAttr(float(radius))
        cap.CreateHeightAttr(float(h))
        cap.CreateDisplayColorAttr([Gf.Vec3f(*color)])
        UsdPhysics.CollisionAPI.Apply(cap.GetPrim())
        pc = PhysxSchema.PhysxCollisionAPI.Apply(cap.GetPrim())
        pc.CreateContactOffsetAttr(float(contact_offset))
        pc.CreateRestOffsetAttr(float(rest_offset))
        UsdShade.MaterialBindingAPI.Apply(cap.GetPrim()).Bind(
            mat, UsdShade.Tokens.weakerThanDescendants, "physics")

    UsdGeom.Scope.Define(stage, "/Rope/joints")
    for i in range(n - 1):
        if joint_type == "spherical":
            j = UsdPhysics.SphericalJoint.Define(stage, f"/Rope/joints/j_{i:03d}")
            j.CreateAxisAttr("X")
        else:
            # generic D6: translations locked (low > high), rotations free, one drive per rot axis.
            # (A UsdPhysics.SphericalJoint in an articulation gets NO active drives: probes/probe_drives.py.)
            j = UsdPhysics.Joint.Define(stage, f"/Rope/joints/j_{i:03d}")
            for ax in ("transX", "transY", "transZ"):
                lim = UsdPhysics.LimitAPI.Apply(j.GetPrim(), ax)
                lim.CreateLowAttr(1.0)
                lim.CreateHighAttr(-1.0)
        j.CreateBody0Rel().SetTargets([Sdf.Path(f"/Rope/link_{i:03d}")])
        j.CreateBody1Rel().SetTargets([Sdf.Path(f"/Rope/link_{i + 1:03d}")])
        j.CreateLocalPos0Attr(Gf.Vec3f(0.5 * d, 0.0, 0.0))
        j.CreateLocalPos1Attr(Gf.Vec3f(-0.5 * d, 0.0, 0.0))
        j.CreateLocalRot0Attr(Gf.Quatf(1.0, 0.0, 0.0, 0.0))
        j.CreateLocalRot1Attr(Gf.Quatf(1.0, 0.0, 0.0, 0.0))
        jp = j.GetPrim()
        for ax in ("rotX", "rotY", "rotZ"):
            drv = UsdPhysics.DriveAPI.Apply(jp, ax)
            drv.CreateTypeAttr("force")
            drv.CreateTargetPositionAttr(0.0)
            drv.CreateStiffnessAttr(0.0)
            drv.CreateDampingAttr(0.0)
    stage.GetRootLayer().Save()
    return str(path)
