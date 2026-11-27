"""The efe-robot MCP server in every standard and realtime task (docs/protocol/standard_mode.md "MCP tools"): what
`scripts/task_conventions.py` `normalize` writes into a task so that its robot service is reachable through the service's
client (HTTP, as before) and through MCP tools, the agent's choice.

Per task (manifest(): None for a task without it, exception() says why):
  environment/efe_mcp/        the server (SERVER_FILES, copied unchanged from this directory; suites.py too for a
                              match) and manifest.json: the task's tool list (TOOLS rule below), its protocol and mode
  environment/Dockerfile      `COPY efe_mcp /opt/tools/efe_mcp` (DOCKER_LINE) after the task's last /opt/tools line
  task.toml                   one `[[environment.mcp_servers]]` entry (TOML_BLOCK): Harbor registers the server with the
                              agent's harness (Claude Code, Codex, Gemini CLI, ...) as a stdio server
  instruction.md              the mode line names both routes and `### MCP tools` (section()) follows `### Client`

The tools of an RCB task (manifest "kind": "rcb"): spec, observe, submit and finish everywhere; reset where the task
declares a reset budget; kinematics where its service serves POST /kinematics (the shared or the operations layer with an
adapter that passes `kinematics=`). No other endpoint gets a tool: GET /status (its fields come back in every reply's meta) and
GET /operations/<id> (the server re-queries it itself after a lost reply); ENDPOINTS is the table, and
ci_checks/check-mcp-tools.py holds every served route to it."""
from __future__ import annotations
import json, pathlib, re, shutil

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SERVER_FILES = ("server.py", "rcb_tools.py", "schema.py", "workspace.py", "schema/tools.json")
SUITE_FILES = ("suites.py",)                  # a match's tools (kind "eo-match")
DIR = "environment/efe_mcp"
DOCKER_LINE = "COPY efe_mcp /opt/tools/efe_mcp"
DOCKER_COMMENT = "# the robot's MCP tools (docs/protocol/standard_mode.md \"MCP tools\"): the server Harbor starts, efe-robot"
TOML_MARK = "# The robot's MCP tools (docs/protocol/standard_mode.md \"MCP tools\"): Harbor starts this server for the agent."
TOML_BLOCK = TOML_MARK + """
[[environment.mcp_servers]]
name = "efe-robot"
transport = "stdio"
command = "python3"
args = ["/opt/tools/efe_mcp/server.py"]
"""
FORMAT = "efe-mcp-manifest/1"
SECTION = "### MCP tools"

# Every agent-facing endpoint of the standard / realtime protocol and its tool; None: no tool, with the reason
# (owner 11-25: every agent-facing capability has a tool; no status tool, no operations tool).
ENDPOINTS = {
    "GET /spec": "spec",
    "POST /observe": "observe",
    "POST /submit": "submit",
    "POST /reset": "reset",
    "POST /kinematics": "kinematics",
    "POST /finish": "finish",
    "GET /status": None,           # its fields (done, reason, budgets, time and steps left) come back in every reply's meta
    "GET /operations/<id>": None,  # the operations capability: the server re-queries it itself when a reply is lost (rcb_tools._lost)
}
NO_TOOL = {
    "GET /status": "its fields come back in every tool result's meta",
    "GET /operations/<id>": "the tool server re-queries it itself when a reply is lost",
}
# a match's eai-standard service with the match extension (kind "eo-match", suites.py): the RCB endpoints' tools
# (no /finish, /reset, /kinematics: 404 in a match) and the extension's calls
EO_ENDPOINTS = {"GET /spec": "spec", "POST /observe": "observe", "POST /submit": "submit", "POST /start": "start",
                "POST /ready": "ready", "POST /say": "say", "POST /team": "team", "GET /status": None,
                "POST /finish": None}
EO_NO_TOOL = {
    "GET /status": "its fields come back in every tool result's meta",
    "POST /finish": "a match has none (404): its rules end it",
}
EO_TOOLS = ("spec", "observe", "submit", "start", "ready")
EO_TEAM_TOOLS = ("say", "team")              # a team format's
# tasks that keep only their own interface, and why (their docs say so too)
EO = "embodied-olympics-match"


