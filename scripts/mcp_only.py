#!/usr/bin/env python3
"""Runner side of the efe-robot MCP modes (`standard-mcp`, owner decisions D131 and D145; `standard-mcp-shell`).

standard-mcp (D145): the agent may write and run code to compute (inverse kinematics, trajectories, gaits, filtering,
image processing), but every robot command and observation is a call of an `efe-robot` MCP tool that the model makes
itself: no code contacts the simulator, and no code starts or calls the MCP server. The harness runs with its standard
tools (as in standard mode); the rule is enforced by the audit below. The no-code ablation (mode alias
`standard-mcp-nocode` in scripts/run_agent_batch.sh, the same task dirs) takes every code and file-writing tool away:

    scripts/mcp_only.py claude-args                     # no-code: --ak flags for Harbor's -a claude-code
    scripts/mcp_only.py codex-config [<config.toml>]    # no-code: a Codex config.toml for --ak config= (stdout)
    scripts/mcp_only.py audit [--mode M] [--no-code] <trial dir> [...]
                                                        # one JSON line per trial; exit 1 if one has a violation
    scripts/mcp_only.py audit-job <job dir> [--mode M] [--no-code] [--out FILE]
                                                        # the runner's verdict on a job: {ok, violations[], trials[]}
                                                        # (default FILE: <job dir>/mcp_audit.json); exit 0

No-code harness settings. Claude Code: `--permission-mode=dontAsk` (a tool call that needs permission and is not
allowed is denied, so no shell or file-writing tool can run, whatever its name), ALLOWED (the efe-robot tools and the
file readers, which view the images the tools write) and DISALLOWED (removed from the model's tool list, the web tools
among them; also the tools that need no permission but start other agents or schedule work). Codex: CODEX_OFF set to
false (no shell, unified exec or patch tool; the connectors, apps and plugins of scripts/codex_tools_off.py) and no web
search; `view_image` stays. Harbor's `--enable unified_exec` on the command line does not bring a shell back once
`shell_tool` is off (measured on Codex 0.155 / 0.160 against a recorded tool list).

Audit of a trial (machine-readable: every violation is {"kind", "detail"}):
  - the sim service's episode log (<trial>/artifacts/episode.jsonl) against the efe-robot server's call log
    (<trial>/agent/efe-mcp.jsonl: a `server` line per server process, a `sim` line per request it sent, written before
    the request): a submit whose note lacks the server's mark `efe-mcp:<tool>#<n>` (unmarked_request), a marked note
    the harness's server never sent (forged_mark), more /submit, /observe, /reset or /kinematics requests at the
    service than the harness's server sent (untraced_request);
  - an efe-robot server started by a script rather than by the agent's harness (script_server);
  - agent code that contacts the simulator or the MCP server, as far as the agent log shows it: the simulator's
    address, a robot client imported, the server started from the shell (agent_code);
  - a web tool call (web_tool); with --no-code also any tool outside the MCP-only set (tool_not_allowed).
standard-mcp-shell (the tools beside the task's own client and a shell): no rule on routes; the audit only counts the
requests that did not come through the server (`requests.direct`). Standard library only."""
from __future__ import annotations
import collections, json, pathlib, re, sys

SERVER = "efe-robot"
MODES = ("standard-mcp", "standard-mcp-shell")
ALLOWED = [f"mcp__{SERVER}", "Read", "Glob", "Grep", "ToolSearch"]
DISALLOWED = ["Bash", "BashOutput", "KillShell", "KillBash", "Edit", "MultiEdit", "Write", "NotebookEdit", "WebFetch",
              "WebSearch", "Task", "Agent", "Workflow", "Skill", "Monitor", "CronCreate", "CronDelete", "CronList",
              "ScheduleWakeup", "EnterWorktree", "ExitWorktree", "SendMessage", "ListAgents", "TaskStop",
              "ReportFindings", "TodoWrite", "SlashCommand", "PowerShell", "REPL", "LSP"]
CODEX_OFF = ["features.shell_tool", "features.unified_exec", "features.apply_patch_freeform",
             "features.apps", "features.plugins", "features.remote_plugin", "features.tool_suggest",
             "features.image_generation", "features.skill_mcp_dependency_install", "apps._default.enabled"]
