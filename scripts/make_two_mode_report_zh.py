#!/usr/bin/env python3
"""中文报告：一批 TopoGym 任务的 unlimited 与 limited 两种模式对比，带视频（GIF 预览 + mp4 链接）。
usage: make_two_mode_report_zh.py <jobs_dir> <unlimited_job> <limited_job> <report_dir> [<batch_plan.json>]
TopoGym (adapted from robot_coding_bench fa59c1a6, whose version was written for one RoboTwin batch): the task list comes
from the two jobs unless a batch plan gives one ({"all_tasks": [...], "keep": [...], "seeds": {...}, "note": "..."});
difficulty labels come from RCB_TASKLIST_STATE (a YAML {task: {difficulty: easy|medium|hard|extreme}}) if it is set; the
failure analysis of a batch is written by hand into ANALYSIS below (write_task_results.py --analysis reads it from here)."""
import json, os, pathlib, shutil, subprocess, sys, datetime as dt, glob, re
jobs, ju, jl, rep = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3], pathlib.Path(sys.argv[4])
plan = json.load(open(sys.argv[5])) if len(sys.argv) > 5 else {}
STATE = pathlib.Path(os.environ["RCB_TASKLIST_STATE"]) if os.environ.get("RCB_TASKLIST_STATE") else None
DIFF = {}
if STATE is not None and STATE.exists():
    import yaml
    DIFF = {t: (b or {}).get("difficulty", "unrated") for t, b in (yaml.safe_load(open(STATE)) or {}).items()}
ZH_DIFF = {"easy": "易", "medium": "中", "hard": "难", "extreme": "极难", "unrated": "未评"}
# 失败分析（人工阅读 agent transcript / verifier 输出后写的；键为家族名，U = unlimited，L = limited），每个批次自己填写
ANALYSIS = {
}

vid = rep / "videos"; vid.mkdir(parents=True, exist_ok=True)
def span(x):
    try:
        a = dt.datetime.fromisoformat(x["started_at"].replace("Z", "+00:00")); b = dt.datetime.fromisoformat(x["finished_at"].replace("Z", "+00:00")); return round((b - a).total_seconds())
    except Exception: return None
def last_msg(trial):
    try:
        d = json.load(open(glob.glob(str(trial / "agent/trajectory.json"))[0]))
        msgs = [(s.get("message") or "").strip() for s in d.get("steps", []) if s.get("source") == "agent" and (s.get("message") or "").strip()]
        return msgs[-1][:600] if msgs else ""
    except Exception: return ""
def task_name(t):
    try: return json.load(open(t / "result.json")).get("task_name", "").split("/")[-1]
    except Exception: return ""
def trial_for(job, task, limited):
    """Map by result.json task_name (Harbor truncates long trial directory names)."""
    want = {task + suffix for suffix in (("-standard", "-limited") if limited else ("-privileged", ""))}
    for t in sorted((jobs / job).glob("topogym-*")):
        if t.is_dir() and (t / "result.json").exists() and task_name(t) in want: return t
    return None
def media(trial, task, mode):
    v = trial / "verifier"; out = {}
    if (v / "replay.mp4").exists():
        mp4 = vid / f"{task}_{mode}.mp4"; shutil.copy(v / "replay.mp4", mp4); out["mp4"] = mp4.name
        gif = vid / f"{task}_{mode}.gif"
        if not gif.exists():
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mp4), "-vf", "fps=5,scale=480:-1:flags=lanczos", str(gif)], check=False)
        if gif.exists(): out["gif"] = gif.name
    if (v / "replay.last.png").exists():
        png = vid / f"{task}_{mode}.png"; shutil.copy(v / "replay.last.png", png); out["png"] = png.name
    return out
