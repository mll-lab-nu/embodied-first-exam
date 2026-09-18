"""Render a complete assembly, with an optional separately reported gravity check.

Default: CUDA/Nyx. Headless CPU fallback:
    PYOPENGL_PLATFORM=egl LIBGL_ALWAYS_SOFTWARE=1 .venv-gs121-nyx/bin/python \
        -m demos.environment_bootstrap.horseshoe_ring \
        env.genesis.backend=cpu env.renderer.type=rasterizer
"""
import hashlib
from html import escape
import json
from pathlib import Path
import time

import hydra
import numpy as np
from omegaconf import OmegaConf
from PIL import Image
from scipy.spatial.transform import Rotation


def as_numpy(value):
    return value.detach().cpu().numpy() if hasattr(value, "detach") else np.asarray(value)


def write_review(output, report):
    g = report["geometry"]
    settling = report.get("settling")
    parts = ['<!doctype html><html lang="zh-CN"><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        '<title>Horseshoe Ring · 完整装配初态</title>',
        '<style>body{margin:32px auto;padding:0 22px;max-width:1160px;background:#f4f5f7;color:#24313c;'
        'font:17px/1.7 system-ui}h1{margin-bottom:8px}a{color:#14699a}section{background:white;'
        'padding:24px;border:1px solid #dde2e8;border-radius:12px;margin:22px 0}img,video{width:100%;'
        'display:block;border-radius:8px}figure{margin:0}figcaption{margin-top:10px;color:#52616e}'
        '.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.tag{display:inline-block;'
        'padding:4px 12px;background:#e7edf2;border-radius:20px;margin:4px}.ok{color:#16623f}'
        'table{width:100%;border-collapse:collapse}td,th{text-align:left;border-bottom:1px solid #e2e6ea;'
        'padding:10px}@media(max-width:760px){.grid{grid-template-columns:1fr}}</style>',
        '<p><a href="../../index.html">← 环境搭建与验证</a></p>',
        '<h1>Horseshoe Ring：双马蹄完整装配</h1>',
        '<p>按参考照片搭建两个开口马蹄件、两条短连接链和一个独立的目标圆环。'
        '目标是保持马蹄与链条完整，将中央圆环取下。</p>',
        f'<p><span class="tag">2 个马蹄件</span><span class="tag">2 × {g["links_per_span"]} 个独立链节</span>'
        f'<span class="tag">1 个目标圆环</span><span class="tag">{g["scale"]:g} 倍原型尺度</span></p>',
        '<section><figure><a href="initial_overview.png"><img src="initial_overview.png" '
        'alt="两个开口马蹄件由两条短链相连，中央独立圆环套在两条链外"></a>'
        '<figcaption>完整装配初态。全部零件采用银灰金属外观；中央斜立的大圆环是待取目标。'
        '这是静态装配展示，初始悬空的零件没有被固定或隐藏焊接。</figcaption></figure></section>',
        '<section class="grid"><figure><a href="initial_top.png"><img src="initial_top.png" alt="完整装配俯视图"></a>'
        '<figcaption>俯视：两个马蹄件的开口朝向中间，上下两条链分别连接端部。</figcaption></figure>'
        '<figure><a href="initial_detail.png"><img src="initial_detail.png" alt="中央圆环及端部连接近景"></a>'
        '<figcaption>近景：马蹄端部的闭合连接孔、交替转向的链节，以及包围两条链的目标圆环。</figcaption></figure></section>']
    if report.get("room_overview_created"):
        parts.insert(parts.index(next(p for p in parts if p.startswith('<section><figure>'))),
            '<section><figure><a href="initial_room.png"><img src="initial_room.png" '
            'alt="共用封闭实验室、桌面、Panda 和 Robotiq 夹爪，以及马蹄环任务"></a>'
            '<figcaption>共用 compact_lab 实验室与桌面布置。机械臂保持初始姿态；本页展示环境，不执行机器人求解。</figcaption>'
            '</figure></section>')
    if report["video_created"]:
        parts.append('<section><h2>绕行观察</h2><video controls loop preload="metadata" poster="initial_overview.png" '
                     'src="preview.mp4"></video><p>视频只移动相机，零件保持初态；尚未演示取环。</p></section>')
    parts.extend([
        '<section><h2>本次检查</h2><table><tr><th>项目</th><th>结果</th></tr>',
        f'<tr><td>独立刚体</td><td>{g["body_count"]} 个，每个 6 个自由度；零件之间没有关节或焊接约束</td></tr>',
        f'<tr><td>初始间隙</td><td class="ok">通过；跨零件碰撞几何的最小保守间隙约 '
        f'{g["minimum_clearance_lower_bound_m"]*1000:.2f} mm</td></tr>',
        f'<tr><td>链条装配</td><td class="ok">{len(g["topology"]["adjacent_pairs"])} 处相邻互套关系通过；无额外误串链环</td></tr>',
        '<tr><td>目标圆环</td><td>两条链穿过目标环孔；与任意单只链环的两两链接数为 0。此项不证明可取出。</td></tr>',
        '<tr><td>实物一致性</td><td>结构参考原图；尺寸、每条链 3 个链节及端部连接孔构造为原型假设。尚无实测 CAD。</td></tr>',
        '<tr><td>待验证</td><td>精确实物比例、合法取环路径、双臂操作和完整任务物理稳定性</td></tr></table>',
        '<p><a href="inspection_report.json">场景检查报告</a> · <a href="assets/geometry_report.json">几何与连接检查</a> · '
        '<a href="config.yaml">运行配置</a> · <a href="assets/template.json">尺寸模板</a> · '
        '<a href="assets/assembly.glb">下载完整三维模型（GLB）</a></p>',
        f'<p>本次渲染：{escape(report["renderer"])} / {escape(report["backend"])}。'
        '马蹄表面的钉孔装饰尚未重建；真实碰撞保留马蹄开口、端部连接孔、链节孔及目标环孔。</p></section>'])
    if settling:
        parts.append('<section><h2>额外的重力落桌检查</h2>'
            f'<p>模拟 {settling["simulated_seconds"]:.3f} 秒，最大接触穿透 '
            f'{settling["max_penetration_m"]*1000:.3f} mm，连接关系异常采样数 '
            f'{settling["topology_failure_samples"]}；'
            f'本次短时检查{"通过" if settling["passed"] else "未通过"}。</p>'
            '<img src="settled_overview.png" alt="重力检查后的场景">'
            '<p>短时落桌检查不代表折叠、拉紧或取环过程已通过。</p></section>')
    parts.append('</html>')
    (output/"index.html").write_text("\n".join(parts))


