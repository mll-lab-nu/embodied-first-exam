import os, sys, argparse
from isaaclab.app import AppLauncher
ap = argparse.ArgumentParser(); AppLauncher.add_app_launcher_args(ap); args = ap.parse_args(); args.headless = True
app = AppLauncher(args).app
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bw_runner import make_env
env = make_env("very_easy")
import omni.usd
from pxr import Usd, UsdGeom, UsdPhysics
st = omni.usd.get_context().get_stage()
xc = UsdGeom.XformCache(Usd.TimeCode.Default())
root = st.GetPrimAtPath("/World/envs/env_0/RightArm/arm/link_6")
L = np.array(xc.GetLocalToWorldTransform(root)).T
Li = np.linalg.inv(L)
for p in Usd.PrimRange(root):
    if p.HasAPI(UsdPhysics.CollisionAPI):
        M = np.array(xc.GetLocalToWorldTransform(p)).T
        pts = p.GetAttribute("points").Get() if p.GetTypeName() == "Mesh" else None
        if pts is not None:
            P = np.array(pts, float)
            W = (M[:3, :3] @ P.T).T + M[:3, 3]
            Lp = (Li[:3, :3] @ W.T).T + Li[:3, 3]
            print(p.GetPath().name, p.GetTypeName(), len(P), Lp.min(0).round(4), Lp.max(0).round(4))
        else:
            print(p.GetPath(), p.GetTypeName())
env.close(); app.close()
