"""Preserve a verified, synchronized single-arm demo and its physical evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil

from .archive import probe
from .physics import ROOT, save
from .robot_render import CAMERAS, sha
from .render import physical_assets_signature


def archive(source, suite, run_id):
    source, suite = Path(source).resolve(), Path(suite).resolve()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", run_id):
        raise ValueError("Use a simple run ID")
    report = json.loads((source / "report.json").read_text())
    qualification = json.loads(suite.read_text())
    if not all(
        (
            report["complete"],
            not report["preview_only"],
            report["source_passed"],
            report["robot_present"],
            qualification["passed"],
        )
    ):
        raise ValueError("Complete, passing robot physics and rendering are required")
    if report["cameras"] != list(CAMERAS):
        raise ValueError("Three synchronized robot cameras are required")
    for name, digest in report["source_sha256"].items():
        if sha(source / "source_evidence" / name) != digest:
            raise ValueError("Source evidence changed: " + name)
    if (
        qualification["runs"]["nominal"]["report_sha256"]
        != report["source_sha256"]["report.json"]
    ):
        raise ValueError("Rendering must use the qualified nominal rollout")
    records = json.loads((source / "camera_poses.json").read_text())
    if len(records) != report["frame_count"] or any(
        r["frame"] != i
        or abs(r["time_s"] - i / report["fps"]) > 1e-8
        or set(r["cameras"]) != set(CAMERAS)
        for i, r in enumerate(records)
    ):
        raise ValueError("Camera timestamps are not synchronized")
    if physical_assets_signature(source / "assets") != physical_assets_signature(
        source / "source_evidence/assets"
    ):
        raise ValueError("Rendered collision/inertial asset mismatch")
    probes = {}
    for name in CAMERAS:
        video = source / f"{name}.mp4"
        if sha(video) != report["video_sha256"][name]:
            raise ValueError("Video digest mismatch")
        data = probes[name] = probe(video)
        n, d = map(int, data["avg_frame_rate"].split("/"))
        if (
            int(data["nb_read_frames"]) != report["frame_count"]
            or n / d != report["fps"]
            or abs(float(data["duration"]) - report["duration_s"]) > 1e-5
        ):
            raise ValueError("Video timeline mismatch")
    metadata = ROOT / "runs/demo_metadata/buzz_wire_3d" / run_id
    destinations = {
        n: ROOT / "demos/buzz_wire_3d" / n / f"{run_id}_{n}.mp4" for n in CAMERAS
    }
    if metadata.exists() or any(p.exists() for p in destinations.values()):
        raise FileExistsError("Use a new archive ID")
    metadata.mkdir(parents=True)
    for folder in ("source_evidence", "assets", "robot_assets"):
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
    for previous_source in source.glob("render_source_previous_*.py"):
        shutil.copy2(previous_source, metadata / previous_source.name)
    shutil.copy2(
        Path(__file__).with_name("robot_verify.py"), metadata / "verify_source.py"
    )
    for name, run in qualification["runs"].items():
        original = Path(run["directory"])
        for item in ("report.json", "frames.json"):
            if sha(original / item) != run[item.replace(".json", "_sha256")]:
                raise ValueError("Physical evidence changed")
        shutil.copytree(original, metadata / "stability" / name)
        run.update(original_directory=str(original), directory=f"stability/{name}")
    save(metadata / "stability_report.json", qualification)
    shutil.copy2(suite.with_suffix(".png"), metadata / "stability_plot.png")
    for name in (
        "regression_checks.txt",
        "source_checks.json",
        "attempt_history.json",
        "grasp_convergence.json",
        "configuration_audit.json",
        "plan_summary.json",
    ):
        if (suite.parent / name).is_file():
            shutil.copy2(suite.parent / name, metadata / name)
    for name in ("render_chunks.json", "parallel_settings.json"):
        if (source / name).is_file():
            shutil.copy2(source / name, metadata / name)
    videos = {}
    for name, destination in destinations.items():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / f"{name}.mp4", destination)
        if sha(destination) != report["video_sha256"][name]:
            raise ValueError("Archive copy digest mismatch")
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
        "紧凑低矮 3D Buzz Wire：单台 Panda + Robotiq 2F-85 从预抓取位置夹住平面手柄，"
        "通过该实例全部关卡，在末端直立段松手，圆环随后靠重力滑到末端支座；机械臂退开并等待静置。"
        "抓持依靠接触摩擦，没有焊接约束、环杆外力驱动或运行中位姿覆盖。"
        "三路视频来自同一次连续物理执行的完整实测状态；包含夹爪被动关节，重渲染没有新增物理执行。"
    )
    nominal = qualification["reports"]["nominal"]
    geometry = json.loads(
        (source / "source_evidence/assets/geometry_report.json").read_text()
    )
    base = " × ".join(f"{100 * v:.1f}" for v in geometry["layout"]["base_size_m"])
    maximum_height = max(
        geometry["rail_bounds_m"][0][2], geometry["rail_bounds_m"][1][2]
    )
    details = (
        f"底座 {base} cm，导线最高距台面约 {100 * maximum_height:.1f} cm。每路 {report['duration_s']:.2f} 秒，"
        f"{report['fps']} fps，{report['frame_count']} 帧，960 × 720，无叠字。"
        f"受控通行零触线；最大位置偏差 {1000 * nominal['maxima']['tracking_error_m']:.3f} mm；"
        f"4 ms / 2 ms 时间步对照最大位置差 {1000 * qualification['maximum_controlled_position_difference_m']:.3f} mm。"
        "验收仅覆盖此实例及控制策略；刚性导线不模拟铜线弯曲或真实蜂鸣电路。"
    )
    links = "\n".join(f"- [{n}]({v['path']})" for n, v in videos.items())
    (metadata / "README.md").write_text(
        "# 3D Buzz Wire · 紧凑单臂完整动作\n\n"
        + scope
        + "\n\n"
        + details
        + "\n\n"
        + links
        + "\n\n[稳定性验收](stability_report.json) · [视频检查](archive_validation.json)\n\n"
        "完整配置、资产、轨迹与运行时源码见 `source_evidence/`、`stability/`，核心证据不依赖原始运行目录。"
        "机器人以预抓取起点开始；不包含从桌面拾取和初始穿环。\n"
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
        counts_as_complete_robotics_demo=True,
        counts_as_complete_process_demo=True,
        robot_present=True,
        source_physics_success=True,
        new_physics_execution=False,
        pregrasp_start=True,
        assisted_grasp=report["assisted_grasp"],
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
        title=f"3D Buzz Wire · {report['variant']} · 单臂完整动作",
        directory=f"buzz_wire_3d/{run_id}",
        index=f"buzz_wire_3d/{run_id}/README.md",
        video_directory="../../demos/buzz_wire_3d",
        video_layout="camera_subdirectories",
        video_files={
            n: os.path.relpath(p, catalog_path.parent) for n, p in destinations.items()
        },
    )
    catalog["entries"].append(entry)
    catalog["complete_robotics_demo_count"] = sum(
        bool(e.get("counts_as_complete_robotics_demo")) for e in catalog["entries"]
    )
    catalog["excluded"] = [
        e for e in catalog.get("excluded", []) if e.get("task_id") != "buzz_wire_3d"
    ]
    catalog.setdefault("task_video_layout", {})["buzz_wire_3d"] = dict(
        organization="MP4-only camera directories; single-arm and retained fixture versions",
        video_directory="../../demos/buzz_wire_3d",
        metadata_directory="buzz_wire_3d",
        cameras=list(CAMERAS),
        historical_fixture_cameras=["overview", "front_oblique", "topdown"],
    )
    catalog.setdefault("canonical_directory_exceptions", {})["buzz_wire_3d"] = (
        "demos/buzz_wire_3d/<camera>"
    )
    catalog["updated_at_utc"] = now
    save(catalog_path, catalog)
    path = catalog_path.parent / "README.md"
    with path.open("a") as stream:
        stream.write(
            f"\n[{entry['title']}](buzz_wire_3d/{run_id}/README.md)：三路各 {report['duration_s']:.2f} 秒；预抓取、摩擦抓持、完整通行及末端释放，时间步减半复验通过。\n"
        )
    print(metadata)
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    archive(**vars(parser.parse_args()))


if __name__ == "__main__":
    main()
