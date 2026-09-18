"""Qualify and independently archive the three inverse-designed physical demos."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from html import escape
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
from scipy.spatial.transform import Rotation

from .geometry import ASSET_ROOT
from .inverse_variants import OUTPUT, TITLES, VARIANTS, save, sha
from .robot_motion import ROOT
from .solution import read_motion
from .variant_runtime import load_instance

CAMERAS = ("cam_high", "cam_low", "cam_left_wrist", "cam_right_wrist", "detail", "oblique", "four_views")
SCOPE = "预抓取起点 → 双指接触后辅助抓持 → 完整解锁 → 双件分离并保持；末态仍由双臂持有，未包含桌面拾取和释放。"
NOTES = {
    "offset_window": "顶部轨迹向外偏移，反推非对称窗口。原解法仍可通过，这是兼容原解法的结构变体。",
    "double_gate": "增加一组错开的挡齿；退出时先向右换道、下移，再向左对齐第二道门，最后向右退出。原退出路线被新挡齿阻断。",
    "tilted_window": "金色件采用三层截面窗口；银色件先增加 25° 侧转与 8° 出平面倾斜，穿窗后恢复姿态。原路线及省略倾转的对照均发生碰撞。",
}
CSS = """body{margin:32px auto;max-width:1280px;padding:0 22px;font:16px/1.7 system-ui;background:#edf1f5;color:#22313f}section{background:white;border-radius:12px;padding:22px;margin:22px 0}video,img{width:100%;border-radius:8px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:18px}figure{margin:0}a{color:#146a94}button{padding:9px 14px;margin:4px;border:0;border-radius:6px;background:#dcebf4;cursor:pointer}table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:10px;border-bottom:1px solid #d9e1e8}.note{background:#fff0ca;padding:12px;border-radius:8px}code{overflow-wrap:anywhere}"""
JS = """const vs=[...document.querySelectorAll('video')];function allPlay(){Promise.allSettled(vs.map(v=>v.play()))}function allPause(){vs.forEach(v=>v.pause())}function seek(t){vs.forEach(v=>{v.currentTime=Math.min(t,v.duration||t)})}function rate(r){vs.forEach(v=>v.playbackRate=r)}"""


def document(title, body):
    return f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)}</title><style>{CSS}</style></head><body><h1>{escape(title)}</h1>{body}<script>{JS}</script></body></html>\n'


def check_links(path):
    for link in re.findall(r'(?:href|src)="([^"]+)"', path.read_text()):
        if re.match(r"https?://|#|data:", link):
            continue
        if not (path.parent / link.split("#")[0]).exists():
            raise ValueError(f"Missing local link in {path}: {link}")


def video_check(path, report):
    probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
        "-show_entries", "stream=nb_read_frames,avg_frame_rate,duration,width,height", "-of", "json", str(path)]))
    stream = probe["streams"][0]
    num, den = map(int, stream["avg_frame_rate"].split("/"))
    if (int(stream["nb_read_frames"]) != report["frames"] or abs(num / den - report["fps"]) > 1e-9
            or abs(float(stream["duration"]) - report["duration_s"]) > .001):
        raise ValueError(f"Video does not match recorded trajectory: {path}")
    subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-threads", "2", "-i", str(path), "-f", "null", "-"],
                   check=True, capture_output=True)
    return dict(stream, sha256=sha(path), decoded=True)


