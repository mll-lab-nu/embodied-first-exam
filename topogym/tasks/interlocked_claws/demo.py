"""Render original meshes, reference start, separated inspection, and camera orbit.

This is a zero-step scene inspection. The initial parts are pregrasped in the
reference recording; physical grasp constraints and extraction are future work.
"""
import json
from pathlib import Path

import hydra
import numpy as np
from omegaconf import OmegaConf
from PIL import Image
from scipy.spatial.transform import Rotation


def write_review(output, report):
    geometry = report["geometry"]
    video = ('<section><h2>初态环绕</h2><video controls loop preload="metadata" '
             'poster="initial_detail.png" src="preview.mp4"></video>'
             '<p>只有相机运动，机器人和零件保持初态。</p></section>') if report["video_created"] else ""
    robot = "原始 ALOHA 双臂起始关节姿态已复原，末端坐标已核对。" if report["robot_present"] else "本次未加载机器人。"
    (output / "index.html").write_text(f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Interlocked Claws · 原始模型场景</title>
<style>body{{max-width:1180px;margin:36px auto;padding:0 22px;background:#eef2f4;color:#25333e;font:17px/1.7 system-ui}}section{{background:white;padding:24px;margin:22px 0;border-radius:12px}}img,video{{width:100%;border-radius:8px}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}figure{{margin:0}}a{{color:#146b98}}td{{padding:10px;border-bottom:1px solid #ddd}}@media(max-width:760px){{.grid{{grid-template-columns:1fr}}}}</style>
<p><a href="../../index.html">← 环境汇总</a> / TOPOGYM</p>
<h1>Claw 互锁件：原始几何与基础场景</h1>
<p>直接导入作者演示页的两件原始 OBJ，保留弯爪、曲面、凹槽和连接结构，以及参考初始装配关系。</p>
<section><img src="initial_detail.png" alt="橙色与青蓝色原始互锁件"><p>参考初态，按原始 0.1 m / 模型单位缩放；仅整体平移到 TopoGym 桌面坐标。</p></section>
<section class="grid"><figure><img src="initial_opposite.png" alt="互锁装配背面"><figcaption>背面结构与互锁空间</figcaption></figure><figure><img src="parts_inspection.png" alt="两件独立结构"><figcaption>显式重置后的拆件检查，仅用于看清模型结构</figcaption></figure></section>
<section><img src="initial_overview.png" alt="完整双臂实验室"><p>{robot}保留作者的 15 个支架几何，使用共享 Nyx 实验室与桌面。</p></section>
{video}
<section><h2>模型文件与检查</h2><table>
<tr><td>原始三角面</td><td>橙色 14,780；青蓝色 14,480；SHA-256 与上游清单一致</td></tr>
<tr><td>实体结构</td><td>每件为单一、封闭、法向一致的非凸实体；各为独立 6 自由度刚体</td></tr>
<tr><td>初态间隙</td><td>{geometry['initial_surface_clearance_m']*1000:.4f} mm；原始三角网格未相交</td></tr>
<tr><td>碰撞导入</td><td>保留原始三角面，关闭凸化和简化；Genesis 接触查询采用采样 SDF，尚未完成动力学验收</td></tr>
<tr><td>当前范围</td><td>模型、初态、双臂位姿、支架和渲染。物理步数为 0；尚未安装抓持约束或执行脱困</td></tr>
</table><p><a href="assets/assembly.glb">初态装配 GLB</a> · <a href="assets/separated_inspection.glb">拆件 GLB</a> ·
<a href="assets/claw_0/mesh.obj">橙色 OBJ（米）</a> · <a href="assets/claw_1/mesh.obj">青蓝色 OBJ（米）</a> ·
<a href="assets/claw_0/claw_0.urdf">橙色 URDF</a> · <a href="assets/claw_1/claw_1.urdf">青蓝色 URDF</a></p>
<p><a href="inspection_report.json">本次检查报告</a> · <a href="config.yaml">配置快照</a> · <a href="assets/reference_scene.json">来源、单位与初态变换</a></p>
<p>来源：<a href="https://qinengwang-aiden.github.io/demos/constraint_demos/">Qineng Wang 演示页</a> ·
<a href="https://qinengwang-aiden.github.io/demos/constraint_demos/methods.html">作者方法与来源说明</a>。
零件来自 C-Space Tunnel Discovery for Puzzle Path Planning 补充材料。上游未确认几何单独再分发许可；模型不套用本项目代码许可证。</p></section></html>''')


@hydra.main(version_base="1.3", config_path=str(Path(__file__).resolve().parents[3] / "configs"),
            config_name="interlocked_claws_preview")
def main(cfg):
    import genesis as gs
    import imageio.v2 as imageio
    from .scene import as_numpy, build_scene

    if (not np.isfinite([cfg.run.video_seconds, cfg.run.fps, cfg.run.orbit_degrees]).all()
            or cfg.run.video_seconds <= 0 or cfg.run.fps <= 0):
        raise ValueError("Video duration and frame rate must be positive and finite")
    output = Path(cfg.run.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    cfg.env.cameras = OmegaConf.create({name: OmegaConf.to_container(cfg.env.cameras[name], resolve=True)
                                       for name in ("overview", "detail", "opposite")})
    OmegaConf.save(cfg, output / "config.yaml", resolve=True)
    gs.init(backend=getattr(gs, str(cfg.env.genesis.backend)), precision=str(cfg.env.genesis.precision),
            logging_level="warning", seed=int(cfg.task.seed))
    print("Building original Claw meshes and reference ALOHA pose", flush=True)
    task = build_scene(cfg, output / "assets")
    initial = {name: as_numpy(body.get_qpos()).copy() for name, body in task.bodies.items()}
    robot_initial = as_numpy(task.controller.robot.get_qpos()).copy() if task.controller else None
    images = {}
    for name, camera in task.cameras.items():
        rgb = camera.render(force_render=True)[0]
        if np.std(rgb) < 5:
            raise RuntimeError(f"Blank camera: {name}")
        Image.fromarray(rgb).save(output / f"initial_{name}.png")
        images[name] = dict(resolution=list(camera.res), pixel_std=float(rgb.std()))
        print(f"Rendered {name}", flush=True)
    camera, cc = task.cameras["detail"], cfg.env.cameras.detail
    aim, offset = np.asarray(cc.lookat), np.asarray(cc.pos)-np.asarray(cc.lookat)
    if cfg.run.record_video:
        count = max(1, round(float(cfg.run.video_seconds)*int(cfg.run.fps)))
        with imageio.get_writer(output / "preview.mp4", fps=int(cfg.run.fps), codec="libx264", quality=8,
                               macro_block_size=1, ffmpeg_log_level="error") as writer:
            for i in range(count):
                angle = float(cfg.run.orbit_degrees)*(.5-.5*np.cos(np.pi*i/max(1, count-1)))
                camera.set_pose(pos=aim+Rotation.from_euler("z", angle, degrees=True).apply(offset),
                                lookat=aim, up=(0, 0, 1))
                writer.append_data(camera.render(force_render=True)[0])
                if i % 18 == 0:
                    print(f"Camera orbit {i}/{count}", flush=True)
    drift = max(float(np.max(np.abs(as_numpy(task.bodies[n].get_qpos())-q))) for n, q in initial.items())
    if task.controller:
        drift = max(drift, float(np.max(np.abs(as_numpy(task.controller.robot.get_qpos())-robot_initial))))
    if drift != 0:
        raise RuntimeError("Camera-only inspection moved scene entities")
    # Explicit display reset: this is deliberately not presented as extraction.
    display_center = task.world_offset + np.array([0, -.18, .40])
    if task.controller:
        task.controller.reset_home(settle_steps=0)
    for i, b in enumerate(task.assembly.bodies):
        center = b.mesh.copy().apply_transform(b.pose).bounds.mean(axis=0)
        delta = display_center + np.array([(i-.5)*.38, 0, 0]) - (task.world_offset+center)
        task.bodies[b.name].set_pos(initial[b.name][:3]+delta)
    task.scene.visualizer.update_visual_states(force_render=True)
    camera.set_pose(pos=display_center+[.12, -1.10, .52], lookat=display_center, up=(0, 0, 1))
    Image.fromarray(camera.render(force_render=True)[0]).save(output / "parts_inspection.png")
    for name, body in task.bodies.items():
        body.set_qpos(initial[name], zero_velocity=True)
    if task.controller:
        task.controller.robot.set_qpos(robot_initial, zero_velocity=True)
        for arm in task.controller.arms.values():
            q = robot_initial[arm.qs_idx]
            task.controller.robot.control_dofs_position(q[:7], arm.actuated_dofs)
    task.scene.visualizer.update_visual_states(force_render=True)
    camera.set_pose(pos=cc.pos, lookat=cc.lookat, up=(0, 0, 1))
    restore_error = max(float(np.max(np.abs(as_numpy(task.bodies[n].get_qpos())-q))) for n, q in initial.items())
    if restore_error > 1e-9:
        raise RuntimeError("Inspection failed to restore the reference assembly")
    report = dict(scope="original_claw_geometry_and_reference_initial_scene", geometry=task.asset_report,
        loading=task.loading_report, renderer=str(cfg.env.renderer.type), backend=str(cfg.env.genesis.backend),
        robot_present=bool(cfg.run.include_robot), source_initial_state="pregrasped reference pose",
        grasp_constraints_installed=False, physics_steps=0, full_task_deployed=False,
        extraction_verified=False, dynamics_qualified=False, video_created=bool(cfg.run.record_video),
        camera_motion_only=True, max_static_qpos_change=drift,
        parts_inspection_is_pose_reset=True, parts_inspection_restore_error=restore_error,
        reference_to_world_translation_m=task.world_offset.tolist(), images=images,
        initial_body_qpos={n: q.tolist() for n, q in initial.items()},
        initial_robot_qpos=None if robot_initial is None else robot_initial.tolist(),
        sdf=dict(requested_cell_size_m=float(cfg.task.sdf_cell_size_m), max_res=int(cfg.task.sdf_max_res)),
        solver=dict(dt=float(cfg.env.sim.dt), substeps=int(cfg.env.sim.substeps), iterations=100,
                    constraint_timeconst=.001, max_collision_pairs=8192, friction=.3))
    (output / "inspection_report.json").write_text(json.dumps(report, indent=2) + "\n")
    write_review(output, report)
    print(f"Claw initial scene: {output / 'index.html'}", flush=True)
    if cfg.run.viewer:
        # Static inspection has no physical grasp constraints, so do not step.
        import time
        while task.scene.viewer.is_alive():
            task.scene.visualizer.update()
            time.sleep(1/30)


if __name__ == "__main__":
    main()
