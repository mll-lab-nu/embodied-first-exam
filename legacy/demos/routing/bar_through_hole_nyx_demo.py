"""Film the existing oracle with Nyx and the shared oblique/front/wrist rig.

    .venv-gs121-nyx/bin/python -m demos.routing.bar_through_hole_nyx_demo
    .venv-gs121-nyx/bin/python -m demos.routing.bar_through_hole_nyx_demo run.inspect_only=true

The builder, controller, contacts, assisted grasp and verifier are the physical
demo's. Nyx reads the live state; the movie is sampled in simulation time.
"""

from __future__ import annotations

from dataclasses import asdict
from contextlib import ExitStack
from importlib.metadata import version
import json
from pathlib import Path
import time

import genesis as gs
import hydra
import imageio.v2 as imageio
import numpy as np
from omegaconf import DictConfig, OmegaConf
from PIL import Image
import torch

from demos.routing.bar_through_hole_physical_insert_demo import configure_contacts, run_demo
from topogym.generation import EpisodeKey
from topogym.generation.layout_randomization import randomize_task_cfg
from topogym.tasks_legacy import BarThroughHoleSceneBuilder
from topogym.utils.franka import initialize_franka_controller
from topogym.utils.recording import (
    apply_recording_camera_overrides, recording_camera_output_path,
    select_recording_camera_items, update_dynamic_camera,
)
from topogym.world import nyx


def camera_readings(sensors, rasters):
    """Check the world poses actually submitted to Nyx against the original rig.

    Reads plugin 0.1.4's pose buffers after rendering, including the moving wrist.
    This catches wrong link offsets or a frozen camera during the real rollout.
    """
    readings = {}
    for name, sensor in sensors.items():
        raster = rasters[name]
        update_dynamic_camera(raster)
        if sensor._attached_pos is not None:
            pos, lookat, up = (getattr(sensor, f"_attached_{key}")[0].cpu().numpy()
                               for key in ("pos", "lookat", "up"))
        else:
            pos, lookat, up = (np.asarray(getattr(sensor._options, key))
                               for key in ("pos", "lookat", "up"))
        matrix = nyx.pos_lookat_up_to_T(pos, lookat, up)
        error = float(np.max(np.abs(matrix - raster.transform)))
        if error > 5e-5 or tuple(sensor._options.res) != tuple(raster.res):
            raise RuntimeError(f"Nyx/{name} differs from the shared camera rig: {error=}")
        readings[name] = {"world_T": matrix.tolist(), "rig_max_abs_error": error}
    return readings


