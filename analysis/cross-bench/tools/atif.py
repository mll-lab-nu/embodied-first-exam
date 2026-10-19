"""Normalize an ATIF trajectory (Codex, Claude Code, Antigravity, dsh) into one event list.

event: {t: minutes since the first step (None if unknown), kind, name, text, out, img}
kind: shell · write · read · image · plan · message · thought · other. `text` is the command / path + content, `out` the
observation text, `img` the number of images the agent saw in that step.
dsh steps carry no timestamps; their times are mapped onto the gateway's request times by index (t_approx = True).
"""
from __future__ import annotations
import datetime as dt, json, re

SHELL = {"bash", "run_command", "exec_command", "shell", "exec", "local_shell", "terminal", "bashoutput", "send_command_input"}
WRITE = {"write", "edit", "multiedit", "write_to_file", "replace_file_content", "multi_replace_file_content",
         "apply_patch", "create_file", "notebookedit", "str_replace_based_edit_tool"}
READ = {"read", "view_file", "list_dir", "glob", "grep", "find_by_name", "grep_search", "view_file_outline", "ls"}
IMAGE = {"read_image", "view_image"}
PLAN = {"todowrite", "manage_task", "update_plan", "task_boundary"}
IMG_RE = re.compile(r"input_image|\"type\": ?\"image\"|'type': ?'image'|image/png|image/jpeg|data:image")
IMG_PATH = re.compile(r"\.(png|jpe?g)\b", re.I)


def _ts(s: str | None) -> float | None:
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _text(x) -> str:
    if x is None:
        return ""
    return x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)


def _kind(name: str, args: dict, text: str) -> str:
    n = name.lower()
    if n == "exec":                              # Codex: JS calling tools.<name>(...)
        inner = set(re.findall(r"tools\.(\w+)\(", text))
        if "apply_patch" in inner:
            return "write"
        if "view_image" in inner:
            return "image"
        return "shell"
    if n in IMAGE or (n in READ and IMG_PATH.search(_text(args.get("file_path") or args.get("AbsolutePath") or args.get("path")))):
        return "image"
    for kind, names in (("shell", SHELL), ("write", WRITE), ("read", READ), ("plan", PLAN)):
        if n in names:
            return kind
    return "other"


def events(traj: dict, request_times: list[float] | None = None) -> tuple[list[dict], bool]:
    steps = traj.get("steps") or []
    times = [_ts(s.get("timestamp")) for s in steps]
    approx = False
    if not any(times) and request_times:
        approx = True                            # step i -> request i*R/N: long waits show up as gaps between requests
        r, n = len(request_times), max(len(steps), 1)
        times = [request_times[min(r - 1, i * r // n)] for i in range(len(steps))]
    t0 = next((t for t in times if t), None)
    out = []
    for s, t in zip(steps, times):
        tm = round((t - t0) / 60, 2) if t and t0 else None
        obs = s.get("observation") or {}
        results = {r.get("source_call_id"): _text(r.get("content")) for r in obs.get("results", []) if isinstance(r, dict)}
        msg = _text(s.get("message")).strip()
        thought = _text(s.get("reasoning_content")).strip()
        if s.get("source") == "agent" and thought:
            out.append({"t": tm, "kind": "thought", "name": "", "text": thought, "out": "", "img": 0})
        if s.get("source") == "agent" and msg:
            out.append({"t": tm, "kind": "message", "name": "", "text": msg, "out": "", "img": 0})
        for c in s.get("tool_calls") or []:
            args = c.get("arguments") or {}
            args = args if isinstance(args, dict) else {"input": args}
            text = _text(args.get("command") or args.get("CommandLine") or args.get("input") or args.get("cmd") or args)
            if not isinstance(args.get("command"), str) and "file_path" in args:
                text = f'{args["file_path"]}\n{_text(args.get("content") or args.get("new_string") or "")}'
            res = results.get(c.get("tool_call_id"), "")
            out.append({"t": tm, "kind": _kind(c.get("function_name") or "", args, text), "name": c.get("function_name") or "",
                        "text": text, "out": res, "img": len(IMG_RE.findall(res))})
    return out, approx


def request_times(detail: dict) -> list[float]:
    return sorted(u[0] for u in detail.get("usage") or [] if isinstance(u, list) and u)


def instruction(traj: dict) -> str:
    """The task text: the first user message that is not Codex's environment context (later user messages can be
    post-compaction summaries, which are often longer)."""
    msgs = [_text(s.get("message")) for s in traj.get("steps") or [] if s.get("source") == "user"]
    real = [m for m in msgs if not m.lstrip().startswith("<environment_context>") and len(m) > 200]
    return real[0] if real else max(msgs, key=len, default="")


BUDGET = [re.compile(p, re.I) for p in (
    r"You have (\d+(?:\.\d+)?) (seconds|minutes|hours) to complete this task",     # the harness's own Time limit section
    r"wall[- ]clock budget \((\d+(?:\.\d+)?) ?(h|min|s)\)",
    r"your (\d+(?:\.\d+)?) ?(s|seconds|min|minutes|h|hours) (?:are|is) up",
    r"(?:wall[- ]clock|time) budget(?: is| of|:)\s*(?:about\s*)?([\d.]+)\s*(h|hours?|min|minutes?|s|seconds)\b",
    r"budget[^.\n]{0,20}?\(\s*(\d{3,6})\s*(s)\b",
    r"(?:you have|time limit(?: is)?:?)\s*([\d.]+)\s*(h|hours?|min|minutes?)\b(?:[^.\n]{0,30}(?:wall|clock|time))?",
)]


def stated_budget_min(text: str) -> float | None:
    """Wall-clock budget the instruction states, in minutes (tasks changed cutoffs over time; this is what the trial ran under)."""
    for rx in BUDGET:
        m = rx.search(text)
        if m:
            v, u = float(m.group(1)), m.group(2).lower()
            return round(v * 60 if u.startswith("h") else v / 60 if u.startswith("s") else v, 1)
    return None
