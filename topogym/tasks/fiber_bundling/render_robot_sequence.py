"""Render saved real-robot states in a separate scene without stepping physics."""
import argparse
import hashlib
import io
import json
from pathlib import Path

import numpy as np

from .scene import FiberSceneBuilder, cable_state


def label(phase, whole_bundle=False):
    if phase.startswith("spiral_capture_"):
        return "整束小幅绕行并推进"
    if phase.startswith("adaptive_contact_"):
        return "接触环边并转动粗电缆"
    if phase.startswith("wire_"):
        _, i, action = phase.split("_", 2)
        color = ("红", "蓝", "绿", "棕", "白", "黄", "黑", "灰")[int(i) % 8]
        prefix = f"当前突出部位（{color}线）：" if whole_bundle else f"第 {int(i)+1} 根（{color}线）："
        return prefix+dict(park="退至环前", lift="提离托架", select="调整粗电缆方向",
            approach="接近环缘", press="借助环缘整理", settle="保持接触", release="撤离环缘", inspect="检查整理结果",
            lift_hold="提起后保持", park_hold="环前保持", select_hold="选线后保持",
            clear_cradle="横向移出托架范围", clearance="按整束轮廓增加环外余量").get(action, action)
    return dict(initial="初始场景", initial_hold="初态检查", approach_above_cable="机械臂接近粗电缆",
        lower_open_gripper="张开夹爪，对准护套", close_on_working_jacket="两侧手指接触粗电缆",
        lift_for_regrasp="提起电缆，准备换抓", settle_before_regrasp="换抓前保持",
        open_for_regrasp="张开夹爪准备换抓", shift_grasp_to_rear_jacket="移向较后方的护套抓点",
        close_on_rear_jacket="重新夹住较后方护套",
        grasp_hold="保持夹持，检查稳定性", bundle_retreat="整束后撤", bundle_unroll="调整整体方向",
        bundle_align="整束对准环孔", before_final_feed="检查全部电线", final_axial_feed="一次向前送入",
        final_hold="保持并检查完整穿环", bundle_lift="提起粗电缆",
        bundle_clear_ring="退到环前调整区", bundle_center_at_entry="整束对准环孔",
        entry_hold="检查入环前状态", bundle_axial_feed="整束向前送入",
        spiral_approach="偏置接近环孔", greedy_lift_clear="抬起电缆，离开接触区",
        greedy_retreat="退到环前调整区", greedy_orient_clear="在空处调整整束方向",
        greedy_orientation_hold="保持并检查线束方向", greedy_lower="对准当前突出部位",
        greedy_lower_hold="保持环外接近距离",
        greedy_contact_approach="接近环边", greedy_envelope_press="借环边收束当前突出部位",
        greedy_release="横向撤离环边", greedy_inspect="重新测量整束包络",
        greedy_final_lift="收束后抬起电缆", greedy_final_orient="整束回正",
        greedy_final_align="整束对准环孔", greedy_before_feed="送入前检查").get(phase, phase)


