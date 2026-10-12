"""Scene probe in the full YAMLab task env: loads, resets, nop steps (rope stability with robots),
arm/finger frames, and a reach test of the TCP (gripper down) over key rope points."""
import argparse, json, os, sys, time
from isaaclab.app import AppLauncher
p = argparse.ArgumentParser()
p.add_argument("--task", default="KnotUntying-VeryEasy-v0")
p.add_argument("--nop_steps", type=int, default=90)
p.add_argument("--reach", action="store_true")
AppLauncher.add_app_launcher_args(p)
args = p.parse_args(); args.headless = True
app = AppLauncher(args).app
import numpy as np, torch
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yamlab
print("YAMLAB_FROM", yamlab.__file__)
from yamlab.utils.task_creation import create_task_environment
from oracle_lib import Arm, OPEN
from yamlab.envs.tasks.knot_untying_lib import rope_geom as G

env = create_task_environment(task_name=args.task, assets_instance_paths={}, mode="evaluation",
                              observation_modalities=["proprioception"], num_envs=1, device="cpu", strip_cameras=True)
t = time.time(); env.reset(); print("RESET_s", time.time() - t)
L, R = Arm(env, "left_arm"), Arm(env, "right_arm")
print("ARM_BODIES", L.bn); print("ARM_JOINTS", list(L.art.joint_names))
print("CAL_L", L.calibrate()); print("CAL_R", R.calibrate())
for a in (L, R):
    p6, R6 = a.body_pose(a.l6); tcp, _ = a.tcp()
    print("HOME", a.name, "link6", p6.round(4).tolist(), "tcp", tcp.round(4).tolist(), "q", a.q().round(3).tolist())
act = torch.zeros(1, 14); act[0, 6] = OPEN; act[0, 13] = OPEN
t = time.time()
for k in range(args.nop_steps):
    obs, r, term, trunc, info = env.step(act)
    if k % 15 == 14:
        g = info["goal"][0]
        print("NOP", k + 1, json.dumps({kk: g[kk] for kk in ("planar_clear", "on_table", "quiet", "intact", "n_crossings", "over_under",
              "maximum_speed_m_s", "z_min_surface_above_table_m", "z_max_surface_above_table_m", "minimum_nonlocal_distance_m")}),
              "term", bool(term[0]), "succ", bool(info["success"][0]))
print("CTRL_STEPS_PER_S", args.nop_steps / (time.time() - t))
if args.reach:
    pos, quat, lv, av = env.rope_state(0)
    joints, _ = G.chain_points_from_links(pos, quat, env.link_length)
    cr = G.crossings_fast(joints)
    targets = {"start_end": joints[0], "end_end": joints[-1], "crossing": np.r_[cr[0]["xy"], joints[:, 2].min()] if cr else joints[50],
               "loop_far": joints[np.argmax(joints[:, 0])], "far_left": np.array([0.45, 0.30, 0.754]), "far_right": np.array([0.45, -0.30, 0.754]),
               "near_center": np.array([0.36, 0.0, 0.754])}
    for arm in (L, R):
        for name, tgt in targets.items():
            env.reset()
            pd = np.array(tgt, float).copy(); pd[2] = 0.754 + 0.002   # TCP at rope-centre height
            Rd = arm.down_rotation(np.pi / 2)
            res = None
            for k in range(150):
                hover = pd + np.array([0, 0, 0.08 * max(0.0, 1 - k / 80)])
                qt, ep, er = arm.ik_step(hover, Rd)
                a = act.clone(); sl = slice(0, 6) if arm.name == "left_arm" else slice(7, 13)
                a[0, sl] = torch.tensor(qt, dtype=torch.float32)
                # hold the other arm at its current pose
                env.step(a)
                res = (ep, er)
            print("REACH", arm.name, name, np.round(pd, 3).tolist(), "pos_err_mm %.1f rot_err_deg %.1f" % (res[0] * 1000, np.degrees(res[1])),
                  "q", arm.q().round(2).tolist())
sys.stdout.flush(); os._exit(0)  # Kit shutdown can hang
