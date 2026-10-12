import sys
from pxr import Usd, UsdGeom, UsdPhysics
st = Usd.Stage.Open(sys.argv[1])
cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "proxy", "render", "guide"])
for p in st.Traverse():
    if p.HasAPI(UsdPhysics.CollisionAPI):
        b = cache.ComputeWorldBound(p).ComputeAlignedRange()
        print(p.GetPath(), [round(v, 3) for v in b.GetMin()], [round(v, 3) for v in b.GetMax()])