# what a no-code trial's agent log may show besides the efe-robot tools
CLAUDE_OK = {"Read", "Glob", "Grep", "ToolSearch"}
CODEX_OK_ITEMS = {"mcp_tool_call", "agent_message", "reasoning", "error", "todo_list", "view_image"}
WEB_TOOLS = {"WebSearch", "WebFetch", "web_search", "web_fetch"}
# the service requests the audit counts, and the episode-log events that stand for them
PATHS = ("/submit", "/observe", "/reset", "/kinematics")
EVENTS = {"submit": "/submit", "observe": "/observe", "reset": "/reset"}
MARK = "efe-mcp:"
# the process that starts the efe-robot server: the harness (Claude Code: claude or node; Codex: codex), else a script
HARNESS_PARENT = re.compile(r"^(claude|node|codex)")
SCRIPT_PARENT = re.compile(r"^(python[0-9.]*|bash|sh|dash|zsh|ksh|fish|perl|ruby|env|timeout|setsid|nohup|stdbuf|"
                           r"script|socat|tmux.*|screen|uv|pip)$")
# agent code that reaches the simulator or the MCP server: (pattern, what, commands only), in commands and in the text
# of the files the agent writes
CODE_PATTERNS = [
    (re.compile(r"\b(?:localhost|127\.0\.0\.1|0\.0\.0\.0|sim):8000\b"), "the simulator's address", False),
    (re.compile(r"\b(?:localhost|127\.0\.0\.1|sim)\s+8000\b"), "the simulator's address", True),
    (re.compile(r"(?:environ(?:\.get)?\s*[\[(]\s*['\"]SIM_URL|getenv\(\s*['\"]SIM_URL|\$\{?SIM_URL\b)"),
     "the simulator's address (SIM_URL)", False),
    (re.compile(r"\b(?:import|from)\s+(?:rcb_client|rcb1|rcb_adapter|mcp_client|efe_robot|ro_client)\b"),
     "a robot client or the server's code imported", False),
    (re.compile(r"\bpython[0-9.]*\s+(?:-\S+\s+)*\S*efe_mcp/server\.py\b(?![^\n;&|]*--print-tools)"),
     "the efe-robot server started from code", False),
    (re.compile(r"(?:^|\s|/)game\s+(?:spec|status|start|wait|observe|act|ready|say|team)\b"),
     "the match's game command", True),
]
# a shell segment that only reads (its text is not code that runs)
READER = re.compile(r"^\s*(?:sudo\s+)?(?:grep|rg|egrep|fgrep|cat|sed|awk|head|tail|less|more|find|ls|wc|file|stat|diff|"
                    r"echo|printf|nl|strings|xxd|od|tree|type|which)\b")


def claude_args() -> list[str]:
    return ["--ak", "permission_mode=dontAsk", "--ak", "allowed_tools=" + ",".join(ALLOWED),
            "--ak", "disallowed_tools=" + ",".join(DISALLOWED)]


def codex_config(text: str) -> str:
    """`text` (a config.toml, possibly empty) with every CODEX_OFF key = false, `include_apply_patch_tool = false` and
    `web_search = "disabled"` (scripts/codex_tools_off.py writes the keys; it refuses a config that turns one on)."""
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import codex_tools_off as cto
    cto.OFF = list(dict.fromkeys(CODEX_OFF + list(cto.OFF)))
    out = cto.tools_off(text)
    top = []
    for k, v in (("web_search", '"disabled"'), ("include_apply_patch_tool", "false")):
        m = re.search(rf"(?m)^\s*{k}\s*=\s*(.*?)\s*$", out)
        if m and m.group(1) != v:
            raise ValueError(f"the config sets {k} = {m.group(1)}; a no-code run sets {v}")
        if not m:
            top.append(f"{k} = {v}")
    if top:
        out = "\n".join(top) + "\n" + out
    try:
        import tomllib
        tomllib.loads(out)
    except ModuleNotFoundError:
        pass
    return out


# ------------------------------------------------------------------------------------------------------------ audit
def _jsonl(path: pathlib.Path) -> list[dict]:
    out = []
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return out
    for ln in lines:
        try:
            v = json.loads(ln)
        except ValueError:
            continue
        if isinstance(v, dict):
            out.append(v)
    return out


