"""The no-code audit of direct play (docs/benchmarks/roboolympics-modes.md, play switch `direct`), shared by every
sport: the generator copies it into tests/ of every task with declared switches; a grader applies it when final.json
says `play` = "direct".

Every tool call of every model response of the session (think_calls.jsonl, recorded by the metering proxy) must be a
literal `game` command or the opening of a saved camera image (or a planning note); anything else - a program, a
script, another shell command, a pipe, a redirection, command substitution, a file edit - forfeits the contest: a
valid trial that is lost (decided 2026-10-06), reported as `nocode_violations` with the calls in nocode_audit.json.

The audit window starts at the player's first `game start` (decided 2026-10-06): before it, self-inspection is also
allowed - listing the harness's tools, reading the instruction, the spec or other files (read-only commands and file
viewers, a code cell that calls no tool). Starting a program, writing a file or any other side effect is a violation
before `game start` too (a program started then would run during play).
"""
import json
import re
from pathlib import Path

VIEWS = re.compile(r"^/app/output/views/[A-Za-z0-9_.-]+\.png$")
WORD = re.compile(r"^[A-Za-z0-9_.+\-:/=,%]+$")
PLAN_TOOLS = {"TodoWrite", "update_plan"}


READONLY = {"cat", "ls", "head", "tail", "wc", "pwd", "which", "file", "stat", "echo", "less", "more", "tree"}
INSPECT_TOOLS = {"Read", "Glob", "Grep", "LS", "TodoWrite", "update_plan", "view_image"}


def literal_words(cmd: str):
    """The words of a command with literal arguments only, or None (see literal_game)."""
    return _words(cmd)


def literal_game(cmd: str) -> bool:
    """`game WORD ...` with literal arguments only: quoted texts may hold anything but an unescaped $ or ` inside double
    quotes (a backslash there only makes the next character literal); outside quotes only plain words (no ; | & < > $
    ` ( ) { } newline ...)."""
    return _game_ok(_words(cmd))


def _words(cmd: str):
    words, cur, quote, quoted, esc = [], "", None, False, False
    for ch in cmd.strip():
        if quote:
            if esc:
                cur += ch; esc = False
            elif quote == '"' and ch == "\\":
                esc = True
            elif ch == quote:
                quote = None
            elif quote == '"' and ch in '$`':
                return None
            else:
                cur += ch
            continue
        if ch in "\"'":
            quote, quoted = ch, True
        elif ch in " \t":
            if cur or quoted:
                words.append(cur)
            cur, quoted = "", False
        elif WORD.match(ch):
            cur += ch
        else:
            return None
    if quote:
        return None
    if cur or quoted:
        words.append(cur)
    return words


def _game_ok(words) -> bool:
    return bool(words) and len(words) >= 2 and words[0] == "game"


def _args(tool):
    a = tool.get("input") or tool.get("arguments") or tool.get("action") or (tool.get("function") or {}).get("arguments")
    if isinstance(a, str):
        try:
            a = json.loads(a)
        except ValueError:
            return {"_raw": a}
    return a if isinstance(a, dict) else {"_raw": a}


def _shell(cmd):
    """The command a shell tool runs: codex wraps it as [bash, -lc, CMD]."""
    if isinstance(cmd, list):
        if len(cmd) == 3 and cmd[0] in ("bash", "sh", "/bin/bash", "/bin/sh") and cmd[1] in ("-lc", "-c"):
            return cmd[2]
        return None
    return cmd if isinstance(cmd, str) else None


# Codex 0.158 with GPT-6 has no direct shell tool: every tool use is an `exec` cell of JavaScript that calls tools
# (tools.exec_command, tools.view_image). JavaScript is code, so only the two one-call cells below are allowed (a
# literal `game` command, or opening a saved camera image, and printing its result); anything else in a cell (loops,
# several calls, computation, other tools) is a violation.
_JS_LIT = r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|-?\d+(?:\.\d+)?'
_JS_CALL = re.compile(r'^\s*const\s+(\w+)\s*=\s*await\s+tools\.(\w+)\(\{(.*)\}\)\s*;?\s*$', re.S)
_JS_PAIR = re.compile(r'\s*(\w+)\s*:\s*(' + _JS_LIT + r')\s*(?:,|$)', re.S)
# the parameters each allowed tool may take (all literal), and what it must be called with
_JS_TOOLS = {"mcp__game__game": {"command"},          # direct-native: the `game` MCP tool (game_mcp.py)
             "exec_command": {"cmd", "workdir", "max_output_tokens", "yield_time_ms"},
             "view_image": {"path", "detail"},
             "write_stdin": {"session_id", "chars", "yield_time_ms", "max_output_tokens"}}


def _js_value(lit):
    if lit[0] in "\"'":
        body = lit[1:-1]
        if lit[0] == "'":
            body = body.replace("\\'", "'").replace('"', '\\"')
        try:
            return json.loads('"' + body + '"')
        except ValueError:
            return None
    return float(lit)


