"""Read one trial's agent log as a flat list of events (message, thought, shell, write, read, image, ...), each with
an id (e1, e2, ...), the minute it happened, the text the agent wrote or ran, and the cleaned output. Every harness
is read by atif.events (tools/atif.py); this module only cleans what it returns."""
from __future__ import annotations
import ast, json, re
from .paths import RAW
import atif

B64 = re.compile(r"data:image/[a-z]+;base64,[A-Za-z0-9+/=]+")
CALL = re.compile(r"tools\.(\w+)\(\{")
ARG = re.compile(r'(cmd|chars|path|input)\s*:\s*"((?:[^"\\]|\\.)*)"')


def clean_out(raw: str) -> str:
    """Output text without JSON wrappers or base64 images: Codex wraps output in {"output": ..., "exit_code": ...}."""
    if not raw:
        return ""
    texts = []

    def walk(x):
        if isinstance(x, str):
            s = x.strip()
            if s.startswith("Script completed") and s.count("\n") <= 3:
                return
            if s.startswith("{") and '"output"' in s:
                try:
                    d = json.loads(s)
                    code = d.get("exit_code")
                    texts.append((f"[exit {code}] " if code not in (None, 0) else "") + str(d.get("output", "")))
                    return
                except ValueError:
                    pass
            texts.append(x)
        elif isinstance(x, list):
            for y in x:
                walk(y)
        elif isinstance(x, dict):
            if x.get("type") in ("input_image", "image", "image_url"):
                texts.append("[image]")
            else:
                walk(x.get("text") if "text" in x else x.get("content", ""))
    obj = raw
    for parse in (json.loads, ast.literal_eval):
        try:
            obj = parse(raw)
            break
        except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
            continue
    walk(obj)
    out = B64.sub("[image]", "\n".join(t for t in texts if t))
    return re.sub(r"^(Script completed\nWall time [\d.]+ seconds\nOutput:\n)", "", out).strip()


def clean_cmd(name: str, text: str) -> str:
    """Codex `exec` wraps tool calls in JavaScript; return one readable line per inner call."""
    if name != "exec":
        return text
    parts = []
    for m in CALL.finditer(text):
        tool, rest = m.group(1), text[m.end():m.end() + 200000]
        a = ARG.search(rest[:rest.find("})") + 2 if "})" in rest else len(rest)]) or ARG.search(rest)
        val = ""
        if a:
            try:
                val = json.loads('"' + a.group(2) + '"')
            except ValueError:
                val = a.group(2)
        if tool == "write_stdin":
            parts.append("轮询后台进程" if not val else f"向进程输入: {val}")
        elif tool == "exec_command":
            parts.append(f"$ {val}")
        elif tool == "view_image":
            parts.append(f"看图 {val}")
        else:
            parts.append(f"{tool}: {val}")
    return "\n".join(parts) if parts else text


def trajectory(key: str) -> dict:
    return json.load(open(f"{RAW}/{key}/agent/trajectory.json"))


def load_events(key: str) -> list[dict]:
    """atif events with an id and a cleaned text and output."""
    meta = json.load(open(f"{RAW}/{key}/trial.json"))
    ev, _ = atif.events(trajectory(key), atif.request_times(meta["detail"]))
    for i, e in enumerate(ev, 1):
        e["id"] = f"e{i}"
        e["out"] = clean_out(e["out"])
        e["text"] = B64.sub("[image]", clean_cmd(e["name"], e["text"]))
    return ev


def agent_t0(key: str) -> float:
    """Absolute time (s) of the agent's first step: minute 0 of every event."""
    return next(t for t in (atif._ts(s.get("timestamp")) for s in trajectory(key).get("steps") or []) if t)


def instruction(key: str) -> str:
    return atif.instruction(trajectory(key))


def stamp(t) -> str:
    """minutes -> mm:ss"""
    if t is None:
        return "--:--"
    s = int(round(t * 60))
    return f"{s // 60:02d}:{s % 60:02d}"


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("\\n", " ").replace("\\\"", "\"")).strip().lower()