def info(trial):
    r = json.load(open(trial / "result.json")) if (trial / "result.json").exists() else {}
    rw = json.load(open(trial / "verifier/reward.json")) if (trial / "verifier/reward.json").exists() else None
    ar = r.get("agent_result") or {}
    return {"done": rw is not None, "success": (rw or {}).get("success"), "rw": rw or {}, "agent_s": span(r.get("agent_execution") or {}),
            "tok_in": ar.get("n_input_tokens"), "tok_out": ar.get("n_output_tokens"), "msg": last_msg(trial),
            "exc": (r.get("exception_info") or {}).get("exception_type")}
def fmt_res(i):
    if i is None: return "未开始"
    if not i["done"]: return "运行中" if not i["exc"] else f"⚠ {i['exc']}"
    if i["rw"].get("grader_error"): return "⚠ verifier 报错（待重判）"
    return "✅ 成功" if i["success"] == 1 else ("❌ 失败（未交付轨迹）" if i["rw"].get("missing_trajectory") else "❌ 失败")
tasks = plan.get("all_tasks") or sorted({re.sub(r"-(limited|standard|privileged)$", "", task_name(t)) for job in (ju, jl) for t in (jobs / job).glob("topogym-*")
                                         if t.is_dir() and task_name(t)})
from regrade_trials import original_task
releases = {}
for job in (ju, jl):
    for trial in (jobs / job).glob("*/result.json"):
        try:
            release_file = original_task(trial.parent) / "task_release.json"
            record = json.loads(release_file.read_text())["release"]
        except (OSError, ValueError, KeyError):
            record = {"name": "historical_unrecorded"}
        releases[record.get("definition_sha256", record["name"])] = record
if len(releases) > 1:
    raise ValueError("Input jobs have different releases; generate separate reports")
L = ["# TopoGym — unlimited 与 limited 两种模式对比报告\n",
     f"生成时间 {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}。Harbor 作业：`{ju}`（unlimited）、`{jl}`（limited）。" + (plan.get("note") or ""),
     "",
     "Release: `" + json.dumps(list(releases.values()), ensure_ascii=False) + "`",
     "## 两种模式",
     "| | unlimited | limited（机器人即服务） |", "|---|---|---|",
     "| 仿真器 | 与 agent 同一容器，可直接 import（rcb_topogym） | 独立 sidecar 容器，agent 打不开 |",
     "| reset | 无限 | 没有：一次 trial 一个 episode |",
     "| 可见信息 | 物体位姿、成功判据源码、薄原语（IK 移动、关节移动、夹爪、保持） | 相机 RGB（可选深度，含标定）+ 关节/夹爪/末端位姿 |",
     "| 动作 | 原语 / 低层 step（每臂关节目标 + 夹爪开口宽度） | `joint_position` 或 `ee_pose` 分块 |",
     "| 交付物 | agent 保存的轨迹 | 服务端录制的轨迹 |",
     "| verifier | 独立沙箱全新进程回放两遍 + 相机拼图视频 | 独立沙箱读 sidecar 记录（服务端已回放核验）+ 相机拼图视频 |\n",
     "视频为相机拼图：第一台相机原尺寸，其余相机缩放后竖排在右侧。GIF 为预览（5 fps），点击链接看 mp4。\n"]
rows = []; tot = {"u": [0, 0], "l": [0, 0]}
for task in tasks:
    tu, tl = trial_for(ju, task, False), trial_for(jl, task, True)
    iu, il = (info(tu) if tu else None), (info(tl) if tl else None)
    mu, ml = (media(tu, task, "unlimited") if tu else {}), (media(tl, task, "limited") if tl else {})
    for k, i in (("u", iu), ("l", il)):
        if i and i["done"] and not i["rw"].get("grader_error"): tot[k][1] += 1; tot[k][0] += int(i["success"] == 1)
    cat = ("keep" if task in plan.get("keep", []) else "") if plan else ""
    rows.append((task, cat, iu, il, mu, ml))
