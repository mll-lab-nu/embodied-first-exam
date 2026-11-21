#!/usr/bin/env python3
"""Runner side of the MCP-only mode (`standard-mcp`, owner decision D131): the agent reaches the robot only through
the task's `efe-robot` MCP server, with no shell, no code execution and no web tool. Nothing in a task can switch a
harness's tools off, so the runner does it, from the task's mode:

    scripts/mcp_only.py claude-args                     # --ak flags for Harbor's -a claude-code
    scripts/mcp_only.py codex-config [<config.toml>]    # a Codex config.toml for --ak config= (stdout)
    scripts/mcp_only.py audit <trial dir> [...]         # was the trial MCP-only? exit 1 if not

Claude Code: `--permission-mode=dontAsk` (a tool call that needs permission and is not allowed is denied, so no shell
or file-writing tool can run, whatever its name), ALLOWED (the efe-robot tools and the file readers, which view the
images the tools write) and DISALLOWED (removed from the model's tool list; also the tools that need no permission but
start other agents or schedule work). Codex: CODEX_OFF set to false (no shell, unified exec or patch tool; the
connectors, apps and plugins of scripts/codex_tools_off.py) and no web search; `view_image` stays. Harbor's
`--enable unified_exec` on the command line does not bring a shell back once `shell_tool` is off (measured on Codex
0.155 / 0.160 against a recorded tool list).

audit: a trial is MCP-only when (a) its agent log has no tool call outside the allowed set and (b) the efe-robot
server's call log (`agent/efe-mcp.jsonl`) shows the robot calls. Standard library only."""
from __future__ import annotations
import json, pathlib, re, sys

SERVER = "efe-robot"
ALLOWED = [f"mcp__{SERVER}", "Read", "Glob", "Grep", "ToolSearch"]
DISALLOWED = ["Bash", "BashOutput", "KillShell", "KillBash", "Edit", "MultiEdit", "Write", "NotebookEdit", "WebFetch",
              "WebSearch", "Task", "Agent", "Workflow", "Skill", "Monitor", "CronCreate", "CronDelete", "CronList",
              "ScheduleWakeup", "EnterWorktree", "ExitWorktree", "SendMessage", "ListAgents", "TaskStop",
              "ReportFindings", "TodoWrite", "SlashCommand", "PowerShell", "REPL", "LSP"]
CODEX_OFF = ["features.shell_tool", "features.unified_exec", "features.apply_patch_freeform",
             "features.apps", "features.plugins", "features.remote_plugin", "features.tool_suggest",
             "features.image_generation", "features.skill_mcp_dependency_install", "apps._default.enabled"]
# what an MCP-only trial's agent log may show besides the efe-robot tools
CLAUDE_OK = {"Read", "Glob", "Grep", "ToolSearch"}
CODEX_OK_ITEMS = {"mcp_tool_call", "agent_message", "reasoning", "error", "todo_list"}


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
            raise ValueError(f"the config sets {k} = {m.group(1)}; an MCP-only run sets {v}")
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
def _claude_tools(lines):
    for ln in lines:
        try:
            ev = json.loads(ln)
        except ValueError:
            continue
        msg = ev.get("message") if isinstance(ev, dict) else None
        for c in (msg or {}).get("content") or [] if isinstance(msg, dict) else []:
            if isinstance(c, dict) and c.get("type") == "tool_use":
                yield c.get("name", "")


def _codex_items(lines):
    for ln in lines:
        try:
            ev = json.loads(ln)
        except ValueError:
            continue
        it = ev.get("item") if isinstance(ev, dict) else None
        if isinstance(it, dict) and ev.get("type") in ("item.started", "item.completed"):
            yield it


def audit(trial: pathlib.Path) -> dict:
    agent = trial / "agent"
    out = {"trial": str(trial), "harness": None, "violations": [], "robot_calls": 0}
    cc = agent / "claude-code.txt"
    cx = agent / "codex.txt"
    if cc.is_file():
        out["harness"] = "claude-code"
        for name in _claude_tools(cc.read_text(errors="replace").splitlines()):
            if not (name.startswith(f"mcp__{SERVER}__") or name in CLAUDE_OK):
                out["violations"].append(name)
    elif cx.is_file():
        out["harness"] = "codex"
        for it in _codex_items(cx.read_text(errors="replace").splitlines()):
            t = it.get("type")
            if t == "mcp_tool_call" and it.get("server") not in (SERVER, SERVER.replace("-", "_")):
                out["violations"].append(f"mcp:{it.get('server')}:{it.get('tool')}")
            elif t not in CODEX_OK_ITEMS and t != "mcp_tool_call" and t != "view_image":
                out["violations"].append(t)
    else:
        out["violations"].append("no agent log (agent/claude-code.txt or agent/codex.txt)")
    log = agent / "efe-mcp.jsonl"
    if log.is_file():
        calls = [json.loads(x) for x in log.read_text().splitlines() if x.strip()]
        out["robot_calls"] = len(calls)
        out["tools"] = sorted({c.get("tool") for c in calls})
    out["violations"] = sorted(set(out["violations"]))
    out["mcp_only"] = not out["violations"]
    return out


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
        bad = 0
        for t in rest:
            r = audit(pathlib.Path(t))
            print(json.dumps(r))
            bad += not r["mcp_only"]
        return 1 if bad else 0
    print(f"unknown command {cmd!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