def _claude_tools(events):
    """(tool name, its input) of every tool call in Claude Code's stream-json log."""
    for ev in events:
        msg = ev.get("message")
        for c in (msg or {}).get("content") or [] if isinstance(msg, dict) else []:
            if isinstance(c, dict) and c.get("type") == "tool_use":
                yield c.get("name", ""), c.get("input") if isinstance(c.get("input"), dict) else {}


def _codex_items(events):
    for ev in events:
        it = ev.get("item")
        if isinstance(it, dict) and ev.get("type") in ("item.started", "item.completed"):
            yield it


def _code_texts(name: str, inp: dict) -> list[str]:
    """The text of a tool call that runs or writes code: a command, a file's new content."""
    if name in ("Bash", "PowerShell", "REPL"):
        return [str(inp.get("command") or inp.get("code") or "")]
    if name == "Write":
        return [str(inp.get("content") or "")]
    if name == "Edit":
        return [str(inp.get("new_string") or "")]
    if name == "MultiEdit":
        return [str(e.get("new_string") or "") for e in inp.get("edits") or [] if isinstance(e, dict)]
    if name == "NotebookEdit":
        return [str(inp.get("new_source") or "")]
    return []


def _code_hits(text: str, command: bool) -> list[str]:
    """CODE_PATTERNS found in `text`; in a command, the segments that only read files are skipped."""
    if command:
        segs = [s for s in re.split(r"&&|\|\||[;|\n]", text) if s.strip() and not READER.match(s)]
        text = "\n".join(segs)
    hits = []
    for rx, what, only_commands in CODE_PATTERNS:
        if only_commands and not command:
            continue
        m = rx.search(text)
        if m:
            a = max(0, m.start() - 60)
            hits.append(f"{what}: {' '.join(text[a:m.end() + 60].split())[:200]}")
    return hits


def ev_done(it: dict) -> bool:
    """A Codex item counted once: at its completed event (a started one is in progress)."""
    return it.get("status") != "in_progress"


def _agent_log(trial: pathlib.Path, out: dict, no_code: bool, strict: bool) -> None:
    agent = trial / "agent"
    cc, cx = agent / "claude-code.txt", agent / "codex.txt"
    V = out["violations"]
    if cc.is_file():
        out["harness"] = "claude-code"
        for name, inp in _claude_tools(_jsonl(cc)):
            out["agent_tool_calls"] += name.startswith(f"mcp__{SERVER}__")
            if name in WEB_TOOLS:
                V.append({"kind": "web_tool", "detail": name})
            elif no_code and not (name.startswith(f"mcp__{SERVER}__") or name in CLAUDE_OK):
                V.append({"kind": "tool_not_allowed", "detail": name})
            if strict:
                for t in _code_texts(name, inp):
                    V += [{"kind": "agent_code", "detail": f"{name}: {h}"} for h in _code_hits(t, name == "Bash")]
    elif cx.is_file():
        out["harness"] = "codex"
        for it in _codex_items(_jsonl(cx)):
            t = it.get("type")
            out["agent_tool_calls"] += (t == "mcp_tool_call" and it.get("server") in (SERVER, SERVER.replace("-", "_"))
                                        and ev_done(it))
            if t == "web_search":
                V.append({"kind": "web_tool", "detail": "web_search"})
            elif t == "mcp_tool_call" and it.get("server") not in (SERVER, SERVER.replace("-", "_")):
                if no_code:
                    V.append({"kind": "tool_not_allowed", "detail": f"mcp:{it.get('server')}:{it.get('tool')}"})
            elif no_code and t not in CODEX_OK_ITEMS:
                V.append({"kind": "tool_not_allowed", "detail": str(t)})
            if strict and t == "command_execution":
                V += [{"kind": "agent_code", "detail": f"command: {h}"}
                      for h in _code_hits(str(it.get("command") or ""), True)]
    else:
        out["warnings"].append("no agent log (agent/claude-code.txt or agent/codex.txt): the agent's tool calls were "
                               "not checked")


def _nkey(note) -> str:
    """A submit's note as both logs can be compared on (services shorten notes and fold their whitespace)."""
    return " ".join(str(note or "").split())[:200]


