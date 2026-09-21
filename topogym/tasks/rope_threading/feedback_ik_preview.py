"""Render an explicitly labelled CPU handoff preview, without a rope simulation.

Run with MUJOCO_GL=osmesa for CPU-only rendering. Outputs are development
artifacts beside the plan, not a completed physical demo in demos/.
"""
import argparse
import hashlib
import json
from pathlib import Path

import imageio.v2 as imageio
import mujoco
import numpy as np
from omegaconf import OmegaConf
from PIL import Image, ImageDraw, ImageFont
from scipy.spatial.transform import Rotation

from .feedback_ik_plan import GRASP_OFFSET, PIVOT_AXIS, smoothstep
from .reference_preflight import model_with_fixtures


def render(directory, *, fps=20):
    report = json.loads((directory/"report.json").read_text())
    if not report["sampled_kinematic_checks_passed"]:
        raise ValueError("Refusing to preview a failed plan as the selected candidate")
    snapshot = json.loads((directory/"snapshot.json").read_text())
    trajectory = np.load(directory/"handoff_trajectory.npz")
    times, qpos = trajectory["time_s"], trajectory["qpos"]
    model = model_with_fixtures(OmegaConf.load(directory/"config.yaml"))
    model.vis.global_.offwidth, model.vis.global_.offheight = 960, 540
    model.vis.headlight.active = 1
    model.vis.headlight.ambient[:] = .5
    model.vis.headlight.diffuse[:] = .8
    for i in range(model.ngeom):
        name = model.geom(i).name
        for prefix, color in [("audit_R1", [.04, .68, .73, 1.]),
                              ("audit_R2", [.16, .58, .28, 1.]),
                              ("audit_R3", [.62, .33, .78, 1.]),
                              ("audit_table", [.48, .40, .30, 1.])]:
            if name.startswith(prefix):
                model.geom_rgba[i] = color
    data = mujoco.MjData(model)
    renderer = mujoco.Renderer(model, 540, 960)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 19)
    small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
    cameras = {}
    for name, lookat, distance, azimuth, elevation in [
            ("overview", [0., .14, .30], 1.7, 40., -28.),
            ("detail", [.04, .18, .33], .72, 40., -22.)]:
        camera = mujoco.MjvCamera()
        camera.lookat[:] = lookat
        camera.distance, camera.azimuth, camera.elevation = distance, azimuth, elevation
        cameras[name] = camera
    paths = {name: directory/f"kinematic_{name}.mp4" for name in cameras}
    if any(p.exists() for p in paths.values()):
        raise FileExistsError("Preserve previous previews; choose a new plan directory")
    writers = {name: imageio.get_writer(str(path), fps=fps, codec="libx264", quality=8,
                macro_block_size=1, ffmpeg_params=["-pix_fmt", "yuv420p"])
               for name, path in paths.items()}
    frame_times = np.linspace(0., times[-1], int(round(times[-1]*fps)))
    try:
        for frame, t in enumerate(frame_times):
            data.qpos[:] = [np.interp(t, times, qpos[:, j]) for j in range(16)]
            mujoco.mj_forward(model, data)
            stage = next((s for s in report["stages"] if t <= s["end_s"]), report["stages"][-1])
            anchor = np.asarray(snapshot["anchor"])
            if t <= 3.5:
                fraction = smoothstep(np.clip((t-.5)/3., 0., 1.))
                pivot = Rotation.from_rotvec(PIVOT_AXIS*np.deg2rad(report["pivot_deg"])*fraction)
                tip = anchor+pivot.apply(np.asarray(snapshot["tip"])-anchor)
            elif t < 21.5:
                tip = np.asarray(report["tip_after_pivot_model_m"])
            else:
                body = data.body("right/gripper_link")
                tip = body.xpos+body.xmat.reshape(3, 3)@GRASP_OFFSET
            for name, camera in cameras.items():
                renderer.update_scene(data, camera=camera)
                geom = renderer.scene.geoms[renderer.scene.ngeom]
                mujoco.mjv_initGeom(geom, mujoco.mjtGeom.mjGEOM_SPHERE,
                    np.array([.005, 0., 0.]), tip, np.eye(3).ravel(), np.array([1., .2, .1, 1.]))
                renderer.scene.ngeom += 1
                image = Image.fromarray(renderer.render())
                draw = ImageDraw.Draw(image)
                draw.rectangle((0, 0, 960, 78), fill=(18, 25, 34))
                draw.text((16, 8), "KINEMATIC PLAN ONLY | No rope dynamics or grasp verification", font=font, fill="white")
                draw.text((16, 37), f"{t:05.2f} / {times[-1]:.1f} s  |  {stage['name'].replace('_', ' ')}", font=font, fill=(120, 215, 250))
                draw.rectangle((0, 504, 960, 540), fill=(18, 25, 34))
                draw.text((16, 512), "Red: predicted tip target. Runtime must stop at observation/contact gates (waits omitted).",
                          font=small, fill=(255, 193, 142))
                writers[name].append_data(np.asarray(image))
            if frame % 200 == 0:
                print(f"Rendered {frame}/{len(frame_times)} frames per view", flush=True)
    finally:
        for writer in writers.values():
            writer.close()
        renderer.close()
        trajectory.close()
    metadata = dict(kind="partial kinematic handoff preview; no rope simulation",
        physical_execution_verified=False, fps=fps, frames_per_view=len(frame_times),
        playback_duration_s=len(frame_times)/fps,
        videos={name: dict(path=str(path.resolve()), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
                for name, path in paths.items()},
        trajectory_sha256=hashlib.sha256((directory/"handoff_trajectory.npz").read_bytes()).hexdigest(),
        report_sha256=hashlib.sha256((directory/"report.json").read_bytes()).hexdigest())
    (directory/"preview_manifest.json").write_text(json.dumps(metadata, indent=2)+"\n")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    render(args.directory)
