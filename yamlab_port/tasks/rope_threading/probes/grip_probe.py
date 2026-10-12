"""Grip robustness of the fingertip pinch on the stiff rope (RopeThreading-Easy scene, left arm).
Pinch-pick the rope `--from_tip` from the end tip (top-down, fingertips 2 mm above the table), lift, then rotate
about the grip point: phase yaw (+90 deg about vertical), phase pitch (approach from down to +x pitched 45 deg).
Logs the held station offset in the TCP frame and the finger joint after each phase.
Usage: vrun.sh 1200 grip_probe.py --out runs/gp1 --grip_close -0.0015 --ang_speed 0.4"""
import argparse, json, os, sys
from isaaclab.app import AppLauncher
p = argparse.ArgumentParser()
p.add_argument("--out", default="gp")
p.add_argument("--grip_close", type=float, default=-0.0015)
p.add_argument("--ang_speed", type=float, default=0.4)
p.add_argument("--from_tip", type=float, default=0.15)
p.add_argument("--order", default="yaw,roll")
p.add_argument("--lift_z", type=float, default=0.95)
AppLauncher.add_app_launcher_args(p)
args = p.parse_args(); args.headless = True
app = AppLauncher(args).app
import numpy as np
from scipy.spatial.transform import Rotation as Rot
sys.path.insert(0, "/workspace/yamlab_port/runs/rope_threading/task/tools")
from rt_common import Runner, make_env, OPEN, SL
from plan_np import frame, frame_az, EX, EY, EZ, polyline_station

env = make_env("RopeThreading-Easy-v0")
R = Runner(env, args.out)
R.hold(5)
R.goto("left", frame((0.7071, 0, -0.7071), (0, 1, 0), (0.40, 0.30, 0.95)), 45)
pt, t = polyline_station(R.centerline(), args.from_tip)
t[2] = 0; t /= np.linalg.norm(t)
Tg = frame_az(-EZ, -t); Tg[:3, 3] = pt + 0.035 * EZ
Tpre = Tg.copy(); Tpre[:3, 3] += 0.08 * EZ
R.goto("left", Tpre, 60); R.move("left", Tg, speed=0.04); R.hold(5)
R.set_grip("left", args.grip_close, 15); R.hold(20)


def held():
    T = R.tcp("left")
    P = R.centerline()
    pt, _ = polyline_station(P, args.from_tip)
    loc = T[:3, :3].T @ (pt - T[:3, 3])
    d = np.linalg.norm(P - T[:3, 3] - T[:3, 0] * loc[0], axis=1)
    return loc, R.finger("left")


res = {"pinch": held()}
T = R.tcp("left", R.cur[0, SL["left"]].numpy().astype(float)); T[:3, 3][2] = args.lift_z
R.move("left", T, speed=0.04); R.hold(20)
res["lift"] = held()
gp = R.tcp("left")[:3, :3] @ res["lift"][0] + R.tcp("left")[:3, 3]


def rotate_about_grip(Rw):
    T0 = R.tcp("left", R.cur[0, SL["left"]].numpy().astype(float))
    off = res["lift"][0]
    T1 = np.eye(4); T1[:3, :3] = Rw @ T0[:3, :3]
    T1[:3, 3] = gp - T1[:3, :3] @ off
    R.move("left", T1, speed=0.04, ang_speed=args.ang_speed)
    R.hold(30)


for ph in args.order.split(","):
    try:
        if ph == "yaw":
            rotate_about_grip(Rot.from_rotvec([0, 0, np.pi / 2]).as_matrix())
        elif ph == "roll":
            # rotate about the rope axis (z_tcp) until the approach is +x pitched 45 deg down (or as close as possible)
            T0 = R.tcp("left", R.cur[0, SL["left"]].numpy().astype(float))
            ax = T0[:3, 2]
            a_t = np.array([0.7071, 0, -0.7071]); a_t = a_t - ax * (ax @ a_t); a_t /= np.linalg.norm(a_t)
            ang = np.arctan2(np.cross(T0[:3, 0], a_t) @ ax, T0[:3, 0] @ a_t)
            rotate_about_grip(Rot.from_rotvec(ax * ang).as_matrix())
    except RuntimeError as e:
        res[ph + "_error"] = str(e)[:200]
        break
    res[ph] = held()
out = {k: (dict(offset=np.round(v[0], 4).tolist(), finger=round(v[1], 5)) if isinstance(v, tuple) else v) for k, v in res.items()}
out["approach_final"] = np.round(R.tcp("left")[:3, 0], 3).tolist()
print("GRIP_PROBE", json.dumps(dict(args=vars(args), **out)))
R.save()
sys.stdout.flush(); os._exit(0)
