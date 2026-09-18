"""Static ALOHA 2 dual-arm demo in the shared Nyx laboratory.

    .venv-gs121-nyx/bin/python -m demos.environment_bootstrap.aloha_lab
Use --check-steps 100 for an additional, separately reported joint-hold check.
"""
import argparse
from dataclasses import asdict
from html import escape
import json
from pathlib import Path

import genesis as gs
from hydra import compose, initialize_config_dir
import imageio.v2 as imageio
import numpy as np
from omegaconf import OmegaConf

from topogym.data.episode_dataset_writer import _grab_rgb
from topogym.robot import initialize_robot_controller
from topogym.world import StandardTabletopSceneBuilder, nyx

ROOT = Path(__file__).resolve().parents[2]


def write_preview_page(output, cfg, images):
    sections = []
    observation = list(cfg.env.camera_rig.observation_cameras)
    for title, names in (
        ("官方模型展示视角", ["teleoperator", "collaborator"]),
        ("四路机器人观测", observation),
        ("TopoGym 实验室展示", ["oblique", "front", "room"]),
    ):
        figures = []
        for name in names:
            if name not in images:
                continue
            label = escape(str(cfg.env.cameras[name].get("label", name)))
            description = escape(str(cfg.env.cameras[name].get("description", "")))
            figures.append(f'<figure><a href="{images[name]}"><img src="{images[name]}" alt="{label}"></a>'
                           f'<figcaption>{label}<br>{description}</figcaption></figure>')
        if figures:
            sections.append(f"<h2>{title}</h2>" + "".join(figures))
    (output / "index.html").write_text('''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>ALOHA 双臂 · 相机预设</title>
<style>body{max-width:1120px;margin:40px auto;padding:0 24px;font:17px/1.65 system-ui;background:#edf1f0;color:#243c39}h1{font-size:36px}img{width:100%;border-radius:12px}a{color:#146c74}figure{margin:24px 0}figcaption{padding:8px 0;color:#48605d}</style>
<p>TOPOGYM / ALOHA 2 CAMERA RIG</p><h1>双臂机器人相机预设</h1>
<p>静态 home 姿态；官方模型展示位、四路观测和 TopoGym 实验室展示分别列出。</p>
<p>官方位姿随机器人平移到本实验室；四路观测保持原模型的 16:9 宽高比与垂直视场角，以 640×360 输出。</p>
<p><a href="config.yaml">本次配置</a> · <a href="report.json">验证报告</a> · <a href="../../../configs/camera_configs/README.md">相机预设说明</a> · <a href="../../../docs/develop/modules/dual_arm_aloha_zh.md">双臂接入说明</a></p>
''' + "".join(sections) + '''
<p>这是 TopoGym 的仿真渲染，不是官方演示视频。相机参数来自固定版本的 ALOHA 2 模型；Genesis 的单一 FOV 相机不完整复现 D405 标定内参。任务执行与实机部署尚未验收。</p></html>''')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "runs/environment_bootstrap/aloha_lab")
    parser.add_argument("--renderer", choices=("nyx", "rasterizer"), default="nyx")
    parser.add_argument("--backend", choices=("cuda", "cpu"), default="cuda")
    parser.add_argument("--camera-preset", choices=("aloha_demo", "aloha_observation"), default="aloha_demo")
    parser.add_argument("--check-steps", type=int, default=0)
    parser.add_argument("--viewer", action="store_true")
    args = parser.parse_args()
    if args.check_steps < 0:
        parser.error("--check-steps must be non-negative")
    if args.renderer == "nyx" and args.backend != "cuda":
        parser.error("Nyx requires --backend cuda")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with initialize_config_dir(config_dir=str(ROOT / "configs"), version_base="1.3"):
        cfg = compose(config_name="aloha_lab_preview", overrides=[
            f"env.renderer.type={args.renderer}", f"env.genesis.backend={args.backend}",
            f"camera_configs@env={args.camera_preset}"])
    cfg.env.cameras = OmegaConf.create({name: OmegaConf.to_container(cfg.env.cameras[name], resolve=True)
                                       for name in cfg.env.camera_rig.preview_cameras})
    OmegaConf.save(cfg, output / "config.yaml", resolve=True)
    gs.init(backend=getattr(gs, args.backend), logging_level="warning", seed=0)
    builder = StandardTabletopSceneBuilder(cfg.env, cfg.robot_control, debug_label="aloha")
    base = builder.create(show_viewer=args.viewer)
    builder.finalize(base)
    controller = initialize_robot_controller(scene=base.scene, manifest=base.manifest,
                                              robot_cfg=cfg.robot_control, settle_steps=0)
    robot = controller.robot
    assert int(robot.n_dofs) == 16 and int(robot.n_qs) == 16
    assert set(controller.left.arm_dofs).isdisjoint(controller.right.arm_dofs)
    initial = controller.state()
    for side, arm in controller.arms.items():
        assert np.allclose(arm.arm_qpos(), cfg.robot_control.home[side][:6], atol=1e-6)
        base_pos = robot.get_link(f"{side}/base_link").get_pos().cpu().numpy().reshape(-1, 3)[0]
        assert abs(base_pos[2] - base.frames.table_surface_origin[2]) < 1e-6

    images, camera_checks = {}, {}
    for name, camera in base.cameras.items():
        frame = _grab_rgb(camera)
        assert frame.shape == (camera.res[1], camera.res[0], 3)
        assert frame.dtype == np.uint8 and frame.std() > 5, f"Blank render: {name}"
        filename = f"{name}.png"
        imageio.imwrite(output / filename, frame)
        images[name] = filename
        camera_checks[name] = dict(shape=list(frame.shape), std=float(frame.std()),
                                   world_from_camera=camera.transform.tolist(),
                                   vertical_fov_deg=float(cfg.env.cameras[name].fov))
        if name.startswith("wrist") and args.renderer == "nyx":
            sensor = camera.sensor
            pose = [getattr(sensor, f"_attached_{key}")[0].cpu().numpy()
                    for key in ("pos", "lookat", "up")]
            error = float(np.max(np.abs(nyx.pos_lookat_up_to_T(*pose) - camera.transform)))
            assert error < 5e-5, error
            camera_checks[name]["attachment_error"] = error
    assert not np.allclose(base.cameras["wrist"].transform, base.cameras["wrist_right"].transform)
    background_geoms = sum(base.manifest.get(name).n_geoms for name in base.presentation["dressing"])
    assert background_geoms == 0
    hold = dict(performed=False)
    if args.check_steps:
        controller.step(args.check_steps)
        final = controller.state()
        drift = {side: float(np.max(np.abs(np.asarray(final[side]["arm_qpos"])
                                            - initial[side]["arm_qpos"]))) for side in controller.arms}
        assert all(np.isfinite(v) and v < 0.15 for v in drift.values()), drift
        hold = dict(performed=True, steps=args.check_steps, seconds=args.check_steps * float(cfg.env.sim.dt),
                    max_arm_drift_rad=drift, final_state=final, passed=True)
    report = dict(passed=True, scope="static_dual_arm_lab_integration", robot="aloha_2",
                  **base.presentation, n_dofs=int(robot.n_dofs), native_actuator_count=14,
                  arms=initial, robot_footprint=asdict(base.robot_footprint),
                  camera_checks=camera_checks, images=images, background_collision_geoms=background_geoms,
                  camera_rig=OmegaConf.to_container(cfg.env.camera_rig, resolve=True),
                  static_preview_simulation_steps=0, hold_check=hold,
                  task_rollout_performed=False, hardware_deployment_validated=False)
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    write_preview_page(output, cfg, images)
    print(f"ALOHA demo: {output / 'index.html'}", flush=True)
    if args.viewer:
        try:
            while base.scene.viewer.is_alive():
                controller.step(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