def _js_print_ok(stmt, var):
    """Printing the call's result, nothing else: text(r.output), text(JSON.stringify(r)), text("..." + JSON.stringify(r)),
    image(r.image_url[, "detail"])."""
    v = re.escape(var)
    lit = r'(?:"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\')'
    pats = (rf'text\(\s*{v}\.output\s*\)', rf'text\(\s*JSON\.stringify\(\s*{v}\s*\)\s*\)',
            rf'text\(\s*{lit}\s*\+\s*JSON\.stringify\(\s*{v}\s*\)\s*\)', rf'image\(\s*{v}\.image_url\s*(?:,\s*{lit}\s*)?\)')
    return any(re.fullmatch(p + r'\s*;?\s*', stmt) for p in pats)


_JS_FORBIDDEN = re.compile(r"tools\.|ALL_TOOLS|\bawait\b|\bwhile\b|\bdo\b|\bfunction\b|\beval\b|Function\(|\bimport\b|"
                           r"\brequire\b|\batob\b|\bbtoa\b|Buffer|Uint8Array|ArrayBuffer|DataView|charCodeAt|"
                           r"fromCharCode|codePointAt|setTimeout|setInterval|\bMath\.|\bnew\b|\bclass\b|\byield\b")


def _js_light_display_ok(rest, var) -> bool:
    """Formatting the result for display without computing on it (direct-native, Codex): no further tool call, no loop
    other than over the result's content items, no arithmetic library, no access to the image bytes except passing
    them to image(); at most 800 characters."""
    body = re.sub(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|`(?:[^`\\]|\\.)*`', '""', rest)
    if len(rest) > 800 or _JS_FORBIDDEN.search(body):
        return False
    for m in re.finditer(r"\bfor\s*\(", body):
        if not re.match(rf"for\s*\(\s*(?:const|let|var)\s+\w+\s+of\s+\(?\s*{re.escape(var)}\s*\??\.\s*content", body[m.start():]):
            return False
    for m in re.finditer(r"\.data\b", body):
        if not re.search(r"image\(\s*[\w.]*$", body[:m.start()]):
            return False
    return True


def _js_display_ok(rest, var) -> bool:
    """The statements after the call only display its result: text(r), text(r.output), text(JSON.stringify(r)),
    text("..." + JSON.stringify(r)), image(r.image_url[, "..."]), or the loop that shows an MCP result's content
    (`for (const c of (r.content || [])) { if (c.type === "image") image(c); else if (c.type === "text") text(c.text); }`)."""
    compact = re.sub(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'', "L", rest)
    compact = re.sub(r"\s+", "", compact)
    v = re.escape(var)
    c = r"(?P<c>\w+)"
    simple = (rf"text\({v}\);?", rf"text\({v}\.output\);?", rf"text\(JSON\.stringify\({v}\)\);?",
              rf"text\(L\+JSON\.stringify\({v}\)\);?", rf"image\({v}\.image_url(,L)?\);?")
    show = r"(?:image\((?P=c)(?:\.data)?\)|text\((?P=c)(?:\.text)?\))"
    loop = (rf"for\((?:const|let|var){c}of\(?{v}\.content(?:\|\|\[\])?\)?\)\{{"
            rf"(?:(?:else)?if\((?P=c)\.type===?L\){show};?)+(?:else{show};?)?\}};?")
    while compact:
        for pat in simple + (loop,):
            m = re.match(pat, compact)
            if m:
                compact = compact[m.end():]
                break
        else:
            return False
    return True


def codex_exec_ok(src, cmd_ok=literal_game) -> bool:
    """One literal tool call (a `game` command, opening a camera image, or polling that command's output) and printing
    its result; no other code."""
    if not isinstance(src, str):
        return False
    lines = [x for x in src.strip().split("\n") if x.strip()]
    if not lines:
        return False
    m = _JS_CALL.match(lines[0])
    if not m or m.group(2) not in _JS_TOOLS:
        return False
    var, tool, body = m.group(1), m.group(2), m.group(3)
    args, pos = {}, 0
    while pos < len(body.strip()):
        pm = _JS_PAIR.match(body, pos)
        if not pm:
            return False
        args[pm.group(1)] = _js_value(pm.group(2)); pos = pm.end()
    if not set(args) <= _JS_TOOLS[tool] or any(v is None for v in args.values()):
        return False
    rest = "\n".join(lines[1:])
    if tool == "mcp__game__game":      # direct-native: canonical display or light formatting of the result
        return (_js_display_ok(rest, var) or _js_light_display_ok(rest, var)) and _player_command(args.get("command"))
    if not _js_display_ok(rest, var):
        return False
    if tool == "exec_command":
        return isinstance(args.get("cmd"), str) and cmd_ok(args["cmd"])
    if tool == "view_image":
        return isinstance(args.get("path"), str) and bool(VIEWS.match(args["path"]))
    return args.get("chars", "") == ""            # write_stdin: only polling a running command, never input


def _player_command(cmd) -> bool:
    import shlex
    if not isinstance(cmd, str) or "\n" in cmd.strip():
        return False
    try:
        w = shlex.split(cmd)
    except ValueError:
        return False
    return len(w) >= 2 and w[0] == "game"


def _readonly(cmd) -> bool:
    w = _words(cmd)
    return bool(w) and (w[0] in READONLY or _game_ok(w))


def tool_name(tool):
    return tool.get("name") or (tool.get("function") or {}).get("name") or tool.get("type")


def is_game_start(tool) -> bool:
    """A literal `game start` (shell call or Codex cell)."""
    name, a = tool_name(tool), _args(tool)
    cmd = None
    if name == "exec" and tool.get("type") == "custom_tool_call":
        m = _JS_CALL.match((tool.get("input") or "").strip().split("\n")[0]) if isinstance(tool.get("input"), str) else None
        if m and m.group(2) == "exec_command":
            pm = re.search(r'cmd\s*:\s*(' + _JS_LIT + ')', m.group(3))
            cmd = _js_value(pm.group(1)) if pm else None
    elif name in SHELL_TOOLS or name in ("game", "mcp__game__game", "game__game"):
        cmd = _shell(a.get("command", a.get("cmd")))
    w = _words(cmd) if isinstance(cmd, str) else None
    return bool(w) and w[:2] == ["game", "start"]


def inspection_ok(tool) -> bool:
    """Before `game start`: read-only self-inspection (file viewers, read-only commands, a code cell calling no tool)."""
    if allowed(tool):
        return True
    name, a = tool_name(tool), _args(tool)
    if name in INSPECT_TOOLS:
        return True
    if name == "exec" and tool.get("type") == "custom_tool_call":
        src = tool.get("input")
        code = re.sub(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|`(?:[^`\\]|\\.)*`', '""', src) if isinstance(src, str) else ""
        if isinstance(src, str) and "tools." not in code and "await" not in code and "import" not in code:
            return True                              # pure JavaScript in the harness's sandbox: no tool, no side effect
        return codex_exec_ok(src, _readonly)
    if name in SHELL_TOOLS:
        cmd = _shell(a.get("command", a.get("cmd")))
        return isinstance(cmd, str) and _readonly(cmd)
    return False


SHELL_TOOLS = ("Bash", "shell", "exec_command", "local_shell_call", "container.exec", "shell_command")


def allowed(tool) -> bool:
    name = tool.get("name") or (tool.get("function") or {}).get("name") or tool.get("type")
    a = _args(tool)
    if name in PLAN_TOOLS:
        return True
    if name == "wait" and set(a) <= {"cell_id", "yield_time_ms", "max_tokens"}:   # Codex: wait for a running cell
        return True
    if name in ("game", "mcp__game__game", "game__game"):  # direct-player (harbor_agents/direct_loop.py): its only tool; no shell
        return _player_command(a.get("command"))  # runs it, the line is data for the harness's parser
    if name == "exec" and tool.get("type") == "custom_tool_call":         # Codex code mode (see above)
        return codex_exec_ok(tool.get("input"))
    if name in ("Read", "view_image"):
        return isinstance(a.get("file_path", a.get("path")), str) and bool(VIEWS.match(a.get("file_path", a.get("path"))))
    if name in ("Bash", "shell", "exec_command", "local_shell_call", "container.exec", "shell_command"):
        cmd = _shell(a.get("command", a.get("cmd")))
        return isinstance(cmd, str) and literal_game(cmd)
    return False


def gate_blocked_ids(path):
    """Item ids the gateway (direct_gate.py) blocked, from its log; empty if there is none."""
    ids = set()
    try:
        for line in Path(path).read_text().splitlines():
            e = json.loads(line)
            if e.get("ev") == "blocked" and e.get("item_id"):
                ids.add(e["item_id"])
    except (OSError, ValueError):
        pass
    return ids


def nocode_audit(path, skip_ids=()):
    """(tool calls, violations [(seq, tool name, arguments excerpt)]) of the session's model responses. skip_ids: the
    item ids the gateway blocked (they never reached the agent, so they are not judged)."""

    n, bad = 0, []
    try:
        lines = Path(path).read_text().splitlines()
    except OSError:
        return 0, []
    started = False                                  # the window opens at the first `game start`
    for line in lines:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        for tool in rec.get("tool_calls") or []:
            if tool.get("id") in skip_ids:               # blocked by the gateway (direct-native/1.1): it never ran
                continue
            n += 1
            ok = allowed(tool) if started else inspection_ok(tool)
            started = started or is_game_start(tool)
            if not ok:
                bad.append({"seq": rec.get("seq"), "tool": tool.get("name") or (tool.get("function") or {}).get("name")
                            or tool.get("type"), "args": json.dumps(_args(tool))[:300]})
    return n, bad
