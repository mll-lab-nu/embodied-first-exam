"""Retain independently playable, qualified physical horseshoe recordings."""
from topogym.utils.demo_paths import demo_video_root

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil

from omegaconf import OmegaConf

from .gravity_demo import ROOT, sha
from .variant_video import check_video, save
from .verify_physical import compare_runs, verify_run

SCOPE = "原始预抓持初态开始，重力和碰撞下连续折合、接触交接、取环及释放落桌；接触确认后辅助抓持，非纯摩擦抓取验证。"


def archive(source, recording, half_step, run_id, *, incomplete_half_step=None, variation=None):
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
    source_cfg = OmegaConf.load(source/"config.yaml")
    variation = variation or OmegaConf.select(source_cfg, "task.generation.family_id") or source_cfg.task.variant
    videos_dir = demo_video_root(ROOT, "horseshoe_ring", variation)
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
    camera_links = " · ".join(f"[{name}]({videos[name]})" for name in cameras)
    timestep_note = ("同参数半时间步完整复验通过。" if half else
                     "仅当前步长完整执行通过；尚未完成半时间步复验。")
    (meta/"README.md").write_text(
        f"# Horseshoe Ring · {videos_dir.name}\n\n{SCOPE}\n\n"
        f"{camera_links}\n\n同一次连续执行，{render['duration_s']:.2f} 秒，"
        f"{render['frame_count']} 帧，{render['fps']} FPS。{timestep_note}\n\n"
        "视频来自完整实测状态，不插值，不重新执行动力学；固定相机调整见 "
        "[相机记录](recording/render_cameras.json)。\n\n"
        "[物理验收](physical_verification.json) · [执行报告](result.json) · "
        "[录像来源](recording/render_report.json) · [保留清单](archive_manifest.json)\n")
    verification["local_video_links_exist"] = all((meta/path).is_file() for path in videos.values())
    save(meta/"physical_verification.json", verification)
    entry = dict(task_id="horseshoe_ring", title="马蹄环 · 重力下 ALOHA 完整解法", variant=source_cfg.task.variant,
        variation_id=videos_dir.name,
        classification="physical_execution_with_grasp_assistance", counts_as_complete_robotics_demo=True,
        timestep_replication_passed=bool(half),
        scope=SCOPE, duration_s=render["duration_s"], frames=render["frame_count"], fps=render["fps"], cameras=cameras,
        source_directory=str(source.relative_to(ROOT)), source_recording_directory=str(recording.relative_to(ROOT)),
        archived_at_utc=datetime.now(timezone.utc).isoformat())
    files = [dict(path=os.path.relpath(path, meta), bytes=path.stat().st_size, sha256=sha(path))
             for path in sorted([path for path in meta.rglob("*") if path.is_file() and path != meta/"archive_manifest.json"]+list(targets.values()))]
    save(meta/"archive_manifest.json", dict(entry, schema_version=2, directory=str(meta.relative_to(ROOT)), index="README.md",
        video_directory=os.path.relpath(videos_dir, meta), video_files=videos, files=files,
        file_count=len(files), total_bytes=sum(item["bytes"] for item in files),
        manifest_note="Paths are relative to this manifest; the manifest excludes itself."))
    entry.update(directory=str(meta.relative_to(meta_root)), index=str((meta/"README.md").relative_to(meta_root)),
        video_directory=os.path.relpath(videos_dir, meta_root),
        video_files={f"{name}.mp4": os.path.relpath(path, meta_root) for name, path in targets.items()})
    catalog = json.loads((meta_root/"catalog.json").read_text())
    catalog["entries"].append(entry)
    catalog["complete_robotics_demo_count"] = sum(e.get("counts_as_complete_robotics_demo", False) for e in catalog["entries"])
    catalog["kinematic_preview_count"] = sum(e.get("classification") == "kinematic_rehearsal" for e in catalog["entries"])
    catalog["archived_at_utc"] = entry["archived_at_utc"]
    save(meta_root/"catalog.json", catalog)
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
    parser.add_argument("--variation", help="Optional fixed variant ID; defaults to the source family or baseline")
    args = parser.parse_args()
    print(archive(args.source, args.recording, args.half_step, args.run_id,
                  incomplete_half_step=args.incomplete_half_step, variation=args.variation), flush=True)


if __name__ == "__main__":
    main()