def qualify(folder):
    record, motion, proof, _, _ = load_instance(folder)
    physics_dir = folder / "physics"
    physical = json.loads((physics_dir / "report.json").read_text())
    audit = json.loads((physics_dir / "audit.json").read_text())
    recording = folder / "recording"
    report = json.loads((recording / "replay_report.json").read_text())
    rendered = json.loads((recording / "render_motion.json").read_text())
    trace = json.loads((physics_dir / "trajectory.json").read_text())
    solid = json.loads((folder / "solid_audit.json").read_text())
    if not (solid["passed"] and physical["passed"] and audit["passed"] and not audit["errors"]
            and not physical["pose_writes_after_reset"] and physical["robot_execution_verified"]
            and physical["minimum_sampled_gap_m"] > 0 and physical["final_separation_lower_bound_m"] > .02
            and physical["max_contact_penetration_m"] < .001 and len(physical["attached"]) == 2
            and report["passed"] and report["robot_execution_verified"] and not report["kinematic_replay"]
            and report["source_physical_audit_passed"] and report["maximum_genesis_pad_fk_error_m"] < .00002
            and report["render_motion_sha256"] == sha(recording / "render_motion.json")
            and report["physical_source_sha256"] == audit["source_sha256"]
            and report["geometry_sha256"] == physical["geometry_sha256"] == sha(folder / "geometry.json")
            and report["certificate_sha256"] == sha(folder / "certificate.json")
            and physical["motion_sha256"] == sha(folder / "robot_motion.json")
            and physical["runner_sha256"] == sha(Path(__file__).with_name("variant_runtime.py"))
            and record["input_trace_sha256"] == sha(folder / "ik_proposal.json")
            and record["source_proposal_sha256"] == sha(folder / "proposal.json")
            and record["source_template_sha256"] == sha(ASSET_ROOT / "template.json")
            and report["frames"] == len(rendered["frames"]) and report["physics_steps"] == physical["physics_steps"]
            and trace[0]["physics_step"] == 0 and trace[-1]["physics_step"] == physical["physics_steps"]):
        raise ValueError("Incomplete, failed, or stale physical recording evidence")
    if any(sha(physics_dir / name) != digest for name, digest in audit["source_sha256"].items()):
        raise ValueError("Physical trace differs from the audited input")
    if any(b["time_s"] <= a["time_s"] or b["physics_step"] <= a["physics_step"] for a, b in zip(trace, trace[1:])):
        raise ValueError("Physical state sequence is not monotonic")
    proposal = json.loads((folder / "proposal.json").read_text())
    expected_r, expected_t = read_motion(proposal["motions"][0], 3.).pose(0)
    gold, silver = (trace[0]["bodies"][n] for n in ("keyhole_gold", "keyhole_silver"))
    rg, rs = (Rotation.from_quat(p["quat"]).as_matrix() for p in (gold, silver))
    initial_error = np.linalg.norm(rg.T @ (np.array(silver["pos"]) - gold["pos"]) - expected_t)
    initial_angle = Rotation.from_matrix(rg.T @ rs @ expected_r.T).magnitude()
    if initial_error > .00002 or initial_angle > .0001:
        raise ValueError("Physical recording starts from a different relative puzzle instance")
    for result in (physical, report):
        if not result["loaded_collision_audit"] or not all(p["passed"] for p in result["loaded_collision_audit"]):
            raise ValueError("Simulator loaded different solids")
    indices = []
    for frame in rendered["frames"]:
        index = frame["source_trace_index"]
        actual = trace[index]
        if any(frame[key] != actual[key] for key in ("qpos", "bodies", "physics_step", "time_s", "stage")):
            raise ValueError("Rendered frame is not an actual saved physics state")
        indices.append(index)
    if indices != sorted(set(indices)) or indices[0] != 0 or indices[-1] != len(trace) - 1:
        raise ValueError("Recording does not cover the full physical execution in order")
    camera_poses = json.loads((recording / "camera_poses.json").read_text())
    if len(camera_poses) != report["frames"] or any(set(p) != set(CAMERAS[:4]) for p in camera_poses):
        raise ValueError("Incomplete synchronized camera pose evidence")
    return record, report, physical, audit, proof


