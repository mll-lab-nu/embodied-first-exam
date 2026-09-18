"""Render a static CLASSIC reconstruction, with a visible stationary robot.

Run from the repository root:
    .venv-gs121-nyx/bin/python -m topogym.tasks.hedgehog_in_cage.demo

Only cameras move. No simulation time passes, no oracle is executed, and the
free hedgehog is not attached to a robot or silently welded to the cage.
"""
import hashlib
import json
from pathlib import Path

import hydra
import numpy as np
from omegaconf import OmegaConf
from PIL import Image



def as_numpy(value):
    return value.detach().cpu().numpy() if hasattr(value, "detach") else np.asarray(value)


@hydra.main(version_base="1.3", config_path="../../../configs", config_name="hedgehog_in_cage_classic_preview")
def main(cfg):
    import genesis as gs
    import imageio.v2 as imageio
    from topogym.utils.franka import initialize_franka_controller
    from .scene import HedgehogSceneBuilder

    if cfg.task.variant != "classic_3star_reconstruction_v1":
        raise ValueError("Only the CLASSIC three-star reconstruction is implemented")
    if cfg.run.fps <= 0 or cfg.run.video_seconds <= 0:
        raise ValueError("Video duration and frame rate must be positive")
    output = Path(cfg.run.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    # Keep only the explicitly designed inspection cameras, not inherited
    # legacy cameras that point at other tabletop tasks.
    closeup = OmegaConf.to_container(cfg.env.cameras.detail, resolve=True)
    names = ("overview", "detail", "opposite", "video") if cfg.run.save_stills else ("video",)
    cfg.env.cameras = OmegaConf.create({n: OmegaConf.to_container(cfg.env.cameras[n], resolve=True) for n in names})
    OmegaConf.save(cfg, output/"config.yaml", resolve=True)
    print("Building CLASSIC three-star static scene", flush=True)
    gs.init(backend=gs.cuda if cfg.env.genesis.backend == "cuda" else gs.cpu,
            logging_level="warning", seed=int(cfg.task.seed))
    task = HedgehogSceneBuilder(cfg.env, cfg.task, cfg.robot_control).build(
        asset_dir=output/"assets", show_viewer=bool(cfg.run.viewer))
    initialize_franka_controller(scene=task.scene, manifest=task.manifest,
        robot_cfg=cfg.robot_control, settle_steps=0)
    robot = task.manifest.get("robot")
    initial_q = as_numpy(robot.get_qpos()).copy()
    initial_ball = as_numpy(task.hedgehog.get_qpos()).copy()
    if task.hedgehog.n_dofs != 6:
        raise RuntimeError("The hedgehog must remain a single free rigid body")
    for name in (n for n in names if n != "video"):
        rgb = task.cameras[name].render(force_render=True)[0]
        Image.fromarray(rgb).save(output/f"initial_{name}.png")
        print(f"Rendered {name}", flush=True)
    if cfg.run.record_video:
        camera = task.cameras["video"]
        cam_cfg = cfg.env.cameras.video
        target = np.asarray(cam_cfg.lookat, dtype=float)
        offset = np.asarray(cam_cfg.pos, dtype=float)-target
        count = round(float(cfg.run.video_seconds)*int(cfg.run.fps))
        closeup_fraction = float(cfg.run.closeup_fraction)
        if not 0 <= closeup_fraction < 1:
            raise ValueError("closeup_fraction must be in [0, 1)")
        with imageio.get_writer(output/"preview.mp4", fps=int(cfg.run.fps), codec="libx264", quality=8,
                               macro_block_size=1, ffmpeg_log_level="error") as writer:
            for i in range(count):
                t = i/max(count-1, 1)
                if t < 1-closeup_fraction or closeup_fraction == 0:
                    phase = t/(1-closeup_fraction)
                    aim, arm = target, offset
                    orbit = float(cfg.run.orbit_degrees)
                else:
                    phase = (t-(1-closeup_fraction))/closeup_fraction
                    aim = np.asarray(closeup["lookat"], dtype=float)
                    arm = np.asarray(closeup["pos"], dtype=float)-aim
                    orbit = 28.
                angle = np.radians(orbit)*(.5-.5*np.cos(np.pi*phase))
                c, s = np.cos(angle), np.sin(angle)
                shift = np.array([c*arm[0]-s*arm[1], s*arm[0]+c*arm[1], arm[2]])
                camera.set_pose(pos=aim+shift, lookat=aim, up=(0, 0, 1))
                writer.append_data(camera.render(force_render=True)[0])
                if i % 40 == 0:
                    print(f"Camera preview {i}/{count}", flush=True)
    q_error = float(np.max(np.abs(as_numpy(robot.get_qpos())-initial_q)))
    ball_error = float(np.max(np.abs(as_numpy(task.hedgehog.get_qpos())-initial_ball)))
    if q_error != 0 or ball_error != 0:
        raise RuntimeError("Static preview changed the scene state")
    report = dict(scope="static_scene_inspection_only", variant=str(cfg.task.variant),
        scale=float(cfg.task.scale), simulation_steps=0, simulated_seconds=0,
        robot_present=True, robot_tool="Panda + Robotiq 2F-85", robot_qpos=initial_q.tolist(),
        max_robot_qpos_change=q_error, max_hedgehog_qpos_change=ball_error,
        hedgehog_dofs=int(task.hedgehog.n_dofs), spike_count=10,
        initial_pose=task.asset_report["initial_pose"],
        asset_geometry_status=task.asset_report["geometry_status"],
        full_task_deployed=False, extraction_route_verified=False,
        gravity_stability_verified=False, robot_reachability_qualified=False,
        video_created=bool(cfg.run.record_video), camera_motion_only=True,
        renderer=str(cfg.env.renderer.type), visual_finish=str(cfg.task.finish),
        physical_material_parameters_changed=False)
    (output/"inspection_report.json").write_text(json.dumps(report, indent=2)+"\n")
    artifacts = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir())
                 if p.is_file() and p.name != "artifact_manifest.json"}
    (output/"artifact_manifest.json").write_text(json.dumps(artifacts, indent=2)+"\n")
    print(f"Video: {output/'preview.mp4'}", flush=True)


if __name__ == "__main__":
    main()