def on_match_extension(task: pathlib.Path | None) -> bool:
    """A match that serves the match extension (standard_mode.md Part 5): it carries environment/sim/eai_std/."""
    return task is not None and (pathlib.Path(task) / "environment/sim/eai_std").is_dir()


EXCEPTIONS = (
    (lambda folder, name, protocol, task: protocol.startswith("eai-policy/"),
     "RoboEngineer (eai-policy): the agent hands in a policy the platform runs; there is no live robot to call"),
    (lambda folder, name, protocol, task: folder == EO and "-matchlow-" in name,
     "a matchlow match: the player delivers skill code the platform runs in the loop; tool calls cannot deliver it"),
    (lambda folder, name, protocol, task: folder == EO and not on_match_extension(task),
     "an exported match without the match extension (no environment/sim/eai_std/; the G1 table-tennis tasks): its "
     "service serves only the seat API /<SEAT>/<call> of the `game` command, not the /spec, /observe and /submit the "
     "tools call"),
)


def service_layer(task: pathlib.Path) -> str:
    """The task's service layer: "operations" (operations/rcb_limited.py), "shared" (rcb_limited.py), "realtime"
    (realtime/rcb_realtime.py), else "sidecar" (a benchmark's rcb_service.py copy, or its own server). From what its sim
    image takes from the files-only image standard-files, else from what the sim directory's server imports (so a task
    whose Dockerfile lost its layer still counts as that layer's, and the identity check flags it)."""
    sim = pathlib.Path(task) / "environment/sim"
    try:
        txt = (sim / "Dockerfile").read_text()
    except OSError:
        txt = ""
    if "/operations/rcb_limited.py" in txt:
        return "operations"
    if re.search(r"(?m)^\s*/rcb_limited\.py\b|\s/rcb_limited\.py\s", txt):
        return "shared"
    if "/realtime/rcb_realtime.py" in txt:
        return "realtime"
    for name, layer in (("rcb_realtime.py", "realtime"), ("rcb_limited.py", "shared")):
        if (sim / name).is_file():
            return layer
    try:
        src = (sim / "server.py").read_text()
    except OSError:
        src = ""
    if re.search(r"(?m)^\s*(import rcb_limited\b|from rcb_limited import)", src):
        return "shared"
    return "sidecar"


def eo_clock(task: pathlib.Path) -> str:
    """realtime | lockstep | turn: a match on the extension says it in its sim's EAI_STD_CLOCK."""
    try:
        txt = (pathlib.Path(task) / "environment/docker-compose.yaml").read_text()
    except OSError:
        txt = ""
    m = re.search(r'EAI_STD_CLOCK: "(\w+)"', txt)
    return m.group(1) if m else ("realtime" if pathlib.Path(task).name.endswith("-realtime") else "lockstep")


def exception(folder: str, name: str, protocol: str, task: pathlib.Path | None = None) -> str | None:
    return next((why for rule, why in EXCEPTIONS if rule(folder, name, protocol, task)), None)


_KIN: dict[str, bool] = {}


def serves_kinematics(task: pathlib.Path, folder: str) -> bool:
    """Whether the task's service adapter hands the layer a kinematics function: the task's own environment/sim/*.py or
    its benchmark's shared adapter (embodied_first_exam/benchmarks/<folder>/**/sim/server.py, images/<folder>/tools/)."""
    own = [p for p in (task / "environment/sim").glob("*.py")] if (task / "environment/sim").is_dir() else []
    if any("kinematics=" in p.read_text(errors="replace") for p in own):
        return True
    if folder not in _KIN:
        srcs = [p for p in (ROOT / "embodied_first_exam/benchmarks" / folder).rglob("server.py")
                if "privileged" not in p.parts and "sim" in p.parts]
        srcs += list((ROOT / "images" / folder / "tools").rglob("server.py"))
        _KIN[folder] = any("kinematics=" in p.read_text(errors="replace") for p in srcs)
    return _KIN[folder]


