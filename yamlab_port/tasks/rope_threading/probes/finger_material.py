import sys
from pxr import Usd, UsdPhysics, UsdShade
st = Usd.Stage.Open(sys.argv[1])
seen = set()
for p in st.Traverse():
    if p.HasAPI(UsdPhysics.CollisionAPI) and ("finger" in str(p.GetPath()) or "tip" in str(p.GetPath())):
        b = UsdShade.MaterialBindingAPI(p)
        m, rel = b.ComputeBoundMaterial("physics")
        mp = m.GetPrim() if m else None
        key = str(mp.GetPath()) if mp else None
        info = None
        if mp and mp.HasAPI(UsdPhysics.MaterialAPI):
            ma = UsdPhysics.MaterialAPI(mp)
            info = (ma.GetStaticFrictionAttr().Get(), ma.GetDynamicFrictionAttr().Get(), ma.GetRestitutionAttr().Get(),
                    mp.GetAttribute("physxMaterial:frictionCombineMode").Get())
        print(p.GetPath(), "->", key, info)
