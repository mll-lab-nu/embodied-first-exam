"""Render the reference initial scene and measure an unforced FEM settle."""
import json
from pathlib import Path

import hydra
import numpy as np
from omegaconf import OmegaConf


def write_review(output, report, images):
    from html import escape
    figures = "".join(f'<figure><a href="{name}.png"><img src="{name}.png" alt="{escape(title)}"></a>'
                      f'<figcaption>{escape(title)}</figcaption></figure>' for name, title in images.items())
    video = ('<h2>初态环绕预览</h2><video controls preload="metadata" src="preview.mp4"></video>'
             '<p>物体与机械臂保持初态，仅相机移动。</p>') if report["video_frames"] else ""
    (output/"index.html").write_text('''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>TopoGym · 绳穿三环</title>
<style>body{max-width:1120px;margin:40px auto;padding:0 24px;background:#eef2f2;color:#21383d;font:17px/1.7 system-ui}
h1{font-size:40px}img,video{width:100%;border-radius:12px}figure{margin:30px 0}figcaption{color:#496067}a{color:#09697c}
.card{background:white;padding:24px;border-radius:16px;margin:24px 0}code{font-size:14px}</style>
<p>TOPOGYM / ROPE THREADING / INITIAL SCENE</p><h1>一根绳子，三个空间圆环</h1>
<p>依据 Wang 公开演示的几何与首帧数据重建：青、绿、紫三环保留原位置、倾角和侧置支架；
橙色 U 形绳平放桌面，两端自由。完整 ALOHA 双臂位于共享 Nyx 实验室。</p>
<div class="card"><b>本阶段：基础场景与建模</b><br>
绳长 1.100 m，直径 8 mm；环中心线半径 75 mm，管径 12 mm，净孔径 138 mm。
原 80 段绳的材料顺序保留，现使用直绳参考态的连续 FEM 体。目标顺序 R1− → R2+ → R3+。</div>
<p><a href="inspection_report.json">验证报告</a> · <a href="config.yaml">运行配置</a> ·
<a href="assets/assembly.glb">完整任务 GLB（世界坐标）</a> · <a href="assets/layout.json">位置与有向法线</a> ·
<a href="assets/asset_report.json">资产清单</a> · <a href="../../index.html">环境汇总</a></p>'''
        + f'<p>自由静置 {report["simulated_seconds"]:.3f} s；检查结果：'
        + ("通过" if report["short_settle_passed"] else "未通过或未运行")
        + f'。最大绳体位移 {1000*report["max_vertex_displacement_m"]:.2f} mm。</p>'
        + figures + video + '''<div class="card">机器人尚未执行抓取或穿环。
当前检查覆盖初始几何、体网格、短时自由静置和相机输出；完整穿环、长期接触稳定性与双臂路径仍待实现。
本场景采用 TopoGym 的 FEM+IPC、桌面和机器人安装方式；不复用原 MuJoCo 控制器，也不声称动力学等价。</div>
<p>来源：<a href="https://qinengwang-aiden.github.io/demos/constraint_demos/?demo=threading">作者演示</a> ·
<a href="https://qinengwang-aiden.github.io/demos/constraint_demos/methods.html">方法与适用范围</a></p></html>''')


@hydra.main(version_base="1.3", config_path=str(Path(__file__).resolve().parents[3]/"configs"),
            config_name="rope_threading_preview")
