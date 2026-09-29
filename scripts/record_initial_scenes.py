#!/usr/bin/env python3
"""Index every registered setting and record short Nyx scenes from a source snapshot.

Uses test_scene_presets / SceneEvidence / RecordingSession; owns no renderer or
video writer. Each implemented setting runs serially in an isolated process.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, data):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def catalog(root):
    tree = ast.parse((root / "topogym/config/variation_records.py").read_text())
    return list(next(ast.literal_eval(node.value) for node in tree.body
                     if isinstance(node, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == "RECORDS" for t in node.targets)))


def source_files(root):
    for folder in ("topogym", "scripts", "tests"):
        for path in sorted((root / folder).rglob("*")):
            if path.is_file() and not {"__pycache__", "deferred"}.intersection(path.parts):
                if path.suffix in {".py", ".json", ".yaml", ".yml"} or "resources" in path.parts:
                    yield path
    yield root / "pyproject.toml"


def publish(output, index, summary):
    write_json(output / "summary.json", summary)
    if index is None:
        return

    def link(label, path):
        return f"[{label}]({os.path.relpath(path, index.parent)})"

    counts = Counter(item["status"] for item in summary["results"])
    formal_count = sum(item['pool'] == 'tier' for item in summary['results'])
    extra_count = len(summary['results'])-formal_count
    lines = ["# 所有任务变体的初始化场景录像", "",
        f"录制批次：`{output.name}`；创建时间：{summary['started_at_utc']}。",
        "主表只列每个任务的 easy / medium / hard；兼容和实验候选另列附表，不计入正式变体。未开发或阻塞项的图像与录像留空。",
        "`base` 是表内注明的默认别名，不重复录制；已退役且未注册的 legacy 入口不列为当前变体。", "",
        f"正式 **{formal_count}** 个变体（完整目录为 13 × 3 = 39）；另有 {extra_count} 个兼容／实验候选。目录录制状态：" +
        "、".join(f"{key}={value}" for key, value in sorted(counts.items())) + "。", "",
        f"统一配置：seed=0，默认机器人与任务声明的 segment0（Claws 为已夹持初态，其余沿用 home），Genesis CUDA + Nyx + compact_lab，848×480，30 fps；"
        f"请求 {summary['seconds']:g} s（{math.ceil(summary['seconds'] / .025)} 个控制步，"
        "每步 10 个 2.5 ms 物理 tick），不执行解题策略。",
        "每组视频来自同一次连续运行；首帧 PNG 是未压缩的 reset 图像。短片很短，播放器可能显示 0 秒，查看初态建议打开 PNG。",
        "“已录制”表示本次短程场景检查及完整视频解码通过，不表示任务解出、长期稳定或全部视角已人工验收。"
        "失败项保留诊断录像和原因，不标为已完成录制。", "",
        "录制使用固定源码快照，避免其他会话中途修改造成混批。" +
        link("源码 SHA-256", output / "source_hashes.json") + " · " +
        link("批次规格与实时结果", output / "summary.json") +
        (" · " + link("固定源码", output / "source_snapshot") if (output / "source_snapshot").exists() else "；合并目录的实际固定源码见每行的来源批次") + "。",
        "如有补录，各行“源码”指向该次实际批次；原失败尝试保留在汇总记录中。",
        "共享资源路径和实际任务参数保存在逐项报告；各 recording_manifest.json 保存视频 SHA-256 和状态/帧来源。", "",
        "| 任务 | 档位／类型 | 变体 ID／结构 | 开发状态 | 本次录制状态 | 初始 PNG | 全部视角 MP4 | 物理时长 | 证据 |",
        "|---|---|---|---|---|---|---|---:|---|"]
    order = {name: i for i, name in enumerate(dict.fromkeys(r["task_id"] for r in summary["results"]))}
    tier_order = {"easy": 0, "medium": 1, "hard": 2, None: 3}
    appendix = False
    for item in sorted(summary["results"], key=lambda r: (r['pool'] != 'tier', order[r["task_id"]], tier_order.get(r["difficulty"], 4), r["variation_id"])):
        if item['pool'] != 'tier' and not appendix:
            appendix = True
            lines += ['', '## 附表：兼容／实验候选（不计入 39 个正式变体）', '',
                'compatibility 用于保留可复现的旧入口；experimental 用于尚未纳入三档的候选。它们不是额外的难度档位。', '',
                '| 任务 | 档位／类型 | 变体 ID／结构 | 开发状态 | 本次录制状态 | 初始 PNG | 全部视角 MP4 | 物理时长 | 证据 |',
                '|---|---|---|---|---|---|---|---:|---|']
        source_output = Path(item.get("source_output", output))
        folder = source_output / item["variation_id"] / item["task_id"]
        report_path = folder / "report.json"
        report = json.loads(report_path.read_text()) if report_path.exists() else {}
        images = " · ".join(link(p.stem, p) for p in sorted((folder / "initial_frames").glob("*.png")))
        videos = " · ".join(link(p.stem, p) for p in sorted((folder / "branch_000/videos").glob("*.mp4")))
        evidence = []
        if report_path.exists():
            evidence.append(link("报告", report_path))
        logfile = source_output / (item["variation_id"] + ".log")
        if logfile.exists():
            evidence.append(link("日志", logfile))
        if report_path.exists():
            evidence.append(link("源码", source_output / "source_hashes.json"))
        if item.get('asset_equivalence_audit'):
            evidence.append(link('当前资产一致性', Path(item['asset_equivalence_audit'])))
        status = {"pending": "待录制", "running": "录制中", "passed": "已录制", "failed": "失败／诊断", "unavailable": ""}[item["status"]]
        gpu = item.get("gpu_preflight", {})
        if item["status"] == "running" and gpu.get("free_mib", 0) < gpu.get("required_mib", 0):
            status = "等待 GPU 空闲显存"
        if item["status"] == "passed" and item.get("task_definition_changes"):
            status = "已录制；任务定义已更新，待刷新"
        elif item['status'] == 'passed' and item.get('asset_equivalence_audit'):
            status = '已录制；当前资产一致性已核对'
        if item.get("error"):
            status += "：" + item["error"].replace("|", "/").replace("\n", " ")[:160]
        development = {"integrated": "已接入", "planned": "待开发", "blocked": "阻塞"}[item["development_status"]]
        variation = f"`{item['variation_id']}` / {item['family_id']}"
        if "base" in item["aliases"]:
            variation += "（默认 base）"
        duration = report.get("physical_time_s")
        lines.append("| " + " | ".join([item["task_id"], item["difficulty"] or item["pool"], variation,
            development, status, images, videos, "" if duration is None else f"{duration:g} s", " · ".join(evidence)]) + " |")
    lines += ["", "## 最新源码适用范围", ""]
    comparison = summary.get("source_comparison")
    if summary.get('mixed_sources'):
        lines.append('这是多批次合并目录，目录清单不代表一次物理执行。每行“源码”与录制 manifest 指向该视频实际使用的固定快照；标为“待刷新”的旧片不能当作当前版本验收。')
    elif comparison is None:
        lines.append("批次尚未结束；结束时将对照工作树源码哈希。")
    else:
        lines.append(f"结束时对照：{len(comparison['changed'])} 个快照文件变化／缺失，{len(comparison['added'])} 个新增文件。"
                     "仅快照相同的版本可直接使用本批证据；后续改动需重新核对或补录。")
        lines.append(link("源码差异明细", output / "source_comparison.json"))
    lines += ["", "## 历史与专门候选", "",
        "- " + link("9 月 24–25 日基础场景历史索引", index.parent / "README_20260925.md") + "：保留旧版本的短程、稳定性与诊断录像。",
        "- " + link("Blanket 单折稳定初态候选", ROOT / "runs/test_results/blanket_stable_segment0_20260926_01/README.md") + "：未替换默认三档，独立列示。",
        "- " + link("历史完整流程 demo", ROOT / "demos/README.md") + "：不作为当前变体初始化证据。", "",
        "重新录制（输出目录必须是新目录）：", "", "```bash", "cd /home/jianwen/topogym",
        ".venv-gs121-nyx/bin/python scripts/record_initial_scenes.py \\",
        "  --output runs/test_results/initial_scenes_NEW_BATCH --seconds 0.1 \\",
        "  --index runs/test_results/base_acceptance_final/README.md", "```", ""]
    temporary = index.with_suffix(".md.tmp")
    temporary.write_text("\n".join(lines))
    temporary.replace(index)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--index", type=Path)
    parser.add_argument("--seconds", type=float, default=.1)
    parser.add_argument("--timeout", type=float, default=900)
    parser.add_argument("--variations", nargs="+",
                        help="Record only these canonical IDs in a new evidence batch (e.g. retries)")
    parser.add_argument("--min-free-gpu-mib", type=int, default=0,
                        help="Wait for this much free GPU 0 memory before each case; wait bounded by --timeout")
    args = parser.parse_args()
    if not math.isfinite(args.seconds) or args.seconds <= 0:
        parser.error("seconds must be positive and finite")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("timeout must be positive and finite")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    index = args.index.resolve() if args.index else None
    if index:
        historical = index.parent / "README_20260925.md"
        if index.exists() and not historical.exists():
            shutil.copy2(index, historical)
    snapshot = output / "source_snapshot"
    hashes = {}
    for path in source_files(ROOT):
        relative = path.relative_to(ROOT)
        target = snapshot / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        hashes[str(relative)] = digest(target)
    write_json(output / "source_hashes.json", hashes)
    rows = catalog(snapshot)
    if args.variations:
        unknown = set(args.variations) - {row["variation_id"] for row in rows}
        if unknown:
            parser.error(f"Unknown variations: {sorted(unknown)}")
        rows = [row for row in rows if row["variation_id"] in args.variations]
    summary = dict(started_at_utc=datetime.now(timezone.utc).isoformat(), seconds=args.seconds,
        scope="all registered settings, reset plus short home hold; not solved-task qualification",
        assertions=["Nyx + compact_lab", "848x480 default cameras", "finite state", "existing scene physics checks", "full video decode"],
        results=[dict(row, development_status=row["status"],
                      status="pending" if row["status"] == "integrated" else "unavailable") for row in rows])
    publish(output, index, summary)
    env = dict(os.environ, PYTHONPATH=str(snapshot) + os.pathsep + str(snapshot / "tests"),
               TOPOGYM_ASSET_ROOT=str(ROOT / "assets"),
               TOPOGYM_VISUAL_ASSET_ROOT=str(ROOT / ".external/nyx-assets"),
               PYOPENGL_PLATFORM="egl")
    for item in summary["results"]:
        if item["status"] == "unavailable":
            continue
        item["status"] = "running"
        command = [sys.executable, str(snapshot / "scripts/test_scene_presets.py"),
            "--case", item["task_id"], "--variation", item["variation_id"],
            "--seconds", str(args.seconds), "--output", str(output / item["variation_id"])]
        item["command"] = command
        publish(output, index, summary)
        if args.min_free_gpu_mib:
            deadline = time.monotonic() + args.timeout
            while True:
                probe = subprocess.run(["nvidia-smi", "--id=0", "--query-gpu=memory.free",
                    "--format=csv,noheader,nounits"], capture_output=True, text=True)
                free = int(probe.stdout.strip()) if probe.returncode == 0 else 0
                item["gpu_preflight"] = dict(free_mib=free, required_mib=args.min_free_gpu_mib,
                    checked_at_utc=datetime.now(timezone.utc).isoformat())
                if free >= args.min_free_gpu_mib:
                    break
                if time.monotonic() >= deadline:
                    item.update(status="failed", error="GPU memory wait timed out; no simulator started")
                    break
                print(item["variation_id"], f"waiting for GPU memory: {free}/{args.min_free_gpu_mib} MiB", flush=True)
                publish(output, index, summary)
                time.sleep(10)
            if item["status"] == "failed":
                publish(output, index, summary)
                continue
        print(item["variation_id"], "running", flush=True)
        with (output / (item["variation_id"] + ".log")).open("x") as log:
            process = subprocess.Popen(command, cwd=snapshot, env=env, stdout=log,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            try:
                code = process.wait(timeout=args.timeout)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                code = -1
                item["error"] = f"timeout after {args.timeout:g}s"
            except BaseException:
                os.killpg(process.pid, signal.SIGTERM)
                raise
        report_path = output / item["variation_id"] / item["task_id"] / "report.json"
        report = json.loads(report_path.read_text()) if report_path.exists() else {}
        item.update(status="passed" if code == 0 and report.get("status") == "passed" else "failed", exit_code=code)
        if item["status"] == "failed" and "error" not in item:
            error = report.get("traceback") or report.get("recording_error")
            item["error"] = error.strip().splitlines()[-1] if error else f"process exit {code}; see log"
        publish(output, index, summary)
        print(item["variation_id"], item["status"], item.get("error", ""), flush=True)
    current = {str(p.relative_to(ROOT)): digest(p) for p in source_files(ROOT)}
    comparison = dict(changed=[name for name, sha in hashes.items() if current.get(name) != sha],
                      added=sorted(set(current) - set(hashes)))
    summary.update(finished_at_utc=datetime.now(timezone.utc).isoformat(), source_comparison=comparison)
    write_json(output / "source_comparison.json", comparison)
    publish(output, index, summary)
    return int(any(item["status"] == "failed" for item in summary["results"]))


if __name__ == "__main__":
    raise SystemExit(main())
