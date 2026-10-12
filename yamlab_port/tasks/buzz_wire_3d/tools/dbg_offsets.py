import os, sys, argparse
from isaaclab.app import AppLauncher
ap = argparse.ArgumentParser(); AppLauncher.add_app_launcher_args(ap); args = ap.parse_args(); args.headless = True
app = AppLauncher(args).app
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bw_runner import make_env
env = make_env("very_easy"); env.reset()
import omni.usd
from pxr import Usd, UsdPhysics, PhysxSchema
st = omni.usd.get_context().get_stage()
seen = 0
for p in Usd.PrimRange(st.GetPrimAtPath("/World/envs/env_0")):
    if p.HasAPI(UsdPhysics.CollisionAPI):
        path = str(p.GetPath())
        if any(k in path for k in ("link_6", "left_finger", "rail/collisions/seg_000", "wand/collisions/ring_00", "deck/collisions/box_1", "link_4")):
            c = PhysxSchema.PhysxCollisionAPI(p)
            approx = p.GetAttribute("physics:approximation").Get() if p.HasAPI(UsdPhysics.MeshCollisionAPI) else None
            print(path, "contactOffset", c.GetContactOffsetAttr().Get(), "restOffset", c.GetRestOffsetAttr().Get(), "approx", approx)
            seen += 1
            if seen > 14:
                break
env.close(); app.close()