def _episode_log(trial: pathlib.Path) -> pathlib.Path | None:
    a = trial / "artifacts"
    if (a / "episode.jsonl").is_file():
        return a / "episode.jsonl"
    found = sorted(a.rglob("episode.jsonl")) if a.is_dir() else []
    return found[0] if found else None


def audit(trial: pathlib.Path, mode: str = "standard-mcp", no_code: bool = False) -> dict:
    trial = pathlib.Path(trial)
    strict = mode == "standard-mcp"
    out = {"trial": trial.name, "mode": mode, "no_code": no_code, "harness": None, "ok": True, "violations": [],
           "warnings": [], "agent_tool_calls": 0, "robot_calls": 0, "tools": [], "requests": {}}
    V, W = out["violations"], out["warnings"]
    _agent_log(trial, out, no_code, strict)

    # the efe-robot servers of this trial and what they sent
    log = _jsonl(trial / "agent" / "efe-mcp.jsonl")
    servers = {r.get("pid"): r for r in log if "server" in r}
    harness_pids = set()
    for pid, h in servers.items():
        comm = str((h.get("parent") or {}).get("comm") or "")
        if h.get("via") or SCRIPT_PARENT.match(comm):
            if strict:
                V.append({"kind": "script_server", "detail": f"an efe-robot server (pid {pid}) started by "
                          + (f"{h['via']!r}" if h.get("via") else f"{comm!r}: "
                             + str((h.get("parent") or {}).get("cmd") or "")[:120])})
        else:
            harness_pids.add(pid)
            if not HARNESS_PARENT.match(comm):
                W.append(f"an efe-robot server (pid {pid}) started by {comm or 'an unknown process'!r}")
    ours = (lambda r: r.get("pid") in harness_pids) if (strict and servers) else (lambda r: True)
    calls = [r for r in log if "tool" in r and "sim" not in r and "server" not in r and ours(r)]
    sims = [r for r in log if "sim" in r and ours(r)]
    out["robot_calls"] = len(calls)
    out["tools"] = sorted({str(c.get("tool")) for c in calls})
    traced = collections.Counter(str(r.get("sim")) for r in sims)
    out["requests"]["via_server"] = {p: traced[p] for p in PATHS if traced[p]}
    if log and not servers:
        W.append("the call log has no request records (an efe-robot server before 0.2.0): requests are not compared")

    # the service's own record of the requests it received
    ep = _episode_log(trial)
    if ep is None:
        W.append("no episode log (artifacts/episode.jsonl): the service side was not checked")
        out["ok"] = not V
        return out
    recs = [r for r in _jsonl(ep) if "seat" not in r]       # a match service's per-seat records are not requests
    seen, got = set(), collections.Counter()
    for i, r in enumerate(recs):
        e = r.get("ev")
        if e in EVENTS:
            key = (e, r["call"]) if isinstance(r.get("call"), int) else (e, f"#{i}")   # a crash-resumed call: once
            if key not in seen:
                seen.add(key)
                got[EVENTS[e]] += 1
    begun = collections.Counter(str(r.get("path")) for r in recs if r.get("ev") == "call_begin")
    service = {p: max(got[p], begun[p]) for p in PATHS if max(got[p], begun[p])}
    out["requests"]["service"] = service
    if not strict:
        out["requests"]["direct"] = {p: n - traced[p] for p, n in service.items() if n > traced[p]}
        out["ok"] = not V
        return out
    # marks: every submit the service logged with its note was sent by the harness's server: the server's mark
    # `efe-mcp:<tool>#<n>`, or (a `signal` of a communication action) the agent's note that server sent
    if servers:
        sent = collections.Counter(_nkey(r.get("note")) for r in sims if r.get("sim") == "/submit")
    else:                   # a server before 0.2.0: its marks, and the notes of its signal calls
        sent = collections.Counter(_nkey((c.get("args") or {}).get("note")) for c in calls if c.get("tool") == "signal")
    unmarked, forged = [], []
    seen_notes = set()
    for i, r in enumerate(recs):
        if r.get("ev") != "submit" or "note" not in r:
            continue
        key = ("submit", r["call"]) if isinstance(r.get("call"), int) else ("submit", f"#{i}")
        if key in seen_notes:
            continue
        seen_notes.add(key)
        note = _nkey(r.get("note"))
        if sent[note] > 0:
            sent[note] -= 1
        elif not note.startswith(MARK):
            unmarked.append(r.get("call"))
        elif servers:
            forged.append(note)
    if unmarked:
        V.append({"kind": "unmarked_request", "detail": f"{len(unmarked)} submit(s) without the {MARK} mark (service "
                  f"call {', '.join(map(str, unmarked[:10]))}{', ...' if len(unmarked) > 10 else ''})"})
    if forged:
        V.append({"kind": "forged_mark", "detail": f"{len(forged)} marked submit(s) the harness's efe-robot server "
                  f"did not send ({', '.join(sorted(set(forged))[:5])})"})
    if not log and service:
        if out["harness"] and not out["agent_tool_calls"]:
            V.append({"kind": "untraced_request", "detail": "requests at the service, and no efe-robot tool call in "
                      "the agent log: " + ", ".join(f"{p} x{n}" for p, n in service.items())})
        else:
            W.append("no call log (agent/efe-mcp.jsonl): the service's requests were not compared with the server's")
    if servers:
        extra = {p: n - traced[p] for p, n in service.items() if n > traced[p]}
        if extra:
            V.append({"kind": "untraced_request", "detail": "requests at the service the harness's efe-robot server "
                      "did not send: " + ", ".join(f"{p} x{n}" for p, n in extra.items())})
    out["ok"] = not V
    return out