def manifest(task: pathlib.Path, folder: str, mode: str, protocol: str, resets: int | None) -> dict | None:
    """The task's manifest.json, or None (a privileged task, an exception, a protocol without tools)."""
    task = pathlib.Path(task)
    if mode not in ("standard", "realtime") or exception(folder, task.name, protocol, task):
        return None
    if folder == EO:
        m = json.loads((HERE / "manifests/embodied-olympics-match.json").read_text())
        m.update({"manifest": FORMAT, "task": task.name, "protocol": protocol,
                  "realtime": eo_clock(task) == "realtime", "turn": eo_clock(task) == "turn"})
        m["tools"] = list(EO_TOOLS) + (list(EO_TEAM_TOOLS) if m.get("team") else [])   # = suites.tools_for (tests)
        return m
    tools = ["spec", "observe", "submit"]
    if resets:
        tools.append("reset")
    if service_layer(task) in ("shared", "operations") and serves_kinematics(task, folder):
        tools.append("kinematics")
    tools.append("finish")
    return {"manifest": FORMAT, "kind": "rcb", "suite": folder, "task": task.name, "protocol": protocol,
            "realtime": mode == "realtime", "tools": tools}


def files_for(m: dict) -> tuple[str, ...]:
    return SERVER_FILES + (SUITE_FILES if m.get("kind") != "rcb" else ())


def apply(task: pathlib.Path, m: dict | None) -> None:
    """Write (m) or remove (None) the server, the Dockerfile line and the task.toml entry; idempotent."""
    task = pathlib.Path(task)
    d = task / DIR
    if m is None:
        if d.exists():
            shutil.rmtree(d)
    else:
        want = {f: (HERE / f).read_bytes() for f in files_for(m)}
        want["manifest.json"] = (json.dumps(m, indent=1, ensure_ascii=False) + "\n").encode()
        if d.exists():
            for p in sorted(d.rglob("*"), reverse=True):
                rel = p.relative_to(d).as_posix()
                if p.is_file() and rel not in want:
                    p.unlink()
                elif p.is_dir() and not any(p.iterdir()):
                    p.rmdir()
        for rel, b in want.items():
            p = d / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            if not p.is_file() or p.read_bytes() != b:
                p.write_bytes(b)
    df = task / "environment/Dockerfile"
    if df.is_file():
        s = df.read_text()
        t = dockerfile(s, m is not None)
        if t != s:
            df.write_text(t)
    tt = task / "task.toml"
    if tt.is_file():
        s = tt.read_text()
        t = toml(s, m is not None)
        if t != s:
            tt.write_text(t)


def dockerfile(s: str, on: bool) -> str:
    lines = [ln for ln in s.rstrip("\n").split("\n") if ln.strip() not in (DOCKER_LINE, DOCKER_COMMENT)]
    if on:
        at = max((i for i, ln in enumerate(lines) if "/opt/tools" in ln and not ln.lstrip().startswith("#")), default=None)
        if at is None:      # a match's seat: before WORKDIR
            at = next((i for i, ln in enumerate(lines) if ln.startswith("WORKDIR")), len(lines)) - 1
        while at + 1 < len(lines) and lines[at].rstrip().endswith("\\"):
            at += 1
        lines[at + 1:at + 1] = [DOCKER_COMMENT, DOCKER_LINE]
    return "\n".join(lines) + "\n"


def toml(s: str, on: bool) -> str:
    """task.toml with TOML_BLOCK (on) right after the `[environment]` table's keys, or without it; one blank line around."""
    lines = s.rstrip("\n").split("\n")
    if TOML_MARK in lines:
        a = lines.index(TOML_MARK)
        b = next(k for k in range(a, len(lines)) if lines[k].startswith('args = ["/opt/tools/efe_mcp/server.py"]'))
        while a > 0 and not lines[a - 1].strip():
            a -= 1
        lines[a:b + 1] = []
    if on:
        env = next((k for k, ln in enumerate(lines) if ln.strip() == "[environment]"), None)
        if env is None:
            at = len(lines)
        else:
            at = next((k for k in range(env + 1, len(lines)) if lines[k].startswith("[")), len(lines))
            while at > env + 1 and (not lines[at - 1].strip() or lines[at - 1].lstrip().startswith("#")):
                at -= 1     # before the blank lines and the comment that belong to the next table
        lines[at:at] = [""] + TOML_BLOCK.rstrip("\n").split("\n")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------------------------------------- the text
