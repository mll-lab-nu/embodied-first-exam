"""Render the initial single knot and record a short, unforced FEM settle."""
import json
from pathlib import Path

import hydra
import numpy as np
from omegaconf import OmegaConf


def inspect_settled_centerline(points, layout):
    """Conservative nominal-radius tube diagnostic, separate from FEM contacts."""
    from .geometry import inspect_geometry
    try:
        result = inspect_geometry(points, layout)
        result["passed"] = True
    except ValueError as exc:
        result = {"passed": False, "reason": str(exc)}
    result["scope"] = "reconstructed_centerline_with_nominal_radius; not deformed FEM surface distance"
    return result


def write_review(output, report, video):
    images = [("initial_overview", "实验室与机械臂"), ("initial_topdown", "单结俯视：三个交叉、两个自由端"),
              ("initial_detail", "松结近景"), ("settled_detail", "短时自由静置后的形状")]
    content = """<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>解绳结 · 基础 Trefoil</title>
<style>body{max-width:1120px;margin:36px auto;padding:0 24px;background:#f4f6f8;color:#203143;font:17px/1.7 system-ui}
img,video{width:100%;border-radius:12px}section{background:white;padding:24px;margin:20px 0;border-radius:14px}a{color:#126995}</style>
<h1>解绳结 · 一个松的单结</h1>
<p>一根两端开放的 8 mm 绳，中间只打一个 overhand 结；把自由端从外侧闭合后对应 trefoil（三叶结）。
绳体是连续可变形的 FEM 体，具有自接触和桌面接触；材料参考态为直绳，两端均未固定。</p>
<p><a href="inspection_report.json">场景检查报告</a> · <a href="config.yaml">复现配置</a> ·
<a href="assets/asset_report.json">初始几何检查</a> · <a href="assets/rope_initial.glb">局部坐标 GLB</a> ·
<a href="../../index.html">环境汇总</a></p>"""
    content += (f"<p>总长 {report['rope_length_m']:.3f} m；两端各预留 {report['tail_length_m']*1000:g} mm。"
                f"初态最小非相邻绳面间距 {report['initial_surface_gap_m']*1000:.2f} mm。"
                f"本次自由静置 {report['simulated_seconds']:.3f} s。</p>")
    for name, title in images:
        if (output/f"{name}.png").exists():
            content += f'<section><h2>{title}</h2><img src="{name}.png" alt="{title}"></section>'
    if video:
        content += '<section><h2>初始结形环绕预览</h2><video controls src="preview.mp4"></video><p>仅移动相机。</p></section>'
    content += """<p>当前交付是基础场景、初始几何与短时静置检查。机械臂在场景中待命，尚未执行抓绳和解结。
短时形态保留不等于完整解结、长时接触稳定性或双臂可达性验证。</p></html>"""
    (output/"index.html").write_text(content)


@hydra.main(version_base="1.3", config_path=str(Path(__file__).resolve().parents[3]/"configs"),
            config_name="knot_untying_preview")