def audit_job(job: pathlib.Path, mode: str = "standard-mcp", no_code: bool = False) -> dict:
    trials = sorted(p for p in pathlib.Path(job).glob("*__*") if p.is_dir())
    res = [audit(t, mode, no_code) for t in trials]
    return {"job": pathlib.Path(job).name, "mode": mode, "no_code": no_code, "ok": all(r["ok"] for r in res),
            "violations": [{"trial": r["trial"], **v} for r in res for v in r["violations"]],
            "warnings": [{"trial": r["trial"], "warning": w} for r in res for w in r["warnings"]],
            "trials": res}


def _opts(rest: list[str]):
    mode, no_code, out, pos = "standard-mcp", False, None, []
    it = iter(rest)
    for a in it:
        if a == "--mode":
            mode = next(it, "")
        elif a == "--no-code":
            no_code = True
        elif a == "--out":
            out = next(it, "")
        else:
            pos.append(a)
    if mode == "standard-mcp-nocode":
        mode, no_code = "standard-mcp", True
    if mode not in MODES:
        raise SystemExit(f"--mode must be one of {', '.join(MODES)} (or standard-mcp-nocode)")
    return mode, no_code, out, pos


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "claude-args":
        print(" ".join(claude_args()))
        return 0
    if cmd == "codex-config":
        text = pathlib.Path(rest[0]).read_text() if rest else ""
        try:
            sys.stdout.write(codex_config(text))
        except ValueError as e:
            print(f"mcp_only.py: {e}", file=sys.stderr)
            return 2
        return 0
    if cmd == "audit":
        mode, no_code, _, pos = _opts(rest)
        bad = 0
        for t in pos:
            r = audit(pathlib.Path(t), mode, no_code)
            print(json.dumps(r))
            bad += not r["ok"]
        return 1 if bad else 0
    if cmd == "audit-job":
        mode, no_code, out, pos = _opts(rest)
        if len(pos) != 1:
            print("usage: mcp_only.py audit-job <job dir> [--mode M] [--no-code] [--out FILE]", file=sys.stderr)
            return 2
        r = audit_job(pathlib.Path(pos[0]), mode, no_code)
        dst = pathlib.Path(out) if out else pathlib.Path(pos[0]) / "mcp_audit.json"
        tmp = dst.with_name(dst.name + ".tmp")
        tmp.write_text(json.dumps(r, indent=1) + "\n")
        tmp.replace(dst)
        print(f"mcp audit {r['job']}: {'ok' if r['ok'] else 'VIOLATIONS'} ({len(r['trials'])} trial(s), "
              f"{len(r['violations'])} violation(s), {len(r['warnings'])} warning(s)) -> {dst}")
        return 0
    print(f"unknown command {cmd!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
