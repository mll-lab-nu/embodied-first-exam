"""Clean, synchronized videos of a qualified continuous physical execution."""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path

import numpy as np
from omegaconf import OmegaConf

from topogym.world.aloha_cameras import CAMERA_NAMES
from .gravity_demo import sha


def render(source, output, *, fps=10, width=960, camera_names=None, camera_overrides=None):
    import genesis as gs
    import imageio.v2 as imageio
    from PIL import Image
    from .scene import build_scene

    source, output = Path(source).resolve(), Path(output).resolve()
    cameras = list(camera_names) if camera_names is not None else [*CAMERA_NAMES, "detail"]
    if not cameras or len(set(cameras)) != len(cameras) or set(cameras) - {*CAMERA_NAMES, "detail"}:
        raise ValueError("Select distinct supported cameras")
    camera_overrides = camera_overrides or {}
    if set(camera_overrides) - set(cameras):
        raise ValueError("Camera overrides must belong to selected views")
    report = json.loads((source/"result.json").read_text())
    if not report.get("task_success") or report.get("checkpoint_start") or not report.get("goal", {}).get("passed"):
        raise ValueError("Full videos require a successful continuous physical run including free release")
    trace = source/"physical_states.jsonl"
    if sha(trace) != report["physical_states_sha256"]:
        raise ValueError("Physical state evidence changed")
    original = [json.loads(line) for line in trace.read_text().splitlines()]
    if len(original) != report["physical_frame_count"]:
        raise ValueError("Incomplete physical frame sequence")
    stride = report["physical_frame_fps"]/fps
    if fps <= 0 or not np.isclose(stride, round(stride)) or stride < 1:
        raise ValueError("Video FPS must divide the recorded physics observation rate")
    if width <= 0 or width % 16:
        raise ValueError("Width must be a positive multiple of 16")
    selected = original[::int(round(stride))]
    if any(not np.isclose(f["time_s"], f["step"]*report["dt"]) for f in selected):
        raise ValueError("Frame timestamps do not agree with actual physics steps")
    output.mkdir(parents=True, exist_ok=False)
    cfg = OmegaConf.load(source/"config.yaml")
    rig = json.loads((source/"recording_cameras.json").read_text())
    for camera in CAMERA_NAMES:
        rig[camera]["res"] = [width, width*9//16]
    # Keep the upstream low camera mounting pose, with enough vertical FOV for
    # the raised extraction and the subsequent table release in one shot.
    rig["cam_low"]["fov"] = 66.
    rig["detail"] = dict(res=[width, width*3//4], pos=[.32, -.70, 1.56],
        lookat=[-.06, .015, 1.22], up=[0., 0., 1.], fov=48., near=.005, far=12.)
    for name, override in camera_overrides.items():
        if name.endswith("wrist"):
            raise ValueError("Task-view overrides apply only to fixed cameras; preserve wrist mounts")
        rig[name].update(override)
    from scipy.spatial.transform import Rotation
    from trimesh.bounds import corners
    from .geometry import HorseshoeAssembly
    assembly = HorseshoeAssembly(json.loads((source/"input_template.json").read_text()), float(cfg.task.scale))
    local = {body.name: corners(body.visual.bounds-body.visual.center_mass) for body in assembly.bodies}
    points = np.concatenate([Rotation.from_quat(np.asarray(frame["bodies"][name]["quat_wxyz"])[[1, 2, 3, 0]])
        .apply(vertices)+frame["bodies"][name]["pos"] for frame in original for name, vertices in local.items()])
    coverage = {}
    from topogym.world.tabletop import tabletop_frames_from_config
    table_z = float(tabletop_frames_from_config(cfg.env).table_surface_origin[2])
    for name in ("cam_high", "cam_low", "detail"):
        if name not in cameras:
            continue
        camera = rig[name]
        if camera["pos"][2] <= table_z:
            raise ValueError(f"{name} is below the tabletop; configure a visible fixed task-view mount")
        forward = np.asarray(camera["lookat"])-camera["pos"]
        forward /= np.linalg.norm(forward)
        right = np.cross(forward, camera["up"])
        right /= np.linalg.norm(right)
        up = np.cross(right, forward)
        delta = points-camera["pos"]
        depth = delta@forward
        if depth.min() <= camera["near"]:
            raise ValueError(f"{name} cannot cover the physical task from its configured mounting pose")
        aspect = camera["res"][0]/camera["res"][1]
        tangent = max(float(np.max(np.abs(delta@up)/depth)), float(np.max(np.abs(delta@right)/depth/aspect)))
        required = float(np.rad2deg(2*np.arctan(tangent))+2.)
        if required > 100.:
            raise ValueError(f"{name} needs a new task-view mounting pose, not an extreme FOV")
        camera["fov"] = max(camera["fov"], required)
        coverage[name] = dict(required_vertical_fov_deg=required, configured_vertical_fov_deg=camera["fov"],
            camera_height_above_table_m=float(camera["pos"][2]-table_z),
            scope="All recorded puzzle body bounding boxes; frustum coverage does not certify absence of occlusion")
    cfg.env.cameras = OmegaConf.create({name: rig[name] for name in cameras})
    cfg.task.template_path = str(source/"input_template.json")
    cfg.env.genesis.backend, cfg.env.renderer.type = "cpu", "rasterizer"
    OmegaConf.save(cfg, output/"render_config.yaml", resolve=True)
    (output/"render_cameras.json").write_text(json.dumps(dict(cameras=rig,
        adaptation="Explicit fixed task-view mounts where recorded; FOV expanded to cover the complete measured task",
        fixed_camera_overrides=camera_overrides,
        fixed_view_coverage=coverage,
        hardware_calibration_equivalent=False), indent=2))
    gs.init(backend=gs.cpu, precision="64", logging_level="warning", seed=0)
    task = build_scene(cfg, output/"render_assets")
    if sha(output/"render_assets/template.json") != sha(source/"assets/template.json"):
        raise ValueError("Rendered geometry differs from the physical run")
    def geometry_hashes(folder):
        return {str(path.relative_to(folder)): sha(path) for path in folder.rglob("*")
                if path.suffix in (".urdf", ".obj", ".stl", ".ply", ".dae", ".glb")}
    if geometry_hashes(output/"render_assets") != geometry_hashes(source/"assets"):
        raise ValueError("Actual rendered mesh/URDF assets differ from the physics assets")
    robot = task.manifest.get("robot")
    camera_poses, camera_checks = [], {}
    previous_stage = None
    with ExitStack() as stack:
        writers = {name: stack.enter_context(imageio.get_writer(output/f"{name}.mp4", fps=fps,
            codec="libx264", quality=8, macro_block_size=1, ffmpeg_params=["-threads", "2"],
            ffmpeg_log_level="error")) for name in cameras}
        for index, frame in enumerate(selected):
            robot.set_qpos(np.asarray(frame["qpos"]), zero_velocity=True)
            for name, body in task.bodies.items():
                pose = frame["bodies"][name]
                body.set_pos(np.asarray(pose["pos"]))
                body.set_quat(np.asarray(pose["quat_wxyz"]))
            task.scene.visualizer.update_visual_states(force_render=True)
            poses = dict(source_frame=frame["frame"], time_s=frame["time_s"], cameras={})
            for name, writer in writers.items():
                camera = task.cameras[name]
                if name.endswith("wrist"):
                    camera.move_to_attach()
                rgb = camera.render(force_render=True)[0]
                writer.append_data(rgb)
                poses["cameras"][name] = np.asarray(camera.transform).tolist()
                if index == 0:
                    camera_checks[name] = dict(shape=list(rgb.shape), intrinsics=np.asarray(camera.intrinsics).tolist())
                    Image.fromarray(rgb).save(output/f"initial_{name}.jpg")
                if index == len(selected)-1:
                    Image.fromarray(rgb).save(output/f"final_{name}.jpg")
                if frame["stage"] != previous_stage:
                    Image.fromarray(rgb).save(output/f"stage_{frame['frame']:05d}_{name}.jpg")
            camera_poses.append(poses)
            previous_stage = frame["stage"]
            if index % 20 == 0:
                print(f"Rendered {index+1}/{len(selected)} physical snapshots in {len(cameras)} views", flush=True)
    (output/"camera_poses.json").write_text(json.dumps(camera_poses))
    evidence = dict(recording_kind="exact_physical_state_render", source_result_sha256=sha(source/"result.json"),
        source_states_sha256=sha(trace), source_physics_steps=report["physics_steps"], render_physics_steps=0,
        no_interpolation=True, source_frame_indices=[f["frame"] for f in selected], frame_count=len(selected),
        fps=fps, duration_s=len(selected)/fps, final_snapshot_time_s=selected[-1]["time_s"],
        cameras=cameras, camera_checks=camera_checks, task_success=True,
        overlays=False, videos={name: dict(path=f"{name}.mp4", sha256=sha(output/f"{name}.mp4")) for name in cameras})
    (output/"render_report.json").write_text(json.dumps(evidence, indent=2)+"\n")
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fps", type=int, default=10)
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--cameras", nargs="+", choices=[*CAMERA_NAMES, "detail"],
                        help="Re-render selected views of the same complete recorded execution")
    parser.add_argument("--camera-overrides", type=Path,
                        help="JSON mapping fixed camera names to rendering-only mounting overrides")
    args = parser.parse_args()
    overrides = json.loads(args.camera_overrides.read_text()) if args.camera_overrides else None
    render(args.source, args.output, fps=args.fps, width=args.width,
           camera_names=args.cameras, camera_overrides=overrides)


if __name__ == "__main__":
    main()