def main():
    import genesis as gs
    import imageio.v2 as imageio
    from omegaconf import OmegaConf
    from PIL import Image, ImageDraw, ImageFont

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--speed", type=float, default=1.)
    parser.add_argument("--fps", type=int, default=20)
    parser.add_argument("--backend", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--renderer", choices=("nyx", "rasterizer"), default="nyx")
    parser.add_argument("--render-precision",choices=("32","64"),default="32",
                        help="Graphics playback precision; recorded physics is never rerun or modified")
    parser.add_argument("--shadows",action=argparse.BooleanOptionalAction,default=False,
                        help="Optional raster shadow maps; disabled for clear indoor inspection")
    parser.add_argument("--stills-only", action="store_true")
    parser.add_argument("--multiview", action="store_true",
                        help="Also export synchronized agentview/front_oblique/wrist MP4s")
    parser.add_argument("--clean", action="store_true",
                        help="Export only three full-frame camera streams, without captions, HUD or picture-in-picture")
    args = parser.parse_args()
    if args.clean:
        args.multiview = True
    folder = args.folder.resolve()
    report_bytes = (folder/"report.json").read_bytes()
    trajectory_bytes = (folder/"trajectory.npz").read_bytes()
    report = json.loads(report_bytes)
    with np.load(io.BytesIO(trajectory_bytes)) as archive:
        data = {key: archive[key] for key in archive.files}
    if not np.isclose(data["time_s"][-1], report["simulated_seconds"]):
        raise ValueError("The saved trajectory does not cover the completed report")
    cfg = OmegaConf.load(folder/"config.yaml")
    recorded_precision=str(cfg.env.genesis.get("precision","32"))
    cfg.env.genesis.precision=args.render_precision
    if not args.shadows:
        if "vis" not in cfg.env:
            cfg.env.vis=OmegaConf.create({})
        cfg.env.vis.shadow=False
    cfg.env.genesis.backend = args.backend
    cfg.env.renderer.type = args.renderer
    cfg.env.renderer.spp = 16
    cfg.env.cameras = OmegaConf.create(dict(
        detail=dict(res=[1280, 900], pos=[.38, .74, 1.40], lookat=[-.015, .4, 1.17],
                    up=[0, 0, 1], fov=36, near=.002, far=12),
        overview=dict(res=[640, 480], pos=[.82, -1.1, 1.9], lookat=[-.22, .24, 1.18],
                      up=[0, 0, 1], fov=44, near=.002, far=12)))
    if args.multiview:
        shared = OmegaConf.load(Path(__file__).resolve().parents[3]/"configs/env_configs/world_tabletop_v1.yaml")
        cfg.env.cameras.wrist = OmegaConf.create(OmegaConf.to_container(shared.cameras.wrist, resolve=True))
        cfg.env.cameras.wrist.res = [1280, 900]
        # The cable points toward local -x for the 150-degree grasp. Mount
        # the wrist camera on that side and look toward the branching end.
        cfg.env.cameras.wrist.attach.offset_pos = [-.050, 0., .005]
        cfg.env.cameras.wrist.attach.offset_lookat = [-.100, 0., .170]
        cfg.env.cameras.wrist.attach.offset_up = [-1., 0., 0.]
        cfg.env.cameras.overview.res = [1280, 900]
    gs.init(backend=gs.cuda if args.backend == "cuda" else gs.cpu, logging_level="warning",
            performance_mode=args.backend == "cpu", precision=args.render_precision)
    # Regenerate identical assets in an isolated playback folder.
    task = FiberSceneBuilder(cfg.env, cfg.task, cfg.robot_control).build(asset_dir=folder/"playback_assets")
    robot = task.manifest.get("robot")
    font_path = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
    if not args.clean:
        title, font, small = [ImageFont.truetype(font_path, s) for s in (30, 23, 19)]
    if args.speed <= 0 or args.fps <= 0:
        parser.error("Positive playback speed and fps required")
    times = data["time_s"]
    diagnostic_only = report["plan"].get("neighbor_shape_policy") == "diagnostic_only_final_current_bundle_fit"
    whole_bundle = report.get("whole_bundle_policy", False)
    shape_key = "prepared_shape_change_m" if "prepared_shape_change_m" in data else "protected_shape_change_m"
    wanted = np.arange(0, times[-1]+1e-8, args.speed/args.fps)
    indices = np.array([int(np.abs(times-t).argmin()) for t in wanted])
    indices = np.r_[indices, len(times)-1]
    if args.stills_only:
        indices = np.unique([0, len(times)-1])
    maximum = 0.
    writer = None if args.stills_only or args.clean else imageio.get_writer(folder/"demo.mp4", fps=args.fps,
        codec="libx264", quality=8, macro_block_size=1, ffmpeg_log_level="error")
    streams = {"agentview": "overview", "front_oblique": "detail", "wrist": "wrist"} if args.multiview else {}
    view_writers = {name: imageio.get_writer(folder/f"demo_{name}.mp4", fps=args.fps,
        codec="libx264", quality=8, macro_block_size=1, ffmpeg_log_level="error")
        for name in streams} if not args.stills_only else {}
    OmegaConf.save(cfg, folder/"render_config.yaml", resolve=True)
    (folder/"source/render_robot_sequence.py").write_bytes(Path(__file__).read_bytes())
    try:
        for j, i in enumerate(indices):
            task.bundle.set_qpos(data["cable_qpos"][i], zero_velocity=False)
            robot.set_qpos(data["robot_qpos"][i], zero_velocity=False)
            state = cable_state(task.bundle, task.layout)
            error = float(np.linalg.norm(state["fibers_m"]-data["fibers"][i], axis=-1).max())
            maximum = max(maximum, error)
            if error > 2e-6:
                raise RuntimeError(f"Saved physics / playback mismatch: {error} m")
            task.scene.visualizer.update_visual_states(force_render=True)
            raw_frames = {"detail": task.cameras["detail"].render(force_render=True)[0],
                          "overview": task.cameras["overview"].render()[0]}
            if args.multiview:
                raw_frames["wrist"] = task.cameras["wrist"].render()[0]
            if args.clean:
                # Write camera RGB directly. No cropping, text, bars, montage
                # or image overlays are applied in the clean export path.
                for name, camera_name in streams.items():
                    rgb = raw_frames[camera_name]
                    if name in view_writers:
                        view_writers[name].append_data(rgb)
                        if j == len(indices)-1:
                            for _ in range(2*args.fps):
                                view_writers[name].append_data(rgb)
                    if j in (0, len(indices)-1):
                        imageio.imwrite(folder/f"{'initial' if j == 0 else 'final'}_{name}.png", rgb)
                if j % 30 == 0:
                    print(f"Rendered clean {j}/{len(indices)}", flush=True)
                continue
            frame = Image.fromarray(raw_frames["detail"])
            overview = Image.fromarray(raw_frames["overview"]).resize((320, 240))
            frame.paste(overview, (936, 158))
            draw = ImageDraw.Draw(frame)
            draw.rectangle((0, 0, 1280, 130), fill=(22, 31, 42))
            continuation = report.get("scope") == "checkpoint_continuation_diagnostic_not_complete_execution"
            heading = "保存状态续跑诊断 · 非完整执行" if continuation else (
                f"固定终端电缆 · {task.layout.fiber_count} 芯 · 环 R={task.layout.ring_inner_radius_m*1000:g} mm")
            draw.text((24, 12), heading, font=title, fill="white")
            draw.text((24, 58), label(str(data["phase"][i]), whole_bundle), font=font, fill=(245, 186, 96))
            draw.text((24, 96), f"仿真时间 {times[i]:.2f} s  |  回放 {args.speed:g} 倍速  |  夹爪碰细线即失败", font=small, fill=(208, 218, 230))
            passed = int(np.sum(state["fibers_m"][:, :, 0].min(axis=1)-task.layout.fiber_radius_m >
                                task.ring_center[0]+task.layout.ring_tube_radius_m))
            draw.rectangle((0, 795, 1280, 900), fill=(22, 31, 42))
            shape_label = "线形变化（仅记录）" if diagnostic_only else "已整理线变化"
            extra = "无逐根顺序要求" if whole_bundle else f"{shape_label} {data[shape_key][i]*1000:.3f} mm"
            total = task.layout.fiber_count
            draw.text((24, 806), f"整根穿环 {passed}/{total} 根    {extra}",
                      font=font, fill="white")
            status = "完整穿环已通过" if report["full_threading_verified"] and data["success"][i] else "完整穿环尚未完成"
            if continuation:
                status = "续跑达到穿环目标（非完整执行）" if data["success"][i] else "保存状态续跑诊断"
            assistance = "接触后启用夹持约束" if report["plan"]["grasp_assist"] != "none" else "纯接触夹持"
            draw.text((24, 853), f"{status}  |  {assistance}  |  细线被动、终端和环固定", font=small, fill=(208, 218, 230))
            if data["failed"][i]:
                draw.rectangle((24, 146, 820, 192), fill=(140, 30, 35))
                draw.text((36, 151), "任务规则判定失败，保留此状态用于诊断", font=font, fill="white")
            elif i == len(times)-1 and report.get("failure"):
                reason = report["failure"]
                reason_zh = "检查未通过，停止本次尝试"
                if "still branches outward" in reason:
                    reason_zh = "选中线仍超出孔径，停止本次尝试"
                elif "Grasp lost" in reason:
                    reason_zh = "夹持保持检查失败，停止本次尝试"
                elif "wires changed" in reason or "wire disturbed" in reason:
                    reason_zh = "邻线形状变化超限，停止本次尝试"
                elif "Fine contact penetration exceeded" in reason:
                    reason_zh = "细线接触穿透超限，停止本次尝试"
                elif "IK solution discontinuity" in reason:
                    reason_zh = "IK 关节目标不连续，停止本次尝试"
                draw.rectangle((24, 146, 900, 192), fill=(140, 65, 25))
                draw.text((36, 151), reason_zh, font=font, fill="white")
            if writer:
                writer.append_data(np.asarray(frame))
            for name, camera_name in streams.items():
                view = Image.fromarray(raw_frames[camera_name])
                caption = ImageDraw.Draw(view)
                caption.rectangle((0, 0, 1280, 90), fill=(22, 31, 42))
                caption.text((20, 8), f"{name}  |  {times[i]:.2f} s  |  {label(str(data['phase'][i]), whole_bundle)}",
                             font=font, fill="white")
                caption.text((20, 48), f"{status}  |  {assistance}  |  夹爪碰细线即失败", font=small, fill=(245, 186, 96))
                if name in view_writers:
                    view_writers[name].append_data(np.asarray(view))
                    if j == len(indices)-1:
                        for _ in range(2*args.fps):
                            view_writers[name].append_data(np.asarray(view))
                if j in (0, len(indices)-1):
                    view.save(folder/f"{'initial' if j == 0 else 'final'}_{name}.png")
            if j == 0:
                frame.save(folder/"initial.png")
            if j == len(indices)-1:
                frame.save(folder/"final.png")
                if writer:
                    for _ in range(2*args.fps):
                        writer.append_data(np.asarray(frame))
            if j % 30 == 0:
                print(f"Rendered {j}/{len(indices)}", flush=True)
    finally:
        if writer:
            writer.close()
        for stream_writer in view_writers.values():
            stream_writer.close()
    (folder/"render_report.json").write_text(json.dumps(dict(
        source="recorded native physics states; separate playback scene, no interpolation or stepping",
        report_sha256=hashlib.sha256(report_bytes).hexdigest(),
        trajectory_sha256=hashlib.sha256(trajectory_bytes).hexdigest(), playback_physics_steps=0,
        max_replay_centerline_error_m=maximum, renderer=args.renderer, backend=args.backend,
        recorded_physics_precision=recorded_precision,render_precision=args.render_precision,
        fps=args.fps, speed=args.speed,
        recorded_simulated_seconds=float(times[-1]), source_frames=len(times), rendered_frames=len(indices),
        stills_only=args.stills_only, encoded_frames=0 if args.stills_only else len(indices)+2*args.fps,
        synchronized_camera_streams=list(streams),
        ui_overlays=not args.clean, picture_in_picture=not args.clean,
        composite_video_generated=not args.clean and not args.stills_only,
        playback_duration_s=0 if args.stills_only else len(indices)/args.fps+2.,
        full_threading_verified=report["full_threading_verified"], robot_grasp_executed=report["robot_grasp_executed"]), indent=2)+"\n")


if __name__ == "__main__":
    main()
