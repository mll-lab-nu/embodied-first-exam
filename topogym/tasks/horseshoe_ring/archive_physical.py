"""Retain independently playable, qualified physical horseshoe recordings."""
import argparse
from datetime import datetime, timezone
from html import escape
import json
import os
from pathlib import Path
import re
import shutil

from omegaconf import OmegaConf

from .gravity_demo import ROOT, sha
from .variant_video import check_links, check_video, save
from .verify_physical import compare_runs, verify_run

SCOPE = "原始预抓持初态开始，重力和碰撞下连续折合、接触交接、取环及释放落桌；接触确认后辅助抓持，非纯摩擦抓取验证。"


def archive(source, recording, half_step, run_id, *, incomplete_half_step=None):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", run_id):
        raise ValueError("Use one filename component for the archive ID")
    source, recording = Path(source).resolve(), Path(recording).resolve()
    half_step = Path(half_step).resolve() if half_step else None
    physics, half = verify_run(source), verify_run(half_step) if half_step else None
    timestep_comparison = compare_runs(source, half_step) if half_step else None
    if timestep_comparison and not timestep_comparison["passed"]:
        raise ValueError("Half-step qualification requires matching code, geometry and control parameters")
    if half_step and incomplete_half_step:
        raise ValueError("Use either a qualified half-step run or an incomplete attempt")
    render = json.loads((recording/"render_report.json").read_text())
    if not physics["passed"] or (half and (not half["passed"] or abs(half["dt"]*2-physics["dt"]) > 1e-12)):
        raise ValueError("Every run submitted as qualified must pass complete physical validation")
    height_delta = abs(physics["final_ring_height_m"]-half["final_ring_height_m"]) if half else None
    if (height_delta is not None and height_delta >= .0005) or render["source_states_sha256"] != physics["source_states_sha256"] or \
            render["source_result_sha256"] != sha(source/"result.json"):
        raise ValueError("Recording provenance or timestep comparison failed")
    cameras = render["cameras"]
    if not {"cam_high", "cam_low", "cam_left_wrist", "cam_right_wrist", "detail"}.issubset(cameras):
        raise ValueError("Preserve four synchronized ALOHA views and a readable task overview")
    checks = {name: check_video(recording/f"{name}.mp4", render["frame_count"], render["fps"]) for name in cameras}
    if any(checks[name]["sha256"] != render["videos"][name]["sha256"] for name in cameras):
        raise ValueError("Encoded video changed after rendering")
    meta_root = ROOT/"runs/demo_metadata"
    meta = meta_root/"horseshoe_ring"/run_id
    videos_dir = ROOT/"demos/horseshoe_ring"
    targets = {name: videos_dir/name/f"{run_id}_{name}.mp4" for name in cameras}
    if meta.exists() or any(path.exists() for path in targets.values()):
        raise FileExistsError("Preserve previous qualified copies; select a new archive ID")
    shutil.copytree(source, meta, ignore=shutil.ignore_patterns("*.mp4"))
    if half_step:
        shutil.copytree(half_step, meta/"half_timestep", ignore=shutil.ignore_patterns("*.mp4"))
    if incomplete_half_step:
        shutil.copytree(Path(incomplete_half_step), meta/"half_timestep_attempt", ignore=shutil.ignore_patterns("*.mp4"))
        save(meta/"half_timestep_attempt/attempt_status.json", dict(
            status="incomplete_not_qualified", task_success=False,
            note="The raw result was left at running; no complete execution evidence was produced. This attempt is not a timestep validation."))
    shutil.copytree(recording, meta/"recording", ignore=shutil.ignore_patterns("*.mp4"))
    for folder in [meta]+([meta/"half_timestep"] if half_step else [])+([meta/"half_timestep_attempt"] if incomplete_half_step else []):
        cfg = OmegaConf.load(folder/"config.yaml")
        cfg.task.template_path = str(folder/"input_template.json")
        cfg.run.output = str(folder)
        OmegaConf.save(cfg, folder/"config.yaml", resolve=True)
    cfg = OmegaConf.load(meta/"recording/render_config.yaml")
    cfg.task.template_path = str(meta/"input_template.json")
    OmegaConf.save(cfg, meta/"recording/render_config.yaml", resolve=True)
    videos_dir.mkdir(parents=True, exist_ok=True)
    videos = {}
    for name, target in targets.items():
        original = recording/f"{name}.mp4"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, target)
        if sha(target) != checks[name]["sha256"] or target.is_symlink() or target.stat().st_ino == original.stat().st_ino:
            raise ValueError("Expected an independent byte-identical video copy")
        videos[name] = os.path.relpath(target, meta)
    verification = dict(passed=True, baseline=verify_run(meta), half_step=verify_run(meta/"half_timestep") if half else None,
        timestep_replication_passed=bool(half),
        timestep_comparison=timestep_comparison,
        qualification_scope="Complete baseline execution; timestep replication is a separate result",
        incomplete_half_step_attempt="half_timestep_attempt/result.json" if incomplete_half_step else None,
        final_ring_height_difference_m=height_delta, videos=checks, independent_video_copies=True,
        counts_as_complete_robotics_demo=True, scope=SCOPE)
    if not verification["baseline"]["passed"] or (half and not verification["half_step"]["passed"]):
        raise ValueError("Copied archive failed independent physical qualification")
    save(meta/"physical_verification.json", verification)
    result = json.loads((meta/"result.json").read_text())
    states = [json.loads(line) for line in (meta/"physical_states.jsonl").read_text().splitlines()]
    labels = {"翻转马蹄": "翻转", "双臂折合": "折合", "rotate_to_horizontal_stack": "水平叠放",
              "combined_grasp_approach": "交接", "track_and_approach_ring": "抓取圆环",
              "extract_ring_milestone_0": "取环", "open_left_after_ring_release": "松爪落桌"}
    seen, chapters = set(), []
    for state in states:
        stage = state["stage"]
        if stage in labels and stage not in seen:
            chapters.append(f'<button onclick="seekAll({state["time_s"]})">{labels[stage]}</button>')
            seen.add(stage)
    def player(name, synchronized=False):
        return (f'<video {"class=sync" if synchronized else ""} controls preload="metadata" '
                f'src="{escape(videos[name], quote=True)}" poster="recording/initial_{name}.jpg"></video>')
    cards = "".join(f'<figure>{player(name, True)}<figcaption>{name}</figcaption></figure>' for name in cameras if name != "detail")
    timestep_note = (f"半步长 {half['dt']*1000:g} ms 独立连续执行也通过，最大谜题穿透 {half['maximum_puzzle_penetration_m']*1000:.3f} mm。"
                    if half else f"当前只验收此基础实例在 {physics['dt']*1000:g} ms 步长下的完整执行；额外半时间步复验未完成，不宣称跨时间步稳定性。")
    if incomplete_half_step:
        timestep_note += ' <a href="half_timestep_attempt/attempt_status.json">保留的未完成复验记录</a>。'
    page = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Horseshoe Ring · 重力下完整解法</title>
