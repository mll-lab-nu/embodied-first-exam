"""Inspect the reconstructed plates; camera orbit and display resets are not solutions."""
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
    from .geometry import mesh_clearance

    dt, seconds = float(cfg.env.sim.dt), float(cfg.run.settle_seconds)
    steps = max(1, round(seconds/dt))
    initial = {n: as_numpy(b.get_qpos()).copy() for n, b in task.bodies.items()}
    max_penetration = max_drift = max_angle = 0.0
    tail_linear, tail_angular = [], []
    tail_start = max(0, steps-max(1, round(min(.1, seconds/2)/dt)))
    for i in range(steps):
        task.scene.step()
        contacts = task.scene.sim.rigid_solver.collider.get_contacts()
        p = as_numpy(contacts["penetration"])
        if p.size:
            max_penetration = max(max_penetration, float(p.max()))
        for name, body in task.bodies.items():
            q, v, w = as_numpy(body.get_qpos()), as_numpy(body.get_vel()), as_numpy(body.get_ang())
            if not np.isfinite(np.r_[q, v, w]).all():
                raise RuntimeError("Non-finite Keyhole state")
            max_drift = max(max_drift, float(np.linalg.norm(q[:3]-initial[name][:3])))
            r0 = Rotation.from_quat(initial[name][[4,5,6,3]])
            r1 = Rotation.from_quat(q[[4,5,6,3]])
            max_angle = max(max_angle, float((r0.inv()*r1).magnitude()))
            if i >= tail_start:
                tail_linear.append(float(np.linalg.norm(v)))
                tail_angular.append(float(np.linalg.norm(w)))
        if i % max(1, steps//5) == 0:
            print(f"Free settling {i+1}/{steps}", flush=True)
    meshes = []
    for source, item in zip(task.assembly.bodies, task.asset_report["bodies"]):
        q = as_numpy(task.bodies[source.name].get_qpos())
        transform = np.eye(4)
        transform[:3,:3] = Rotation.from_quat(q[[4,5,6,3]]).as_matrix()
        transform[:3,3] = q[:3]
        mesh = source.visual.copy().apply_translation(-np.asarray(item["origin_m"])).apply_transform(transform)
        meshes.append(mesh)
    minimum_floor = min(m.bounds[0,2] for m in meshes)-task.tabletop.frames.table_surface_origin[2]
    pair_distance = mesh_clearance(*meshes)
    # A short gravity check permits physical settling. Pose preservation is
    # reported separately and is never equated with route or interlock proof.
    limits = dict(max_contact_penetration_m=.0005, max_final_floor_penetration_m=.0005,
                  max_final_linear_speed_m_s=.01, max_final_angular_speed_rad_s=.1,
                  max_final_pair_surface_distance_m=.01, max_displacement_m=.05)
    passed = (max_penetration < limits["max_contact_penetration_m"] and
              minimum_floor > -limits["max_final_floor_penetration_m"] and
              max(tail_linear) < limits["max_final_linear_speed_m_s"] and
              max(tail_angular) < limits["max_final_angular_speed_rad_s"] and
              0 <= pair_distance < limits["max_final_pair_surface_distance_m"] and
              max_drift < limits["max_displacement_m"])
    return dict(scope="short free gravity settling only; no route or interlock certificate",
        passed=bool(passed), physics_steps=steps, simulated_seconds=steps*dt,
        max_contact_penetration_m=max_penetration, max_body_displacement_m=max_drift,
        max_body_rotation_rad=max_angle, final_window_max_speed_m_s=max(tail_linear),
        final_window_max_angular_speed_rad_s=max(tail_angular), final_floor_clearance_m=float(minimum_floor),
        final_pair_surface_distance_m=pair_distance, limits=limits,
        initial_pose_preserved=bool(max_drift < .003 and max_angle < .05),
        pose_writes_during_probe=False, assistance="none",
        final_body_qpos={n: as_numpy(b.get_qpos()).tolist() for n,b in task.bodies.items()})


def write_review(output, report):
    g = report["geometry"]
    parts = ['<!doctype html><html lang="zh-CN"><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        '<title>Cast Keyhole · 基础场景</title><style>',
        'body{max-width:1120px;margin:36px auto;padding:0 22px;background:#f4f5f7;color:#24313e;font:17px/1.7 system-ui}'
        'section{background:white;padding:24px;border:1px solid #dce1e5;border-radius:12px;margin:22px 0}'
        'img,video{width:100%;border-radius:8px}a{color:#146b98}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}'
        'figure{margin:0}figcaption{color:#596672}td,th{border-bottom:1px solid #e1e5ea;padding:10px;text-align:left}'
        'table{width:100%;border-collapse:collapse}@media(max-width:760px){.grid{grid-template-columns:1fr}}</style>',
        '<p><a href="../../index.html">← 环境汇总</a></p><h1>Cast Keyhole：双板槽道迷宫</h1>',
        '<p><a href="../../../environment-solvability/cast_keyhole/diagram_reference_v1/index.html">'
        '后续接触台架、时间步复核与官方路线准备 →</a></p>',
        '<p>基线选择 Hanayama Huzzle Cast Keyhole（Vesa Timonen，4 / 6）。厂家有 16 步拆解图；'
        '本地模型按公开照片重建轮廓，尺寸与初态为工程设定，完整拆解尚未验证。</p>',
        '<section class="grid"><figure><img src="initial_detail.png" alt="Keyhole 穿插初态">'
        '<figcaption>候选初态：金件穿过银件下部孔道，两件均为自由刚体。</figcaption></figure>'
        '<figure><img src="initial_opposite.png" alt="装配背面"><figcaption>背面检查：槽壁、板厚与交叉关系。</figcaption></figure></section>',
        '<section><img src="initial_overview.png" alt="共享实验室与机器人"><p>Genesis / Nyx 共用实验室桌面。'
        + ('Panda + Robotiq 2F-85 为静止尺度参照。' if report["robot_present"] else '此次未加载机器人。') + '</p></section>',
        '<section><h2>两件轮廓</h2><img src="parts_inspection.png" alt="金件开口叉与银件封闭阶梯孔">'
        '<p>左侧金件是带错列齿的开口叉；右侧银件是带阶梯内壁的封闭通孔，底部外凹口与内孔隔开。'
        '此图通过独立展示重置生成，随后恢复装配；不是拆解轨迹。</p></section>']
    if report["video_created"]:
        parts.append('<section><h2>相机绕行</h2><video controls loop preload="metadata" poster="initial_detail.png" src="preview.mp4"></video>'
                     '<p>只移动相机，零件位姿保持不变。</p></section>')
    parts.extend(['<section><h2>工程状态</h2><table>',
        f'<tr><td>尺度</td><td>重建单件包络 26 × 69 × 3 mm；场景统一放大 {g["scale"]:g} 倍，非实测尺寸</td></tr>',
        f'<tr><td>碰撞</td><td>两个单 link 自由刚体；金 / 银分别 {g["pieces"][0]["collision_prisms"]} / '
        f'{g["pieces"][1]["collision_prisms"]} 个不重叠凸棱柱，保留真实空槽</td></tr>',
        f'<tr><td>初态</td><td>下部孔道穿插候选，非原厂出盒位姿；最小表面间隙 {g["minimum_initial_surface_clearance_m"]*1000:.2f} mm</td></tr>',
        '<tr><td>实物解法</td><td>官方 16 步拆解图支持实物可解；未转换为本地连续轨迹</td></tr>',
        '<tr><td>后续</td><td>实测槽宽 / 板厚 / 倒角、官方连续滑转路径、应通 / 应阻检查、机器人抓持</td></tr></table>',
        f'<p>本次后端：{escape(report["backend"])} / {escape(report["renderer"])}；'
        f'{escape(str(report["solver"].get("precision", "32")))} 位精度。</p>',
        '<p><a href="inspection_report.json">场景报告</a> · <a href="assets/geometry_report.json">几何检查</a> · '
        '<a href="config.yaml">配置</a> · <a href="assets/template.json">尺寸模板</a> · '
        '<a href="assets/sources.json">来源与假设</a> · <a href="assets/assembly.glb">装配 GLB</a></p>',
        '<p>资料：<a href="https://hanayama-toys.com/product/cast-keyhole/">厂家介绍</a> · '
        '<a href="https://hanayama-toys.com/wp-content/uploads/2018/06/Keyhole-2-800x800.jpg">厂家拆件照片</a> · '
        '<a href="https://www.logicagiochi.com/pub/media/wysiwyg/pdf/473743-Cast-Keyhole-Japan.pdf">Hanayama 拆解图</a></p></section>'])
    if s := report.get("settling"):
        parts.append('<section><h2>自由静置检查</h2>'
            f'<p>{s["simulated_seconds"]:.3f} 秒：{"通过" if s["passed"] else "未通过"}；最大接触穿透 '
            f'{s["max_contact_penetration_m"]*1000:.3f} mm，最大位移 {s["max_body_displacement_m"]*1000:.3f} mm。'
            f'最大转角 {np.degrees(s["max_body_rotation_rad"]):.2f}°，初始摆姿{"保持" if s["initial_pose_preserved"] else "未保持"}。'
            '无位姿覆写、抓持或外力驱动；检查范围为短时静置。</p><img src="settled_detail.png" alt="静置后的状态"></section>')
    parts.append('</html>')
    (output / "index.html").write_text("\n".join(parts))


@hydra.main(version_base="1.3", config_path=str(Path(__file__).resolve().parents[3]/"configs"), config_name="cast_keyhole_preview")
def main(cfg):
    import genesis as gs
    import imageio.v2 as imageio
    from .scene import build_scene

    durations = [cfg.run.video_seconds, cfg.run.fps, cfg.run.settle_seconds, cfg.env.sim.dt, cfg.run.orbit_degrees]
    if not np.isfinite(durations).all() or min(durations[:2]) <= 0 or cfg.run.settle_seconds < 0 or cfg.env.sim.dt <= 0:
        raise ValueError("Invalid preview duration or timestep")
    output = Path(cfg.run.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    cfg.env.cameras = OmegaConf.create({n: OmegaConf.to_container(cfg.env.cameras[n], resolve=True)
                                       for n in ("overview", "detail", "opposite", "video")})
    OmegaConf.save(cfg, output / "config.yaml", resolve=True)
    precision = str(cfg.env.genesis.get("precision", "64"))
    gs.init(backend=gs.cuda if cfg.env.genesis.backend == "cuda" else gs.cpu,
            precision=precision, logging_level="warning", seed=int(cfg.task.seed))
    print("Building two free Cast Keyhole plates", flush=True)
    task = build_scene(cfg, output / "assets")
    if cfg.run.include_robot:
        from topogym.utils.franka import initialize_franka_controller
        initialize_franka_controller(scene=task.scene, manifest=task.manifest, robot_cfg=cfg.robot_control, settle_steps=0)
    initial = {n: as_numpy(b.get_qpos()).copy() for n,b in task.bodies.items()}
    task.scene.visualizer.update_visual_states(force_render=True)
    for name in ("overview", "detail", "opposite"):
        Image.fromarray(task.cameras[name].render(force_render=True)[0]).save(output / f"initial_{name}.png")
        print(f"Rendered {name}", flush=True)
    if cfg.run.record_video:
        camera, cc = task.cameras["video"], cfg.env.cameras.video
        aim, offset = np.asarray(cc.lookat), np.asarray(cc.pos)-np.asarray(cc.lookat)
        count = max(1, round(float(cfg.run.video_seconds)*int(cfg.run.fps)))
        with imageio.get_writer(output / "preview.mp4", fps=int(cfg.run.fps), codec="libx264", quality=8,
                               macro_block_size=1, ffmpeg_log_level="error") as writer:
            for i in range(count):
                angle = float(cfg.run.orbit_degrees)*(.5-.5*np.cos(np.pi*i/max(1, count-1)))
                camera.set_pose(pos=aim+Rotation.from_euler("z", angle, degrees=True).apply(offset), lookat=aim, up=(0,0,1))
                writer.append_data(camera.render(force_render=True)[0])
                if i % 20 == 0:
                    print(f"Camera orbit {i}/{count}", flush=True)
    drift = max(float(np.max(np.abs(as_numpy(task.bodies[n].get_qpos())-q))) for n,q in initial.items())
    if drift != 0:
        raise RuntimeError("Camera-only inspection moved puzzle bodies")
    camera = task.cameras["detail"]
    # Flatten both plates into a separate face-on inspection layout. Restore
    # every DOF and zero velocities before any physics step.
    for sign, (name, body) in zip((-1,1), task.bodies.items()):
        source_rotation = Rotation.from_euler("x", 90, degrees=True)
        if name == "keyhole_gold":
            source_rotation = Rotation.from_euler("z", 90, degrees=True)*source_rotation
        position = np.r_[np.asarray(cfg.task.center_xy_m)+[sign*.065, 0],
                         task.tabletop.frames.table_surface_origin[2]+task.assembly.template["thickness"]*task.assembly.unit/2+.0005]
        body.set_qpos(np.r_[position, source_rotation.inv().as_quat()[[3,0,1,2]]], zero_velocity=True)
    aim = np.r_[cfg.task.center_xy_m, task.tabletop.frames.table_surface_origin[2]]
    camera.set_pose(pos=aim+[0,-.04,.63], lookat=aim, up=(0,1,0))
    task.scene.visualizer.update_visual_states(force_render=True)
    Image.fromarray(camera.render(force_render=True)[0]).save(output / "parts_inspection.png")
    for name, body in task.bodies.items():
        body.set_qpos(initial[name], zero_velocity=True)
    camera.set_pose(pos=cfg.env.cameras.detail.pos, lookat=cfg.env.cameras.detail.lookat, up=(0,0,1))
    task.scene.visualizer.update_visual_states(force_render=True)
    restore_error = max(float(np.max(np.abs(as_numpy(task.bodies[n].get_qpos())-q))) for n,q in initial.items())
    if restore_error > 1e-7:
        raise RuntimeError("Inspection failed to restore the assembly")
    report = dict(scope="cast_keyhole_prototype_initial_scene", variant=str(cfg.task.variant),
        initial_relative_pose_id=str(cfg.task.initial_relative_pose_id), factory_initial_pose_reproduced=False,
        human_reference_solution_documented=True, full_task_deployed=False, measured_replica=False,
        extraction_route_verified=False, turning_windows_verified=False, dual_arm_qualified=False,
        robot_present=bool(cfg.run.include_robot), robot_role="stationary scale reference" if cfg.run.include_robot else None,
        renderer=str(cfg.env.renderer.type), backend=str(cfg.env.genesis.backend),
        video_created=bool(cfg.run.record_video), camera_motion_only=True, static_preview_physics_steps=0,
        parts_inspection_is_pose_reset=True, parts_inspection_restore_error=restore_error,
        max_static_qpos_change=drift, body_free_dofs={n:int(b.n_dofs) for n,b in task.bodies.items()},
        inter_body_joints=False, initial_body_qpos={n:q.tolist() for n,q in initial.items()}, geometry=task.asset_report,
        solver=dict(precision=precision, dt=float(cfg.env.sim.dt), substeps=int(cfg.env.sim.substeps), iterations=100,
                    constraint_timeconst=.001, friction=.35, max_collision_pairs=8192))
    if cfg.run.settle_seconds:
        report["settling"] = check_settling(task, cfg)
        Image.fromarray(camera.render(force_render=True)[0]).save(output / "settled_detail.png")
    report["gravity_stability_verified"] = bool(report.get("settling", {}).get("passed", False))
    (output / "inspection_report.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n")
    write_review(output, report)
    artifacts = {str(p.relative_to(output)):hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in sorted(output.rglob("*")) if p.is_file() and p.name != "artifact_manifest.json"}
    (output / "artifact_manifest.json").write_text(json.dumps(artifacts, indent=2)+"\n")
    print(f"Review: {output / 'index.html'}", flush=True)
    if report.get("settling") and not report["settling"]["passed"]:
        raise SystemExit("Scene rendered, but free settling did not pass")


if __name__ == "__main__":
    main()
