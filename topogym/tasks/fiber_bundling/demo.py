"""Build, briefly simulate and render the branched cable in the shared lab."""
import json
from pathlib import Path

import hydra
import numpy as np
from omegaconf import OmegaConf


@hydra.main(version_base="1.3", config_path=str(Path(__file__).resolve().parents[3]/"configs"),
            config_name="fiber_bundling_preview")
def main(cfg):
    import genesis as gs
    import imageio.v2 as imageio
    from PIL import Image
    from topogym.utils.franka import initialize_franka_controller
    from .scene import FiberSceneBuilder, as_numpy

    if cfg.task.variant not in ("branched_passive_v1", "anchored_terminal_v2"):
        raise ValueError("Unknown fiber bundling variant")
    if cfg.run.settle_steps < 0 or cfg.run.fps <= 0 or cfg.run.video_seconds <= 0:
        raise ValueError("Invalid simulation or video duration")
    output = Path(cfg.run.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    cfg.env.cameras = OmegaConf.create({n: OmegaConf.to_container(cfg.env.cameras[n], resolve=True)
                                       for n in ("overview", "detail", "axial", "cable_end", "terminal")
                                       if n in cfg.env.cameras})
    OmegaConf.save(cfg, output/"config.yaml", resolve=True)
    gs.init(backend=gs.cuda if cfg.env.genesis.backend == "cuda" else gs.cpu,
            logging_level="warning", seed=int(cfg.task.geometry.seed))
    print("Building passive branched cable and fixed ring", flush=True)
    task = FiberSceneBuilder(cfg.env, cfg.task, cfg.robot_control).build(
        asset_dir=output/"assets", show_viewer=bool(cfg.run.viewer))
    initialize_franka_controller(scene=task.scene, manifest=task.manifest,
                                 robot_cfg=cfg.robot_control, settle_steps=0)
    initial = task.state()
    q0 = as_numpy(task.bundle.get_qpos()).copy()
    robot_contact_steps = 0
    for _ in range(int(cfg.run.settle_steps)):
        task.step()
        robot_contact_steps += int(len(task.bundle.get_contacts(with_entity=task.manifest.get("robot"))["force_a"]) > 0)
    final = task.state()
    drift = float(np.max(np.linalg.norm(final["fibers_m"]-initial["fibers_m"], axis=-1)))
    for name, camera in task.cameras.items():
        Image.fromarray(camera.render(force_render=True)[0]).save(output/f"initial_{name}.png")
        print(f"Rendered {name}", flush=True)
    if cfg.run.record_video:
        camera = task.cameras["detail"]
        cam_cfg = cfg.env.cameras.detail
        target = np.asarray(cam_cfg.lookat)
        offset = np.asarray(cam_cfg.pos)-target
        count = round(float(cfg.run.video_seconds)*int(cfg.run.fps))
        with imageio.get_writer(output/"preview.mp4", fps=int(cfg.run.fps), codec="libx264",
                               quality=8, macro_block_size=1, ffmpeg_log_level="error") as writer:
            for i in range(count):
                angle = np.radians(32)*i/max(1, count-1)
                c, s = np.cos(angle), np.sin(angle)
                camera.set_pose(pos=target+[c*offset[0]-s*offset[1], s*offset[0]+c*offset[1], offset[2]],
                                lookat=target, up=(0, 0, 1))
                writer.append_data(camera.render(force_render=True)[0])
                if i % 20 == 0:
                    print(f"Camera preview {i}/{count}", flush=True)
    report = dict(scope="basic_scene_and_free_settle_only", variant=str(cfg.task.variant),
        robot_present=True, robot_tool="Panda + Robotiq 2F-85", robot_manipulation_executed=False,
        fiber_count=task.layout.fiber_count, fiber_length_m=task.layout.fiber_length_m,
        initial_tip_tangent_range_deg=[task.layout.fan_angle_min_deg, task.layout.fan_angle_max_deg],
        initial_curve="axial sleeve exit then gradual outward bend; initialization only",
        cable_dofs=int(task.bundle.n_dofs),
        simulation_steps=int(cfg.run.settle_steps), simulated_seconds=int(cfg.run.settle_steps)*float(cfg.env.sim.dt),
        max_fiber_settle_displacement_m=drift, max_root_error_m=final["max_root_error_m"],
        robot_cable_contact_steps=robot_contact_steps,
        contact_rule=final["contact_rule"], episode_failed=final["failed"],
        max_cable_qpos_change=float(np.max(np.abs(as_numpy(task.bundle.get_qpos())-q0))),
        gravity_neutral_settle_passed=bool(cfg.run.settle_steps > 0 and drift < 1e-4
                                         and robot_contact_steps == 0 and not final["failed"]),
        ring_center_m=task.ring_center.tolist(), renderer=str(cfg.env.renderer.type),
        gravity_compensation_scope="whole cable; world gravity unchanged", video_camera_motion_only=True,
        full_threading_verified=False, robot_reachability_qualified=False,
        graspable_links=task.asset_report["graspable_links"])
    report["ring_fixture"] = task.asset_report["ring_fixture_signature"]
    if task.asset_report.get("terminal_fixed"):
        report.update(scope="anchored_terminal_scene_and_short_settle",terminal_fixed=True,
            fixture_spacing=task.asset_report["fixture_spacing"],
            anchor_layout=task.asset_report["anchor"],
            cradle_center_m=(task.origin+np.array([task.asset_report["anchor"]["cradle_x_m"],0,0])).tolist(),
            free_cable_root=False,lead_length_m=task.asset_report["lead_length_m"],
            initial_cradle="fixed open U support, contact only",
            anchor_error_m=final["threading"]["max_attachment_error_m"],
            threading=final["threading"],legacy_free_cable_results_apply=False)
    (output/"inspection_report.json").write_text(json.dumps(report, indent=2)+"\n")
    np.savez_compressed(output/"settle_states.npz", initial=initial["fibers_m"], final=final["fibers_m"])
    (output/"index.html").write_text('''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>光纤收束 · 分叉绳基础场景</title>
<style>body{max-width:1120px;margin:36px auto;padding:0 24px;background:#f4f6f8;color:#203143;font:17px/1.7 system-ui}
img,video{width:100%;border-radius:12px}section{background:white;padding:24px;margin:20px 0;border-radius:14px}a{color:#126995}</style>
<h1>光纤收束 · 粗绳末端分叉</h1><p>''' +
        f'{2*task.layout.trunk_radius_m*1000:g} mm 粗绳连接 {task.layout.fiber_count} 根 '
        f'{2*task.layout.fiber_radius_m*1000:g} mm 细绳，露出长度 {task.layout.fiber_length_m*1000:g} mm，'
        f'穿过内径 {2*task.layout.ring_inner_radius_m*1000:g} mm 的固定闭环。' + '''
黑色电缆护套包裹彩色绝缘线，端部可见护套切口、填充层与短铜丝线头。
连接点固定在端面，细绳先沿护套轴向伸出，再逐渐向外弯曲，各线曲率略有不同。
曲线仅用于初始化；被动关节无回弹弹簧，有阻尼、碰撞和重力补偿，碰撞后可保留新形状。机械臂抓取接口只接受粗绳。</p>
<p><a href="inspection_report.json">初态与静置报告</a> · <a href="assets/asset_report.json">资产参数</a> ·
<a href="config.yaml">复现配置</a> · <a href="../contact_probe/index.html">碰撞与卸载形变验证</a> ·
<a href="../single_strand_demo/index.html">单根红线整理过程</a> · <a href="../../index.html">环境汇总</a></p>
<section><h2>整体场景</h2><img src="initial_overview.png" alt="机械臂、分叉绳与固定环"></section>
<section><h2>细绳与环口</h2><img src="initial_detail.png" alt="电线沿轴向伸出再自然外弯"></section>
<section><h2>电缆切口与绝缘线细节</h2><img src="initial_cable_end.png" alt="黑色电缆护套、彩色绝缘线和铜丝端头"></section>
<section><h2>沿环轴观察</h2><img src="initial_axial.png" alt="环孔与分散细绳的尺度对照"></section>
''' + ('<section><h2>初态环绕预览</h2><video controls src="preview.mp4"></video></section>' if cfg.run.record_video else '') + '''
<p>当前交付为资产、基础场景与局部物理检查；视频仅移动相机。尚未执行机器人完整捋顺穿环，未认证微米光纤材料或连续细杆接触精度。
形状保持采用零刚度阻尼关节近似，不包含铜材屈服与硬化本构。
整个绳组件均采用重力补偿，粗绳也是中性浮力；桌面和其他物体仍使用正常重力。</p></html>''')
    if task.asset_report.get("terminal_fixed"):
        page=(output/"index.html").read_text()
        page=page.replace("<h1>光纤收束 · 粗绳末端分叉</h1>",
            '<h1>光纤收束 · 固定电源终端与承托支架</h1><p>电缆尾端永久连接固定电源终端，'
            '通过约 830 mm 的弯曲粗线保留操作余量；前部 240 mm 工作段放在独立开放托架上。'
            '托架只通过接触承托，允许向上提起。终端和环不能移动，机械臂只能抓工作粗绳。</p>'
            f'<p>新成功条件：分叉端先入孔、{task.layout.fiber_count} 根细线及前端护套穿过环，尾端保持连接。'
            '反向／中段先入环、绕过孔洞、移动终端或环会使本次执行无效。'
            '夹爪手指、外壳或连杆直接接触任意细线也立即判失败，撤开后仍无效。'
            '旧版自由电缆 demo 和通过结果仅作历史参考，不能用于新版验收。</p>')
        page=page.replace('<section><h2>细绳与环口</h2>', '<section><h2>固定终端、余量电缆与托架</h2>')
        page=page.replace('<section><h2>沿环轴观察</h2>',
            '<section><h2>固定电源终端与出线口</h2><img src="initial_terminal.png"></section>'
            '<section><h2>沿环轴观察</h2>')
        page=page.replace('<a href="inspection_report.json">初态与静置报告</a>',
            '<a href="inspection_report.json">初态与静置报告</a> · '
            '<a href="../../../environment-solvability/fiber_bundling/anchored_attachment/report.json">新版固定连接与施力检查</a>')
        page=page.replace('>碰撞与卸载形变验证</a>','>历史自由电缆卸载试验</a>')
        page=page.replace('>单根红线整理过程</a>','>历史自由电缆单根整理</a>')
        page=page.replace('<p>当前交付为资产、基础场景与局部物理检查；',
            f'<p>本次预览渲染后端：{report["renderer"]}；物理后端：{cfg.env.genesis.backend}。'
            '当前交付为资产、基础场景与局部物理检查；')
        (output/"index.html").write_text(page)
    print(json.dumps(report, indent=2), flush=True)
    print(output/"index.html", flush=True)
    if cfg.run.settle_steps > 0 and not report["gravity_neutral_settle_passed"]:
        raise SystemExit("Free-settle check failed; see inspection_report.json")


if __name__ == "__main__":
    main()
