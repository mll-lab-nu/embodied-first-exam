"""Faithful videos of a YAMLab oracle run by state playback (generic over task families).

Why: enabling cameras perturbs PhysX (a camera replay diverges from the no-camera run at the
first rich contact), so re-simulating with cameras does not show the real trajectory.

Two passes:
  dump   (no cameras, reference stack, e.g. on vast): step the saved actions from the same reset
         and save the full scene state (InteractiveScene.get_state) every step, plus the task's
         success flag. Cameras are stripped from the scene cfg.
  render (cameras, RTX host, e.g. ws with venv_vast): reset, then for every --frame_every-th
         dumped state: scene.reset_to(state) -> sim.forward() -> sim.render() -> read cameras.
         Physics is never stepped. It writes PNGs + MP4 per camera and a consistency check: the
         body poses read back after reset_to vs the dumped poses.

usage:
  PYTHONPATH=<yamlab copy> python render_states.py dump   --task T --actions A.npy --out D [--device cpu]
  PYTHONPATH=<yamlab copy> python render_states.py render --task T --states D/states_full.npz --out V --enable_cameras
"""
import argparse, json, os, sys, time
from isaaclab.app import AppLauncher

p = argparse.ArgumentParser()
p.add_argument("mode", choices=["dump", "render"])
p.add_argument("--task", required=True)
p.add_argument("--actions")
p.add_argument("--states")
p.add_argument("--out", required=True)
p.add_argument("--frame_every", type=int, default=2)
p.add_argument("--cameras", default="top,left_wrist,right_wrist")
p.add_argument("--width", type=int, default=640)
p.add_argument("--height", type=int, default=480)
p.add_argument("--fps", type=int, default=15)
p.add_argument("--closeup", action="append", default=[], metavar="NAME=ex,ey,ez:tx,ty,tz[:fov_deg]",
               help="render: add a render-only world camera looking from eye to target (world m); repeatable")
p.add_argument("--grasp_clamp", action="store_true", help="enable_gripper_grasp_clamp=True (as the family's oracle used)")
p.add_argument("--task_kwargs", action="store_true", help="pass yamlab.configs.get_task_kwargs(task, 'evaluation')")
p.add_argument("--assets_call", default=None, metavar="module:function:arg",
               help="assets_instance_paths = module.function(arg) (e.g. cast_keyhole asset_paths)")
p.add_argument("--no_patch", action="store_true", help="dump: rely on the task's own YAMLAB_STRIP_CAMERAS instead of the generic scene patch")
AppLauncher.add_app_launcher_args(p)
args = p.parse_args(); args.headless = True
if not any(a.startswith('--device') for a in sys.argv):
    args.device = 'cpu'   # reference runs are CPU PhysX; AppLauncher would default to cuda:0
if args.mode == "render":
    args.enable_cameras = True
app = AppLauncher(args).app

import numpy as np, torch
import yamlab.envs.yam_bimanual_scene as ys
if args.mode == "dump":
    os.environ["YAMLAB_STRIP_CAMERAS"] = "1"
if args.mode == "dump" and not args.no_patch:
    _orig = ys.YamBimanualSceneCfg.__post_init__
    def _no_cams(self):
        _orig(self)
        for n in list(vars(self)):
            if n.endswith("_camera"):
                setattr(self, n, None)
    ys.YamBimanualSceneCfg.__post_init__ = _no_cams
if args.mode == "render" and args.closeup:
    import isaaclab.sim as sim_utils
    from isaaclab.sensors.camera import TiledCameraCfg

    def _look_at_quat(eye, target):
        # Isaac Lab "world" camera convention: forward +X, up +Z
        f = np.asarray(target, float) - np.asarray(eye, float); f /= np.linalg.norm(f)
        left = np.cross([0.0, 0.0, 1.0], f)
        if np.linalg.norm(left) < 1e-6:
            left = np.array([0.0, 1.0, 0.0])
        left /= np.linalg.norm(left); up = np.cross(f, left)
        from scipy.spatial.transform import Rotation
        x, y, z, w = Rotation.from_matrix(np.stack([f, left, up], axis=1)).as_quat()
        return (float(w), float(x), float(y), float(z))

    _specs = []
    for spec in args.closeup:
        name, rest = spec.split("=")
        parts = rest.split(":")
        eye = [float(v) for v in parts[0].split(",")]; tgt = [float(v) for v in parts[1].split(",")]
        fov = float(parts[2]) if len(parts) > 2 else 40.0
        _specs.append((name, eye, tgt, fov))
    _orig_r = ys.YamBimanualSceneCfg.__post_init__
    def _with_closeups(self):
        _orig_r(self)
        for name, eye, tgt, fov in _specs:
            focal = 24.0; aperture = 2 * focal * np.tan(np.radians(fov) / 2)
            setattr(self, f"{name}_camera", TiledCameraCfg(
                prim_path=f"{{ENV_REGEX_NS}}/RenderOnly_{name}", update_period=0.0,
                height=args.height, width=args.width, data_types=["rgb"],
                spawn=sim_utils.PinholeCameraCfg(focal_length=focal, horizontal_aperture=float(aperture),
                                                 clipping_range=(0.01, 20.0)),
                offset=TiledCameraCfg.OffsetCfg(pos=tuple(eye), rot=_look_at_quat(eye, tgt), convention="world")))
    ys.YamBimanualSceneCfg.__post_init__ = _with_closeups
    args.cameras = ",".join([args.cameras] + [n for n, *_ in _specs])
from yamlab.utils.task_creation import create_task_environment

