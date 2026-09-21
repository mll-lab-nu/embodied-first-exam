"""Generate assets and record synchronized, zero-step initial-scene inspections."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path

import hydra
import numpy as np
from omegaconf import OmegaConf

from .geometry import OrbitsLayout, generate_assets


def _array(value):
    return value.detach().cpu().numpy() if hasattr(value, "detach") else np.asarray(value)


@hydra.main(version_base="1.3", config_path=str(Path(__file__).resolve().parents[3]/"configs"),
            config_name="orbits_preview")
def main(cfg):
    output = Path(cfg.run.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if cfg.run.render and not cfg.run.build_scene:
        raise ValueError("Rendering requires run.build_scene=true")
    if cfg.run.fps <= 0 or cfg.run.video_seconds <= 0:
        raise ValueError("Video duration and fps must be positive")
    names = list(cfg.run.cameras)
    cfg.env.cameras = OmegaConf.create({n: OmegaConf.to_container(cfg.env.cameras[n], resolve=True) for n in names})
    OmegaConf.save(cfg, output/"config.yaml", resolve=True)
    if not cfg.run.build_scene:
        _, report = generate_assets(output/"assets", OrbitsLayout(
            **OmegaConf.to_container(cfg.task.geometry, resolve=True)).scaled(float(cfg.task.get("scale", 1.))))
        print(json.dumps(report["checks"], indent=2), flush=True)
        return

    import genesis as gs
    from topogym.robot import initialize_robot_controller
    from .scene import OrbitsSceneBuilder

    gs.init(backend=getattr(gs, cfg.env.genesis.backend), seed=int(cfg.task.seed), logging_level="warning")
    task = OrbitsSceneBuilder(cfg.env, cfg.task, cfg.robot_control).build(
        asset_dir=output/"assets", show_viewer=bool(cfg.run.viewer), include_robot=bool(cfg.run.include_robot))
    if cfg.run.include_robot:
        initialize_robot_controller(scene=task.scene, manifest=task.manifest,
                                    robot_cfg=cfg.robot_control, settle_steps=0)
    tracked = dict(task.entities)
    if cfg.run.include_robot:
        tracked["robot"] = task.manifest.get("robot")
    initial = {n: _array(e.get_qpos()).copy() for n, e in tracked.items()}
    frame_count = round(float(cfg.run.video_seconds)*int(cfg.run.fps)) if cfg.run.render else 0
    if cfg.run.render:
        import imageio.v2 as imageio
        from PIL import Image
        with ExitStack() as stack:
            writers = {n: stack.enter_context(imageio.get_writer(output/f"initial_{n}.mp4",
                fps=int(cfg.run.fps), codec="libx264", quality=8, macro_block_size=1,
                ffmpeg_log_level="error", output_params=["-movflags", "+faststart"])) for n in names}
            for i in range(frame_count):
                phase = i/max(frame_count-1, 1)
                angle = np.radians(float(cfg.run.orbit_degrees))*np.sin(2*np.pi*phase)
                c, s = np.cos(angle), np.sin(angle)
                for n in names:
                    spec = cfg.env.cameras[n]
                    aim = np.asarray(spec.lookat)
                    arm = np.asarray(spec.pos)-aim
                    shift = [c*arm[0]-s*arm[1], s*arm[0]+c*arm[1], arm[2]]
                    task.cameras[n].set_pose(pos=aim+shift, lookat=aim, up=spec.up)
                # Nyx updates all registered cameras together on the first read.
                for j, n in enumerate(names):
                    rgb = task.cameras[n].render(force_render=(j == 0))[0]
                    writers[n].append_data(rgb)
                    if i == 0:
                        Image.fromarray(rgb).save(output/f"initial_{n}.png")
                if i % 15 == 0:
                    print(f"Static camera inspection: {i}/{frame_count}", flush=True)
    drift = {n: float(np.max(np.abs(_array(e.get_qpos())-initial[n]), initial=0)) for n, e in tracked.items()}
    if any(drift.values()):
        raise RuntimeError(f"Static preview changed entity coordinates: {drift}")
    report = dict(task_id="orbits", task_number=13, variant=str(cfg.task.variant),
                  origin_xy_m=list(cfg.task.origin_xy_m), yaw_deg=float(cfg.task.yaw_deg),
                  uniform_scale=float(cfg.task.get("scale", 1.)),
                  scope="static_scene_inspection_only", simulation_steps=0, simulated_seconds=0,
                  camera_motion_only=True, all_task_entities_fixed=True, task_collision_enabled=False,
                  cord_model="continuous yellow visual cord; authored handle eyes; no deformable solver or attachment constraints",
                  robot_present=bool(cfg.run.include_robot), robot_family=str(cfg.robot_control.robot.name),
                  renderer=str(cfg.env.renderer.type), background=str(cfg.env.presentation.background),
                  cameras=names, frame_count=frame_count, fps=int(cfg.run.fps),
                  video_seconds=frame_count/int(cfg.run.fps), max_qpos_change=drift,
                  imported_geometry=task.import_audit,
                  geometry_passed=task.asset_report["passed"], physics_qualified=False,
                  full_task_deployed=False, full_robot_demo=False, solution_verified=False)
    (output/"inspection_report.json").write_text(json.dumps(report, indent=2)+"\n")
    (output/"artifact_manifest.json").write_text(json.dumps({
        str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(output.rglob("*")) if p.is_file() and p.name != "artifact_manifest.json"
    }, indent=2)+"\n")
    print(f"Inspection complete: {output}", flush=True)


if __name__ == "__main__":
    main()
