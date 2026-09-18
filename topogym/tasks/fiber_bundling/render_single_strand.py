"""Render recorded physical states; never synthesize a straightening animation.

Every displayed wire pose comes from trajectory.npz. Rendering writes those
recorded states into a separate scene without advancing its physics solver.
"""
import argparse
import json
from pathlib import Path
import re

import numpy as np

from .geometry import FiberLayout, shape_in_root_frame
from .scene import apply_cable_colors, cable_state
from .single_strand import strand_metrics


PHASE_NAMES = dict(initial="初态：红线自然外弯", settle="初态：红线自然外弯",
    align_tip="偏移粗绳，对准红色线头", capture_tip="送入线头，接近环口",
    feed_and_comb="推进并回正，利用环口捋线", recenter="继续回正粗绳",
    draw_back="回拉粗绳，利用环口捋直红线", verify_feed="再次向前送线，检查穿环方向",
    trim_axis="微调粗绳朝向，对齐穿环方向", hold="停止动作，观察整理结果")


def main():
    import genesis as gs
    import imageio.v2 as imageio
    from hydra import compose, initialize_config_dir
    from omegaconf import OmegaConf
    from PIL import Image, ImageDraw, ImageFont
    from topogym.world import StandardTabletopSceneBuilder

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--stride", type=int, default=1)
    args = parser.parse_args()
    output = args.output.resolve()
    report = json.loads((output/"report.json").read_text())
    full_mode = report["scope"] == "sequential_full_bundle_by_trunk_fixture"
    layout = FiberLayout(**report["layout"])
    data = np.load(output/"trajectory.npz")
    with initialize_config_dir(version_base="1.3", config_dir=str(Path(__file__).resolve().parents[3]/"configs")):
        cfg = compose(config_name="fiber_bundling_preview")
    cfg.env.cameras = OmegaConf.create({
        "detail": dict(res=[1280, 900], pos=[.26, .82, 1.36], lookat=[.060, .400, 1.158],
                       up=[0, 0, 1], fov=22, near=.002, far=12),
        "axial": dict(res=[480, 480], pos=[.55, .401, 1.170], lookat=[.10, .40, 1.160],
                      up=[0, 0, 1], fov=17, near=.002, far=12)})
    if full_mode:
        cfg.env.cameras.detail.pos = [.27, .0, 1.38]
        cfg.env.cameras.detail.fov = 28
    gs.init(backend=gs.cuda, logging_level="warning", seed=layout.seed)
    builder = StandardTabletopSceneBuilder(cfg.env, cfg.robot_control)
    base = builder.create(show_viewer=False, include_robot=False)
    scene, manifest = base.scene, base.manifest
    shift = np.array([-.24, .40, base.frames.table_surface_origin[2]+.24-.5])
    ring_center = np.asarray(report["ring_center_m"])+shift
    cable = manifest.add("fiber_bundle", scene.add_entity(gs.morphs.MJCF(
        file=str(output/"assets/bundle_fixture.xml"), pos=data["root_positions"][0]+shift,
        convexify=True, decimate=False), material=gs.materials.Rigid(gravity_compensation=1.)))
    apply_cable_colors(cable)
    manifest.add("bundling_ring", scene.add_entity(gs.morphs.URDF(
        file=str(output/"assets/ring.urdf"), pos=ring_center, euler=(0, 90, 0), fixed=True,
        merge_fixed_links=False, decimate=False), material=gs.materials.Rigid(friction=.35)))
    floor = base.frames.table_surface_origin[2]
    bottom = ring_center[2]-(layout.ring.radius_m+layout.ring.tube_radius_m)
    manifest.add("ring_mount", scene.add_entity(gs.morphs.Box(pos=(ring_center[0], ring_center[1], (floor+bottom)/2),
        size=(.012, .016, bottom-floor), fixed=True), surface=gs.surfaces.Plastic(color=(.38, .43, .49))))
    builder.finalize(base)
    font_path = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
    title_font, font, small = [ImageFont.truetype(font_path, size) for size in (30, 24, 19)]
    if args.stride < 1:
        raise ValueError("stride must be positive")
    unique_times = np.r_[np.flatnonzero(np.diff(data["times"]) > 1e-10), len(data["times"])-1]
    frames = unique_times[::args.stride]
    if frames[-1] != len(data["times"])-1:
        frames = np.append(frames, len(data["times"])-1)
    fps = 15
    max_replay_error = 0.
    phase_stills = {}
    phase_seek = {}
    last_phase = None
    references = []
    for event in report.get("preparation_events", []):
        if event["prepared"]:
            j = np.argmin(np.abs(data["times"]-event["simulation_time"]))
            references.append((event["target"], event["simulation_time"],
                               shape_in_root_frame(data["fibers"][j])[event["target"]]))
    with imageio.get_writer(output/"demo.mp4", fps=fps, codec="libx264", quality=8,
                           macro_block_size=1, ffmpeg_log_level="error") as writer:
        for frame_number, index in enumerate(frames):
            # Display an actual saved state, with no intervening simulation.
            cable.set_pos(data["root_positions"][index]+shift, zero_velocity=False)
            if "root_quaternions" in data:
                cable.set_quat(data["root_quaternions"][index], zero_velocity=False)
            cable.set_qpos(data["qpos"][index], zero_velocity=False)
            state = cable_state(cable, layout)
            error = float(np.linalg.norm(state["fibers_m"]-(data["fibers"][index]+shift), axis=-1).max())
            max_replay_error = max(max_replay_error, error)
            if error > 2e-6:
                raise RuntimeError(f"Replay differs from recorded physics by {error} m")
            phase = str(data["phases"][index])
            phase_seek.setdefault(phase, frame_number/fps+(1 if frame_number else 0))
            metric = strand_metrics(state["fibers_m"], ring_center, layout)
            phase_label = PHASE_NAMES.get(phase, phase)
            if full_mode:
                match = re.fullmatch(r"wire_(\d+)_(\w+)", phase)
                if match:
                    color = ("红", "蓝", "绿", "棕", "白", "黄", "黑", "灰")[int(match[1])]
                    phase_label = dict(park="后撤至环前", select=f"转动粗绳，选择{color}线",
                        approach=f"将{color}线头移至环外侧", press=f"用环外侧轻压{color}线",
                        settle="接触静置", release="撤开粗绳，保留整理形状",
                        inspect=f"检查{color}线及已整理电线")[match[2]]
                else:
                    phase_label = dict(initial="初态：8 根电线自然外弯", initial_hold="检查初态",
                        bundle_retreat="全部整理后，退至环前", bundle_unroll="恢复粗绳朝向",
                        bundle_align="整束对准环孔", before_push="确认整束电线可以容入孔径",
                        whole_bundle_push="一次推进：细线与粗绳依次穿环", final_hold="通过后静置检查").get(phase, phase)
                if phase in ("whole_bundle_push", "final_hold"):
                    progress = np.clip((data["root_positions"][index,0]+.020)/.390, 0., 1.)
                    focus = np.array([.060+.13*progress, .400, 1.158])
                    base.cameras["detail"].set_pose(pos=focus+np.array([.210,-.400,.222])*(1+1.2*progress),
                                                   lookat=focus, up=(0,0,1))
            # Replay does not advance scene.t; explicitly refresh visual poses.
            scene.visualizer.update_visual_states(force_render=True)
            frame = Image.fromarray(base.cameras["detail"].render(force_render=True)[0])
            # Nyx renders both cameras in one shared pass above.
            inset = Image.fromarray(base.cameras["axial"].render()[0]).resize((260, 260))
            frame.paste(inset, (995, 180))
            draw = ImageDraw.Draw(frame)
            draw.rectangle((0, 0, 1280, 140), fill=(22, 31, 42))
            title = "逐根整理电线，再整束穿环" if full_mode else "单根细线整理 · 观察红色电线"
            draw.text((28, 15), title, font=title_font, fill="white")
            draw.text((28, 62), phase_label, font=font, fill=(245, 186, 96))
            draw.text((28, 103), f"仿真时间 {data['times'][index]:.2f} s   ·   仅驱动粗绳夹持端   ·   固定圆环", font=small, fill=(203, 215, 228))
            draw.rectangle((0, 810, 1280, 900), fill=(22, 31, 42))
            bottom_text = f"红线末端与环轴夹角  {metric['tip_angle_deg']:.1f}°    |    线头越过环后  {metric['tip_beyond_ring_m']*1000:.1f} mm"
            if full_mode:
                local = shape_in_root_frame(state["fibers_m"])
                radii = np.linalg.norm(local[:,:,1:], axis=-1).max(axis=1)+layout.fiber_radius_m
                prepared = int(np.sum((radii < layout.minimum_aperture_radius-.0003) &
                                     (np.diff(local[:,:,0], axis=1)>0).all(axis=1)))
                beyond = int(np.sum(state["fibers_m"][:,:,0].min(axis=1)-layout.fiber_radius_m >
                                    ring_center[0]+layout.ring_tube_radius_m))
                protected_error = max((float(np.linalg.norm(local[i]-ref,axis=-1).max()) for i,t,ref in references
                                       if data["times"][index] >= t), default=0.)
                bottom_text = f"可容入孔径  {prepared}/8 根    |    整根过环  {beyond}/8 根    |    已整理线变化  {protected_error*1000:.2f} mm"
            draw.text((28, 823), bottom_text, font=font, fill="white")
            draw.text((28, 866), "实际物理轨迹慢放；显式夹持端演示，尚未执行机械臂抓取。", font=small, fill=(203, 215, 228))
            draw.text((1008, 151), "沿环轴观察", font=small, fill=(25, 35, 45))
            rgb = np.asarray(frame)
            writer.append_data(rgb)
            if frame_number == 0:
                frame.save(output/"initial.png")
                for _ in range(fps):
                    writer.append_data(rgb)
            if phase != last_phase and last_phase is not None:
                previous.save(output/f"phase_{last_phase}.png")
                phase_stills[last_phase] = f"phase_{last_phase}.png"
            last_phase, previous = phase, frame
            if frame_number % 30 == 0:
                print(f"Rendered {frame_number}/{len(frames)}", flush=True)
        frame.save(output/"final.png")
        for _ in range(fps*2):
            writer.append_data(rgb)
    metadata = dict(source="recorded physical trajectory.npz; no pose interpolation or physics during rendering",
        max_replay_centerline_error_m=max_replay_error, fps=fps, sampled_frames=len(frames),
        source_simulated_seconds=report["simulated_seconds"], cameras=OmegaConf.to_container(cfg.env.cameras),
        display_world_translation_m=shift.tolist(), robot_grasp_executed=False)
    (output/"render_report.json").write_text(json.dumps(metadata, indent=2)+"\n")
    start, end = report["initial"], report["final"]
    status = "通过" if report["passed"] else "探索中：尚未通过"
    (output/"index.html").write_text(f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>红色细线整理过程</title>
<style>body{{max-width:1120px;margin:36px auto;padding:0 24px;background:#f4f6f8;color:#203143;font:17px/1.7 system-ui}}
video,img{{width:100%;border-radius:12px}}section{{background:white;padding:24px;margin:20px 0;border-radius:14px}}a{{color:#126995}}</style>
<h1>整理一根细线：红色电线</h1><p>局部检查：{status}。偏移粗绳对准线头，送入环口，再回正与小幅回拉。
细线全程被动，环的位置固定；仅移动粗绳后端的显式夹持端。其余七根细线仍保留真实碰撞。</p>
<section><video controls preload="metadata" poster="initial.png" src="demo.mp4"></video>
<p>记录的物理仿真状态慢放，右上角为沿环轴视图。当前验证的是粗绳夹持端动作，尚未执行机械臂实际抓取。</p></section>
<p>红线末端与环轴夹角：{start['tip_angle_deg']:.1f}° → {end['tip_angle_deg']:.1f}°；
线头越过环后 {end['tip_beyond_ring_m']*1000:.1f} mm。
红线横向包络半径（含线本身半径）：{start['radial_envelope_m']*1000:.2f} → {end['radial_envelope_m']*1000:.2f} mm；
环最小净孔半径 {layout.minimum_aperture_radius*1000:.2f} mm。整束细线和粗绳全部穿环尚未验证。</p>
<section><h2>整理前</h2><img src="initial.png"></section>
<section><h2>整理后</h2><img src="final.png"></section>
<p><a href="report.json">物理检查</a> · <a href="plan.json">粗绳动作</a> ·
<a href="render_report.json">录制来源与回放误差</a> · <a href="trajectory.npz">原始轨迹</a> ·
<a href="../branched_initial/index.html">基础场景</a></p></html>''')
    if full_mode:
        events = "".join(f"<tr><td>{e['target']+1}</td><td>{e['envelope_radius_m']*1000:.2f} mm</td>"
                         f"<td>{'完成' if e['prepared'] else '未完成'}</td></tr>" for e in report["preparation_events"])
        drift = max(report["protected_shape_changes_m"].values(), default=0.)*1000
        conclusion = "完整穿环检查通过" if report["passed"] else "本次尝试未完成："+str(report["failure"])
        names = {**{f"wire_{i}_press": f"整理{color}线" for i,color in enumerate(("红", "蓝", "绿", "棕", "白", "黄", "黑", "灰"))},
                 "before_push": "整理结果", "whole_bundle_push": "整束穿环"}
        chapters = " ".join(f'<button data-time="{phase_seek[p]:.2f}">{label}</button>'
                            for p,label in names.items() if p in phase_seek)
        (output/"index.html").write_text(f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>逐根整理与整束穿环</title>
<style>body{{max-width:1120px;margin:36px auto;padding:0 24px;background:#f4f6f8;color:#203143;font:17px/1.7 system-ui}}
video,img{{width:100%;border-radius:12px}}section{{background:white;padding:24px;margin:20px 0;border-radius:14px}}
td{{padding:6px 24px}}a{{color:#126995}}button{{margin:4px;padding:8px 12px;cursor:pointer}}</style><h1>{conclusion}</h1>
<p>依次转动粗绳选择电线，用固定环的外侧轻压线头。撤开后检查该线的横向包络，
并检查之前整理过的电线是否改变形状。全部准备好后，整束对准内孔，一次向前推进。</p>
<section><video id="demo" controls preload="metadata" poster="initial.png" src="demo.mp4"></video><p>{chapters}</p>
<p>记录的实际 {report['backend']} 物理状态慢放，原始模拟时长 {report['simulated_seconds']:.2f} 秒。
只驱动粗绳夹持端，8 根细线全程被动，固定环及支架参与碰撞；尚未执行机械臂实际抓取。</p></section>
<p>已整理电线的累计最大形状变化为 {drift:.3f} mm，验收阈值为 0.5 mm。
“整根过环”要求整个细线及其半径越过环后平面；完整成功还要求粗绳也全部通过。</p>
<table><tr><th>电线</th><th>整理后横向包络半径</th><th>状态</th></tr>{events}</table>
<section><h2>初态</h2><img src="initial.png"></section>
<section><h2>最终状态</h2><img src="final.png"></section>
<p><a href="report.json">实际物理结果</a> · <a href="plan.json">动作策略与阈值</a> ·
<a href="render_report.json">回放误差</a> · <a href="trajectory.npz">原始状态</a> ·
<a href="timestep_validation.json">全流程时间步复核</a> · <a href="demo.mp4">视频文件</a> ·
<a href="../../../environment-solvability/fiber_bundling/stability_cpu/index.html">稳定性检查</a> ·
<a href="../branched_initial/index.html">基础场景</a></p>
<script>document.querySelectorAll('button[data-time]').forEach(b=>b.onclick=()=>{{const v=document.getElementById('demo');v.currentTime=Number(b.dataset.time);v.play();}});</script></html>''')
        from .assess_sequence import publish_summary
        publish_summary(output)
    page=(output/"index.html").read_text()
    page=page.replace('<h1>', '<p><strong>历史自由电缆演示。</strong>当前任务已改成固定终端，'
        '本视频不作为新版验收依据。<a href="../anchored_initial/index.html">打开当前场景</a></p><h1>',1)
    (output/"index.html").write_text(page)
    print(output/"index.html", flush=True)


if __name__ == "__main__":
    main()