def playback_page(meta, videos, record, report, physical, proof):
    name = record["id"]
    lead = f'<p><strong>完整双臂物理执行 · 接触后辅助抓持</strong> · {report["duration_s"]:.2f} 秒</p><p>{NOTES[name]}</p><p class="note">{SCOPE}</p>'
    body = lead + '<section><h2>近景与四视角总览</h2><p><button onclick="allPlay()">全部播放</button><button onclick="allPause()">全部暂停</button><button onclick="seek(0)">回到开头</button><button onclick="rate(.5)">半速</button><button onclick="rate(1)">正常速度</button></p><div class="grid">'
    for camera, label in (("detail", "谜题近景"), ("four_views", "ALOHA 四路同步观测")):
        body += f'<figure><video controls muted playsinline preload="metadata" src="{videos[camera]["path"]}"></video><figcaption>{label}</figcaption></figure>'
    body += '</div><p>所有视角来自同一次连续物理执行的实际状态；可在下面按阶段跳转。</p><p>'
    for phase in report["phases"]:
        body += f'<button onclick="seek({phase["time_s"]})">{escape(phase["name"])} · {phase["time_s"]:.1f}s</button>'
    body += '</p></section><section><h2>结构变化</h2><img src="geometry_comparison.png" alt="原始轮廓与逆向设计轮廓对照"><p>先修改已知可解轨迹并求双臂 IK，再从银色件扫掠体反推金色件。银色件与抓持区域保持原几何。灰色虚线为原始轮廓，金色为新轮廓；单位是原模板 mm，场景使用 3 倍尺寸。</p>'
    if name == "tilted_window":
        body += '<p>上图为中央截面；金色件的实际碰撞体和可视网格均包含三层不同截面。下面放大穿窗部位，各层采用相同坐标与比例。</p><img src="layer_sections.png" alt="倾转窗口沿厚度方向的三个真实截面">'
    negative = proof["negative_controls"]["unchanged_baseline_solution"]
    base_result = f'检测到 {abs(negative["minimum_sample_gap_m"])*1000:.2f} mm 碰撞' if negative["collision_found"] else '所检采样仍可通过'
    body += f'<p>原解法对照：{base_result}。已验证所给新解法可行；未证明全局唯一解。</p></section>'
    body += '<section><h2>单独视角</h2><div class="grid">'
    for camera in (*CAMERAS[:4], "oblique"):
        body += f'<figure><video controls muted playsinline preload="none" src="{videos[camera]["path"]}"></video><figcaption>{camera}</figcaption></figure>'
    body += '</div></section><section><h2>检查与证据</h2><table><tr><th>检查</th><th>结果</th></tr>'
    for label, value in (("连续几何路径最小间隙下界", f'{proof["continuous_gap_lower_bound_m"]*1000:.3f} mm'),
                         ("物理状态采样最小件间间隙", f'{physical["minimum_sampled_gap_m"]*1000:.3f} mm'),
                         ("最终件间分离下界", f'{physical["final_separation_lower_bound_m"]*1000:.2f} mm'),
                         ("最大接触穿透（含指尖）", f'{physical["max_contact_penetration_m"]*1000:.3f} mm'),
                         ("物理执行步数", str(physical["physics_steps"]))):
        body += f'<tr><td>{label}</td><td>{value}</td></tr>'
    body += '</table><p>'
    for path, label in (("certificate.json", "几何路径证书"), ("geometry.json", "新结构参数"), ("robot_motion.json", "完整 IK"),
                        ("physics/report.json", "物理报告"), ("physics/audit.json", "独立状态复查"),
                        ("recording_qualification.json", "完整 Demo 验收"), ("archive_validation.json", "视频归档验证"),
                        ("archive_manifest.json", "文件与哈希清单")):
        body += f'<a href="{path}">{label}</a> · '
    body += '</p></section><p><a href="../../index.html">全部任务 Demo</a></p>'
    (meta / "index.html").write_text(document(f'Cast Keyhole · {TITLES[name]}', body))


def layer_sections(meta, record):
    if "gold" not in record.get("layers", {}):
        return
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(12, 5), sharex=True, sharey=True)
    for ax, layer in zip(axes, record["layers"]["gold"]):
        ring = np.asarray(layer["rings_mm"][0])
        ax.fill(ring[:, 0], ring[:, 1], color="#c9ac68", edgecolor="#876b2e", linewidth=1.2)
        ax.set(xlim=(-9, 15), ylim=(-13, 7), aspect="equal", xlabel="template x / mm",
               title=f'z = {layer["z_min_mm"]:g} to {layer["z_max_mm"]:g} mm')
        ax.grid(alpha=.15)
    axes[0].set_ylabel("template y / mm")
    fig.suptitle("Actual depth sections of the tilted window (scene scale 3)")
    fig.tight_layout()
    fig.savefig(meta / "layer_sections.png", dpi=160)
    plt.close(fig)


