"""Validate the USD-based YAM FK against PhysX, then map IK reachability (gripper pointing down,
fingertips 2 mm above the table) over the tabletop for both arms."""
import argparse, json, os, sys, time
from isaaclab.app import AppLauncher
p = argparse.ArgumentParser()
p.add_argument("--task", default="KnotUntying-VeryEasy-v0")
AppLauncher.add_app_launcher_args(p)
args = p.parse_args(); args.headless = True
app = AppLauncher(args).app
import numpy as np, torch
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from yamlab.utils.task_creation import create_task_environment
from isaaclab.sim.utils import get_current_stage
from oracle_lib import Arm, OPEN, YamKin

env = create_task_environment(task_name=args.task, assets_instance_paths={}, mode="evaluation",
                              observation_modalities=["proprioception"], num_envs=1, device="cpu", strip_cameras=True)
env.reset()
stage = get_current_stage()
arms = {n: Arm(env, n) for n in ("left_arm", "right_arm")}
kins = {}
for n, a in arms.items():
    a.calibrate(pad_along=0.0)
    pb, Rb = a.body_pose(0)
    prim = "/World/envs/env_0/" + ("LeftArm" if n == "left_arm" else "RightArm")
    kins[n] = YamKin(stage, prim, pb, Rb, a.tcp_l6)
    print("LIMITS", n, np.round(kins[n].lo, 2).tolist(), np.round(kins[n].hi, 2).tolist(), "tcp_l6", np.round(a.tcp_l6, 4).tolist())
    T = kins[n].fk_link6(a.q()); p6, R6 = a.body_pose(a.l6)
    print("FK_HOME_ERR", n, float(np.linalg.norm(T[:3, 3] - p6)), float(np.abs(T[:3, :3] - R6).max()))
json.dump({n: dict(kin=kins[n].to_json(), tool_l6=arms[n].tool_l6.tolist(), close_l6=arms[n].close_l6.tolist()) for n in arms},
          open("yam_kin.json", "w"))
if os.environ.get("KIN_DUMP_ONLY"):
    sys.stdout.flush(); os._exit(0)
# drive to a random-ish configuration and compare
rng = np.random.default_rng(0)
for trial in range(3):
    act = torch.zeros(1, 14); act[0, 6] = OPEN; act[0, 13] = OPEN
    qs = {}
    for n, sl in (("left_arm", slice(0, 6)), ("right_arm", slice(7, 13))):
        k = kins[n]
        q = np.clip(rng.uniform(-0.8, 0.8, 6), k.lo + 0.1, k.hi - 0.1); q[1] = abs(q[1]) + 0.5; q[2] = abs(q[2]) + 0.5
        qs[n] = q; act[0, sl] = torch.tensor(q, dtype=torch.float32)
    for _ in range(60):
        env.step(act)
    for n, a in arms.items():
        T = kins[n].fk_link6(a.q()); p6, R6 = a.body_pose(a.l6)
        print("FK_ERR", trial, n, "pos_mm %.3f" % (1000 * np.linalg.norm(T[:3, 3] - p6)), "R %.2e" % np.abs(T[:3, :3] - R6).max(),
              "track_err_rad %.3f" % np.abs(a.q() - qs[n]).max())
# reachability map
TABLE = 0.75
res = {}
for n, a in arms.items():
    k = kins[n]
    seeds = [np.array([0, 1.6, 1.4, -0.6, 0, 0.0]), np.array([0, 2.2, 1.9, -1.0, 0, 0.0]), np.array([0, 1.0, 0.8, -0.3, 0, 0])]
    rows = []
    for x in np.arange(0.32, 0.86, 0.04):
        row = ""
        for y in np.arange(-0.48, 0.49, 0.06):
            ok_any = False
            for yaw in (0.0, np.pi / 2):
                Rd = a.down_rotation(yaw)
                # rough seed: base yaw toward the target
                b = k.base[:3, 3]
                sd = [s.copy() for s in seeds]
                for s in sd: s[0] = np.arctan2(y - b[1], x - b[0])
                q, ep, er = k.ik(np.array([x, y, TABLE + 0.002]), Rd, sd[0], extra_seeds=sd[1:])
                if ep < 0.002 and er < np.radians(2):
                    ok_any = True; break
            row += "#" if ok_any else "."
        rows.append("x=%.2f %s" % (x, row))
    res[n] = rows
    print("REACHMAP", n, "y from -0.48 to 0.48 step 0.06, gripper down, tips 2 mm above table")
    for r in rows: print("  ", r)
sys.stdout.flush(); os._exit(0)
