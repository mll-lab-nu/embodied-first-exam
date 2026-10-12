import sys
import numpy as np
from pxr import Usd, UsdGeom, UsdPhysics
st = Usd.Stage.Open(sys.argv[1])
xc = UsdGeom.XformCache()
for p in st.Traverse():
    if p.HasAPI(UsdPhysics.CollisionAPI):
        M = np.array(xc.GetLocalToWorldTransform(p)).T
        info = p.GetTypeName()
        ext = None
        if p.IsA(UsdGeom.Mesh):
            v = np.array(UsdGeom.Mesh(p).GetPointsAttr().Get(), float)
            w = (M[:3, :3] @ v.T).T + M[:3, 3]
            ext = (np.round(w.min(0), 4).tolist(), np.round(w.max(0), 4).tolist())
        elif p.IsA(UsdGeom.Cube):
            s = UsdGeom.Cube(p).GetSizeAttr().Get()
            c = np.array([[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]) * s / 2
            w = (M[:3, :3] @ c.T).T + M[:3, 3]
            ext = (np.round(w.min(0), 4).tolist(), np.round(w.max(0), 4).tolist())
        print(p.GetPath(), info, ext, "approx", p.GetAttribute("physics:approximation").Get() if p.HasAttribute("physics:approximation") else None)
