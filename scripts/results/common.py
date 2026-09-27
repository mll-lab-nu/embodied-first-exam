"""What every module of the results pages shares: paths, the standard configs, labels and colours, formatting."""
from __future__ import annotations

import hashlib
import html
import json
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
BENCH = "humanoidbench"
RESULTS = os.path.join(REPO, "results", BENCH)
OUT = os.path.join(REPO, "jobs", "results", BENCH)
ANALYSIS = os.path.join(RESULTS, "analysis")   # the hand-written analysis: overview.md, <task>.md
# where the pages go; build.py --bundle points it at another directory and names the only trial files the pages take
SITE = {"out": OUT, "bundle": False, "media": set()}
HB = os.path.join(REPO, "scripts", "humanoidbench")
STANDARD = {   # runs.csv columns a run must match, per mode, to count in the tables
    "limited": {"budget_min": "60", "resets": "50", "obs": "head+joints+imu+room", "effort": "medium"},
    "full": {"budget_min": "60", "resets": "", "obs": "state", "effort": "medium"}}
MODELS = {"openai/gpt-6-luna": "GPT-6 Luna", "openai/gpt-6-sol": "GPT-6 Sol", "deepseek/deepseek-v4.1-flash": "DeepSeek V4.1 Flash",
          "anthropic/claude-opus-5.5": "Claude Opus 5.5"}
OBS = {"imu": "IMU", "room": "外部相机", "depth": "深度"}   # runs.csv obs parts beyond the head cameras and joints
CAMS = {"left_eye_camera": "左眼", "right_eye_camera": "右眼", "room_camera": "外部相机", "made": "拼图/处理过", "unknown": "相机不明"}
UP_M = 1.0   # an episode's end: the head this far above the lower foot (m, replay_episodes.py's final_head_h) or more
             # means the robot was still up (~1.6 standing, ~1.3 crouched; under 1 sitting on the floor or lying)
KIND = {"failed": ("倒下 / 失败", "e-failed"), "endup": ("结束了但没倒", "e-endup"), "steplimit": ("步数到上限", "e-timeout"),
        "downlimit": ("步数到上限但已倒", "e-downlimit"), "success": ("成功", "e-success"),
        "timeout": ("时间到", "e-running"), "error": ("仿真出错", "e-error"), "reset": ("agent 主动 reset", "e-reset"),
        "running": ("agent 停下时还在跑", "e-running")}
WHY = {"success": "达到及格线，服务结束了这一段", "timeout": "时间用完（agent 超时）", "resets_used_up": "reset 用完，最后一段结束后停下",
       "quit_after_end": "最后一段结束后自己停下", "quit_mid_episode": "最后一段还在跑时自己停下",
       "below_bar": "交了轨迹，回放没到及格线", "no_trajectory": "没交 trajectory.npz", "grader_error": "验证出错"}
TOOLS = {   # what a tool call did, as the pages colour it: key -> (label, colour, how it is told); first match in this order wins
    "robot": ("驱动机器人", "#0f9d8a", "跑代码，其间仿真服务记录到 step / observe / reset"),
    "net": ("联网 / 装包", "#e5484d", "pip、curl、git、apt…"),
    "python": ("其他 Python", "#3aa0d8", "跑 python，但没碰机器人"),
    "write": ("写 / 改文件", "#f08c2e", "apply_patch、重定向到文件、cp / mv / rm…"),
    "view": ("看图", "#c026d3", "view_image"),
    "read": ("查看文件", "#94a3b8", "cat、ls、grep、sed…"),
    "other": ("其他", "#c49a1c", "其余命令、codex 自带的其他工具")}
CLOCK = (1160, 84, 10)   # width, label column, right margin: the charts on the session clock line up
READ = {"cat", "sed", "head", "tail", "less", "more", "nl", "grep", "egrep", "rg", "ls", "find", "wc", "file", "stat", "pwd", "du", "tree",
        "diff", "which", "type", "echo", "printf", "true", "od", "xxd", "sort", "uniq", "awk", "jq", "cut", "tr", "column", "date", "env"}
