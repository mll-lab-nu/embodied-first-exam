"""Render the current task reset, separate part inspection, and gravity probe.

The part-inspection poses are explicit display resets, not a solution animation.
All poses are restored before the optional physical settling check.
"""
import hashlib
from html import escape
import json
from pathlib import Path

import hydra
import numpy as np
from omegaconf import OmegaConf
from PIL import Image
from scipy.spatial.transform import Rotation


def as_numpy(value):
    return value.detach().cpu().numpy() if hasattr(value, "detach") else np.asarray(value)


def check_settling(task, cfg):
    dt, seconds = float(cfg.env.sim.dt), float(cfg.run.settle_seconds)
    steps = max(1, round(seconds/dt))
    initial = {n: as_numpy(b.get_pos()).copy() for n, b in task.bodies.items()}
    initial_rot = {n: Rotation.from_quat(as_numpy(b.get_quat())[[1, 2, 3, 0]]) for n, b in task.bodies.items()}
    penetration, drift, rotation_drift, tail_speed = 0., 0., 0., []
    tail_start = max(0, steps-max(1, round(min(.1, seconds/2)/dt)))
    for i in range(steps):
        task.scene.step()
        contacts = task.scene.sim.rigid_solver.collider.get_contacts()
        p = as_numpy(contacts["penetration"])
        if p.size:
            penetration = max(penetration, float(p.max()))
        speeds = []
        for name, body in task.bodies.items():
            q, v = as_numpy(body.get_qpos()), as_numpy(body.get_vel())
            angular = as_numpy(body.get_ang())
            if not np.isfinite(np.r_[q, v, angular]).all():
                raise RuntimeError("Non-finite coil state during settling")
            drift = max(drift, float(np.linalg.norm(as_numpy(body.get_pos())-initial[name])))
            rot = Rotation.from_quat(as_numpy(body.get_quat())[[1, 2, 3, 0]])
            rotation_drift = max(rotation_drift, float((initial_rot[name].inv()*rot).magnitude()))
            speeds.append(float(np.linalg.norm(v)))
        if i >= tail_start:
            tail_speed.append(max(speeds))
        if i % max(1, steps//5) == 0:
            print(f"Free settling {i+1}/{steps}", flush=True)
    result = dict(scope="short free gravity settling; no extraction or interlock certificate",
        physics_steps=steps, simulated_seconds=steps*dt, max_penetration_m=penetration,
        max_body_displacement_m=drift, max_body_rotation_rad=rotation_drift,
        final_window_max_speed_m_s=max(tail_speed),
        pose_writes_during_probe=False, assistance="none", contact_penetration_limit_m=.0005,
        passed=penetration < .0005 and drift < .003 and rotation_drift < .05 and max(tail_speed) < .01)
    return result


def write_review(output, report):
    g = report["geometry"]
    assembling = report.get("objective") == "assemble"
    intro = ("初态为 x、y 两方向均分离的金、银两件。目标是将两件聚合成四层交替的方形装配，并松手后稳定保持。"
             if assembling else "金、银两件形成四层交替的方形装配，中央保留通孔。每件是独立自由刚体，内侧缺口和侧桥参与碰撞。")
    parts = ['<!doctype html><html lang="zh-CN"><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        '<title>Cast Coil · 基础场景</title><style>',
        'body{max-width:1120px;margin:36px auto;padding:0 22px;background:#f3f4f6;color:#27343e;'
        'font:17px/1.7 system-ui}section{background:white;padding:24px;border:1px solid #dce1e5;'
        'border-radius:12px;margin:22px 0}img,video{width:100%;border-radius:8px}a{color:#146b98}'
        '.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}figure{margin:0}figcaption{color:#596672}'
        'td,th{border-bottom:1px solid #e1e5ea;padding:10px;text-align:left}table{width:100%;border-collapse:collapse}'
        '@media(max-width:760px){.grid{grid-template-columns:1fr}}</style>',
        '<p><a href="../../index.html">← 环境汇总</a></p><h1>Cast Coil：方形卷绕件基础场景</h1>',
        '<p>'+intro+'</p>',
        '<section class="grid"><figure><a href="initial_detail.png"><img src="initial_detail.png" alt="金银交错装配近景"></a>'
        '<figcaption>任务初态：两个独立自由刚体。</figcaption></figure>'
        '<figure><a href="initial_opposite.png"><img src="initial_opposite.png" alt="装配背面"></a>'
        '<figcaption>反向观察零件的通孔和侧边连接。</figcaption></figure></section>',
        '<section><img src="initial_overview.png" alt="共享实验室桌面场景"><p>共享 Nyx 实验室和桌面。'
        + ('Panda + Robotiq 2F-85 仅作静止尺度参照。' if report["robot_present"] else '本次未加载机器人。') + '</p></section>',
        '<section><h2>单件结构检查</h2><img src="parts_inspection.png" alt="两件分开展示">'
        '<p>单独重置到分开展示位置，便于检查回折、侧桥与内侧缺口；此图不表示已执行合法拆解路径。</p></section>']
    if report["video_created"]:
        parts.append('<section><h2>初态绕行观察</h2><video controls loop preload="metadata" '
            'poster="initial_detail.png" src="preview.mp4"></video><p>相机绕行，零件保持初态。</p></section>')
    parts.extend(['<section><h2>实现与验证范围</h2><table>',
        f'<tr><td>尺寸</td><td>原型 34 × 24.75 × 34 mm，统一 {g["scale"]:g} 倍；不是实测尺寸</td></tr>',
        '<tr><td>刚体</td><td>2 个单 link 自由刚体，各 6 自由度；零件之间无关节或焊接</td></tr>',
        f'<tr><td>几何检查</td><td>{"通过" if g["passed"] else "未通过"}；每件为连通封闭实体，孔道未被碰撞凸包填平；'
        f'初态最小间隙 {g["minimum_initial_clearance_m"]*1000:.2f} mm</td></tr>',
        '<tr><td>资产状态</td><td>据官方照片与解法图重建的基础原型；内侧槽口尺寸、圆弧和倒角仍需核实</td></tr>',
        '<tr><td>本页范围</td><td>仅初态检查；完整机器人执行以独立 Demo 与物理报告为准</td></tr></table>',
        f'<p>本次渲染：{escape(report["renderer"])} / {escape(report["backend"])}。</p>',
        '<p><a href="inspection_report.json">场景报告</a> · <a href="assets/geometry_report.json">几何报告</a> · '
        '<a href="config.yaml">配置快照</a> · <a href="assets/template.json">尺寸模板</a> · '
        '<a href="assets/assembly.glb">装配 GLB</a> · <a href="assets/separated_inspection.glb">拆件检查 GLB</a></p>',
        '<p>来源：<a href="https://hanayama-toys.com/product/cast-coil/">Hanayama 产品说明</a> · '
        '<a href="https://store.hanayamatoys.co.jp/items/55630234">官方装配与拆件照片</a> · '
        '<a href="https://www.eureka-puzzle.eu/wp-content/uploads/2022/09/515056-Huzzle-Cast-Coil-Oct-2017.pdf">官方分解示意</a></p></section>'])
    if s := report.get("settling"):
        parts.append('<section><h2>短时自由落桌检查</h2>'
            f'<p>{s["simulated_seconds"]:.3f} 秒：{"通过" if s["passed"] else "未通过"}。最大接触穿透 '
            f'{s["max_penetration_m"]*1000:.3f} mm，最大位移 {s["max_body_displacement_m"]*1000:.3f} mm。'
            '此结果只覆盖当前原型的初态稳定性。</p><img src="settled_detail.png" alt="静置后的装配"></section>')
    parts.append('</html>')
    (output/"index.html").write_text("\n".join(parts))


@hydra.main(version_base="1.3", config_path=str(Path(__file__).resolve().parents[3]/"configs"), config_name="cast_coil_preview")
def main(cfg):
    import genesis as gs
    import imageio.v2 as imageio
    from .scene import build_scene

    values = [cfg.run.video_seconds, cfg.run.fps, cfg.run.settle_seconds, cfg.env.sim.dt, cfg.run.orbit_degrees]
    if not np.isfinite(values).all() or min(values[:2]) <= 0 or cfg.run.settle_seconds < 0 or cfg.env.sim.dt <= 0:
        raise ValueError("Invalid video/probe durations or timestep")
    output = Path(cfg.run.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    cfg.env.cameras = OmegaConf.create({n: OmegaConf.to_container(cfg.env.cameras[n], resolve=True)
                                       for n in ("overview", "detail", "opposite", "video")})
    OmegaConf.save(cfg, output/"config.yaml", resolve=True)
    gs.init(backend=gs.cuda if cfg.env.genesis.backend == "cuda" else gs.cpu,
            logging_level="warning", seed=int(cfg.task.seed))
    print("Building two free Cast Coil pieces", flush=True)
    task = build_scene(cfg, output/"assets")
    if cfg.run.include_robot:
        from topogym.utils.franka import initialize_franka_controller
        initialize_franka_controller(scene=task.scene, manifest=task.manifest,
                                     robot_cfg=cfg.robot_control, settle_steps=0)
    initial = {n: as_numpy(b.get_qpos()).copy() for n, b in task.bodies.items()}
    # Same-time pose resets need a render-transform refresh as well as sensor
    # invalidation in Genesis 1.2.1 / Nyx 0.1.4; camera force_render alone is insufficient.
    task.scene.visualizer.update_visual_states(force_render=True)
    for name in ("overview", "detail", "opposite"):
        Image.fromarray(task.cameras[name].render(force_render=True)[0]).save(output/f"initial_{name}.png")
        print(f"Rendered {name}", flush=True)
    if cfg.run.record_video:
        camera, cc = task.cameras["video"], cfg.env.cameras.video
        aim, offset = np.asarray(cc.lookat), np.asarray(cc.pos)-np.asarray(cc.lookat)
        count = max(1, round(float(cfg.run.video_seconds)*int(cfg.run.fps)))
        with imageio.get_writer(output/"preview.mp4", fps=int(cfg.run.fps), codec="libx264", quality=8,
                               macro_block_size=1, ffmpeg_log_level="error") as writer:
            for i in range(count):
                angle = float(cfg.run.orbit_degrees)*(.5-.5*np.cos(np.pi*i/max(1, count-1)))
                camera.set_pose(pos=aim+Rotation.from_euler("z", angle, degrees=True).apply(offset),
                                lookat=aim, up=(0, 0, 1))
                writer.append_data(camera.render(force_render=True)[0])
                if i % 20 == 0:
                    print(f"Camera orbit {i}/{count}", flush=True)
    drift = max(float(np.max(np.abs(as_numpy(task.bodies[n].get_qpos())-q))) for n, q in initial.items())
    if drift != 0:
        raise RuntimeError("Camera-only preview moved coil bodies")
    # Explicit display layout, restored before physics. Never present this as
    # an extraction trajectory, and never write poses during the gravity probe.
    camera = task.cameras["detail"]
    for sign, (name, body) in zip((-1, 1), task.bodies.items()):
        displacement = task.rotation.apply([sign*.75*task.assembly.template["outer_width"]*task.assembly.unit, 0, 0])
        body.set_pos(initial[name][:3]+displacement)
    task.scene.visualizer.update_visual_states(force_render=True)
    aim = task.origin
    camera.set_pose(pos=aim+np.array([.20, -.65, .42]), lookat=aim, up=(0, 0, 1))
    Image.fromarray(camera.render(force_render=True)[0]).save(output/"parts_inspection.png")
    for name, body in task.bodies.items():
        body.set_qpos(initial[name], zero_velocity=True)
    task.scene.visualizer.update_visual_states(force_render=True)
    camera.set_pose(pos=cfg.env.cameras.detail.pos, lookat=cfg.env.cameras.detail.lookat, up=(0, 0, 1))
    restore_error = max(float(np.max(np.abs(as_numpy(task.bodies[n].get_qpos())-q))) for n, q in initial.items())
    if restore_error > 1e-7:
        raise RuntimeError("Part inspection did not restore the initial assembly")
    report = dict(scope="cast_coil_prototype_initial_scene", variant=str(cfg.task.variant), objective=cfg.task.get("objective", "disassemble"),
        full_task_deployed=False, measured_replica=False, extraction_route_verified=False,
        turning_windows_verified=False, dual_arm_qualified=False, robot_present=bool(cfg.run.include_robot),
        robot_role="stationary scale reference" if cfg.run.include_robot else None,
        renderer=str(cfg.env.renderer.type), backend=str(cfg.env.genesis.backend),
        video_created=bool(cfg.run.record_video), camera_motion_only=True, static_preview_physics_steps=0,
        parts_inspection_is_pose_reset=True, parts_inspection_restore_error=restore_error,
        max_static_qpos_change=drift, body_free_dofs={n: int(b.n_dofs) for n, b in task.bodies.items()},
        inter_body_joints=False, initial_body_qpos={n: q.tolist() for n, q in initial.items()},
        assembly_origin_m=task.origin.tolist(), geometry=task.asset_report,
        solver=dict(dt=float(cfg.env.sim.dt), substeps=int(cfg.env.sim.substeps), iterations=100,
                    constraint_timeconst=.001, friction=.35, max_collision_pairs=4096))
    if cfg.run.settle_seconds:
        report["settling"] = check_settling(task, cfg)
        Image.fromarray(camera.render(force_render=True)[0]).save(output/"settled_detail.png")
    report["gravity_stability_verified"] = bool(report.get("settling", {}).get("passed", False))
    (output/"inspection_report.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n")
    write_review(output, report)
    artifacts = {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in sorted(output.rglob("*")) if p.is_file() and p.name != "artifact_manifest.json"}
    (output/"artifact_manifest.json").write_text(json.dumps(artifacts, indent=2)+"\n")
    print(f"Review: {output/'index.html'}", flush=True)
    if report.get("settling") and not report["settling"]["passed"]:
        raise SystemExit("Scene rendered, but the free settling check did not pass")


if __name__ == "__main__":
    main()
