"""Retain a matched-code timestep comparison alongside an existing video demo."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil

from omegaconf import OmegaConf

from .gravity_demo import ROOT, sha
from .variant_video import check_links, save
from .verify_physical import compare_runs, verify_run


def file_manifest(folder, extra=()):
    files = [p for p in folder.rglob("*") if p.is_file() and p != folder/"archive_manifest.json"]
    files.extend(extra)
    return [dict(path=os.path.relpath(p, folder), bytes=p.stat().st_size, sha256=sha(p)) for p in sorted(files)]


def retain(baseline, half_step, demo, run_id):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", run_id):
        raise ValueError("Use a single archive filename component")
    baseline, half_step, demo = map(lambda p: Path(p).resolve(), (baseline, half_step, demo))
    comparison = compare_runs(baseline, half_step)
    if not comparison["passed"] or not verify_run(demo)["passed"]:
        raise ValueError("Both complete comparison runs and the reference demo must pass")
    for filename in ("input_template.json", "source_motion.json"):
        if sha(demo/filename) != sha(baseline/filename):
            raise ValueError("Comparison and video must describe the same baseline instance")
    old_manifest = json.loads((demo/"archive_manifest.json").read_text())
    for item in old_manifest["files"]:
        if sha(demo/item["path"]) != item["sha256"]:
            raise ValueError(f"Existing preserved evidence changed: {item['path']}")
    output = ROOT/"runs/demo_metadata/horseshoe_ring"/run_id
    output.mkdir(parents=True, exist_ok=False)
    for label, source in (("baseline", baseline), ("half_step", half_step)):
        dest = output/label
        shutil.copytree(source, dest, ignore=shutil.ignore_patterns("*.mp4"))
        cfg = OmegaConf.load(dest/"config.yaml")
        cfg.task.template_path = str(dest/"input_template.json")
        cfg.run.output = str(dest)
        OmegaConf.save(cfg, dest/"config.yaml", resolve=True)
    comparison = compare_runs(output/"baseline", output/"half_step")
    if not comparison["passed"]:
        raise ValueError("Independent retained copies failed qualification")
    comparison["reference_video_archive"] = os.path.relpath(demo, output)
    comparison["reference_video_result_sha256"] = sha(demo/"result.json")
    comparison["reference_video_is_comparison_run"] = False
    comparison["source_directories"] = dict(baseline=str(baseline), half_step=str(half_step))
    comparison["verified_at_utc"] = datetime.now(timezone.utc).isoformat()
    shutil.copy2(Path(__file__).with_name("verify_physical.py"), output/"verification_source.py")
    save(output/"comparison.json", comparison)
    a, b = comparison["baseline"], comparison["half_step"]
    rows = "".join(f"<tr><td>{label}</td><td>{v['dt']*1000:g} ms</td><td>{v['simulated_seconds']:.2f} s</td>"
        f"<td>{v['physics_steps']}</td><td>{v['maximum_puzzle_penetration_m']*1000:.3f} mm</td>"
        f"<td>{v['final_goal']['separation_m']*1000:.1f} mm</td></tr>" for label, v in (("对照", a), ("半步长", b)))
    video_link = os.path.relpath(demo/"index.html", output)
    (output/"index.html").write_text(f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>Horseshoe Ring · 半时间步复验</title><style>body{{max-width:1000px;margin:32px auto;padding:20px;font:16px/1.7 system-ui}}td,th{{padding:12px;border-bottom:1px solid #ddd}}table{{border-collapse:collapse}}</style>
<h1>Horseshoe Ring · 半时间步复验通过</h1>
<p>相同代码、初态、几何和控制参数，分别从原始预抓持初态完整执行；两次都完成取环、解除圆环辅助抓持和自由落桌静置。</p>
<table><tr><th>运行</th><th>步长</th><th>仿真时长</th><th>物理步数</th><th>最大谜题穿透</th><th>最终分离间距</th></tr>{rows}</table>
<p>终态圆环高度差 {comparison['final_ring_height_difference_m']*1000:.6f} mm。两次均含接触确认后的辅助抓持，末态马蹄仍由右手保持。</p>
<p>各运行按实测姿态独立重新规划，检查任务在两种时间步下都能完成；未证明固定控制轨迹的数值收敛或纯摩擦抓取。</p>
<p><a href="comparison.json">独立对照验收</a> · <a href="baseline/result.json">2 ms 执行报告</a> ·
<a href="half_step/result.json">1 ms 执行报告</a> · <a href="{video_link}">已有五路完整视频</a> ·
<a href="archive_manifest.json">文件与哈希</a></p>
<p>已有视频来自此前通过的 2 ms 执行；此次对照使用新运行，两次复验均完整保留实测状态。</p></html>''')
    (output/"README.md").write_text("# Horseshoe Ring 半时间步复验\n\n[对照结果](index.html) · [独立验收](comparison.json)\n\n"
        "baseline/ 与 half_step/ 均为从原始初态开始的连续完整物理运行。含辅助抓持；不是固定轨迹收敛验证。\n")
    save(output/"archive_manifest.json", dict(status="building"))
    links = check_links(output/"index.html")
    files = file_manifest(output)
    save(output/"archive_manifest.json", dict(schema_version=2, classification="timestep_verification",
        counts_as_complete_robotics_demo=False, timestep_replication_passed=True,
        reference_video_archive=os.path.relpath(demo, output), files=files, file_count=len(files),
        total_bytes=sum(f["bytes"] for f in files), local_links=links,
        manifest_note="Independent validation evidence; no new video demo is counted. Paths relative to this manifest."))

    # Preserve the earlier qualification report before adding the new result.
    history = demo/"validation_history"/run_id
    history.mkdir(parents=True, exist_ok=False)
    for filename in ("archive_manifest.json", "physical_verification.json", "index.html", "README.md"):
        shutil.copy2(demo/filename, history/filename)
    comparison_link = os.path.relpath(output/"comparison.json", demo)
    page_link = os.path.relpath(output/"index.html", demo)
    verification = json.loads((demo/"physical_verification.json").read_text())
    verification.update(timestep_replication_passed=True, timestep_comparison_report=comparison_link,
        half_step=comparison["half_step"], timestep_comparison_baseline=comparison["baseline"],
        timestep_comparison_scope="Two new matched-code complete runs; original video remains its recorded 2 ms run",
        final_ring_height_difference_m=comparison["final_ring_height_difference_m"])
    save(demo/"physical_verification.json", verification)
    old_note = "当前只验收此基础实例在 2 ms 步长下的完整执行；额外半时间步复验未完成，不宣称跨时间步稳定性。"
    new_note = f'另用同一版代码完成了 2 ms / 1 ms 两次完整复验，均成功取环并自由落桌。<a href="{page_link}">对照结果与证据</a>。'
    page = (demo/"index.html").read_text()
    if old_note not in page:
        raise ValueError("Expected the original baseline-only qualification note")
    page = page.replace(old_note, new_note).replace("保留的未完成复验记录", "此前未完成尝试的历史记录")
    (demo/"index.html").write_text(page)
    with (demo/"README.md").open("a") as stream:
        stream.write(f"\n新增[同代码 2 ms / 1 ms 完整复验]({page_link})，两次均通过。原有录像保持不变。\n")
    old_manifest.update(timestep_replication_passed=True, timestep_comparison_report=comparison_link)
    old_manifest["files"] = file_manifest(demo, [demo/p for p in old_manifest["video_files"].values()])
    old_manifest["file_count"] = len(old_manifest["files"])
    old_manifest["total_bytes"] = sum(f["bytes"] for f in old_manifest["files"])
    save(demo/"archive_manifest.json", old_manifest)
    check_links(demo/"index.html")
    metadata = ROOT/"runs/demo_metadata"
    catalog = json.loads((metadata/"catalog.json").read_text())
    for entry in catalog["entries"]:
        if entry.get("directory") == str(demo.relative_to(metadata)):
            entry.update(timestep_replication_passed=True,
                timestep_validation=str((output/"index.html").relative_to(metadata)))
    save(metadata/"catalog.json", catalog)
    link = str((output/"index.html").relative_to(metadata))
    index = (metadata/"index.html").read_text()
    (metadata/"index.html").write_text(index.replace("</h1>",
        f'</h1><p>马蹄环新增<a href="{link}">同代码 2 ms / 1 ms 完整复验</a>：两次均通过。</p>', 1))
    with (metadata/"README.md").open("a") as stream:
        stream.write(f"\n马蹄环[同代码半时间步复验]({link})已通过；原五路视频保留。\n")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("half_step", type=Path)
    parser.add_argument("--demo", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    print(retain(args.baseline, args.half_step, args.demo, args.run_id), flush=True)


if __name__ == "__main__":
    main()
