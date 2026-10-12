# Dump the YAM arm USD: prims, xforms, joints (axis, limits, frames), collision geoms.
import sys
from pxr import Usd, UsdGeom, UsdPhysics, Gf
st = Usd.Stage.Open(sys.argv[1])
print("upAxis", UsdGeom.GetStageUpAxis(st), "mpu", UsdGeom.GetStageMetersPerUnit(st))
for p in st.Traverse():
    t = p.GetTypeName()
    line = f"{p.GetPath()} [{t}]"
    apis = [a for a in p.GetAppliedSchemas()]
    if apis: line += " apis=" + ",".join(apis)
    if p.IsA(UsdGeom.Xformable):
        x = UsdGeom.Xformable(p)
        ops = x.GetOrderedXformOps()
        if ops:
            line += " ops=" + "; ".join(f"{o.GetOpName()}={o.Get()}" for o in ops)
    if p.IsA(UsdPhysics.Joint):
        j = UsdPhysics.Joint(p)
        line += f" b0={j.GetBody0Rel().GetTargets()} b1={j.GetBody1Rel().GetTargets()} lp0={j.GetLocalPos0Attr().Get()} lr0={j.GetLocalRot0Attr().Get()} lp1={j.GetLocalPos1Attr().Get()} lr1={j.GetLocalRot1Attr().Get()}"
        for a in ("physics:axis", "physics:lowerLimit", "physics:upperLimit"):
            at = p.GetAttribute(a)
            if at and at.Get() is not None: line += f" {a}={at.Get()}"
    if t in ("Cube", "Sphere", "Capsule", "Cylinder"):
        for a in ("size", "radius", "height", "axis"):
            at = p.GetAttribute(a)
            if at and at.Get() is not None: line += f" {a}={at.Get()}"
    if t == "Mesh":
        pts = UsdGeom.Mesh(p).GetPointsAttr().Get()
        if pts is not None:
            import numpy as np
            a = np.array(pts); line += f" npts={len(a)} min={a.min(0).round(4).tolist()} max={a.max(0).round(4).tolist()}"
    m = p.GetAttribute("physics:mass")
    if m and m.Get() is not None: line += f" mass={m.Get()}"
    print(line)