@hydra.main(version_base="1.3", config_path="../../configs", config_name="bar_through_hole_nyx")
def main(cfg: DictConfig) -> None:
    if not torch.cuda.is_available():
        raise RuntimeError("Nyx needs CUDA; use .venv-gs121-nyx on the GPU host")
    if int(cfg.env.sim.n_envs) != 0:
        raise ValueError("Keep env.sim.n_envs=0: this is the single-task Nyx demo")
    if not cfg.recording.enabled:
        raise ValueError("Use run.inspect_only=true for stills; this demo requires recording.enabled=true")
    stride = int(cfg.recording.every_n_steps)
    expected_fps = 1.0 / (float(cfg.env.sim.dt) * stride) if stride > 0 else 0.0
    if stride <= 0 or abs(float(cfg.recording.fps) - expected_fps) > 1e-6:
        raise ValueError("recording.fps must equal 1/(env.sim.dt * recording.every_n_steps)")
    if cfg.run.randomize_layout:
        cfg = randomize_task_cfg(cfg, "bar_through_hole", cfg.run.seed, difficulty=cfg.run.difficulty)
    cfg = apply_recording_camera_overrides(cfg)
    movie = Path(cfg.recording.path).resolve()
    output = movie.parent
    output.mkdir(parents=True, exist_ok=True)
    config_name = "preview_config.yaml" if cfg.run.inspect_only else "config.yaml"
    OmegaConf.save(cfg, output / config_name, resolve=True)
    if not cfg.run.inspect_only:
        (output / "report.json").unlink(missing_ok=True)
    gs.init(backend=gs.cuda, seed=int(cfg.run.seed), precision=str(cfg.env.genesis.precision),
            logging_level=str(cfg.env.genesis.logging_level))

    builder = BarThroughHoleSceneBuilder(cfg.env, cfg.task, cfg.robot_control)
    def select_sensors(tabletop):
        selected = dict(select_recording_camera_items(tabletop.cameras, cfg.recording))
        tabletop.cameras.clear()
        tabletop.cameras.update(selected)

    bar_scene = builder.build(show_viewer=False, before_finalize=select_sensors)
    selected = dict(select_recording_camera_items(bar_scene.cameras, cfg.recording))
    render = {
        "dressing": bar_scene.tabletop.presentation["dressing"],
        "finishes": bar_scene.tabletop.presentation["finishes"],
        "rasters": {name: camera.raster_camera for name, camera in selected.items()},
        "sensors": {name: camera.sensor for name, camera in selected.items()},
    }
    controller = initialize_franka_controller(
        scene=bar_scene.scene, manifest=bar_scene.manifest, robot_cfg=cfg.robot_control,
        settle_steps=int(cfg.task.physical.settle_steps),
    )
    configure_contacts(cfg, bar_scene, controller)
    status = {"phase": "home", "mode": cfg.run.oracle_mode or str(cfg.task.oracle.mode),
              "release_stable": True}
    sensors, rasters = render["sensors"], render["rasters"]

    def snapshot(label, *, raster=False):
        for name, sensor in sensors.items():
            Image.fromarray(nyx.rgb(sensor)).save(output / f"nyx_{name}_{label}.png")
            if raster:
                update_dynamic_camera(rasters[name])
                Image.fromarray(rasters[name].render()[0]).save(output / f"rasterizer_{name}_{label}.png")
        return camera_readings(sensors, rasters)

    initial_cameras = snapshot("initial", raster=True)
    rig = {name: nyx.camera_kwargs(cfg.env.cameras[name], bar_scene.manifest) for name in sensors}
    (output / "cameras.json").write_text(json.dumps(rig, indent=2) + "\n")
    if cfg.run.inspect_only:
        (output / "preview_report.json").write_text(json.dumps({
            "cameras": initial_cameras, "finishes": render["finishes"],
            "background": str(cfg.env.presentation.background), "dressing": render["dressing"],
        }, indent=2) + "\n")
        print(f"nyx previews {list(sensors)} -> {output}", flush=True)
        return

    original_step = bar_scene.scene.step
    frames = []
    step_count = 0
    previous_phase = None
    render_seconds = 0.0
    movie_paths = {name: recording_camera_output_path(movie, name) if len(sensors) > 1 else movie
                   for name in sensors}
    writers = {}

    def record_step(*args, **kwargs):
        nonlocal step_count, previous_phase, render_seconds
        result = original_step(*args, **kwargs)
        step_count += 1
        if step_count % stride:
            return result
        torch.cuda.synchronize()
        started = time.perf_counter()
        images = {name: nyx.rgb(sensor) for name, sensor in sensors.items()}
        render_seconds += time.perf_counter() - started
        phase = str(status["phase"])
        for name, frame in images.items():
            writers[name].append_data(frame)
            if phase != previous_phase:
                Image.fromarray(frame).save(output / f"nyx_{name}_{phase}.png")
        if phase != previous_phase:
            previous_phase = phase
        frames.append({"frame": len(frames), "sim_time_s": step_count * float(cfg.env.sim.dt),
                       "phase": phase, "bar_pos": bar_scene.bar_entity().get_pos().cpu().tolist(),
                       "cameras": camera_readings(sensors, rasters)})
        if len(frames) % 50 == 0:
            print(f"nyx recording frames={len(frames)} sim_s={frames[-1]['sim_time_s']:.2f}", flush=True)
        return result

    started = time.perf_counter()
    with ExitStack() as stack:
        for name, path in movie_paths.items():
            writers[name] = stack.enter_context(
                imageio.get_writer(str(path), fps=expected_fps, codec="libx264", quality=8),
            )
        bar_scene.scene.step = record_step
        try:
            result = run_demo(
                cfg, bar_scene, controller,
                episode_key=EpisodeKey(task_id="bar_through_hole", seed=int(cfg.run.seed)),
                mode=status["mode"], status=status,
            )
        finally:
            bar_scene.scene.step = original_step
            (output / "frames.json").write_text(json.dumps(frames, indent=2) + "\n")

    final_cameras = snapshot("final", raster=True)
    report = {
        "episode": asdict(result), "frames": len(frames), "fps": expected_fps,
        "simulation_seconds": step_count * float(cfg.env.sim.dt),
        "rollout_wall_seconds": time.perf_counter() - started,
        "render_and_readback_seconds": render_seconds,
        "versions": {p: version(p) for p in ("genesis-world", "gs-nyx-plugin", "gs-nyx", "numpy")},
        "gpu": torch.cuda.get_device_name(), "finishes": render["finishes"],
        "videos": {name: str(path) for name, path in movie_paths.items()},
        "cameras": rig, "initial_cameras": initial_cameras, "final_cameras": final_cameras,
        "background": str(cfg.env.presentation.background), "dressing": render["dressing"],
        "camera_alignment_max_error": max(
            item["rig_max_abs_error"] for frame in frames for item in frame["cameras"].values()
        ),
        "physical_control": "existing assisted grasp with geometric insertion clamp",
    }
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"nyx demo success={result.success} frames={len(frames)} cameras={list(sensors)} -> {output}", flush=True)
    if not result.success:
        raise SystemExit("The recorded task failed; see report.json")


if __name__ == "__main__":
    main()