def archive(folder, run_id):
    folder = Path(folder).resolve()
    record, report, physical, audit, proof = qualify(folder)
    checks = {name: video_check(folder / "recording" / f"{name}.mp4", report) for name in CAMERAS}
    meta_root = ROOT / "runs/demo_metadata"
    meta = meta_root / "cast_keyhole" / run_id
    video_dir = ROOT / "runs/demos/cast_keyhole"
    targets = {name: video_dir / f"{run_id}_{name}.mp4" for name in CAMERAS}
    if meta.exists() or any(path.exists() for path in targets.values()):
        raise ValueError("Archive exists; use a new run ID and preserve the old copy")
    video_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(folder, meta, ignore=shutil.ignore_patterns("*.mp4", "*.log"))
    provenance = meta / "provenance"
    provenance.mkdir()
    for name in ("template.json", "baseline_solution.json", "sources.json"):
        shutil.copy2(ASSET_ROOT / name, provenance / name)
    for name in ("inverse_variants.py", "variant_runtime.py", "variant_archive.py", "geometry.py", "collision.py", "robot_motion.py", "route_probe.py", "solution.py", "trajectory_probe.py"):
        shutil.copy2(Path(__file__).with_name(name), provenance / name)
    for name, digest in proof["source_fingerprints"].items():
        if sha(provenance / name) != digest:
            raise ValueError("Copied source differs from certified source")
    videos = {}
    for name, target in targets.items():
        source = folder / "recording" / f"{name}.mp4"
        shutil.copy2(source, target)
        if target.is_symlink() or target.stat().st_ino == source.stat().st_ino or sha(target) != checks[name]["sha256"]:
            raise ValueError("Video is not an independent verified copy")
        videos[name] = dict(checks[name], path=os.path.relpath(target, meta))
    save(meta / "archive_validation.json", dict(passed=True, video_checks=checks, all_views_synchronous=True,
        frames=report["frames"], fps=report["fps"], independent_copies=True, local_page_links_valid=True,
        actual_physical_trace_verified=True, initial_and_final_physical_states_included=True))
    save(meta / "recording_qualification.json", dict(formal_demo_qualified=True,
        classification="physical_execution_with_grasp_assistance", scope=SCOPE,
        pure_friction_grasp_verified=False, pregrasp_start=True, grasp_assistance_active_at_end=True,
        video_decode_and_synchronization_passed=True, unique_solution_proven=False))
    layer_sections(meta, record)
    playback_page(meta, videos, record, report, physical, proof)
    now = datetime.now(timezone.utc).isoformat()
    manifest = dict(task_id="cast_keyhole", instance=record["id"], run_id=run_id, source_directory=str(folder),
        archived_at_utc=now, classification="physical_execution_with_grasp_assistance", scope=SCOPE,
        counts_as_complete_robotics_demo=True, cameras=list(CAMERAS[:4]), duration_s=report["duration_s"],
        videos=videos, metadata_sha256={str(p.relative_to(meta)): sha(p) for p in sorted(meta.rglob("*")) if p.is_file()})
    save(meta / "archive_manifest.json", manifest)
    check_links(meta / "index.html")
    catalog_path = meta_root / "catalog.json"
    catalog = json.loads(catalog_path.read_text())
    relative = str(meta.relative_to(meta_root))
    title = f'Cast Keyhole 逆向设计 · {TITLES[record["id"]]}'
    catalog["entries"].append(dict(task_id="cast_keyhole", title=title, variant=record["id"],
        classification=manifest["classification"], counts_as_complete_robotics_demo=True, duration_s=report["duration_s"],
        cameras=list(CAMERAS[:4]), scope=SCOPE, source_directory=str(folder.relative_to(ROOT)), directory=relative,
        index=relative + "/index.html", archived_at_utc=now, video_directory="../demos/cast_keyhole",
        video_files={f"{n}.mp4": os.path.relpath(p, meta_root) for n, p in targets.items()}))
    catalog["archived_at_utc"] = now
    catalog["complete_robotics_demo_count"] = sum(e.get("counts_as_complete_robotics_demo", False) for e in catalog["entries"])
    catalog["kinematic_preview_count"] = sum(e["classification"] == "kinematic_rehearsal" for e in catalog["entries"])
    save(catalog_path, catalog)
    readme = meta_root / "README.md"
    row = f'| {title} | [打开]({relative}/index.html) | 7 | {SCOPE} |\n'
    readme.write_text(readme.read_text().replace("\n\n保留全部既有 MP4", "\n" + row + "\n保留全部既有 MP4"))
    index = meta_root / "index.html"
    content = re.sub(r"当前保留 \d+ 份完整物理执行及 \d+ 份运动学预演。",
        f'当前保留 {catalog["complete_robotics_demo_count"]} 份完整物理执行及 {catalog["kinematic_preview_count"]} 份运动学预演。', index.read_text())
    card = f'<section><h2><a href="{relative}/index.html">{title}</a></h2><p>完整双臂物理执行 · {report["duration_s"]:.2f} 秒 · 四路同步观测及近景</p><p>{SCOPE}</p></section>'
    index.write_text(content.replace("<section><h2>本次暂未收录", card + "<section><h2>本次暂未收录"))
    check_links(index)
    print(meta / "index.html", flush=True)
    return meta