os.makedirs(args.out, exist_ok=True)
assets = {}
if args.assets_call:
    import importlib
    _m, _f, _a = args.assets_call.split(":")
    assets = getattr(importlib.import_module(_m), _f)(_a)
kw = dict(task_name=args.task, assets_instance_paths=assets, mode="evaluation", num_envs=1, device=args.device)
if args.assets_call:
    kw["objects_randomization"] = None
if args.grasp_clamp:
    kw["enable_gripper_grasp_clamp"] = True
if args.task_kwargs:
    from yamlab.configs import get_task_kwargs
    kw.update(get_task_kwargs(args.task, "evaluation"))
else:
    kw["timeout_steps"] = 100000
if args.mode == "render":
    kw.update(observation_modalities=["rgb", "proprioception"], camera_width=args.width,
              camera_height=args.height, image_downsample_factor=1)
else:
    kw.update(observation_modalities=["proprioception"])
env = create_task_environment(**kw)
print('ENV_CREATED', flush=True)
env.reset(seed=0)
print('ENV_RESET', flush=True)
scene = env.scene


def flatten(d, prefix=""):
    out = {}
    for k, v in d.items():
        key = f"{prefix}/{k}" if prefix else k
        if isinstance(v, dict):
            out.update(flatten(v, key))
        else:
            out[key] = v.detach().cpu().numpy() if torch.is_tensor(v) else np.asarray(v)
    return out


def unflatten(flat, t):
    root = {}
    for key, arr in flat.items():
        parts = key.split("/")
        d = root
        for part in parts[:-1]:
            d = d.setdefault(part, {})
        d[parts[-1]] = torch.as_tensor(arr[t], device=env.device)
    return root


def body_poses():
    out = {}
    for name, a in scene.articulations.items():
        out[name] = a.data.body_pos_w[0].detach().cpu().numpy().copy()
    for name, o in scene.rigid_objects.items():
        out[name] = o.data.root_pos_w[0].detach().cpu().numpy().copy()
    return out


if args.mode == "dump":
    A = np.load(args.actions)
    states, poses, succ = [], [], []
    t0 = time.time()
    for k, a in enumerate(A):
        obs, r, term, trunc, info = env.step(torch.as_tensor(a, dtype=torch.float32).unsqueeze(0))
        s = info.get("success") if isinstance(info, dict) else None
        succ.append(bool(s[0]) if s is not None else False)
        if bool(term[0]) or bool(trunc[0]):
            # the env auto-resets inside this step: the scene now holds the reset state, not the
            # terminal one, so this step is not recorded (the previous frame is the last real one)
            print('DUMP_TERMINATED', k, flush=True)
            break
        states.append(flatten(scene.get_state(is_relative=False)))
        poses.append(body_poses())
        if k % 500 == 0:
            print('DUMP_PROGRESS', k, round(time.time()-t0, 1), flush=True)
    keys = states[0].keys()
    np.savez_compressed(os.path.join(args.out, "states_full.npz"),
                        **{k: np.stack([s[k] for s in states]) for k in keys})
    np.savez_compressed(os.path.join(args.out, "body_poses.npz"),
                        **{k: np.stack([p[k] for p in poses]) for k in poses[0]})
    res = dict(task=args.task, steps=len(states), success=any(succ),
               first_success_step=succ.index(True) if any(succ) else None, wall_s=time.time()-t0,
               keys=sorted(keys))
    json.dump(res, open(os.path.join(args.out, "dump_metrics.json"), "w"), indent=1)
    print("DUMP", json.dumps({k: v for k, v in res.items() if k != "keys"}))
else:
    S = dict(np.load(args.states))
    P = dict(np.load(os.path.join(os.path.dirname(args.states), "body_poses.npz")))
    n = len(next(iter(S.values())))
    cams = [c for c in args.cameras.split(",") if f"{c}_camera" in scene.keys()]
    frames = {c: [] for c in cams}
    maxerr = 0.0
    dt = env.physics_dt
    t0 = time.time()
    idx = list(range(0, n, args.frame_every))
    if idx[-1] != n - 1:
        idx.append(n - 1)
    for t in idx:
        scene.reset_to(unflatten(S, t), env_ids=None, is_relative=False)
        env.sim.forward()
        scene.update(dt)
        for name, ref in P.items():
            cur = body_poses()[name]
            maxerr = max(maxerr, float(np.abs(cur - ref[t]).max()))
        for _ in range(2):
            env.sim.render()
        for c in cams:
            cam = scene[f"{c}_camera"]
            cam.update(dt, force_recompute=True)
            frames[c].append(cam.data.output["rgb"][0].cpu().numpy()[..., :3].astype(np.uint8))
    from PIL import Image
    import imageio
    for c, imgs in frames.items():
        d = os.path.join(args.out, f"frames_{c}"); os.makedirs(d, exist_ok=True)
        for i, img in enumerate(imgs):
            if i % 10 == 0 or i == len(imgs) - 1:
                Image.fromarray(img).save(os.path.join(d, f"{i:05d}.png"))
        imageio.mimsave(os.path.join(args.out, f"{c}.mp4"), imgs, fps=args.fps)
    res = dict(task=args.task, states=args.states, frames=len(idx), max_pose_readback_err_m=maxerr,
               wall_s=time.time()-t0, cameras=cams)
    json.dump(res, open(os.path.join(args.out, "render_metrics.json"), "w"), indent=1)
    print("RENDER", json.dumps(res))
sys.stdout.flush(); os._exit(0)
