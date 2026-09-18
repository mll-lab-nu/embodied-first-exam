"""Validate and independently archive a complete assisted physical Coil run."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from html import escape
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import numpy as np
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation

from .geometry import CoilAssembly, load_template
from .inverse_design import TITLES, variant_route
from .appearance import TITLES as APPEARANCE_TITLES
from .solvability import exported_boxes_match

ROOT = Path(__file__).resolve().parents[3]
CAMERAS = ("cam_high", "cam_low", "cam_left_wrist", "cam_right_wrist", "front_oblique")
REQUIRED_PHASES = {
    "close_grippers",
    "hold_grasp",
    "lift",
    "prototype_slide",
    "prototype_quarter_turn",
    "prototype_extract",
    "place_silver",
    "place_gold",
    "release",
    "retreat",
    "settle",
}
LABELS = {
    "close_grippers": "闭合夹爪",
    "hold_grasp": "接触确认与辅助抓持",
    "pregrasp": "路径对齐",
    "lift": "整体抬升",
    "prototype_slide": "滑开",
    "prototype_quarter_turn": "转动 90°",
    "prototype_extract": "完全分离",
    "place_silver": "放下银件",
    "place_gold": "放下金件",
    "release": "解除辅助并松爪",
    "retreat": "双臂撤回",
    "settle": "自由静置",
    "turn_first_45": "第一次转动 45°",
    "intermediate_offset": "中间错位 6 mm",
    "turn_second_45": "第二次转动 45°",
    "screw_turn": "转动 90°并推进 6 mm",
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def demo_title(report):
    if report.get("appearance_kind"):
        return "Cast Coil · " + APPEARANCE_TITLES[report["appearance_kind"]]
    if report.get("inverse_design_kind"):
        return "Cast Coil · " + TITLES[report["inverse_design_kind"]]
    return "Cast Coil · ALOHA 双臂完整拆解"


def qualify_report(report, *, recording=True):
    """Fail closed on a partial, kinematic, unreleased or unobserved recording."""
    phases = REQUIRED_PHASES
    if report.get("inverse_design_kind"):
        phases = REQUIRED_PHASES - {
            "prototype_slide",
            "prototype_quarter_turn",
            "prototype_extract",
        }
        phases = phases | {m.name for m in variant_route(report["inverse_design_kind"])}
    required = [
        report.get("success"),
        report.get("complete"),
        report.get("physics_steps", 0) > 0,
        report.get("bilateral_grasp_contact_step", 0) > 0,
        report.get("grasp_assistance_active_at_end") is False,
        report.get("grasp_constraints_remaining") == [],
        report.get("release_evidence", {}).get("after") == [],
        max(report.get("released_body_displacement_during_retreat_m", [1])) < 0.002,
        report.get("final_finger_contact_links") == {"0": [], "1": []},
        report.get("live_object_pose_writes") is False,
        report.get("live_robot_pose_writes") is False,
        report.get("geometry_modified") is False,
        not recording or set(report.get("camera_names", [])) == set(CAMERAS),
        not recording or report.get("video_frames", 0) > 0,
        phases.issubset({p["name"] for p in report.get("phases", [])}),
        report.get("final_separation_m", 0) > 0.01,
        report.get("minimum_sampled_sat_gap_m", -1) > 0,
        report.get("maximum_interpiece_penetration_m", 1) < 0.00015,
        report.get("maximum_forbidden_robot_penetration_m", 1) < 0.00015,
        report.get("maximum_cross_arm_penetration_m", 1) < 0.00015,
        max(report.get("final_speed_m_s", [1])) < 0.001,
        max(report.get("final_angular_speed_rad_s", [1])) < 0.02,
    ]
    if not all(required):
        raise ValueError(
            "Recording does not qualify as a complete released physical execution"
        )


def read_trace(folder):
    return [
        json.loads(line)
        for line in (Path(folder) / "states.jsonl").read_text().splitlines()
    ]


def audit(source, reference):
    source, reference = Path(source), Path(reference)
    report = json.loads((source / "result.json").read_text())
    qualify_report(report)
    other = json.loads((reference / "result.json").read_text())
    qualify_report(other, recording=False)
    if (
        not np.isclose(report["dt"] / 2, other["dt"])
        or report["substeps"] != other["substeps"]
        or report.get("precision_bits", 32) != other.get("precision_bits", 32)
        or report.get("backend", "cuda") != other.get("backend", "cuda")
    ):
        raise ValueError("Expected half the timestep with unchanged substep count")
    cfg, cfg_half = (OmegaConf.load(p / "config.yaml") for p in (source, reference))
    for key in ("task", "robot_control"):
        left, right = [
            OmegaConf.to_container(c[key], resolve=True) for c in (cfg, cfg_half)
        ]
        if key == "task":
            left.pop("template_path", None)
            right.pop("template_path", None)
        if left != right:
            raise ValueError(f"Timestep comparison changed {key}")
    assembly = CoilAssembly(load_template(source / "assets/template.json"))
    plan = json.loads((source / "source_plan.json").read_text())
    if plan.get("template", assembly.template) != assembly.template:
        raise ValueError("Planned and executed geometry differ")
    if not all(
        exported_boxes_match(p / "assets", assembly) for p in (source, reference)
    ):
        raise ValueError("Recorded compounds differ from the current geometry")
    rows, half_rows = read_trace(source), read_trace(reference)
    render_evidence = None
    if report.get("recording_kind") == "offline_render_of_exact_physical_states":
        raw = json.loads((source / "physics_result.json").read_text())
        qualify_report(raw, recording=False)
        render_evidence = json.loads((source / "render_evidence.json").read_text())
        if (
            sha(source / "physics_result.json")
            != render_evidence["physical_result_sha256"]
        ):
            raise ValueError("Physical source report hash mismatch")
        if sha(source / "render_states.jsonl") != raw.get("render_states_sha256"):
            raise ValueError("Physical snapshots changed after execution")
        if render_evidence.get("physical_states_sha256") != raw["render_states_sha256"]:
            raise ValueError("Renderer used different physical snapshots")
        for key, value in raw.items():
            if (
                key not in {"camera_names", "video_frames", "video_fps"}
                and report.get(key) != value
            ):
                raise ValueError(f"Rendered report changes physical evidence: {key}")
        if (
            not render_evidence.get("no_interpolation")
            or render_evidence.get("render_scene_physics_steps") != 0
            or render_evidence["maximum_qpos_roundtrip_error"] > 1e-9
            or render_evidence["maximum_body_origin_roundtrip_error_m"] > 1e-9
            or render_evidence["maximum_body_rotation_roundtrip_error_rad"] > 1e-9
        ):
            raise ValueError(
                "Renderer did not faithfully restore the recorded physical states"
            )
        recorded = [
            json.loads(s)
            for s in (source / "render_states.jsonl").read_text().splitlines()
        ]
        state_map = {round(r["time_s"], 8): r for r in rows}
        for frame in recorded:
            common = state_map.get(round(frame["time_s"], 8))
            if common and (
                frame["qpos"] != common["qpos"]
                or any(
                    frame["bodies"][i][k] != common["bodies"][i][k]
                    for i in range(2)
                    for k in ("origin_m", "quaternion_xyzw")
                )
            ):
                raise ValueError(
                    "Recorded video frame differs from the independent physics audit trace"
                )
        if len(recorded) != report["video_frames"]:
            raise ValueError("Rendered frame count differs from physical snapshots")
    tail = [r for r in rows if r["time_s"] >= rows[-1]["time_s"] - 0.5]
    if any(r["grasp_assistance_active"] for r in tail) or any(
        r["phase"] != "settle" for r in tail
    ):
        raise ValueError("Missing final unassisted settling window")
    tail_v = max(b["linear_speed_m_s"] for r in tail for b in r["bodies"])
    tail_w = max(b["angular_speed_rad_s"] for r in tail for b in r["bodies"])
    if tail_v >= 0.001 or tail_w >= 0.02:
        raise ValueError("Final half-second is not stable")
    deltas = []
    for a, b in zip(rows[-1]["bodies"], half_rows[-1]["bodies"]):
        delta = float(np.linalg.norm(np.asarray(a["origin_m"]) - b["origin_m"]))
        angle = float(
            (
                Rotation.from_quat(a["quaternion_xyzw"]).inv()
                * Rotation.from_quat(b["quaternion_xyzw"])
            ).magnitude()
        )
        deltas.append(dict(position_m=delta, rotation_rad=angle))
        if delta > 0.0005 or angle > 0.01:
            raise ValueError(f"Final state disagrees across timesteps: {deltas[-1]}")
    videos = {}
    for name in CAMERAS:
        file = source / f"{name}.mp4"
        data = json.loads(
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
                    str(file),
                ],
                text=True,
            )
        )["streams"][0]
        num, den = map(int, data["avg_frame_rate"].split("/"))
        count, fps = int(data["nb_read_frames"]), num / den
        if count != report["video_frames"] or fps != report["video_fps"]:
            raise ValueError(f"Unsynchronized video: {name}")
        decode = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-threads",
                "2",
                "-i",
                str(file),
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
        )
        if decode.returncode or decode.stderr.strip():
            raise ValueError(f"Video decoding failed: {name}: {decode.stderr}")
        videos[name] = dict(
            **data, frames=count, fps=fps, sha256=sha(file), decoded=True
        )
    cameras = [
        json.loads(line)
        for line in (source / "camera_poses.jsonl").read_text().splitlines()
    ]
    if len(cameras) != report["video_frames"] or not all(
        set(r["transforms"]) == set(CAMERAS) for r in cameras
    ):
        raise ValueError("Camera trace does not cover all recorded frames")
    if not np.allclose(
        np.diff([r["time_s"] for r in cameras]), 1 / report["video_fps"], atol=1e-9
    ):
        raise ValueError("Recorded frame timing is inconsistent")
    if render_evidence is not None and any(
        camera["frame"] != frame["frame"]
        or camera["physical_step"] != frame["step"]
        or camera["time_s"] != frame["time_s"]
        or camera["phase"] != frame["phase"]
        for camera, frame in zip(cameras, recorded)
    ):
        raise ValueError("Video camera trace is not linked to the physical frames")
    table_z = float(cfg.env.frames.table_surface.origin[2])
    minimum_table = min(
        float(
            (
                body.visual.vertices
                @ Rotation.from_quat(pose["quaternion_xyzw"]).as_matrix().T
                + pose["origin_m"]
            )[:, 2].min()
            - table_z
        )
        for row in rows
        for body, pose in zip(assembly.bodies, row["bodies"])
    )
    if minimum_table < -0.00015:
        raise ValueError(f"Observed tabletop penetration: {minimum_table}")
    result = dict(
        passed=True,
        classification="physical_execution_with_grasp_assistance",
        geometry_matches=True,
        precision_bits=report.get("precision_bits", 32),
        complete=True,
        final_unassisted_window_s=0.5,
        thresholds=dict(
            final_speed_m_s=0.001,
            final_angular_speed_rad_s=0.02,
            timestep_position_difference_m=0.0005,
            timestep_rotation_difference_rad=0.01,
            minimum_final_separation_m=0.01,
            maximum_non_grasp_contact_penetration_m=0.00015,
            maximum_table_penetration_m=0.00015,
            maximum_released_retreat_displacement_m=0.002,
        ),
        maximum_tail_speed_m_s=tail_v,
        maximum_tail_angular_speed_rad_s=tail_w,
        minimum_sampled_table_clearance_m=minimum_table,
        timestep_comparison=dict(
            passed=True,
            substeps=report["substeps"],
            dt_s=[report["dt"], other["dt"]],
            final_body_deltas=deltas,
            reference_report_sha256=sha(reference / "result.json"),
        ),
        videos=videos,
        source_result_sha256=sha(source / "result.json"),
        render_evidence=render_evidence,
        limitations=[
            "Pregrasp reset; contact-gated grasp assistance, not friction-only grasping.",
            "Authored Coil route; not a verified commercial eight-step tutorial.",
            "Solver contact maxima and sampled realized geometry are separate from the ideal continuous route certificate.",
        ],
    )
    (source / "validation.json").write_text(json.dumps(result, indent=2) + "\n")
    return report, result


def write_page(folder, report, videos):
    kind = report.get("inverse_design_kind")
    appearance = report.get("appearance_kind")
    title = demo_title(report)
    scope = (
        "从已验证 IK 运动变体反推的新结构；几何、质量和惯量按新实体生成。"
        if kind
        else "这是现有原型的三段解法，不宣称复现商业谜题的官方八步。"
    )
    if appearance:
        p = report["appearance_parameters"]
        scope = (
            "以最初已验证基础版为种子，仅改变一个外观参数，保留三段解法。"
            f"正面缩放 {p['face_scale']:g}，厚度缩放 {p['depth_scale']:g}，外角切角比例 {p['corner_cut_ratio']:g}。"
            "几何、质量惯量、抓点和配套轨迹按该参数重新生成；切角为阶梯近似。"
        )
    lift = report.get("lift_m", 0.07) * 1000
    recording_note = (
        "视频由一次完整物理运行保存的精确 20 Hz 状态离线渲染，不插值、不修改轨迹；渲染场景不进行物理步进。物理报告与渲染报告分开保留。"
        if report.get("recording_kind") == "offline_render_of_exact_physical_states"
        else "所有相机在物理运行期间同步录制。"
    )
    evidence_links = (
        '<a href="physics_result.json">原始物理报告</a> · '
        '<a href="render_evidence.json">离线渲染一致性</a> · '
        '<a href="design_evidence/synthesis_report.json">结构生成与负对照</a> · '
        '<a href="design_evidence/README.md">变体说明</a> · '
        if (kind or appearance)
        and report.get("recording_kind") == "offline_render_of_exact_physical_states"
        else ""
    )
    phases = "".join(
        f'<button onclick="seek({p["time_s"]})">{escape(LABELS.get(p["name"], p["name"]))}</button>'
        for p in report["phases"]
        if p["name"] != "pregrasp"
    )
    cards = "".join(
        f'<figure><video class="sync" controls preload="metadata" src="{escape(videos[n])}" '
        f'poster="pregrasp_{n}.jpg"></video><figcaption>{n}</figcaption></figure>'
        for n in CAMERAS[:4]
    )
    text = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>body{{max-width:1250px;margin:32px auto;padding:0 20px;font:16px/1.7 system-ui;background:#eef2f6;color:#243443}}
section{{background:white;padding:22px;border-radius:10px;margin:22px 0}}video,img{{width:100%;border-radius:7px}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}figure{{margin:0}}button{{padding:8px 12px;margin:4px;border:0;border-radius:5px;background:#e0edf5;cursor:pointer}}a{{color:#146293}}.note{{background:#fff1d0;padding:15px;border-radius:8px}}@media(max-width:700px){{.grid{{grid-template-columns:1fr}}}}</style>
<h1>{title}</h1><p>夹持 → 抬高 {lift:.0f} mm → 完整变体路径 → 分别落桌 → 解除抓持 → 撤回与自由静置。</p>
<p class="note">从明确的张爪预抓取状态开始，金、银件均为自由刚体。四个夹指确认接触后启用两条辅助抓持约束，落桌后解除。
物理执行由关节控制与物理解算推进，执行期间没有逐帧覆写零件或机器人位姿。{scope}</p><p>{recording_note}</p>
<section><h2>完整近景</h2><video class="sync" id="main" controls preload="metadata" src="{escape(videos["front_oblique"])}" poster="pregrasp_front_oblique.jpg"></video>
<div>{phases}</div><p>约 {report["simulated_seconds"]:.1f} 秒，20 fps。所有视角来自同一次连续物理执行。</p></section>
<section><h2>ALOHA 四路同步相机</h2><button onclick="toggleAll()">全部同步播放 / 暂停</button><div class="grid">{cards}</div></section>
<section><h2>执行证据</h2><p>最终两件的分离面间距 {report["final_separation_m"] * 1000:.2f} mm。
记录的最大件间穿透 {report["maximum_interpiece_penetration_m"] * 1000:.4f} mm，机械臂对零件 / 桌面的非抓持穿透 {report["maximum_forbidden_robot_penetration_m"] * 1000:.4f} mm。
夹指抓持接触的最大数值穿透为 {report.get("maximum_finger_penetration_m", 0) * 1000:.4f} mm，单独报告，不计入非抓持碰撞指标。
完整路径完成 {report["physics_steps"]:,} 次物理步进；最后自由静置 2 秒。默认与半时间步检查均通过。</p>
<p>执行期间几何、质量惯量不变，保留机器人力矩上限；初态整体 yaw 为 90°，采用记录在配置中的位置控制增益。未验证纯摩擦抓持的稳定性或真实硬件负载能力。</p>
<p>{evidence_links}<a href="result.json">执行报告</a> · <a href="validation.json">物理、时间步与视频复核</a> · <a href="config.yaml">完整配置</a> ·
<a href="states.jsonl">实际状态轨迹</a> · <a href="source_plan.json">完整计划与几何证书</a> · <a href="camera_report.json">相机参数</a></p>
<img src="settle_front_oblique.jpg" alt="分离放置并松爪后的实际状态"></section>
<script>const streams=[...document.querySelectorAll('.sync')],main=document.getElementById('main');
function seek(t){{streams.forEach(v=>v.currentTime=t)}}
function toggleAll(){{const go=main.paused,t=main.currentTime;streams.forEach(v=>{{v.currentTime=t;go?v.play():v.pause()}})}}
main.addEventListener('seeked',()=>streams.filter(v=>v!==main).forEach(v=>{{if(Math.abs(v.currentTime-main.currentTime)>.1)v.currentTime=main.currentTime}}));</script></html>'''
    (Path(folder) / "index.html").write_text(text)


def archive(source, reference, run_id):
    source, reference = Path(source).resolve(), Path(reference).resolve()
    metadata = ROOT / "runs/demo_metadata/cast_coil" / run_id
    video_root = ROOT / "runs/demos/cast_coil"
    if metadata.exists() or any(
        (video_root / f"{run_id}_{n}.mp4").exists() for n in CAMERAS
    ):
        raise FileExistsError("Archive already exists; preserve the validated copy")
    report, validation = audit(source, reference)
    write_page(source, report, {n: f"{n}.mp4" for n in CAMERAS})
    metadata.mkdir(parents=True)
    video_root.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        if item.suffix == ".mp4":
            continue
        if item.is_dir():
            shutil.copytree(item, metadata / item.name)
        else:
            shutil.copy2(item, metadata / item.name)
    # Keep complete comparison evidence beside the archived run; no dependency
    # on the mutable working directory for the supporting physical result.
    shutil.copytree(
        reference, metadata / "half_dt", ignore=shutil.ignore_patterns("*.mp4")
    )
    files = {}
    for name in CAMERAS:
        target = video_root / f"{run_id}_{name}.mp4"
        shutil.copy2(source / f"{name}.mp4", target)
        if (
            target.is_symlink()
            or target.stat().st_nlink != 1
            or sha(target) != validation["videos"][name]["sha256"]
        ):
            raise RuntimeError("Video is not an independent verified copy")
        files[name] = os.path.relpath(target, metadata)
    write_page(metadata, report, files)
    (metadata / "archive_source.py").write_text(Path(__file__).read_text())
    (metadata / "archive_validation.json").write_text(
        json.dumps(
            dict(
                passed=True,
                videos_independent=True,
                videos_decodable=True,
                synchronized=True,
                validation="validation.json",
            ),
            indent=2,
        )
        + "\n"
    )
    manifest = dict(
        task_id="cast_coil",
        variant=report.get("geometry_variant", "photo_reference_v1_baseline_3x"),
        inverse_design_kind=report.get("inverse_design_kind"),
        appearance_kind=report.get("appearance_kind"),
        appearance_parameters=report.get("appearance_parameters"),
        recording_kind=report.get("recording_kind", "live_physics_recording"),
        run_id=run_id,
        source_directory=str(source.relative_to(ROOT)),
        classification="physical_execution_with_grasp_assistance",
        counts_as_complete_robotics_demo=True,
        scope=report["scope"],
        duration_s=report["video_frames"] / report["video_fps"],
        cameras=list(CAMERAS),
        videos={
            n: dict(path=files[n], sha256=sha(metadata / files[n])) for n in CAMERAS
        },
        metadata_sha256={
            str(p.relative_to(metadata)): sha(p)
            for p in sorted(metadata.rglob("*"))
            if p.is_file()
        },
        archived_at_utc=datetime.now(timezone.utc).isoformat(),
    )
    (metadata / "archive_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )
    update_catalog(metadata, manifest)
    return metadata


def update_catalog(metadata, manifest):
    folder = ROOT / "runs/demo_metadata"
    catalog = json.loads((folder / "catalog.json").read_text())
    relative = str(metadata.relative_to(folder))
    entry = dict(
        task_id="cast_coil",
        title=demo_title(manifest),
        variant=manifest["variant"],
        appearance_kind=manifest.get("appearance_kind"),
        appearance_parameters=manifest.get("appearance_parameters"),
        classification=manifest["classification"],
        counts_as_complete_robotics_demo=True,
        duration_s=manifest["duration_s"],
        cameras=manifest["cameras"],
        scope="张爪预抓取开始；双侧接触后辅助抓持，完整拆解、分别落桌、解除辅助并自由静置。",
        recording_kind=manifest.get("recording_kind", "live_physics_recording"),
        source_directory=manifest["source_directory"],
        directory=relative,
        index=f"{relative}/index.html",
        archived_at_utc=manifest["archived_at_utc"],
        video_directory="../demos/cast_coil",
        video_files={
            n: os.path.relpath(metadata / v["path"], folder)
            for n, v in manifest["videos"].items()
        },
    )
    if entry["recording_kind"] == "offline_render_of_exact_physical_states":
        entry["scope"] += "视频为同一次物理执行的精确状态离线渲染。"
    catalog["entries"].append(entry)
    catalog["excluded"] = [
        e for e in catalog.get("excluded", []) if e["task_id"] != "cast_coil"
    ]
    catalog["complete_robotics_demo_count"] = sum(
        bool(e.get("counts_as_complete_robotics_demo")) for e in catalog["entries"]
    )
    catalog["archived_at_utc"] = manifest["archived_at_utc"]
    (folder / "catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n"
    )
    page = (folder / "index.html").read_text()
    card = f'<section><h2><a href="{relative}/index.html">{entry["title"]}</a></h2><p><strong>完整物理执行 · 含辅助抓持</strong> · {entry["duration_s"]:.2f} 秒 · 5 路同步相机</p><p>{entry["scope"]}</p><p><a href="{relative}/index.html">打开播放页</a> · <a href="{relative}/archive_manifest.json">文件清单</a></p></section>'
    page = page.replace(
        "<section><h2>本次暂未收录", card + "<section><h2>本次暂未收录", 1
    )
    import re

    page = re.sub(r"<tr><td>cast_coil</td><td>.*?</td></tr>", "", page)
    date = manifest["archived_at_utc"][:10]
    page = re.sub(
        r"\d{4}-\d{2}-\d{2} (?:整理|更新)：\d+ 份(?:三视角|多视角)完整物理执行",
        f"{date} 更新：{catalog['complete_robotics_demo_count']} 份多视角完整物理执行",
        page,
    )
    page = re.sub(
        r"当前保留 \d+ 份完整物理执行及 \d+ 份运动学预演",
        f"当前保留 {catalog['complete_robotics_demo_count']} 份完整物理执行及 {catalog.get('kinematic_preview_count', 0)} 份运动学预演",
        page,
    )
    (folder / "index.html").write_text(page)
    readme = (folder / "README.md").read_text()
    row = (
        f"| {entry['title']} | [打开]({relative}/index.html) | 5 | {entry['scope']} |\n"
    )
    readme = readme.replace(
        "\n\n保留全部既有 MP4", "\n" + row + "\n保留全部既有 MP4", 1
    )
    readme = re.sub(r"^- `cast_coil`：.*\n", "", readme, flags=re.MULTILINE)
    readme = readme.replace(
        "以下是首次归档时的扫描结论；本次仅调整目录，不重新评估其他 session 的进展。",
        "以下保留首次归档时的其他任务扫描结论；Cast Coil 已按新完成的物理执行更新收录。",
    )
    (folder / "README.md").write_text(readme)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--run-id", default="2026-09-17_aloha_full")
    args = parser.parse_args()
    print(archive(args.source, args.reference, args.run_id))
