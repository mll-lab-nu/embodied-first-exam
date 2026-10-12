import os, sys, argparse
from isaaclab.app import AppLauncher
ap = argparse.ArgumentParser(); AppLauncher.add_app_launcher_args(ap); args = ap.parse_args(); args.headless = True
app = AppLauncher(args).app
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bw_runner import make_env
env = make_env("very_easy"); env.reset()
v = env.scene["right_arm"].root_physx_view
print("arm contact offsets", np.round(v.get_contact_offsets().numpy(), 4).reshape(-1)[:40])
print("arm rest offsets", np.round(v.get_rest_offsets().numpy(), 4).reshape(-1)[:40])
w = env.scene["wand"].root_physx_view
print("wand contact", np.round(w.get_contact_offsets().numpy(), 4).reshape(-1)[:5], "rest", np.round(w.get_rest_offsets().numpy(), 4).reshape(-1)[:5])
env.close(); app.close()