def current_loops(task):
    from .geometry import Loop
    origins = {b["name"]: np.asarray(b["origin_m"]) for b in task.asset_report["bodies"]}
    poses = {}
    for name, body in task.bodies.items():
        p = as_numpy(body.get_pos()).reshape(3)
        q = as_numpy(body.get_quat()).reshape(4)
        poses[name] = (p, Rotation.from_quat(q[[1, 2, 3, 0]]))
    result = {}
    for name, loop in task.assembly.loops.items():
        p, rotation = poses[loop.body]
        result[name] = Loop(name, loop.body, p+rotation.apply(loop.center-origins[loop.body]),
                           rotation*loop.rotation, loop.radii, loop.wire_radius, loop.segments)
    return result


def check_settling(task, cfg, output):
    seconds, dt = float(cfg.run.settle_seconds), float(cfg.env.sim.dt)
    steps = round(seconds/dt)
    max_penetration, failures, peak_speed = 0., 0, 0.
    samples, final_speeds = [], []
    started = time.monotonic()
    for step in range(steps):
        task.scene.step()
        contacts = task.scene.sim.rigid_solver.collider.get_contacts()
        penetration = as_numpy(contacts["penetration"])
        if penetration.size:
            max_penetration = max(max_penetration, float(penetration.max()))
        loops = current_loops(task)
        values = [loops[a].linking(loops[b]) for a, b in task.assembly.edges]
        target_values = [loops["target_ring"].linking(v) for k, v in loops.items() if k != "target_ring"]
        failures += int(any(abs(v) != 1 for v in values) or any(target_values))
        velocities = [as_numpy(b.get_vel()).reshape(3) for b in task.bodies.values()]
        angular = [as_numpy(b.get_ang()).reshape(3) for b in task.bodies.values()]
        if not np.isfinite(np.r_[np.array(velocities).ravel(), np.array(angular).ravel(),
                                    np.concatenate([v.center for v in loops.values()])]).all():
            raise RuntimeError("Non-finite rigid state during settling")
        speed = float(np.linalg.norm(velocities, axis=1).max())
        peak_speed = max(peak_speed, speed)
        if (step+1)*dt > seconds-min(.2, seconds/2):
            final_speeds.append(speed)
        if step % max(1, round(.05/dt)) == 0:
            samples.append(dict(time_s=(step+1)*dt, link_numbers=values, maximum_speed_m_s=speed))
        if step % max(1, round(.2/dt)) == 0:
            print(f"Gravity check {(step+1)*dt:.3f}/{seconds:.3f} s", flush=True)
    Image.fromarray(task.cameras["overview"].render()[0]).save(output/"settled_overview.png")
    settled = bool(final_speeds) and max(final_speeds) < .01
    result = dict(simulated_seconds=steps*dt, physics_steps=steps, max_penetration_m=max_penetration,
        topology_failure_samples=failures, topology_sample_stride_steps=1, peak_speed_m_s=peak_speed,
        final_window_max_speed_m_s=max(final_speeds) if final_speeds else None, settled=settled,
        passed=failures == 0 and max_penetration < .0005 and settled,
        wall_seconds=time.monotonic()-started, pose_writes_after_reset=False, assistance="none; gravity and table contact only",
        scope="short gravity settling only; not extraction qualification", samples=samples)
    (output/"settling_report.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    return result


@hydra.main(version_base="1.3", config_path=str(Path(__file__).resolve().parents[3]/"configs"), config_name="horseshoe_ring_preview")
def main(cfg):
    import genesis as gs
    import imageio.v2 as imageio
    from .scene import build_scene

    if not np.isfinite([cfg.run.video_seconds, cfg.run.settle_seconds, cfg.env.sim.dt]).all():
        raise ValueError("Durations and timestep must be finite")
    if cfg.run.video_seconds <= 0 or cfg.run.fps <= 0 or cfg.run.settle_seconds < 0 or cfg.env.sim.dt <= 0:
        raise ValueError("Invalid duration, frame rate, or timestep")
    output = Path(cfg.run.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    # Keep the shared world, but remove inherited task-specific camera angles.
    camera_names = [n for n in ("room", "overview", "top", "detail", "video") if n in cfg.env.cameras]
    cfg.env.cameras = OmegaConf.create({n: OmegaConf.to_container(cfg.env.cameras[n], resolve=True)
                                        for n in camera_names})
    OmegaConf.save(cfg, output/"config.yaml", resolve=True)
    gs.init(backend=gs.cuda if cfg.env.genesis.backend == "cuda" else gs.cpu,
            logging_level="warning", seed=int(cfg.task.seed))
    print("Building complete two-horseshoe assembly", flush=True)
    task = build_scene(cfg, output/"assets")
    if cfg.run.include_robot:
        from topogym.utils.franka import initialize_franka_controller
        initialize_franka_controller(scene=task.scene, manifest=task.manifest,
                                     robot_cfg=cfg.robot_control, settle_steps=0)
    initial = {name: as_numpy(body.get_qpos()).copy() for name, body in task.bodies.items()}
    for name in (n for n in camera_names if n != "video"):
        Image.fromarray(task.cameras[name].render()[0]).save(output/f"initial_{name}.png")
        print(f"Rendered {name}", flush=True)
    if cfg.run.record_video:
        camera, cc = task.cameras["video"], cfg.env.cameras.video
        aim = np.asarray(cc.lookat, dtype=float)
        offset = np.asarray(cc.pos, dtype=float)-aim
        count = max(1, round(float(cfg.run.video_seconds)*int(cfg.run.fps)))
        with imageio.get_writer(output/"preview.mp4", fps=int(cfg.run.fps), codec="libx264", quality=8,
                               macro_block_size=1, ffmpeg_log_level="error") as writer:
            for i in range(count):
                t = i/max(1, count-1)
                fraction = float(cfg.run.get("video_room_fraction", 0.))
                if not 0 <= fraction < 1:
                    raise ValueError("video_room_fraction must lie in [0, 1)")
                if "room" in cfg.env.cameras and t < fraction:
                    rc = cfg.env.cameras.room
                    target = np.asarray(rc.lookat, dtype=float)
                    arm = np.asarray(rc.pos, dtype=float)-target
                    angle = 14.*(.5-.5*np.cos(np.pi*t/fraction))
                else:
                    target, arm = aim, offset
                    local_t = max(0., (t-fraction)/(1-fraction)) if "room" in cfg.env.cameras else t
                    angle = float(cfg.run.orbit_degrees)*(.5-.5*np.cos(np.pi*local_t))
                shift = Rotation.from_euler("z", angle, degrees=True).apply(arm)
                camera.set_pose(pos=target+shift, lookat=target, up=(0, 0, 1))
                writer.append_data(camera.render()[0])
                if i % 20 == 0:
                    print(f"Camera orbit {i}/{count}", flush=True)
    drift = max(float(np.max(np.abs(as_numpy(task.bodies[n].get_qpos())-q))) for n, q in initial.items())
    if drift != 0:
        raise RuntimeError("Camera-only preview moved puzzle parts")
    report = dict(scope="complete_assembly_initial_scene", variant=str(cfg.task.variant),
        full_task_deployed=False, extraction_route_verified=False, measured_replica=False,
        renderer=str(cfg.env.renderer.type), backend=str(cfg.env.genesis.backend),
        video_created=bool(cfg.run.record_video), camera_motion_only=True,
        room_overview_created="room" in camera_names,
        static_preview_physics_steps=0, max_static_qpos_change=drift,
        body_free_dofs={n: int(b.n_dofs) for n, b in task.bodies.items()}, inter_body_joints=False,
        robot_present=bool(cfg.run.include_robot), robot_reachability_qualified=False,
        initial_floor_clearance_m=float(cfg.task.initial_floor_clearance_m),
        geometry={k: v for k, v in task.asset_report.items() if k not in ("clearance_pairs", "bodies")},
        initial_body_qpos={n: q.tolist() for n, q in initial.items()},
        assembly_origin_m=task.origin.tolist(), gravity_stability_verified=False)
    if cfg.run.settle_seconds:
        report["settling"] = check_settling(task, cfg, output)
    (output/"inspection_report.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n")
    write_review(output, report)
    artifacts = {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in sorted(output.rglob("*")) if p.is_file() and p.name != "artifact_manifest.json"}
    (output/"artifact_manifest.json").write_text(json.dumps(artifacts, indent=2)+"\n")
    print(f"Review: {output/'index.html'}", flush=True)
    if report.get("settling") and not report["settling"]["passed"]:
        raise SystemExit("Initial scene rendered; the optional settling check did not pass")


if __name__ == "__main__":
    main()
