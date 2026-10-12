"""Replay an action file up to N steps with arm contact sensors; print links in contact."""
import argparse, os, sys
from isaaclab.app import AppLauncher
ap = argparse.ArgumentParser(); ap.add_argument("--actions"); ap.add_argument("--upto", type=int); ap.add_argument("--every", type=int, default=10)
AppLauncher.add_app_launcher_args(ap); args = ap.parse_args(); args.headless = True
app = AppLauncher(args).app
import numpy as np, torch
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bw_runner import make_env
env = make_env("very_easy"); env.reset()
acts = np.load(args.actions)
for k, a in enumerate(acts[:args.upto]):
    env.step(torch.from_numpy(a).unsqueeze(0))
    if k % args.every == 0 or k >= args.upto - 3:
        for arm in ("leftarm", "rightarm"):
            sen = env.scene[f"debug_{arm}_contacts"]
            f = torch.linalg.norm(sen.data.net_forces_w[0], dim=-1).numpy()
            names = sen.body_names
            hit = [(names[i], round(float(f[i]), 2)) for i in np.flatnonzero(f > 1e-3)]
            if hit:
                print(k, arm, hit, flush=True)
        try:
            fm = torch.linalg.norm(env.scene["debug_right_link6"].data.force_matrix_w[0, 0], dim=-1).numpy()
            print(k, "right link_6 vs [rail, deck, stops, wand, workstation]:", np.round(fm, 2), flush=True)
            if fm[0] > 0:
                cp = env.scene["debug_right_link6"].data.contact_pos_w[0, 0, 0].numpy()
                arm = env.scene["right_arm"]; jn = arm.joint_names
                q = arm.data.joint_pos[0].numpy()
                qq = np.array([q[jn.index(f"joint{i+1}")] for i in range(6)])
                from ik import IK
                from grasps import ArmPoints
                from bw_geom import Scene, Layout, TABLE_Z
                ikr = IK("right"); AP = ArmPoints(ikr.arm)
                W = AP.world(qq, float(q[jn.index("left_finger")]))
                sc = Scene("very_easy", Layout(-90.0, (0.96, 0.055679, TABLE_Z)))
                dmin = {l: float(np.linalg.norm(P - cp, axis=1).min()) for l, P in W.items()}
                drail = float(np.linalg.norm(sc.rail - cp, axis=1).min())
                Ti = arm.data.body_link_pos_w[0, arm.body_names.index("link_6")].numpy()
                Tm = ikr.arm.fk_all(qq, 0)["link_6"][:3, 3]
                print("   contact point", cp.round(4), "nearest model link pts (mm):", {l: round(v * 1000, 1) for l, v in sorted(dmin.items(), key=lambda x: x[1])[:3]},
                      "rail pt dist mm", round(drail * 1000, 1), "link6 sim", Ti.round(4), "model", Tm.round(4), "jn", jn, flush=True)
        except Exception as e:
            print("fm err", e)
env.close(); app.close()
