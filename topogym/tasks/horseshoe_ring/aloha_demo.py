"""Solve with gravity, audit a legacy trace, or explicitly render a rehearsal."""
import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path

from hydra import compose, initialize_config_dir
import numpy as np
from omegaconf import OmegaConf, open_dict
from PIL import Image, ImageDraw
from scipy.spatial.transform import Rotation

from topogym.world.aloha_cameras import CAMERA_NAMES, configure_aloha_rig

ROOT = Path(__file__).resolve().parents[3]


def main():
    import genesis as gs
    from topogym.robot import initialize_robot_controller
    from .scene import build_scene

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("cpu", "cuda"))
    parser.add_argument("--renderer", choices=("rasterizer", "nyx"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--mode", choices=("physics", "audit", "kinematic"), default="physics",
                        help="Default: replan and solve with gravity; audit checks the old trace; kinematic is a zero-step rehearsal")
    parser.add_argument("--dt", type=float, default=.002, help="Time step for the replanned physical solution")
    parser.add_argument("--initial-only", action="store_true")
    parser.add_argument("--keyframes-only", action="store_true")
    parser.add_argument("--motion", type=Path)
    parser.add_argument("--config-path", type=Path, help="Resolved per-instance config for a generated scene")
    parser.add_argument("--camera-only", choices=("cam_low",), help="Update the low view and mosaic of an existing complete export")
    args = parser.parse_args()
    preview = args.initial_only or args.keyframes_only or args.camera_only
    args.backend = args.backend or ("cpu" if args.mode == "physics" and not preview else "cuda")
    args.renderer = args.renderer or ("rasterizer" if args.backend == "cpu" else "nyx")
    if args.mode == "physics" and not (args.initial_only or args.keyframes_only or args.camera_only):
        if args.motion or args.config_path:
            parser.error("The physical solver currently supports the packaged tutorial_solvable_v3 seed; use --mode audit for a custom legacy trace")
        if args.backend != "cpu" or args.renderer != "rasterizer":
            parser.error("The qualified physical solver uses --backend cpu --renderer rasterizer")
        import subprocess
        import sys
        output = args.output or ROOT / "runs/environment_bootstrap/horseshoe_ring/aloha_physical"
        subprocess.run([sys.executable, "-m", "topogym.tasks.horseshoe_ring.physical_demo",
                        "--output", str(output), "--dt", str(args.dt)], check=True)
        subprocess.run([sys.executable, "-m", "topogym.tasks.horseshoe_ring.render_physical",
                        str(output), "--output", str(output / "recording")], check=True)
        return
    if args.mode == "audit" and not preview:
        import subprocess
        import sys
        from .gravity_demo import DEFAULT_MOTION
        output = args.output or ROOT / "runs/environment_bootstrap/horseshoe_ring/aloha_gravity"
        command = [sys.executable, "-m", "topogym.tasks.horseshoe_ring.gravity_demo",
                   "--mode", "trace", "--output", str(output), "--backend", args.backend,
                   "--motion", str(args.motion or DEFAULT_MOTION)]
        if args.config_path:
            command += ["--config-path", str(args.config_path)]
        subprocess.run(command, check=True)
        # Render actual states even when the old IK trace fails in physics.
        # A failed audit is never silently replaced with the geometric witness.
        subprocess.run([sys.executable, "-m", "topogym.tasks.horseshoe_ring.render_gravity",
                        str(output), "--cameras", "detail", *CAMERA_NAMES], check=True)
        return
    if args.config_path:
        cfg = OmegaConf.load(args.config_path)
        cfg.env.genesis.backend = args.backend
        cfg.env.renderer.type = args.renderer
    else:
        with initialize_config_dir(config_dir=str(ROOT/"configs"), version_base="1.3"):
            cfg = compose(config_name="horseshoe_ring_aloha", overrides=[
                f"env.genesis.backend={args.backend}", f"env.renderer.type={args.renderer}"])
    output = args.output or ROOT/cfg.run.output
    custom_video = args.config_path and not args.keyframes_only and not args.initial_only
    if custom_video:
        from .variant_video import prepare_recording
        if args.camera_only:
            raise ValueError("Variant recordings require all cameras from one complete run")
        if not args.motion:
            raise ValueError("Variant recordings require an explicit certified motion file")
        prepare_recording(args.motion.parent, output)
        cfg.task.template_path = str((output/"template.json").resolve())
    output.mkdir(parents=True, exist_ok=True)
    metadata = configure_aloha_rig(cfg,
        low_pitch_offset_deg=float(cfg.run.get("aloha_low_camera_pitch_offset_deg", 0)))
    with open_dict(cfg.env.cameras):
        cfg.env.cameras.detail = OmegaConf.create(dict(res=[1280, 720], pos=[.12, -.53, 1.43],
            lookat=[-.1356786, .05, 1.13], up=[0, 0, 1], fov=43, near=.005, far=12))
    OmegaConf.save(cfg, output/"config.yaml", resolve=True)
    gs.init(backend=getattr(gs, args.backend), logging_level="warning", seed=0)
    task = build_scene(cfg, output/"assets")
    controller = initialize_robot_controller(scene=task.scene, manifest=task.manifest,
                                              robot_cfg=cfg.robot_control, settle_steps=0)
    motion_path = args.motion or output/"robot_motion.json"
    motion = None if args.initial_only else json.loads(motion_path.read_text())
    if motion and not motion["report"].get("sampled_robot_scene_clearance_passed", False):
        raise ValueError("Render requires a rehearsal that passed the sampled robot/scene checks")
    if motion:
        template_hash = hashlib.sha256(json.dumps(task.assembly.template, sort_keys=True).encode()).hexdigest()
        if (template_hash != motion["report"]["source_template_sha256"]
                or float(cfg.task.scale) != motion["report"]["scene_scale"]):
            raise ValueError("Rendered geometry differs from the certified rehearsal")
        cfg.run.fps = motion["fps"]
        cfg.run.video_seconds = len(motion["frames"])/motion["fps"]
        OmegaConf.save(cfg, output/"config.yaml", resolve=True)
    mount = np.asarray(cfg.env.robot_mount.pos, dtype=float)

    def pose(frame):
        controller.robot.set_qpos(np.asarray(frame["qpos"]))
        for name, p in frame["bodies"].items():
            task.bodies[name].set_pos(mount+np.asarray(p["pos"]))
            task.bodies[name].set_quat(np.asarray(p["quat"])[[3, 0, 1, 2]])
        task.scene.visualizer.update_visual_states(force_render=True)
        for name in CAMERA_NAMES[2:]:
            task.cameras[name].move_to_attach()

    if motion:
        pose(motion["frames"][0])
    task.scene.visualizer.update_visual_states(force_render=True)
    coverage = {}
    for name, camera in task.cameras.items():
        if name in CAMERA_NAMES[2:]:
            camera.move_to_attach()
        frame = camera.render(force_render=True)[0].copy()
        Image.fromarray(frame).save(output/f"initial_{name}.png")
        coverage[name] = dict(shape=list(frame.shape), std=float(frame.std()),
                              transform=np.asarray(camera.transform).tolist(), intrinsics=np.asarray(camera.intrinsics).tolist())
        print(f"Rendered {name}", flush=True)
    metadata["initial_camera_checks"] = coverage
    (output/"camera_report.json").write_text(json.dumps(metadata, indent=2)+"\n")
    (output/"initial_robot_state.json").write_text(json.dumps(controller.state(), indent=2)+"\n")
    if motion and args.keyframes_only:
        for i, phase in enumerate(motion["phases"]):
            pose(motion["frames"][phase["frame"]])
            for name in ("detail", "oblique", *CAMERA_NAMES):
                Image.fromarray(task.cameras[name].render(force_render=True)[0]).save(output/f"review_{i:02d}_{name}.png")
            print(f"Reviewed {phase['name']}", flush=True)
        return
    if motion:
        import imageio.v2 as imageio
        from .robot_motion import PAD_CENTER
        recorded = [args.camera_only] if args.camera_only else [*CAMERA_NAMES, "oblique", "detail"]
        stages = {p["frame"]: i for i, p in enumerate(motion["phases"])}
        fk_errors = []
        camera_transforms = []
        with ExitStack() as stack:
            writers = {name: stack.enter_context(imageio.get_writer(output/f"{name}.mp4",
                fps=motion["fps"], codec="libx264", quality=7, macro_block_size=1,
                ffmpeg_params=["-threads", "2"], ffmpeg_log_level="error"))
                for name in recorded+([] if args.camera_only else ["four_views"])}
            for i, frame in enumerate(motion["frames"]):
                pose(frame)
                for side, target in frame["grasp_targets"].items():
                    arm = controller.arms[side]
                    quat = arm.hand_quat()
                    actual = arm.hand_pos()+Rotation.from_quat(quat[[1, 2, 3, 0]]).apply(PAD_CENTER)
                    fk_errors.append(float(np.linalg.norm(actual-mount-np.asarray(target["pos"]))))
                    if fk_errors[-1] > .0005:
                        raise RuntimeError(f"Genesis gripper tracking differs from the checked IK at frame {i}")
                grid = Image.new("RGB", (1280, 720))
                for name in recorded:
                    rgb = task.cameras[name].render(force_render=True)[0].copy()
                    writers[name].append_data(rgb)
                    if name in CAMERA_NAMES:
                        j = CAMERA_NAMES.index(name)
                        tile = Image.fromarray(rgb).resize((640, 360))
                        draw = ImageDraw.Draw(tile)
                        draw.rectangle((0, 0, 640, 25), fill=(20, 28, 35))
                        draw.text((12, 7), name, fill="white")
                        grid.paste(tile, ((j % 2)*640, (j // 2)*360))
                    if i in stages and name == "detail":
                        Image.fromarray(rgb).save(output/f"stage_{stages[i]:02d}.png")
                if not args.camera_only:
                    writers["four_views"].append_data(np.asarray(grid))
                camera_transforms.append({n: np.asarray(task.cameras[n].transform).tolist() for n in CAMERA_NAMES})
                if i % 12 == 0:
                    print(f"Rendered {i+1}/{len(motion['frames'])}: {frame['stage']}", flush=True)
        if args.camera_only:
            import subprocess
            import imageio_ffmpeg
            updated = output/"four_views.updated.mp4"
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-y",
                "-i", str(output/"four_views.mp4"), "-i", str(output/"cam_low.mp4"),
                "-filter_complex", "[1:v]scale=640:360,crop=640:335:0:25[low];[0:v][low]overlay=640:25[v]",
                "-map", "[v]", "-c:v", "libx264", "-crf", "18", "-threads", "2", "-an", str(updated)], check=True)
            updated.replace(output/"four_views.mp4")
        for name in ("detail", "oblique"):
            Image.fromarray(task.cameras[name].render(force_render=True)[0]).save(output/f"final_{name}.png")
        report = dict(motion["report"], backend=args.backend, renderer=args.renderer,
            frames=len(motion["frames"]), fps=motion["fps"], duration_s=len(motion["frames"])/motion["fps"],
            maximum_genesis_pad_tracking_error_m=max(fk_errors, default=0.),
            phases=motion["phases"], camera_report="camera_report.json")
        (output/"replay_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False)+"\n")
        (output/"camera_poses.json").write_text(json.dumps(camera_transforms)+"\n")
        if custom_video:
            from .variant_video import write_instance_page
            write_instance_page(output)
            print(f"Complete variant recording: {output}", flush=True)
            return
        buttons = "".join(f'<button onclick="seek({p["time_s"]})">{p["name"]}</button>' for p in motion["phases"])
        cards = "".join(f'<figure><video class="sync" controls preload="metadata" src="{n}.mp4" '
                        f'poster="initial_{n}.png"></video><figcaption>{n}</figcaption></figure>' for n in CAMERA_NAMES)
        (output/"index.html").write_text(f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Horseshoe Ring · ALOHA 全流程预演</title>
<style>body{{max-width:1280px;margin:32px auto;padding:0 22px;font:16px/1.7 system-ui;background:#eff2f5;color:#22313f}}
section{{background:white;border-radius:12px;padding:22px;margin:22px 0}}video,img{{width:100%;border-radius:8px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}figure{{margin:0}}button{{padding:9px 14px;margin:4px;border:0;border-radius:6px;background:#dcebf4;cursor:pointer}}
a{{color:#146a94}}.badge{{background:#fff0ca;padding:12px;border-radius:8px}}@media(max-width:700px){{.grid{{grid-template-columns:1fr}}}}</style>
<p><a href="../../../environment-solvability/horseshoe_ring/index.html">尺寸对照</a> · <a href="../lab_initial/index.html">早期初态</a></p>
<h1>Horseshoe Ring · ALOHA 全流程运动学预演</h1>
<p>双臂抓持 → 翻转与折合 → 右臂合并抓持 → 左臂换抓圆环 → 调整并取出。</p>
<p class="badge">谜题零件的完整几何路径已通过连续碰撞检查。本页逐帧设置机器人关节与零件位姿，物理步数为 0；
合并抓持与换抓采用运动学接触假设，尚未验证力驱动抓取执行。相机图像来自实际 Genesis 场景。</p>
<section><video id="main" controls preload="metadata" src="detail.mp4" poster="initial_detail.png"></video>
<div>{buttons}</div><p>共 {report['duration_s']:.1f} 秒；按钮可跳到动作阶段。</p></section>
<section><h2>ALOHA 四路同步观测</h2><video id="mosaic" controls preload="metadata" src="four_views.mp4"></video>
<p><button onclick="toggleAll()">四路一起播放 / 暂停</button> 高位、低位、左腕、右腕，原始分辨率均为 1280×720。</p>
<div class="grid">{cards}</div></section>
<section><h2>完整实验室视角</h2><video controls preload="metadata" src="oblique.mp4" poster="initial_oblique.png"></video>
<img src="initial_room.png" alt="共用实验室中的双臂场景"></section>
<section><h2>证据与适用范围</h2><p>此原型有 5 个独立刚体：2 只马蹄、2 只中间链环和 1 只目标圆环。
圆环内径 118.4 mm，小于马蹄约 132 mm 的外宽。声明几何与路径的连续间隙下界超过 0.1 mm；
终态圆环与装配包围盒分离约 54.9 mm。尺寸是可解性原型参数，并非商品实测 CAD。</p>
<p><a href="../../../environment-solvability/horseshoe_ring/tutorial_solvable_v3/certificate.json">完整几何证书</a> ·
<a href="replay_report.json">机器人预演报告</a> · <a href="camera_report.json">相机位姿和内参差异</a> ·
<a href="assets/template.json">尺寸模板</a> · <a href="robot_motion.json">逐帧数据</a></p>
<p>全部录像帧通过机器人自身、谜题和桌面的采样穿透检查，容差分别为 0.1 / 0.3 / 1 mm。
该检查不等于机器人连续路径或力学执行保证。为覆盖抬高后的任务区，低位相机保留上游安装位置，朝向额外上仰 20°。</p>
<p>参考 <a href="https://www.youtube.com/watch?v=LAE1w1VNIZg">Professor Puzzle 官方解法视频</a>的翻转、折合和换抓顺序。
在不添加夹具的演示流程中采用双臂；这不证明带夹具或桌面支撑的单臂方案不可能。
外部相机与腕部相机统一采用上游模型坐标变换；Genesis 的单一垂直视场角接口使水平焦距比上游约大 2.4%，未宣称完整硬件标定一致。</p>
<img src="final_detail.png" alt="圆环与装配分离的终态"></section>
<script>const streams=[...document.querySelectorAll('.sync')];
function seek(t){{document.getElementById('main').currentTime=t;document.getElementById('mosaic').currentTime=t;streams.forEach(v=>v.currentTime=t)}}
function toggleAll(){{let go=streams[0].paused;let t=streams[0].currentTime;streams.forEach(v=>{{v.currentTime=t;go?v.play():v.pause()}})}}
streams[0].addEventListener('seeked',()=>streams.slice(1).forEach(v=>{{if(Math.abs(v.currentTime-streams[0].currentTime)>.15)v.currentTime=streams[0].currentTime}}));</script></html>''')
    print(f"Camera inspection: {output}", flush=True)


if __name__ == "__main__":
    main()
