"""Render the shared default and check camera, recording and dataset RGB paths.

    .venv-gs121-nyx/bin/python -m demos.environment_bootstrap.presentation_preview
This is a renderer/rig check, not a task execution or physics qualification.
"""
import argparse
import json
import os
from pathlib import Path
from html import escape

import genesis as gs
from hydra import compose, initialize_config_dir
import imageio.v2 as imageio
import numpy as np
from omegaconf import OmegaConf, open_dict

from topogym.data.episode_dataset_writer import EpisodeDatasetWriter, _grab_rgb
from topogym.generation.episode_spec import EpisodeKey, EpisodeSpec, ScenePreset, TaskVariant
from topogym.utils.franka import initialize_franka_controller
from topogym.utils.recording import recording_session, update_dynamic_camera
from topogym.world import StandardTabletopSceneBuilder, nyx

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "runs/environment_bootstrap/default_presentation")
    parser.add_argument("--renderer", choices=("nyx", "rasterizer"), default="nyx")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with initialize_config_dir(config_dir=str(ROOT / "configs"), version_base="1.3"):
        cfg = compose(config_name="presentation_preview", overrides=[f"env.renderer.type={args.renderer}"])
    cfg.env.cameras = OmegaConf.create({name: OmegaConf.to_container(cfg.env.cameras[name], resolve=True)
                                       for name in ("base_camera", "oblique", "wrist")})
    with open_dict(cfg.env.cameras):
        cfg.env.cameras.room = dict(res=[800, 600], pos=[1.55, -1.40, 2.10], lookat=[-.25, .10, 1.10],
                                   up=[0, 0, 1], fov=74, near=.01, far=12.)
    OmegaConf.save(cfg, output / "config.yaml", resolve=True)
    gs.init(backend=gs.cuda, logging_level="warning", seed=0)
    builder = StandardTabletopSceneBuilder(cfg.env, cfg.robot_control)
    base = builder.create()
    builder.finalize(base)
    controller = initialize_franka_controller(scene=base.scene, manifest=base.manifest,
                                               robot_cfg=cfg.robot_control, settle_steps=2)
    poses = []
    errors = []
    for label in ("initial", "moved"):
        if label == "moved":
            # Deliberate diagnostic joint reset, only to test the camera rig.
            robot = base.manifest.get("robot")
            q = robot.get_dofs_position().cpu().numpy().reshape(-1)
            robot.set_dofs_position([float(q[0]) + .15], dofs_idx_local=[0])
            base.scene.step()
        for name, camera in base.cameras.items():
            frame = _grab_rgb(camera)
            assert frame.shape == (camera.res[1], camera.res[0], 3) and frame.dtype == np.uint8
            assert frame.std() > 5, f"Blank render: {name}"
            imageio.imwrite(output / f"{label}_{name}.png", frame)
        wrist = base.cameras["wrist"]
        update_dynamic_camera(wrist)
        poses.append(wrist.transform.copy())
        if args.renderer == "nyx":
            sensor = wrist.sensor
            pos, lookat, up = [getattr(sensor, f"_attached_{key}")[0].cpu().numpy()
                               for key in ("pos", "lookat", "up")]
            error = float(np.max(np.abs(nyx.pos_lookat_up_to_T(pos, lookat, up) - wrist.transform)))
            assert error < 5e-5, error
            errors.append(error)
    assert not np.allclose(poses[0], poses[1]), "Wrist camera did not follow the joint change"
    # Exercise the unmodified shared recorder, including its frame buffers.
    with recording_session(base.scene, [(n, base.cameras[n]) for n in ("oblique", "wrist")],
                           save_to=output / "camera_check.mp4", fps=20, every_n_steps=5):
        controller.step(10)
    for name in ("oblique", "wrist"):
        with imageio.get_reader(output / f"camera_check_{name}.mp4") as reader:
            assert reader.count_frames() == 2
    key = EpisodeKey("presentation_check", 0)
    spec = EpisodeSpec(key, ScenePreset(key.preset_id), TaskVariant(key, instruction="Camera contract check"))
    with EpisodeDatasetWriter(output / "camera_check.h5", base.scene, base.cameras, controller,
                              spec=spec, camera_names=("oblique", "wrist"), every_n_steps=5):
        controller.step(10)
    import h5py
    with h5py.File(output / "camera_check.h5", "r") as dataset:
        episode = dataset["episode_0"]
        assert list(episode["setup"].attrs["camera_renderers"]) == [args.renderer.encode()] * 2
        assert list(episode["setup"].attrs["camera_backgrounds"]) == [b"compact_lab"] * 2
        assert len([name for name in episode if name.startswith("timestep_")]) == 2
        assert episode["timestep_0/obs/wrist_rgb"].shape == (256, 256, 3)
    background_collision_geoms = sum(base.manifest.get(name).n_geoms for name in base.presentation["dressing"])
    assert background_collision_geoms == 0
    report = dict(passed=True, scope="shared_presentation_and_camera_contract_only",
                  **base.presentation, camera_names=list(base.cameras),
                  wrist_rig_errors=errors, wrist_pose_changed=True,
                  dataset_rgb_read=True, recorded_frames_per_camera=2,
                  dataset_frames=2, background_collision_geoms=background_collision_geoms,
                  diagnostic_joint_reset=True, task_rollout_performed=False)
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    review_href = escape(os.path.relpath(ROOT / "docs/progress/current_zh.md", output), quote=True)
    (output / "index.html").write_text('''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>默认实验室与渲染</title>
<style>body{max-width:1100px;margin:32px auto;padding:0 20px;font:17px/1.7 system-ui;background:#eef2f4;color:#263741}img{max-width:100%}a{color:#126b8b}figure{margin:24px 0}</style>
<h1>默认渲染与背景：''' + args.renderer + ''' + compact_lab</h1>
<p>复用封闭实验室：四面墙、顶棚、地板、柜体、白板和门。所有背景物体固定、无碰撞，不参与柔体耦合。</p>
<p><a href="config.yaml">本次配置</a> · <a href="report.json">相机与录制检查</a> · <a href="''' + review_href + '''">返回环境汇总</a></p>
<figure><img src="initial_room.png" alt="实验室全景"><figcaption>房间全景</figcaption></figure>
<figure><img src="initial_oblique.png" alt="默认斜视相机"><figcaption>共享 oblique 视角</figcaption></figure>
<figure><img src="initial_wrist.png" alt="腕部相机"><figcaption>腕部相机</figcaption></figure>
<p>本页验证渲染、相机跟随、RGB 采集与两帧录像；关节位姿变化仅用于检查相机，不代表任务或物理执行验收。</p></html>''')
    print(f"Presentation checks passed: {output / 'index.html'}", flush=True)


if __name__ == "__main__":
    main()
