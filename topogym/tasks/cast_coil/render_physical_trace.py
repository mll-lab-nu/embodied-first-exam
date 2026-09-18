"""Render exact snapshots of a completed physical execution with Nyx.

The source contains actual 20 Hz states captured during scene.step(), not IK
waypoints. Rendering performs zero physics steps and explicitly reports its
pose assignments separately from the source execution. No interpolation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

import imageio.v2 as imageio
import numpy as np
from omegaconf import OmegaConf
from PIL import Image, ImageDraw
from scipy.spatial.transform import Rotation

from .robot_archive import CAMERAS, qualify_report


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verified_frames(source):
    source = Path(source)
    report = json.loads((source / "result.json").read_text())
    qualify_report(report, recording=False)
    trace = source / "render_states.jsonl"
    if sha(trace) != report.get("render_states_sha256"):
        raise ValueError("Physical snapshot hash does not match the execution report")
    frames = [json.loads(line) for line in trace.read_text().splitlines()]
    if len(frames) != report["physical_frame_count"] or not frames:
        raise ValueError("Physical snapshot count mismatch")
    if [f["frame"] for f in frames] != list(range(len(frames))):
        raise ValueError("Physical snapshot indices are not contiguous")
    expected = np.arange(len(frames)) / report["physical_frame_fps"]
    if not np.allclose([f["time_s"] for f in frames], expected, atol=1e-10, rtol=0):
        raise ValueError("Nonuniform physical frame times")
    if not np.allclose(
        [f["step"] * report["dt"] for f in frames], expected, atol=1e-10, rtol=0
    ):
        raise ValueError("Frames are not linked to physical step indices")
    if (
        report["simulated_seconds"] - frames[-1]["time_s"]
        >= 1 / report["physical_frame_fps"]
    ):
        raise ValueError("Missing the end of the physical execution")
    if frames[-1]["phase"] != "settle" or frames[-1]["grasp_assistance_active"]:
        raise ValueError("The recording does not finish with released pieces")
    return report, frames


def render(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    report, frames = verified_frames(source)
    shutil.copytree(source, output)
    (output / "physics_result.json").write_bytes((source / "result.json").read_bytes())
    # Never expose the original non-recording report as successful video output
    # if the rendering process is interrupted.
    (output / "result.json").write_text(
        json.dumps(dict(success=False, complete=False, stage="render_pending"))
    )
    cfg = OmegaConf.load(output / "config.yaml")
    cfg.env.genesis.backend = "cuda"
    cfg.env.renderer.type = "nyx"
    cfg.env.renderer.spp = 24
    cfg.env.cameras = OmegaConf.create(
        json.loads((source / "recording_cameras.json").read_text())
    )
    cfg.task.template_path = str(output / "input_template.json")
    cfg.run.output = str(output)
    OmegaConf.save(cfg, output / "render_config.yaml", resolve=True)
    (output / "render_source.py").write_text(Path(__file__).read_text())
    import genesis as gs
    from .scene import build_scene
    from . import scene as scene_source

    (output / "render_scene_source.py").write_text(
        Path(scene_source.__file__).read_text()
    )
    gs.init(backend=gs.cuda, precision="64", logging_level="warning", seed=0)
    # No scene.step() is performed: unused collision buffers would compete with
    # the ray tracer for GPU memory. The physical source used full collisions.
    task = build_scene(cfg, output / "render_assets", render_only=True)
    if sha(output / "render_assets/template.json") != sha(
        output / "assets/template.json"
    ):
        raise ValueError("Rendering and physics use different templates")
    robot = task.manifest.get("robot")
    bodies = [task.bodies[n] for n in ("coil_gold", "coil_silver")]
    origins = [np.asarray(b["origin_m"]) for b in task.asset_report["bodies"]]
    writers = {
        n: imageio.get_writer(
            output / f"{n}.mp4",
            fps=report["physical_frame_fps"],
            codec="libx264",
            quality=8,
            macro_block_size=1,
            ffmpeg_log_level="error",
        )
        for n in CAMERAS
    }
    cameras = (output / "camera_poses.jsonl").open("w")
    max_q = max_p = max_r = 0.0
    snapshots = set()
    complete = False

    def arr(x):
        return x.detach().cpu().numpy()

    try:
        for frame in frames:
            robot.set_qpos(np.asarray(frame["qpos"]), zero_velocity=True)
            max_q = max(
                max_q, float(np.max(np.abs(arr(robot.get_qpos()) - frame["qpos"])))
            )
            for i, (body, p) in enumerate(zip(bodies, frame["bodies"])):
                r = Rotation.from_quat(p["quaternion_xyzw"])
                body.set_quat(r.as_quat()[[3, 0, 1, 2]])
                body.set_pos(np.asarray(p["origin_m"]) + r.apply(origins[i]))
                actual_r = Rotation.from_quat(arr(body.get_quat())[[1, 2, 3, 0]])
                actual_p = arr(body.get_pos()) - actual_r.apply(origins[i])
                max_p = max(max_p, float(np.linalg.norm(actual_p - p["origin_m"])))
                max_r = max(max_r, float((actual_r.inv() * r).magnitude()))
            task.scene.visualizer.update_visual_states(force_render=True)
            for name in CAMERAS:
                camera = task.cameras[name]
                if name in ("cam_left_wrist", "cam_right_wrist"):
                    camera.move_to_attach()
                camera.sensor._stale = True
            transforms = {}
            for name, writer in writers.items():
                camera = task.cameras[name]
                rgb = camera.render()[0]
                transforms[name] = np.asarray(camera.transform).tolist()
                picture = Image.fromarray(rgb)
                draw = ImageDraw.Draw(picture)
                draw.rectangle((0, 0, picture.width, 52), fill=(16, 25, 34))
                draw.text(
                    (12, 7),
                    f"CAST COIL | {report.get('appearance_kind') or report.get('inverse_design_kind') or 'baseline'} | {frame['time_s']:.2f}s | {frame['phase']}",
                    fill="white",
                )
                draw.text(
                    (12, 28),
                    "MEASURED PHYSICS TRACE - OFFLINE NYX - CONTACT-GATED GRASP ASSIST",
                    fill=(242, 210, 120),
                )
                pixels = np.asarray(picture)
                writer.append_data(pixels)
                if frame["phase"] not in snapshots:
                    imageio.imwrite(
                        output / f"{frame['phase']}_{name}.jpg", pixels, quality=90
                    )
            cameras.write(
                json.dumps(
                    dict(
                        frame=frame["frame"],
                        time_s=frame["time_s"],
                        physical_step=frame["step"],
                        phase=frame["phase"],
                        transforms=transforms,
                    )
                )
                + "\n"
            )
            snapshots.add(frame["phase"])
            if frame["frame"] % 100 == 0:
                print(
                    "RENDER",
                    frame["frame"],
                    "/",
                    len(frames),
                    frame["phase"],
                    flush=True,
                )
        if max_q > 1e-9 or max_p > 1e-9 or max_r > 1e-9:
            raise ValueError("Rendered state deviates from the physical recording")
        complete = True
    finally:
        for writer in writers.values():
            writer.close()
        cameras.close()
    if not complete:
        raise RuntimeError("Incomplete render")
    evidence = dict(
        recording_kind="offline_render_of_exact_physical_states",
        physical_source_directory=str(source),
        physical_result_sha256=sha(output / "physics_result.json"),
        physical_states_sha256=sha(output / "render_states.jsonl"),
        no_interpolation=True,
        render_scene_physics_steps=0,
        render_scene_collision_enabled=False,
        render_pose_assignments=True,
        maximum_qpos_roundtrip_error=max_q,
        maximum_body_origin_roundtrip_error_m=max_p,
        maximum_body_rotation_roundtrip_error_rad=max_r,
        frames=len(frames),
        fps=report["physical_frame_fps"],
    )
    (output / "render_evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
    result = dict(
        report,
        camera_names=list(CAMERAS),
        video_frames=len(frames),
        video_fps=report["physical_frame_fps"],
        recording_kind=evidence["recording_kind"],
        render_scene_physics_steps=0,
        render_pose_assignments=True,
        physical_result_sha256=evidence["physical_result_sha256"],
    )
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(evidence), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--source", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    render(a.source, a.output)