<style>body{{max-width:1200px;margin:30px auto;padding:0 20px;font:16px/1.7 system-ui;background:#eef2f6;color:#203040}}video{{width:100%}}section{{background:white;padding:20px;margin:20px 0}}figure{{margin:0}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}button{{padding:10px;margin:5px}}@media(max-width:700px){{.grid{{grid-template-columns:1fr}}}}</style>
<h1>Horseshoe Ring · 重力下完整解法</h1><p>{SCOPE}</p>
<p>同一次连续物理运行，{render['duration_s']:.2f} 秒，五路无 UI 视频。目标圆环最终解除辅助抓持并自由落桌静置。</p>
<section><h2>完整过程</h2>{player('detail')}<div>{''.join(chapters)}</div></section>
<section><h2>ALOHA 四路同步观察</h2><button onclick="views.forEach(v=>{{v.currentTime=0;v.play()}})">从头同步播放</button>
<button onclick="views.forEach(v=>v.pause())">全部暂停</button><div class="grid">{cards}</div></section>
<section><h2>物理检查</h2><p>重力 9.81 m/s²；物理步长 {physics['dt']*1000:g} ms、4 子步，
最大谜题穿透为 {physics['maximum_puzzle_penetration_m']*1000:.3f} mm。{timestep_note}
终态圆环仅接触桌面，最终分离间距 {physics['final_goal']['separation_m']*1000:.1f} mm。</p>
<p>从预抓持开始，未验证从桌面自主拾取或纯摩擦抓持。两只马蹄末态仍由右手保持。
视频按 {render['fps']} FPS 抽取同一物理轨迹的实测状态，不插值；渲染不重新执行动力学。
外部固定相机按实际轨迹扩大视场，保留上游安装位置；不宣称完整硬件标定等价。</p>
<p><a href="physical_verification.json">完整验收</a> · <a href="result.json">物理执行报告</a> ·
<a href="physical_states.jsonl">实际关节和物体轨迹</a> · <a href="planned_extraction.json">取环 IK 计划</a> ·
<a href="recording/render_report.json">录像来源</a> · <a href="archive_manifest.json">保留副本与哈希</a></p></section>
<script>const views=[...document.querySelectorAll('.sync')];function seekAll(t){{document.querySelectorAll('video').forEach(v=>v.currentTime=t)}}</script></html>'''
    (meta/"index.html").write_text(page)
    (meta/"README.md").write_text(f"# Horseshoe Ring · 重力下完整解法\n\n{SCOPE}\n\n"
        f"[播放页](index.html) · [物理验收](physical_verification.json)\n\n"
        f"视频目录：`{os.path.relpath(videos_dir, meta)}`。所有视频为独立 MP4 副本。\n"
        "`result.json` 记录仿真本身，不包含录像资格；完整 demo 的收录资格由本目录的清单和物理验收报告给出。\n")
    save(meta/"archive_manifest.json", dict(status="building"))
    verification["local_links"] = check_links(meta/"index.html")
    save(meta/"physical_verification.json", verification)
    entry = dict(task_id="horseshoe_ring", title="马蹄环 · 重力下 ALOHA 完整解法", variant="tutorial_solvable_v3_gravity_replanned_v1",
        classification="physical_execution_with_grasp_assistance", counts_as_complete_robotics_demo=True,
        timestep_replication_passed=bool(half),
        scope=SCOPE, duration_s=render["duration_s"], frames=render["frame_count"], fps=render["fps"], cameras=cameras,
        source_directory=str(source.relative_to(ROOT)), source_recording_directory=str(recording.relative_to(ROOT)),
        archived_at_utc=datetime.now(timezone.utc).isoformat())
    files = [dict(path=os.path.relpath(path, meta), bytes=path.stat().st_size, sha256=sha(path))
             for path in sorted([path for path in meta.rglob("*") if path.is_file() and path != meta/"archive_manifest.json"]+list(targets.values()))]
    save(meta/"archive_manifest.json", dict(entry, schema_version=2, directory=str(meta.relative_to(ROOT)), index="index.html",
        video_directory=os.path.relpath(videos_dir, meta), video_files=videos, files=files,
        file_count=len(files), total_bytes=sum(item["bytes"] for item in files),
        manifest_note="Paths are relative to this manifest; the manifest excludes itself."))
    entry.update(directory=str(meta.relative_to(meta_root)), index=str((meta/"index.html").relative_to(meta_root)),
        video_directory=os.path.relpath(videos_dir, meta_root),
        video_files={f"{name}.mp4": os.path.relpath(path, meta_root) for name, path in targets.items()})
    catalog = json.loads((meta_root/"catalog.json").read_text())
    catalog["entries"].append(entry)
    catalog["complete_robotics_demo_count"] = sum(e.get("counts_as_complete_robotics_demo", False) for e in catalog["entries"])
    catalog["kinematic_preview_count"] = sum(e.get("classification") == "kinematic_rehearsal" for e in catalog["entries"])
    catalog["archived_at_utc"] = entry["archived_at_utc"]
    save(meta_root/"catalog.json", catalog)
    index = (meta_root/"index.html").read_text()
    index = re.sub(r"当前保留 \d+ 份完整物理执行及 \d+ 份运动学预演。",
        f"当前保留 {catalog['complete_robotics_demo_count']} 份完整物理执行及 {catalog['kinematic_preview_count']} 份运动学预演。", index)
    card = f'<section><h2><a href="{entry["index"]}">{entry["title"]}</a></h2><p>{SCOPE}</p><p>{render["duration_s"]:.2f} 秒 · 五路同步视频 · 基础实例完整物理执行通过。</p></section>'
    index = index.replace("</h1>", "</h1>"+card, 1)
    index = index.replace('id="horseshoe-video-directories">马蹄环视频按变体整理：',
        'id="horseshoe-video-directories">马蹄环视频按变体整理：'
        '<a href="../../demos/horseshoe_ring/">重力下完整解法（按视角）</a> · ', 1)
    (meta_root/"index.html").write_text(index)
    with (meta_root/"README.md").open("a") as handle:
        handle.write(f"\n\n马蹄环重力修正：[五路完整视频与物理验收]({entry['index']})。{SCOPE}\n")
    return meta


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("recording", type=Path)
    parser.add_argument("half_step", type=Path, nargs="?", help="Optional successful complete half-step replication")
    parser.add_argument("--incomplete-half-step", type=Path, help="Preserve an unfinished attempt without qualifying it")
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    print(archive(args.source, args.recording, args.half_step, args.run_id,
                  incomplete_half_step=args.incomplete_half_step), flush=True)


if __name__ == "__main__":
    main()
