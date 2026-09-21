"""Render exact recorded gravity-check states, including explicitly failed audits."""
import argparse
from contextlib import ExitStack
from html import escape
import json
from pathlib import Path

import numpy as np
from omegaconf import OmegaConf

from .gravity_demo import sha


def render(source, *, cameras=("detail", "cam_high", "cam_low")):
    import genesis as gs
    import imageio.v2 as imageio
    from PIL import Image, ImageDraw
    from .scene import build_scene

    source = Path(source).resolve()
    report = json.loads((source / "result.json").read_text())
    trace = source / "physical_states.jsonl"
    if sha(trace) != report["physical_states_sha256"] or not report["physics_steps"]:
        raise ValueError("Missing or changed physical state evidence")
    frames = [json.loads(line) for line in trace.read_text().splitlines()]
    if len(frames) != report["physical_frame_count"] or [f["frame"] for f in frames] != list(range(len(frames))):
        raise ValueError("Physical frames are incomplete")
    if not all(np.isclose(f["time_s"], f["step"]*report["dt"]) for f in frames):
        raise ValueError("Snapshots do not match physical time")
    if any((source / f"{name}.mp4").exists() for name in cameras):
        raise FileExistsError("Preserve existing gravity recordings")
    cfg = OmegaConf.load(source / "config.yaml")
    rig = json.loads((source / "recording_cameras.json").read_text())
    cfg.env.cameras = OmegaConf.create({name: rig[name] for name in cameras})
    cfg.task.template_path = str(source / "input_template.json")
    cfg.env.genesis.backend = "cpu"
    cfg.env.renderer.type = "rasterizer"
    gs.init(backend=gs.cpu, precision="64", logging_level="warning", seed=0)
    task = build_scene(cfg, source / "render_assets")
    if sha(source / "render_assets/template.json") != sha(source / "assets/template.json"):
        raise ValueError("Rendering geometry differs from physical geometry")
    robot = task.manifest.get("robot")
    fps = report["physical_frame_fps"]
    failed = bool(report["failure"])
    with ExitStack() as stack:
        writers = {name: stack.enter_context(imageio.get_writer(source / f"{name}.mp4", fps=fps,
                   codec="libx264", quality=8, macro_block_size=1, ffmpeg_log_level="error")) for name in cameras}
        for i, frame in enumerate(frames):
            robot.set_qpos(np.asarray(frame["qpos"]), zero_velocity=True)
            for name, body in task.bodies.items():
                body.set_pos(np.asarray(frame["bodies"][name]["pos"]))
                body.set_quat(np.asarray(frame["bodies"][name]["quat_wxyz"]))
            task.scene.visualizer.update_visual_states(force_render=True)
            for name, writer in writers.items():
                camera = task.cameras[name]
                if name.endswith("wrist"):
                    camera.move_to_attach()
                image = Image.fromarray(camera.render(force_render=True)[0])
                draw = ImageDraw.Draw(image)
                draw.rectangle((0, 0, image.width, 49), fill=(16, 25, 34))
                drop = (report["ring_initial_height_m"]-frame["bodies"]["target_ring"]["pos"][2])*1000
                draw.text((10, 5), f"HORSESHOE | PHYSICS | {name} | t={frame['time_s']:.3f}s | ring drop={drop:.1f}mm", fill="white")
                label = "OLD IK PHYSICAL AUDIT - FAILED" if failed else "GRAVITY HOLD CHECK - NOT AN EXTRACTION DEMO"
                draw.text((10, 26), label + " | PREGRASP ASSIST ON SHOES ONLY", fill=(255, 211, 119))
                writer.append_data(np.asarray(image))
                if i in (0, len(frames)-1):
                    image.save(source / f"{'initial' if i==0 else 'final'}_{name}.jpg")
            if i % 20 == 0:
                print(f"Rendered gravity evidence {i+1}/{len(frames)}", flush=True)
    evidence = dict(recording_kind="offline_render_of_exact_physical_states", source_result_sha256=sha(source/"result.json"),
        source_states_sha256=sha(trace), source_physics_steps=report["physics_steps"], render_physics_steps=0,
        no_interpolation=True, frame_count=len(frames), fps=fps, duration_s=len(frames)/fps,
        final_snapshot_time_s=frames[-1]["time_s"], cameras=list(cameras), task_success=False,
        videos={n: dict(path=f"{n}.mp4", sha256=sha(source/f"{n}.mp4")) for n in cameras})
    (source / "render_report.json").write_text(json.dumps(evidence, indent=2)+"\n")
    status = ("旧 IK 轨迹物理检查未通过："+escape(report["failure"])) if failed else "重力悬挂检查完成；此短片不代表完整取环成功。"
    cards = "".join(f'<figure><video controls class="sync" preload="metadata" src="{n}.mp4" poster="initial_{n}.jpg"></video><figcaption>{n}</figcaption></figure>' for n in cameras)
    (source / "index.html").write_text(f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Horseshoe Ring · 重力检查</title>
<style>body{{max-width:1180px;margin:30px auto;padding:0 20px;font:16px/1.7 system-ui;background:#eef2f6}}video{{width:100%}}figure{{margin:20px 0}}button{{padding:10px;margin:6px}}.note{{background:#fff1cc;padding:15px}}</style>
<h1>Horseshoe Ring · 重力检查</h1><p class="note">{status}</p>
<p>重力 {abs(report['gravity_m_s2'][2]):g} m/s²，实际推进 {report['physics_steps']} 个物理步。
圆环向下移动 {report['ring_downward_displacement_m']*1000:.2f} mm。
初态两只马蹄使用明确的夹手辅助约束，圆环和链环自由运动；仿真期间没有重设任何零件位姿。</p>
<p>视频逐帧渲染同一次物理运行保存的状态。旧几何轨迹的可解性不等于重力下执行成功。</p>
<button onclick="streams.forEach(v=>{{v.currentTime=0;v.playbackRate=1;v.play()}})">同步播放</button>
<button onclick="streams.forEach(v=>{{v.currentTime=0;v.playbackRate=.25;v.play()}})">0.25 倍速看下落</button>
{cards}<p><a href="result.json">物理报告</a> · <a href="physical_states.jsonl">实际状态</a> · <a href="render_report.json">录像证据</a></p>
<script>const streams=[...document.querySelectorAll('.sync')];</script></html>''')
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--cameras", nargs="+", default=["detail", "cam_high", "cam_low"])
    args = parser.parse_args()
    render(args.source, cameras=args.cameras)


if __name__ == "__main__":
    main()
