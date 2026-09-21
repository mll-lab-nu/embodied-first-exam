"""Archive only a complete, independently rechecked physical fiber run."""
import argparse
from datetime import datetime, timezone
import hashlib
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from topogym.tasks.fiber_bundling.assess_ik import assess
from topogym.tasks.fiber_bundling import assess_passage


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("half_step", type=Path)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", args.run_id):
        parser.error("Use a plain run identifier")
    source, half = args.source.resolve(), args.half_step.resolve()
    comparison = assess(source, half)
    if not comparison["checks"]["both_complete_physical_runs_passed"]:
        raise ValueError("Both independent time steps must complete the physical task")
    passage = {name: assess_passage.assess(folder)
               for name, folder in (("baseline", source), ("half_step", half))}
    if not all(result["sampled_passage_passed"] for result in passage.values()):
        raise ValueError("Recorded fine-strand passage audit failed; inspect final plane crossings")
    report = json.loads((source/"report.json").read_text())
    from omegaconf import OmegaConf
    cfg = OmegaConf.load(source/"config.yaml")
    count = int(cfg.task.geometry.fiber_count)
    radius = float(cfg.task.geometry.ring_inner_radius_m)
    support = str(cfg.task.get("ring_mount", {}).get("kind", "legacy_box_v1"))
    variant = f"{support}_{count:02d}cores_r{radius*1000:g}mm"
    title = f"光纤收束 · {count} 芯 · 环内半径 {radius*1000:g} mm"
    plan = report["plan"]
    trace = np.load(source/"trajectory.npz")
    if (not report["robot_grasp_executed"] or trace["time_s"][0] != 0
            or trace["failed"].any() or not trace["success"][-1]
            or any(plan[k] != 0 for k in ("cable_pose_writes", "fine_force_commands",
                "terminal_pose_writes", "ring_pose_writes", "robot_pose_writes_after_home_reset"))):
        raise ValueError("Require a continuous legal run from reset, driven only by robot motors")
    render = json.loads((source/"render_report.json").read_text())
    cameras = ("agentview", "front_oblique", "wrist")
    if (render["stills_only"] or set(render["synchronized_camera_streams"]) != set(cameras)
            or render["report_sha256"] != sha(source/"report.json")
            or render["trajectory_sha256"] != sha(source/"trajectory.npz")
            or render["max_replay_centerline_error_m"] > 2e-6):
        raise ValueError("Require three synchronized views of the exact physical recording")
    validation = {}
    exported_cameras = (*cameras, "composite") if render.get("composite_video_generated", True) else cameras
    for camera in exported_cameras:
        path = source/("demo.mp4" if camera == "composite" else f"demo_{camera}.mp4")
        stream = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-count_frames",
            "-select_streams", "v:0", "-show_entries", "stream=width,height,avg_frame_rate,nb_read_frames,duration",
            "-of", "json", str(path)], text=True))["streams"][0]
        numerator, denominator = map(int, stream["avg_frame_rate"].split("/"))
        if (int(stream["nb_read_frames"]) != render["encoded_frames"]
                or numerator/denominator != render["fps"]
                or abs(float(stream["duration"])-render["playback_duration_s"]) > .001):
            raise ValueError(f"Video timing mismatch: {camera}")
        subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(path),
                        "-f", "null", "-"], check=True)
        validation[camera] = dict(**stream, fully_decoded=True, sha256=sha(path))
    metadata_root = ROOT/"runs/demo_metadata"
    metadata = metadata_root/"fiber_bundling"/args.run_id
    videos = ROOT/"demos/fiber_bundling"
    if metadata.exists() or any((videos/c/f"{args.run_id}_{c}.mp4").exists() for c in validation):
        raise FileExistsError("Archive prefix already exists; preserving the previous recording")
    metadata.mkdir(parents=True)
    videos.mkdir(parents=True, exist_ok=True)
    for src, dst in ((source, metadata), (half, metadata/"half_step")):
        for item in src.iterdir():
            if item.suffix == ".mp4" or item.name in ("playback_assets", "index.html"):
                continue
            if item.is_dir():
                shutil.copytree(item, dst/item.name)
            else:
                dst.mkdir(exist_ok=True)
                shutil.copy2(item, dst/item.name)
    gate = Path(plan["stability_gate"])
    if not gate.is_absolute():
        gate = ROOT/gate
    shutil.copytree(gate.parent, metadata/"stability_gate")
    shutil.copy2(__file__, metadata/"archive_source.py")
    shutil.copy2(assess_passage.__file__, metadata/"passage_audit_source.py")
    (metadata/"fine_passage_validation.json").write_text(json.dumps(passage, indent=2)+"\n")
    (metadata/"timestep_validation.json").write_text(json.dumps(comparison, indent=2)+"\n")
    (metadata/"video_validation.json").write_text(json.dumps(validation, indent=2)+"\n")
    video_records = {}
    for camera in validation:
        old = source/("demo.mp4" if camera == "composite" else f"demo_{camera}.mp4")
        new = videos/camera/f"{args.run_id}_{camera}.mp4"
        new.parent.mkdir(exist_ok=True)
        shutil.copy2(old, new)
        if sha(new) != validation[camera]["sha256"]:
            raise ValueError("Archive copy checksum mismatch")
        video_records[camera] = dict(path=os.path.relpath(new, metadata), sha256=sha(new))
    duration = render["playback_duration_s"]
    convergence = "严格全程时间步线形对照通过。" if comparison["passed"] else "严格全程时间步线形对照未通过，瞬时差异保存在验证报告中。"
    scope = "从场景初态执行抓取、整束接触收束和全部穿环；只操纵粗护套，接触后辅助夹持，末态保持夹持。无固定逐根顺序；两种时间步均完整完成任务。"+convergence
    if not render.get("ui_overlays", True):
        title += " · 无 UI 三视角"
        scope += "视频直接输出三个相机的完整画面，无文字、状态栏或画中画；由已记录的完整物理执行重新渲染。"
    links = "\n".join(f"- [{c}]({r['path']})" for c,r in video_records.items())
    (metadata/"README.md").write_text(f"# 固定终端电缆：完整机器人穿环\n\n{scope}\n\n实际仿真 {report['simulated_seconds']:.3f} s；视频 {duration:.2f} s，含末尾 2 s 保持。视频从同一次物理执行的保存状态渲染，未插值或拼接不同执行。\n\n{links}\n\n[物理报告](report.json) · [减半时间步报告](half_step/report.json) · [时间步对照](timestep_validation.json) · [视频检查](video_validation.json) · [配置](config.yaml)\n\n本目录保存独立的资产、配置、源代码、轨迹、指令与稳定性证据。plan.json 中原始路径保留作来源记录；核心证据与视频不依赖原始运行目录。结论限定于当前初态和离散物理模型，不等于真实铜线材料标定或纯摩擦夹持验证。\n")
    now = datetime.now(timezone.utc).isoformat()
    manifest = dict(task_id="fiber_bundling", variant=variant,
        fiber_count=count, ring_inner_radius_m=radius, support=support,
        run_id=args.run_id, source_directory=str(source.relative_to(ROOT)),
        video_layout="demos/fiber_bundling/<camera>/<original_filename>.mp4",
        classification="physical_execution_with_grasp_assistance", counts_as_complete_robotics_demo=True,
        strict_timestep_convergence_passed=comparison["passed"],
        scope=scope, recording_range_s=[0.,report["simulated_seconds"]], duration_s=duration,
        cameras=list(cameras), videos=video_records, archived_at_utc=now,
        ui_overlays=render.get("ui_overlays", True),
        metadata_sha256={str(p.relative_to(metadata)):sha(p) for p in sorted(metadata.rglob("*")) if p.is_file()})
    (metadata/"archive_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n")
    entry = dict(task_id="fiber_bundling", title=title,
        variant=manifest["variant"], classification=manifest["classification"],
        counts_as_complete_robotics_demo=True, duration_s=duration, cameras=list(cameras), scope=scope,
        source_directory=manifest["source_directory"], directory=f"fiber_bundling/{args.run_id}",
        index=f"fiber_bundling/{args.run_id}/README.md", archived_at_utc=now,
        video_directory="../../demos/fiber_bundling",
        ui_overlays=render.get("ui_overlays", True),
        video_files={c:f"../../demos/fiber_bundling/{c}/{args.run_id}_{c}.mp4" for c in validation})
    # Serialize our concurrent variant archives; preserve current shared entries.
    with (metadata_root/".fiber_archive.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        # Read shared indices immediately before updating, preserving other tasks.
        catalog = json.loads((metadata_root/"catalog.json").read_text())
        catalog["entries"].append(entry)
        catalog["excluded"] = [e for e in catalog["excluded"] if e["task_id"] != "fiber_bundling"]
        catalog["complete_robotics_demo_count"] = sum(e.get("counts_as_complete_robotics_demo",False) for e in catalog["entries"])
        catalog["archived_at_utc"] = now
        (metadata_root/"catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2)+"\n")
        readme = (metadata_root/"README.md").read_text()
        readme = re.sub(r"^- `fiber_bundling`：.*\n", "", readme, flags=re.MULTILINE)
        readme += f"\n[{title}](fiber_bundling/{args.run_id}/README.md)：{scope}\n"
        (metadata_root/"README.md").write_text(readme)
        page = (metadata_root/"index.html").read_text()
        page = re.sub(r"<tr><td>fiber_bundling</td><td>.*?</td></tr>", "", page)
        primary_camera = "composite" if "composite" in validation else "front_oblique"
        primary_video = entry["video_files"][primary_camera]
        section = f'<section><h2>{title}</h2><p>{scope}</p><p><a href="{primary_video}">完整视频</a> · <a href="fiber_bundling/{args.run_id}/README.md">目录与证据</a></p></section>'
        page = page.replace("</body>", section+"</body>")
        (metadata_root/"index.html").write_text(page)
    print(json.dumps(dict(videos=str(videos), metadata=str(metadata), manifest=manifest["run_id"])))


if __name__ == "__main__":
    main()
