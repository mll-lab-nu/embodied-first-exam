"""Archive synchronized full-route fixture videos with portable physical evidence."""

from __future__ import annotations

from topogym.utils.demo_paths import demo_video_root

import argparse
from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from .physics import ROOT, save
from .render import CAMERAS, physics_signature, sha


def probe(path):
    result = json.loads(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-count_frames",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height,avg_frame_rate,nb_read_frames,duration",
                "-of",
                "json",
                str(path),
            ]
        )
    )["streams"][0]
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-xerror",
            "-i",
            str(path),
            "-f",
            "null",
            "-",
        ],
        check=True,
    )
    return result


def archive(source, suite, run_id):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", run_id):
        raise ValueError("Use a simple run ID")
    source, suite = Path(source).resolve(), Path(suite).resolve()
    report = json.loads((source / "report.json").read_text())
    qualification = json.loads(suite.read_text())
    if (
        not report["complete"]
        or report["preview_only"]
        or not report["source_passed"]
        or not qualification["passed"]
    ):
        raise ValueError("Incomplete rendering or failed physical qualification")
    if report["cameras"] != list(CAMERAS) or report["robot_present"]:
        raise ValueError("This archive is specifically for three-view fixture rollouts")
    for name, digest in report["source_sha256"].items():
        if sha(source / "source_evidence" / name) != digest:
            raise ValueError("Source evidence changed: " + name)
    if (
        qualification["runs"]["nominal"]["report_sha256"]
        != report["source_sha256"]["report.json"]
    ):
        raise ValueError(
            "Qualification and rendered physics do not refer to the same rollout"
        )
    records = json.loads((source / "camera_poses.json").read_text())
    if len(records) != report["frame_count"] or any(
        r["frame"] != i
        or abs(r["time_s"] - i / report["fps"]) > 1e-8
        or set(r["cameras"]) != set(CAMERAS)
        for i, r in enumerate(records)
    ):
        raise ValueError(
            "Camera records are not synchronized on the complete measured timeline"
        )
    for asset in ("wire.urdf", "wand.urdf"):
        if physics_signature(source / "assets" / asset) != physics_signature(
            source / "source_evidence/assets" / asset
        ):
            raise ValueError("Rendered physical asset mismatch")
    probes = {}
    for name in CAMERAS:
        path = source / f"{name}.mp4"
        if sha(path) != report["video_sha256"][name]:
            raise ValueError("Video digest mismatch")
        data = probes[name] = probe(path)
        n, d = map(int, data["avg_frame_rate"].split("/"))
        if (
            int(data["nb_read_frames"]) != report["frame_count"]
            or n / d != report["fps"]
            or abs(float(data["duration"]) - report["duration_s"]) > 1e-5
        ):
            raise ValueError("Video timeline mismatch: " + name)
    metadata = ROOT / "runs/demo_metadata/buzz_wire_3d" / run_id
    destinations = {
        n: demo_video_root(ROOT, "buzz_wire_3d", report["variant"]) / n / f"{run_id}_fixture_{n}.mp4"
        for n in CAMERAS
    }
    if metadata.exists() or any(p.exists() for p in destinations.values()):
        raise FileExistsError("Use a new archive ID")
    metadata.mkdir(parents=True)
    for folder in ("source_evidence", "assets"):
        shutil.copytree(source / folder, metadata / folder)
    for name in (
        "report.json",
        "render_config.yaml",
        "render_source.py",
        "camera_poses.json",
        "physics_equivalence.json",
    ):
        shutil.copy2(source / name, metadata / name)
    shutil.copy2(__file__, metadata / "archive_source.py")
    shutil.copy2(
        Path(__file__).with_name("verify_physics.py"),
        metadata / "verify_physics_source.py",
    )
    archived_qualification = json.loads(suite.read_text())
    for name, run in qualification["runs"].items():
        original = Path(run["directory"])
        for item in ("report.json", "frames.json"):
            if sha(original / item) != run[item.replace(".json", "_sha256")]:
                raise ValueError("Physical evidence changed: " + name + "/" + item)
        shutil.copytree(original, metadata / "stability" / name)
        archived_qualification["runs"][name]["original_directory"] = str(original)
        archived_qualification["runs"][name]["directory"] = f"stability/{name}"
    save(metadata / "stability_report.json", archived_qualification)
    if suite.with_suffix(".png").exists():
        shutil.copy2(suite.with_suffix(".png"), metadata / "stability_plot.png")
    exploratory = metadata / "exploratory"
    exploratory.mkdir()
    for candidate in (
        suite.parent / "attempt_history.json",
        *suite.parent.glob("robot_*"),
    ):
        if candidate.is_file():
            shutil.copy2(candidate, exploratory / candidate.name)
    for name in ("geometry.py", "scene.py", "templates.py", "verification.py"):
        shutil.copy2(Path(__file__).with_name(name), metadata / ("render_" + name))
    videos = {}
    for name, destination in destinations.items():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / f"{name}.mp4", destination)
        if sha(destination) != report["video_sha256"][name]:
            raise ValueError("Archive copy mismatch")
        videos[name] = dict(
            path=os.path.relpath(destination, metadata),
            sha256=sha(destination),
            **probes[name],
        )
        for label, i in (
            ("initial", 0),
            ("middle", report["frame_count"] // 2),
            ("final", report["frame_count"] - 1),
        ):
            shutil.copy2(
                source / f"frame_{i:05d}_{name}.jpg", metadata / f"{label}_{name}.jpg"
            )
    scope = (
        "照片布局 spatial_maze_v2，有限力/力矩驱动真实动态环杆，从绿色端走完约 5.93 m 路线至橙色端，"
        "随后撤去驱动力并自由静置。三路来自同一次连续物理执行的实测状态，原速、无叠字。"
        "此为环杆动力学台架 demo；没有机械臂或抓持，不计为完整机器人 demo。"
    )
    details = (
        f"每路 {report['duration_s']:.2f} 秒，{report['fps']} fps，{report['frame_count']} 帧，960 × 720。"
        "验证涵盖自由下落、主动触线/退回、无触线全程通行、终点释放，以及时间步减半对照。"
        "模型采用刚性固定导线与底座；不包含铜线弹性或真实蜂鸣电路。"
    )
    (metadata / "README.md").write_text(
        "# 3D Buzz Wire · 全程环杆动力学 demo\n\n"
        + scope
        + "\n\n"
        + details
        + "\n\n"
        + "\n".join(f"- [{n}]({v['path']})" for n, v in videos.items())
        + "\n\n[物理验收](stability_report.json) · [视频检查](archive_validation.json) · [归档清单](archive_manifest.json)\n\n"
        "完整状态、配置、资产和运行时源码位于 `source_evidence/` 和 `stability/`；播放及核心证据不依赖原运行目录。"
        "`render_*` 为重渲染时使用的实现；物理执行之后没有再进行新的仿真步进。\n"
    )
    cards = "".join(
        f'<section><h2>{n}</h2><video controls preload="metadata" poster="initial_{n}.jpg" src="{html.escape(v["path"])}"></video><p><a href="{html.escape(v["path"])}">下载 MP4</a></p></section>'
        for n, v in videos.items()
    )
    physical = qualification["reports"]
    metrics = (
        "<table><tr><th>检查</th><th>结果</th></tr>"
        f"<tr><td>自由下落并稳定</td><td>最大记录穿透 {1000 * physical['gravity']['maximum_penetration_m']:.3f} mm</td></tr>"
        f"<tr><td>主动触线并退回</td><td>接触被检出；最大记录穿透 {1000 * physical['contact']['maximum_penetration_m']:.3f} mm</td></tr>"
        f"<tr><td>完整路线</td><td>零触线；最大位置误差 {1000 * physical['nominal']['phases']['traverse']['max_tracking_error_m']:.3f} mm</td></tr>"
        f"<tr><td>减半时间步对照</td><td>受控轨迹最大位置差 {1000 * qualification['maximum_controlled_position_difference_m']:.3f} mm</td></tr>"
        "</table>"
    )
    (metadata / "index.html").write_text(
        """<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>3D Buzz Wire · 全程动力学 demo</title><style>body{max-width:1120px;margin:28px auto;padding:0 20px;background:#edf2f5;color:#253541;font:16px/1.7 system-ui}section{background:white;padding:18px;margin:18px 0;border-radius:12px}video{width:100%;max-height:720px}button{padding:9px 18px;margin:5px}a{color:#126d93}</style><h1>3D Buzz Wire · 全程环杆动力学 demo</h1><p>"""
        + html.escape(scope)
        + "</p><p>"
        + html.escape(details)
        + """</p><button onclick="playAll()">三路同步播放</button><button onclick="all().forEach(v=>v.pause())">全部暂停</button><button onclick="seekAll(0)">回到起点</button><button onclick="seekAll(62)">终点释放</button><p><a href="stability_report.json">物理验收</a> · <a href="archive_validation.json">视频检查</a> · <a href="archive_manifest.json">归档清单</a></p>"""
        + metrics
        + cards
        + """<script>function all(){return [...document.querySelectorAll('video')]}function seekAll(t){all().forEach(v=>v.currentTime=t)}function playAll(){const vs=all();seekAll(vs[0].currentTime);vs.forEach(v=>v.play())}setInterval(()=>{const vs=all(),master=vs[0];if(!master.paused)vs.slice(1).forEach(v=>{if(Math.abs(v.currentTime-master.currentTime)>.12)v.currentTime=master.currentTime})},500)</script></html>"""
    )
    page = metadata / "index.html"
    release_time = min(
        r["time_s"]
        for r in json.loads((source / "source_evidence/frames.json").read_text())
        if r["phase"] == "release"
    )
    page.write_text(
        page.read_text()
        .replace("seekAll(62)", f"seekAll({release_time})")
        .replace(
            '<a href="stability_report.json">物理验收</a>',
            '<a href="stability_report.json">物理验收</a> · <a href="stability_plot.png">测量曲线</a>',
        )
    )
    save(
        metadata / "archive_validation.json",
        dict(
            passed=True,
            full_decode=True,
            synchronized=True,
            physical_geometry_preserved=True,
            source_matches_qualification=True,
            videos=probes,
        ),
    )
    now = datetime.now(timezone.utc).isoformat()
    manifest = dict(
        task_id="buzz_wire_3d",
        variant=report["variant"],
        run_id=run_id,
        classification=report["classification"],
        counts_as_complete_robotics_demo=False,
        counts_as_complete_process_demo=True,
        robot_present=False,
        source_physics_success=True,
        new_physics_execution=False,
        scope=scope,
        duration_s=report["duration_s"],
        recording_range_s=report["recording_range_s"],
        cameras=list(CAMERAS),
        source_directory=str(source),
        physical_source_directory=report["source_directory"],
        videos=videos,
        archived_at_utc=now,
        metadata_sha256={
            str(p.relative_to(metadata)): sha(p)
            for p in sorted(metadata.rglob("*"))
            if p.is_file()
        },
    )
    save(metadata / "archive_manifest.json", manifest)
    catalog_path = ROOT / "runs/demo_metadata/catalog.json"
    catalog = json.loads(catalog_path.read_text())
    entry = {
        k: manifest[k]
        for k in (
            "task_id",
            "variant",
            "classification",
            "counts_as_complete_robotics_demo",
            "counts_as_complete_process_demo",
            "scope",
            "duration_s",
            "cameras",
            "archived_at_utc",
        )
    }
    entry.update(
        title="3D Buzz Wire · 全程环杆动力学（无机器人）",
        directory=f"buzz_wire_3d/{run_id}",
        index=f"buzz_wire_3d/{run_id}/index.html",
        video_directory="../../demos/buzz_wire_3d",
        video_layout="camera_subdirectories",
        video_files={
            n: os.path.relpath(p, catalog_path.parent) for n, p in destinations.items()
        },
    )
    catalog["entries"].append(entry)
    catalog.setdefault("task_video_layout", {})["buzz_wire_3d"] = dict(
        organization="one MP4 per camera; finite-wrench fixture, no robot",
        video_directory="../../demos/buzz_wire_3d",
        metadata_directory="buzz_wire_3d",
        cameras=list(CAMERAS),
    )
    catalog["updated_at_utc"] = now
    save(catalog_path, catalog)
    for filename in ("README.md", "index.html"):
        path = catalog_path.parent / filename
        content = path.read_text()
        if filename.endswith(".md"):
            content += f"\n[3D Buzz Wire · 全程环杆动力学](buzz_wire_3d/{run_id}/index.html)：三路各 {report['duration_s']:.2f} 秒；物理台架及减半时间步验收通过，不含机器人。\n"
        else:
            section = f'<section><h2><a href="buzz_wire_3d/{run_id}/index.html">{entry["title"]}</a></h2><p>{html.escape(scope)}</p></section>'
            content = (
                content.replace("</body>", section + "</body>")
                if "</body>" in content
                else content + section
            )
        path.write_text(content)
    print(metadata)
    return metadata


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--suite", type=Path, required=True)
    p.add_argument("--run-id", required=True)
    archive(**vars(p.parse_args()))


if __name__ == "__main__":
    main()