def _wrap(t: str, first: str = "", rest: str = "") -> str:
    import textwrap
    t = re.sub(r"`[^`]*`", lambda mm: mm.group(0).replace(" ", "\0"), " ".join(t.split()))
    return textwrap.fill(t, 120, initial_indent=first, subsequent_indent=rest, break_long_words=False,
                         break_on_hyphens=False).replace("\0", " ")


def section(m: dict) -> str:
    """`### MCP tools` of Robot Interface: what the tools are, plainly; neither route is recommended."""
    names = ", ".join(f"`{t}`" for t in m["tools"])
    if m.get("kind") == "rcb":
        rt = m.get("realtime")
        b = [f"The same service is also an MCP server, `efe-robot` (in your tool list), with one tool per endpoint: "
             f"{names}. A tool takes its endpoint's request fields (any other field in `fields`) and returns the "
             "service's reply `meta` unchanged; images, arrays and video are written as files under `/app/obs/` "
             "(`.png`, `.npy`, `.mp4`) and the result lists them. Long action chunks can be passed as a file "
             "(`actions_file`).",
             "`observe` returns at once with what is already recorded: the current frame, or the last `last_s` "
             "seconds. " + ("Time passes only through `submit`, which answers when its rows have run; a `submit` with "
                            "`interpolate` \"hold\", `seconds` and no rows lets time pass with the robot holding still."
                            if not rt else
                            "`submit` answers at once, as the endpoint does. The clock does not wait for a tool "
                            "call, and a call also takes your harness's own time; each result's `tool_s` is the "
                            "tool's part."),
             "A call still running after 45 s returns `pending` with an `operation` id; `observe(operation=id)` "
             "collects its reply.",
             "The client and the tools drive the same robot in the same episode; use either, or both."]
        return SECTION + "\n" + "\n".join(_wrap(x, "- ", "  ") for x in b) + "\n"
    b = [f"The same service is also an MCP server, `efe-robot` (in your tool list), with one tool per endpoint: "
         f"{names}. A tool takes its endpoint's request fields (any other field in `fields`) and returns the "
         "service's reply `meta` unchanged; images are written as files under `/app/obs/` (`.png`, `.npy`) and the "
         "result lists them. There is no `finish` tool: the match's rules end it.",
         "`observe` returns at once; " + ("`submit` answers at once, as the endpoint does."
                                          if m.get("realtime") else
                                          "time passes only through `submit`; a `submit` with `interpolate` \"hold\", "
                                          "`seconds` and no rows lets it pass" + (" (here: waits for your turn)."
                                                                                   if m.get("turn") else ".")),
         "A call still running after 45 s returns `pending` with an `operation` id; `observe(operation=id)` "
         "collects its reply.",
         "The client, the `game` command and the tools play the same seat in the same match; use any of them."]
    return SECTION + "\n" + "\n".join(_wrap(x, "- ", "  ") for x in b) + "\n"


SECTION_RE = re.compile(r"(?ms)^### MCP tools[ \t]*\n.*?(?=^#{2,3} |\Z)")
CLIENT_RE = re.compile(r"(?ms)^### Client[ \t]*\n.*?(?=^#{2,3} |\Z)")


def place_section(s: str, m: dict | None) -> str:
    """The instruction with `### MCP tools` right after `### Client` (m), or without it (None)."""
    s = SECTION_RE.sub("", s)
    if m is None:
        return s
    c = CLIENT_RE.search(s)
    if not c:
        return s
    block = c.group(0).rstrip("\n") + "\n\n" + section(m) + "\n"
    return s[:c.start()] + block + s[c.end():]
