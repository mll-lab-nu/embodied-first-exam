"""Record birth -> gravity drop -> accepted/rejected initial state, without manipulation."""
from contextlib import ExitStack
import json
from pathlib import Path

import hydra
import numpy as np
from omegaconf import OmegaConf


@hydra.main(version_base="1.3", config_path="../../../configs", config_name="blanket_flatten_preview")
def main(cfg):
    if cfg.task.variant in ('staged_corner_cross_twist_v3', 'staged_gathered_twist_v4'):
        raise ValueError('Use robot_demo --config-name blanket_flatten_cross_twist for controlled preparation before release')
    import genesis as gs
    import imageio.v2 as imageio
    from PIL import Image
    from topogym.supervision.pbd_probe import probe_particles, probe_velocities
    from topogym.utils.franka import initialize_franka_controller
    from .diagnostics import AcceptanceWindow, initial_gates, health_gates, flatten_gates
    from .scene import BlanketSceneBuilder

    output = Path(cfg.run.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    limits = OmegaConf.to_container(cfg.task.initialization, resolve=True)
    dt = float(cfg.env.sim.dt)
    every = int(limits["sample_every"])
    if not 0 < limits["minimum_seconds"] < limits["maximum_seconds"] or limits["stable_seconds"] <= 0 or every < 1:
        raise ValueError("Invalid settling window")
    if cfg.run.fps <= 0 or dt <= 0:
        raise ValueError("Positive dt and fps required")
    cfg.env.cameras = OmegaConf.create({name: OmegaConf.to_container(cfg.env.cameras[name], resolve=True)
                                        for name in ("overview", "detail", "topdown")} if cfg.run.render else {})
    OmegaConf.save(cfg, output/"config.yaml", resolve=True)
    gs.init(backend=getattr(gs, str(cfg.env.genesis.backend)), precision=str(cfg.env.genesis.precision),
            seed=int(cfg.task.geometry.seed), logging_level="warning")
    task = BlanketSceneBuilder(cfg.env, cfg.task, cfg.robot_control).build(
        asset_dir=output/"assets", include_robot=bool(cfg.run.include_robot), show_viewer=bool(cfg.run.viewer))
    if cfg.run.include_robot:
        initialize_franka_controller(scene=task.scene, manifest=task.tabletop.manifest,
                                     robot_cfg=cfg.robot_control, settle_steps=0)
    print("Birth binding: "+json.dumps(task.binding_report), flush=True)
    (output/"birth_report.json").write_text(json.dumps(dict(geometry=task.birth_report, binding=task.binding_report), indent=2)+"\n")
    history, snapshots, velocities, snapshot_steps = [], [], [], []
    window = AcceptanceWindow(limits["stable_seconds"], limits["maximum_window_drift_m"])
    accepted, failure = False, None
    max_steps = int(np.ceil(limits["maximum_seconds"]/dt))
    next_frame = 0
    video_frames = 0
    with ExitStack() as stack:
        writers = {name: stack.enter_context(imageio.get_writer(output/f"drop_{name}.mp4", fps=int(cfg.run.fps),
                    codec="libx264", quality=8, macro_block_size=1, ffmpeg_log_level="error"))
                    for name in task.tabletop.cameras if cfg.run.record_video}
        for step in range(max_steps+1):
            if step:
                task.scene.step()
            now = step*dt
            if cfg.run.render and (now+1e-9 >= next_frame or step == max_steps):
                for name, camera in task.tabletop.cameras.items():
                    rgb = camera.render(force_render=True)[0]
                    if step == 0:
                        Image.fromarray(rgb).save(output/f"birth_{name}.png")
                    if name in writers:
                        writers[name].append_data(rgb)
                video_frames += 1
                next_frame += 1/int(cfg.run.fps)
            if step % every and step != max_steps:
                continue
            metrics = task.measure()
            gates = initial_gates(metrics, limits)
            history.append(dict(step=step, seconds=now, metrics=metrics, gates=gates))
            snapshots.append(probe_particles(task.cloth))
            velocities.append(probe_velocities(task.cloth))
            snapshot_steps.append(step)
            if step % (every*10) == 0:
                print(f"drop t={now:.2f}s {json.dumps(metrics)}", flush=True)
            health = health_gates(metrics, limits)
            if not all(health.values()):
                failure = [name for name, ok in health.items() if not ok]
                break
            accepted = window.update(now, snapshots[-1], {**gates, "minimum_time": now >= limits["minimum_seconds"]})
            if accepted:
                break
        if cfg.run.render:
            for name, camera in task.tabletop.cameras.items():
                Image.fromarray(camera.render(force_render=True)[0]).save(output/f"settled_{name}.png")
    np.savez_compressed(output/"particle_trace.npz", positions=np.asarray(snapshots), velocities=np.asarray(velocities),
                        steps=np.asarray(snapshot_steps), dt=dt, material_uv=task.material_uv, faces=task.faces,
                        edges=task.edges, rest_lengths=task.rest_lengths, supports=task.supports, weights=task.weights)
    result = dict(scope="gravity_initialization_only", task_id="blanket_flatten",
                  initialization_accepted=accepted, full_robot_task_verified=False,
                  robot_present=bool(cfg.run.include_robot), robot_manipulation_executed=False,
                  robot_soft_coupling=False, pinned_particles=0, position_overrides_after_build=0,
                  birth=task.birth_report, binding=task.binding_report, simulated_seconds=now,
                  stable_window_seconds=window.duration, maximum_window_drift_m=window.drift_m,
                  diagnostic_interval_seconds=every*dt,
                  failure=failure if failure else ([] if accepted else [name for name, ok in gates.items() if not ok] or ["stable_window_timeout"]),
                  final=metrics, final_initial_gates=gates,
                  candidate_flatten_gates=flatten_gates(metrics, OmegaConf.to_container(cfg.task.success, resolve=True), released=True),
                  renderer=str(cfg.env.renderer.type), vis_mode=str(cfg.task.vis_mode),
                  video_frames=video_frames if writers else 0, history=history)
    (output/"report.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    status = "初态通过" if accepted else "初态未通过"
    media = "".join(f'<h2>{name}</h2><img width="480" src="birth_{name}.png"><img width="480" src="settled_{name}.png">'
                    +(f'<video controls width="800" src="drop_{name}.mp4"></video>' if name in writers else "")
                    for name in task.tabletop.cameras)
    (output/"index.html").write_text('<!doctype html><meta charset="utf-8"><title>被子重力初始化</title>'
        '<style>body{font-family:sans-serif;max-width:1100px;margin:32px auto;background:#edf0f2}img,video{max-width:100%}</style>'
        f'<h1>被子展平：{status}</h1><p>悬空出生 → 自由重力下落 → 静置。此处未执行机械臂整理。</p>'
        '<p><a href="report.json">物理报告</a> · <a href="config.yaml">配置</a> · <a href="particle_trace.npz">粒子轨迹</a></p>'+media)
    print(f"{status}: {output/'index.html'}", flush=True)
    if not accepted:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