def main(cfg):
    import genesis as gs
    import imageio.v2 as imageio
    from PIL import Image
    from scipy.spatial import cKDTree
    from topogym.utils.franka import initialize_franka_controller
    from topogym.world.rope import make_elastic_tube_mesh, tensor_to_numpy
    from .geometry import projected_crossings
    from .scene import KnotSceneBuilder

    if cfg.run.settle_steps < 0 or cfg.run.fps <= 0 or cfg.run.video_seconds <= 0:
        raise ValueError("Invalid simulation or video duration")
    if cfg.env.genesis.backend not in ("cuda", "gpu"):
        raise ValueError("The FEM+IPC knot requires CUDA")
    output = Path(cfg.run.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    cfg.env.cameras = OmegaConf.create({name: OmegaConf.to_container(cfg.env.cameras[name], resolve=True)
                                       for name in ("overview", "detail", "topdown")})
    OmegaConf.save(cfg, output/"config.yaml", resolve=True)
    gs.init(backend=gs.cuda, logging_level="warning", seed=7)
    task = KnotSceneBuilder(cfg.env, cfg.task, cfg.robot_control).build(
        asset_dir=output/"assets", show_viewer=bool(cfg.run.viewer))
    initialize_franka_controller(scene=task.scene, manifest=task.manifest,
                                 robot_cfg=cfg.robot_control, settle_steps=0)
    initial = task.backend.nodes(task.rope).copy()
    skin, _ = make_elastic_tube_mesh(task.centerline, radius=task.layout.rope_radius_m,
                                   radial_segments=task.layout.radial_segments)
    error, indices = cKDTree(initial).query(skin[:-2])
    if error.max() > 1e-6:
        raise RuntimeError("Tet mesher changed tube rings; cannot measure centerline from skin")
    ring_indices = indices.reshape(-1, task.layout.radial_segments)
    for name, camera in task.cameras.items():
        Image.fromarray(camera.render(force_render=True)[0]).save(output/f"initial_{name}.png")
        print(f"Rendered initial {name}", flush=True)
    if cfg.run.record_video:
        camera = task.cameras["detail"]
        target, offset = np.asarray(cfg.env.cameras.detail.lookat), np.asarray(cfg.env.cameras.detail.pos)
        offset = offset-target
        count = max(1, round(float(cfg.run.video_seconds)*int(cfg.run.fps)))
        with imageio.get_writer(output/"preview.mp4", fps=int(cfg.run.fps), codec="libx264",
                               quality=8, macro_block_size=1, ffmpeg_log_level="error") as writer:
            for i in range(count):
                angle = np.radians(30)*i/max(1, count-1)
                c, s = np.cos(angle), np.sin(angle)
                camera.set_pose(pos=target+[c*offset[0]-s*offset[1], s*offset[0]+c*offset[1], offset[2]],
                                lookat=target, up=(0, 0, 1))
                writer.append_data(camera.render(force_render=True)[0])
                if i % 15 == 0:
                    print(f"Camera preview {i}/{count}", flush=True)
        camera.set_pose(pos=cfg.env.cameras.detail.pos, lookat=target, up=(0, 0, 1))
    trace = []
    finite = True
    for step in range(int(cfg.run.settle_steps)):
        task.scene.step()
        nodes = task.backend.nodes(task.rope)
        finite = bool(np.isfinite(nodes).all())
        if not finite:
            break
        centers = nodes[ring_indices].mean(axis=1)
        trace.append(dict(step=step+1, max_displacement_m=float(np.linalg.norm(nodes-initial, axis=1).max()),
                          crossing_count=len(projected_crossings(centers))))
        if step % 10 == 0:
            print(f"Passive settle {step+1}/{cfg.run.settle_steps}: {trace[-1]}", flush=True)
    final = task.backend.nodes(task.rope).copy()
    final_centers = final[ring_indices].mean(axis=1)
    crossing = projected_crossings(final_centers) if finite else []
    origin = np.array([*cfg.task.origin_xy_m, task.tabletop.frames.table_surface_origin[2]])
    final_geometry = inspect_settled_centerline(final_centers-origin, task.layout)
    final_det = np.linalg.det(final[task.rope.elems][:, 1:]-final[task.rope.elems][:, :1])
    spawn = np.asarray(tensor_to_numpy(task.rope.init_positions))
    initial_det = np.linalg.det(spawn[task.rope.elems][:, 1:]-spawn[task.rope.elems][:, :1])
    inverted = int(np.count_nonzero(final_det*initial_det <= 0))
    for name in ("detail", "topdown"):
        if finite:
            Image.fromarray(task.cameras[name].render(force_render=True)[0]).save(output/f"settled_{name}.png")
    report = dict(scope="initial_scene_and_short_passive_settle", variant=str(cfg.task.variant),
        rope_length_m=task.asset_report["rope_length_m"],
        tail_length_m=task.layout.tail_length_m,
        initial_surface_gap_m=task.asset_report["minimum_nonlocal_surface_gap_m"],
        geometry_verified=True, volume_mesh=task.volume_report, finite_state=finite,
        simulation_steps=len(trace), simulated_seconds=len(trace)*float(cfg.env.sim.dt),
        max_vertex_displacement_m=float(np.linalg.norm(final-initial, axis=1).max()),
        final_crossing_count=len(crossing), final_projected_writhe=sum(hit["sign"] for hit in crossing),
        final_centerline_geometry=final_geometry,
        inverted_final_tetrahedra=inverted,
        short_settle_passed=bool(trace and finite and inverted == 0 and final_geometry["passed"]
                                 and all(x["crossing_count"] == 3 for x in trace)
                                 and max(x["max_displacement_m"] for x in trace) < .08),
        renderer=str(cfg.env.renderer.type), robot_present=True, robot_tool="Panda + Robotiq 2F-85",
        robot_rope_contact_enabled=True, robot_manipulation_executed=False,
        gravity_compensation_scope="robot only; rope uses world gravity",
        video_camera_motion_only=True, untying_verified=False, physics_qualified=False,
        robot_reachability_qualified=False, solver=OmegaConf.to_container(cfg.task.rope, resolve=True),
        simulation=OmegaConf.to_container(cfg.env.sim, resolve=True))
    (output/"inspection_report.json").write_text(json.dumps(report, indent=2)+"\n")
    (output/"settle_trace.json").write_text(json.dumps(trace, indent=2)+"\n")
    np.savez_compressed(output/"settle_states.npz", initial_nodes=initial, final_nodes=final,
                        initial_centerline=task.centerline, final_centerline=final_centers)
    write_review(output, report, bool(cfg.run.record_video))
    print(json.dumps(report, indent=2), flush=True)
    print(output/"index.html", flush=True)
    if cfg.run.settle_steps and not report["short_settle_passed"]:
        raise SystemExit("Short settle did not pass; inspect the recorded diagnostics")


if __name__ == "__main__":
    main()