L += ["## 总表", "| 任务 | 类别 | 难度 | unlimited | 用时 s | 动作 | tokens 入/出 | limited | 用时 s | 动作 | tokens 入/出 |", "|---|---|---|---|---|---|---|---|---|---|---|"]
def cells(i):
    if not i: return ["—", "", "", ""]
    return [fmt_res(i), str(i["agent_s"] or ""), str(i["rw"].get("n_actions") or i["rw"].get("steps") or ""), f"{(i['tok_in'] or 0)/1000:.0f}k / {(i['tok_out'] or 0)/1000:.1f}k" if i["done"] else ""]
for task, cat, iu, il, mu, ml in rows:
    L.append(f"| [{task}](#{task}) | {cat} | {ZH_DIFF.get(DIFF.get(task, 'unrated'))} | " + " | ".join(cells(iu)) + " | " + " | ".join(cells(il)) + " |")
L.append(f"\n**已完成的成功率：** unlimited {tot['u'][0]}/{tot['u'][1]} · limited {tot['l'][0]}/{tot['l'][1]}（不含 verifier 报错和未完成的）\n")
sep = {}
for job in (ju, jl):
    for t in (jobs / job).glob("topogym-*"):
        if (t / "result.json").exists():
            m = json.load(open(t / "result.json")).get("verifier_environment_mode"); sep[m] = sep.get(m, 0) + 1
L.append("## verifier 隔离（确认）\n")
L.append(f"两个作业里已完成 trial 的 `verifier_environment_mode` 统计：{sep}。`separate` 表示 verifier 在独立容器里运行（`tests/Dockerfile` 构建，"
         "同一仿真镜像 + verifier 自己的工具和实例），agent 容器在评分前已停止；limited 模式下由 sidecar 服务端录制和回放，agent 容器里没有仿真器。"
         "CI 检查 `ci_checks/check-verifier-isolation.sh` 强制每个任务 `environment_mode = \"separate\"`。\n")
L.append("## 逐任务（左 unlimited，右 limited）\n")
for task, cat, iu, il, mu, ml in rows:
    head = [f"类别：{cat}"] if cat else []
    head.append(f"难度：{ZH_DIFF.get(DIFF.get(task, 'unrated'))}")
    if plan.get("seeds", {}).get(task) is not None: head.append(f"seed {plan['seeds'][task]}")
    L.append(f"### {task}\n\n" + " · ".join(head) + "\n")
    L.append("| unlimited | limited |\n|---|---|")
    def cell(i, m, mode):
        if not i: return "未运行"
        s = fmt_res(i)
        if i["done"]:
            s += f"<br>用时 {i['agent_s']} s · 动作 {i['rw'].get('n_actions') or i['rw'].get('steps') or '—'} · tokens {(i['tok_in'] or 0)//1000}k/{(i['tok_out'] or 0)//1000}k"
            if mode == "unlimited" and i["rw"].get("agent_resets") is not None:
                s += f"<br>调试过程：{i['rw'].get('agent_sessions')} 个进程，{i['rw'].get('agent_resets')} 次 reset，{i['rw'].get('agent_sim_steps')} 控制步"
        if "gif" in m: s += f"<br>![{task} {mode}](videos/{m['gif']})"
        elif "png" in m: s += f"<br>![{task} {mode}](videos/{m['png']})"
        if "mp4" in m: s += f"<br>[mp4](videos/{m['mp4']})"
        return s
    L.append(f"| {cell(iu, mu, 'unlimited')} | {cell(il, ml, 'limited')} |\n")
    for i, mode in ((iu, "unlimited"), (il, "limited")):
        if i and i["msg"]:
            L.append(f"**{mode} agent 最后一条说明：** {i['msg'].replace(chr(10), ' ')}\n")
    an = ANALYSIS.get(task.removeprefix("topogym-"), {})
    for key, mode, i in (("U", "unlimited", iu), ("L", "limited", il)):
        if i and i["done"] and an.get(key):
            L.append(f"**{mode} 分析：** {an[key]}\n")
(rep / "README.md").write_text("\n".join(L)); print("wrote", rep / "README.md", "| videos:", len(list(vid.glob('*.mp4'))))
