"""Four fixed views of a measured rope-only MuJoCo trajectory.

This renderer does not add robot arms or turn a planning probe into a task
success. The source trajectory and its validation retain that responsibility.
"""
import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path

import imageio.v2 as imageio
import mujoco
import numpy as np


CAMERAS = {
    "overview": dict(lookat=[.10, 0., .15], distance=.92, azimuth=115., elevation=-30.),
    "front": dict(lookat=[.035, 0., .16], distance=.79, azimuth=90., elevation=-12.),
    "side": dict(lookat=[.035, 0., .16], distance=.81, azimuth=155., elevation=-23.),
    "top": dict(lookat=[.10, 0., .12], distance=.90, azimuth=90., elevation=-89.),
}


def render(folder, *, stride=2):
    folder = Path(folder)
    if stride < 1:
        raise ValueError("stride must be positive")
    path = folder / "probe_trajectory.npz"
    with np.load(path) as saved:
        time = saved["time_s"]
        qpos = saved["qpos"]
    intervals = np.diff(time)
    if len(time) < 2 or not np.allclose(intervals, np.median(intervals), atol=1e-7):
        raise ValueError("Rendering requires uniformly sampled measured states")
    indices = np.arange(0, len(time), stride)
    fps = 1. / (np.median(intervals) * stride)
    model = mujoco.MjModel.from_xml_path(str(folder / "model.xml"))
    data = mujoco.MjData(model)
    if qpos.shape[1] != model.nq:
        raise ValueError("Trajectory and model do not match")
    model.vis.global_.offwidth = 1280
    model.vis.global_.offheight = 720
    options = mujoco.MjvOption()
    options.sitegroup[:] = 0
    output = folder / "rope_views"
    output.mkdir(exist_ok=True)
    report = dict(scope="measured_rope_only_replay_no_robot", source=str(path.resolve()),
                  source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                  model_sha256=hashlib.sha256((folder / "model.xml").read_bytes()).hexdigest(),
                  simulation_start_s=float(time[0]), simulation_end_s=float(time[-1]),
                  frames=len(indices), fps=float(fps), cameras=CAMERAS,
                  task_success_claimed=False)
    with ExitStack() as stack:
        renderer = stack.enter_context(mujoco.Renderer(model, height=720, width=1280))
        writers = {name: stack.enter_context(imageio.get_writer(
            output / f"{name}.mp4", fps=fps, codec="libx264", quality=8,
            macro_block_size=1)) for name in CAMERAS}
        cameras = {}
        for name, settings in CAMERAS.items():
            camera = mujoco.MjvCamera()
            camera.lookat[:] = settings["lookat"]
            for key in ("distance", "azimuth", "elevation"):
                setattr(camera, key, settings[key])
            cameras[name] = camera
        for frame, index in enumerate(indices):
            data.qpos[:] = qpos[index]
            mujoco.mj_forward(model, data)
            for name, camera in cameras.items():
                renderer.update_scene(data, camera=camera, scene_option=options)
                rgb = renderer.render()
                writers[name].append_data(rgb)
                if frame in (0, len(indices) - 1):
                    imageio.imwrite(output / f"{name}_{frame}.png", rgb)
    report["videos"] = {
        name: dict(path=str((output / f"{name}.mp4").resolve()),
                   sha256=hashlib.sha256((output / f"{name}.mp4").read_bytes()).hexdigest())
        for name in CAMERAS}
    (output / "render_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(output, flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--stride", type=int, default=2)
    args = parser.parse_args()
    render(args.folder, stride=args.stride)