def overview(run_prefix="2026-09-17_inverse", root=OUTPUT):
    meta_root = ROOT / "runs/demo_metadata"
    output = meta_root / "cast_keyhole" / f"{run_prefix}_variants_v1"
    if output.exists():
        raise ValueError("Overview archive already exists")
    output.mkdir(parents=True)
    body = '<p>从当前可解 IK 出发：修改轨迹 → 反推新结构 → 连续几何验证 → 双臂物理执行 → 同次执行多视角录像。</p><p class="note">' + SCOPE + '</p>'
    sources = []
    for name in VARIANTS:
        sibling = meta_root / "cast_keyhole" / f"{run_prefix}_{name}"
        manifest = json.loads((sibling / "archive_manifest.json").read_text())
        if not json.loads((sibling / "recording_qualification.json").read_text())["formal_demo_qualified"]:
            raise ValueError("All three complete physical archives are required")
        for path, digest in manifest["metadata_sha256"].items():
            if sha(sibling / path) != digest:
                raise ValueError("Archived evidence changed")
        rel = os.path.relpath(sibling, output)
        video = os.path.relpath((sibling / manifest["videos"]["detail"]["path"]).resolve(), output)
        body += f'<section><h2><a href="{rel}/index.html">{TITLES[name]}</a></h2><p>{NOTES[name]}</p><video controls muted playsinline preload="metadata" src="{video}"></video><p>{manifest["duration_s"]:.2f} 秒 · <a href="{rel}/index.html">完整四视角、近景与验证报告</a></p></section>'
        sources.append(dict(variant=name, manifest_path=os.path.relpath(sibling / "archive_manifest.json", output),
                            manifest_sha256=sha(sibling / "archive_manifest.json")))
    body += '<p><a href="../../index.html">全部任务 Demo</a></p>'
    (output / "index.html").write_text(document("Cast Keyhole · 三个逆向设计变体", body))
    check_links(output / "index.html")
    save(output / "comparison_manifest.json", dict(source_archives=sources, group_only=True,
        metadata_sha256={"index.html": sha(output / "index.html")}))
    relative = str(output.relative_to(meta_root))
    main = meta_root / "index.html"
    main.write_text(main.read_text().replace("<section><h2>本次暂未收录",
        f'<section><h2><a href="{relative}/index.html">Cast Keyhole · 三个逆向设计变体对照</a></h2><p>偏心窗口、双重错槽、倾转穿窗：三次独立完整物理执行。</p></section><section><h2>本次暂未收录'))
    readme = meta_root / "README.md"
    readme.write_text(readme.read_text() + f'\n[Cast Keyhole：三个逆向设计变体完整 Demo]({relative}/index.html)。\n')
    root = Path(root)
    link = os.path.relpath(output / "index.html", root)
    (root / "index.html").write_text(document("Cast Keyhole · 逆向设计变体", f'<p><a href="{link}">打开三版完整物理 Demo 对照页</a></p>'))
    check_links(root / "index.html")
    check_links(main)
    print(output / "index.html")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--variant", choices=VARIANTS)
    p.add_argument("--root", type=Path, default=OUTPUT)
    p.add_argument("--run-prefix", default="2026-09-17_inverse")
    p.add_argument("--overview", action="store_true")
    a = p.parse_args()
    if a.overview:
        overview(a.run_prefix, a.root)
    elif a.variant:
        archive(a.root / a.variant, f"{a.run_prefix}_{a.variant}")
    else:
        p.error("--variant or --overview is required")


if __name__ == "__main__":
    main()