WRITE = {"cp", "mv", "rm", "mkdir", "touch", "chmod", "tee", "ln", "rmdir", "truncate", "unlink"}
NET = {"pip", "pip3", "curl", "wget", "git", "apt", "apt-get", "conda", "uv", "npm", "ssh", "scp", "nc", "ping", "nslookup"}
PHASE_COLORS = ["#4f7cff", "#14a38b", "#f08c2e", "#a55eea", "#e0508a", "#5a9e2f", "#c49a1c", "#3aa0d8", "#7a6ff0", "#d9603b"]
RUN_COLORS = ["#4f46e5", "#e5484d", "#14a38b", "#f08c2e", "#a55eea", "#0ea5e9", "#c49a1c", "#e0508a", "#5a9e2f", "#64748b"]
esc = html.escape


def progress_text(p: dict | None) -> str:
    """How far a multi-stage task got (rcb_rewards.progress, after the replay), in words; "" for the others."""
    say = {"current_subtask": lambda v: f"柜子做完 {v - 1}/4 格", "task_index": lambda v: f"放好 {v}/5 个物体",
           "maze_stage": lambda v: f"到过 {v}/4 个检查点（含起点）", "stage": lambda v: f"阶段 {v}",
           "tasks_to_complete": lambda v: f"厨房四项还剩 {len(v)} 项", "packages_on_table": lambda v: f"{v} 个包裹上了桌"}
    return "；".join(say[k](v) for k, v in (p or {}).items() if k in say)


def num(v, nd=2) -> str:
    if v is None:
        return "—"
    s = f"{float(v):,.{nd}f}"
    return s[1:] if s.startswith("-") and not any(c in s for c in "123456789") else s.replace("-", "−")


def usd(v) -> str:
    return "—" if v is None else f"${v:.4f}" if v < 0.01 else f"${v:.3f}" if v < 1 else f"${v:,.2f}"


def tok(n) -> str:
    return "—" if n is None else f"{n / 1e6:.2f}M" if n >= 1e6 else f"{n / 1e3:.1f}k" if n >= 1e3 else f"{n:.0f}"


def tip(*lines) -> str:
    """A tooltip for data-tip: the first line bold, each line escaped."""
    body = "<br>".join([f"<b>{esc(str(lines[0]))}</b>"] + [esc(str(x)) for x in lines[1:] if x])
    return esc(body, quote=True)


def text_w(s: str, size: float = 11) -> float:
    return sum(1.0 if ord(c) > 0x2E80 else 0.6 for c in s) * size


def clip_text(s: str, width: float, size: float = 11) -> str:
    if text_w(s, size) <= width:
        return s
    while s and text_w(s + "…", size) > width:
        s = s[:-1]
    return s + "…" if s else ""


def stamp(path: str) -> str:
    """?v=<content hash>, so a browser never keeps showing its cached copy of a file that changed under the same name.
    A bundle's files are served by name only: none."""
    if SITE["bundle"]:
        return ""
    with open(path, "rb") as f:
        return "?v=" + hashlib.sha1(f.read()).hexdigest()[:8]


def rel(path: str, page_dir: str) -> str:
    return os.path.relpath(path, page_dir).replace(os.sep, "/")


def url(s: dict, path: str, page_dir: str) -> str:
    """A trial's file as the pages link it: hard-linked into media/<job>/ (a copy across filesystems), so the site
    needs nothing outside jobs/results/<bench>/ -- a server rooted there (python -m http.server) serves it all.
    In a bundle, a file it does not take is "" (no link)."""
    if SITE["bundle"] and path not in SITE["media"]:
        return ""
    if not os.path.isfile(path):
        return rel(path, page_dir)
    dst = os.path.join(SITE["out"], "media", s["job"], os.path.relpath(path, s["trial_dir"]))
    if not os.path.exists(dst) or not os.path.samefile(dst, path):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.lexists(dst):
            os.remove(dst)
        try:
            os.link(path, dst)
        except OSError:
            shutil.copyfile(path, dst)
    return rel(dst, page_dir)


def pretty_output(text: str) -> str:
    """codex wraps each command's result in JSON ({"exit_code":..,"output":".."}, or a Promise.allSettled entry):
    show the output itself, with its line breaks."""
    lines = []
    for line in text.splitlines():
        try:
            d = json.loads(line) if line.startswith("{") else None
        except ValueError:
            d = None
        d = (d.get("value") or d.get("reason")) if isinstance(d, dict) and "status" in d and ("value" in d or "reason" in d) else d
        if isinstance(d, dict) and "output" in d:
            lines.append(f"[exit {d.get('exit_code', '?')}]" + ("" if d.get("output", "").startswith("\n") else "\n") + str(d["output"]).rstrip())
        elif isinstance(d, str):
            lines.append(d)
        else:
            lines.append(line)
    return "\n".join(lines)
