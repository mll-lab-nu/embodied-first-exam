import os, sys
from isaaclab.app import AppLauncher
import argparse
ap = argparse.ArgumentParser(); AppLauncher.add_app_launcher_args(ap); args = ap.parse_args(); args.headless = True
app = AppLauncher(args).app
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bw_runner import make_env
from bw_geom import Scene, Layout, TABLE_Z
env = make_env("very_easy"); env.reset()
import omni.usd
from pxr import UsdGeom, Usd
st = omni.usd.get_context().get_stage()
s = Scene("very_easy", Layout(-90.0, (0.96, 0.055679, TABLE_Z)))
xc = UsdGeom.XformCache(Usd.TimeCode.Default())
for i in (0, 50, 100, 150, 217):
    p = st.GetPrimAtPath(f"/World/envs/env_0/rail/collisions/seg_{i:03d}")
    M = np.array(xc.GetLocalToWorldTransform(p)).T
    print(i, "sim", M[:3, 3].round(4), "numpy", ((s.rail[i] + s.rail[i + 1]) / 2).round(4))
for name in ("deck", "stops", "rail", "wand"):
    p = st.GetPrimAtPath(f"/World/envs/env_0/{name}")
    M = np.array(xc.GetLocalToWorldTransform(p)).T
    print(name, M[:3, 3].round(4), M[:3, :3].round(3).tolist())
env.close(); app.close()