def main(cfg):
    import genesis as gs
    import imageio.v2 as imageio
    from scipy.spatial import cKDTree
    from topogym.robot import initialize_robot_controller
    from topogym.world.aloha_cameras import configure_aloha_rig
    from topogym.world.rope import make_elastic_tube_mesh
    from .geometry import route_crossings
    from .scene import ThreadingSceneBuilder

    if cfg.run.settle_steps < 0 or cfg.run.fps <= 0 or cfg.run.video_seconds <= 0:
        raise ValueError("Invalid simulation or video duration")
    if cfg.env.genesis.backend not in ("cuda", "gpu"):
        raise ValueError("FEM+IPC requires CUDA")
    output = Path(cfg.run.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    camera_rig = configure_aloha_rig(cfg, keep=("overview", "detail", "topdown"), resolution=(640, 360))
    OmegaConf.save(cfg, output/"config.yaml", resolve=True)
    gs.init(backend=gs.cuda, logging_level="warning", seed=7)
    task = ThreadingSceneBuilder(cfg.env, cfg.task, cfg.robot_control).build(
        asset_dir=output/"assets", show_viewer=bool(cfg.run.viewer))
    controller = initialize_robot_controller(scene=task.scene, manifest=task.manifest,
        robot_cfg=cfg.robot_control, settle_steps=0,
        reset_home=cfg.task.get("robot_coupling") != "external_articulation")
    if cfg.task.get("robot_coupling") == "external_articulation":
        for side, arm in controller.arms.items():
            arm.set_arm_qpos(cfg.robot_control.home[side][:6])
            arm.set_gripper(cfg.robot_control.home[side][6])
    initial = task.backend.nodes(task.rope).copy()
    skin, _ = make_elastic_tube_mesh(task.centerline, radius=task.layout.radius,
                                    radial_segments=task.layout.radial_segments)
    error, indices = cKDTree(initial).query(skin[:-2])
    if error.max() > 1e-6:
        raise RuntimeError("Tet mesher changed tube rings; cannot measure the material centerline")
    ring_indices = indices.reshape(-1, task.layout.radial_segments)
    images, camera_checks = {}, {}
    titles = dict(overview="完整双臂与实验室", detail="三环侧置支架与自由绳", topdown="U 形绳初态与空间布局",
                  cam_high="ALOHA 高位相机", cam_low="ALOHA 低位相机",
                  cam_left_wrist="左腕相机", cam_right_wrist="右腕相机")

    def capture(prefix, names):
        task.scene.visualizer.update_visual_states(force_render=True)
        for name in names:
            camera = task.cameras[name]
            if getattr(camera, "_attached_link", None) is not None:
                camera.move_to_attach()
            frame = camera.render(force_render=False)[0].copy()
            if frame.shape != (camera.res[1], camera.res[0], 3) or frame.dtype != np.uint8 or frame.std() < 5:
                raise RuntimeError(f"Invalid image from {name}: shape={frame.shape}, dtype={frame.dtype}, std={frame.std():.3f}")
            imageio.imwrite(output/f"{prefix}_{name}.png", frame)
            images[f"{prefix}_{name}"] = ("自由静置后 · " if prefix == "settled" else "")+titles[name]
            camera_checks[f"{prefix}_{name}"] = dict(shape=list(frame.shape), std=float(frame.std()),
                                                      transform=camera.transform.tolist())
        print(f"Rendered {prefix}: {list(names)}", flush=True)

    capture("initial", ("overview", "detail", "topdown", "cam_high", "cam_low", "cam_left_wrist", "cam_right_wrist"))
    video_frames = 0
    if cfg.run.record_video:
        camera = task.cameras["detail"]
        target = np.asarray(cfg.env.cameras.detail.lookat)
        offset = np.asarray(cfg.env.cameras.detail.pos)-target
        count = max(1, round(float(cfg.run.video_seconds)*int(cfg.run.fps)))
        with imageio.get_writer(output/"preview.mp4", fps=int(cfg.run.fps), codec="libx264", quality=8,
            macro_block_size=1, ffmpeg_params=["-threads", "2"], ffmpeg_log_level="error") as writer:
            for i in range(count):
                angle = np.radians(40)*i/max(1, count-1)
                c, s = np.cos(angle), np.sin(angle)
                camera.set_pose(pos=target+[c*offset[0]-s*offset[1], s*offset[0]+c*offset[1], offset[2]],
                                lookat=target, up=(0, 0, 1))
                writer.append_data(camera.render(force_render=True)[0])
                video_frames += 1
                if i % 15 == 0:
                    print(f"Camera orbit {i}/{count}", flush=True)
        camera.set_pose(pos=cfg.env.cameras.detail.pos, lookat=target, up=(0, 0, 1))
        reader = imageio.get_reader(output/"preview.mp4")
        decoded = sum(1 for _ in reader)
        reader.close()
        if decoded != count:
            raise RuntimeError("Preview video failed frame-count verification")
    initial_det = np.linalg.det(initial[task.rope.elems][:, 1:]-initial[task.rope.elems][:, :1])
    initial_robot = controller.state()
    table_z = task.tabletop.frames.table_surface_origin[2]
    trace = []
    for step in range(int(cfg.run.settle_steps)):
        controller.step(1)
        nodes = task.backend.nodes(task.rope)
        finite = bool(np.isfinite(nodes).all())
        centers = nodes[ring_indices].mean(axis=1)
        det = np.linalg.det(nodes[task.rope.elems][:, 1:]-nodes[task.rope.elems][:, :1])
        trace.append(dict(step=step+1, finite=finite,
            max_displacement_m=float(np.linalg.norm(nodes-initial, axis=1).max()),
            minimum_vertex_table_gap_m=float(nodes[:, 2].min()-table_z),
            inverted_tetrahedra=int(np.count_nonzero(initial_det*det <= 0)),
            crossing_count=len(route_crossings(centers, task.layout.rings(), task.layout.radius)) if finite else None))
        if not finite:
            break
        if step % 10 == 0:
            print(f"Passive settle {step+1}/{cfg.run.settle_steps}: {trace[-1]}", flush=True)
    final = task.backend.nodes(task.rope).copy()
    final_centers = final[ring_indices].mean(axis=1)
    robot_final = controller.state()
    robot_drift = {side: float(np.max(abs(np.asarray(robot_final[side]["arm_qpos"])
                                         -initial_robot[side]["arm_qpos"]))) for side in ("left", "right")}
    passed = bool(trace and all(s["finite"] and s["inverted_tetrahedra"] == 0 and s["crossing_count"] == 0
                  and s["minimum_vertex_table_gap_m"] > -.001 and s["max_displacement_m"] < .04 for s in trace)
                  and max(robot_drift.values()) < .15)
    if np.isfinite(final).all():
        capture("settled", ("detail", "topdown"))
    report = dict(scope="reference_initial_scene_and_short_passive_settle", geometry_verified=True,
        variant=str(cfg.task.variant), volume_mesh=task.volume_report, camera_rig=camera_rig,
        camera_checks=camera_checks, renderer=str(cfg.env.renderer.type),
        simulation_steps=len(trace), simulated_seconds=len(trace)*float(cfg.env.sim.dt),
        short_settle_passed=passed, max_vertex_displacement_m=float(np.linalg.norm(final-initial, axis=1).max()),
        final_crossings=route_crossings(final_centers, task.layout.rings(), task.layout.radius)
            if np.isfinite(final).all() else None,
        max_robot_arm_drift_rad=robot_drift, robot="ALOHA 2, original dual grippers, 16 DoFs",
        robot_mount_difference_from_source_m=[0, 0, float(cfg.robot_control.robot.get("base_riser_height_m", 0.))-.0209],
        robot_rope_contact_enabled=True, robot_manipulation_executed=False,
        endpoint_constraints=0, rope_gravity_compensation=0, gravity_compensation_scope="robot only",
        video_frames=video_frames, video_camera_motion_only=True,
        physics_qualified=False, full_threading_verified=False,
        solver=OmegaConf.to_container(cfg.task.rope, resolve=True),
        simulation=OmegaConf.to_container(cfg.env.sim, resolve=True), assets=task.asset_report)
    (output/"inspection_report.json").write_text(json.dumps(report, indent=2)+"\n")
    (output/"settle_trace.json").write_text(json.dumps(trace, indent=2)+"\n")
    np.savez_compressed(output/"settle_states.npz", initial_nodes=initial, final_nodes=final,
                        initial_centerline=task.centerline, final_centerline=final_centers)
    write_review(output, report, images)
    print(f"Preview: {output/'index.html'}; passive settle passed={passed}", flush=True)
    if cfg.run.settle_steps and not passed:
        raise SystemExit("Short settle did not pass; inspect recorded diagnostics")


if __name__ == "__main__":
    main()
