#!/usr/bin/env python3
"""Generate `<base>-standard-mcp` task dirs from their `<base>-standard` twins (branch `standard-mcp`; owner decisions
D126-D131, D145: the agent may run code to compute, the robot is reached only through tool calls of the model's own).
Same sim sidecar, instance, grader and cutoff; the changes, nothing else:

  environment/efe_mcp/   the efe-robot MCP server (this directory's server files, unchanged) + the task's manifest.json
                         (manifests/<suite>.json resolved for the task, manifest.py)
  environment/Dockerfile `COPY efe_mcp /opt/tools/efe_mcp`; the robot client goes to the server's own directory
                         /opt/efe_mcp_client (off the agent's PYTHONPATH), an Embodied Olympics match's `game` command
                         is not installed
  task.toml              `[[environment.mcp_servers]]` efe-robot (stdio), the description and keywords
  instruction.md         a `## Robot tools` section (from the manifest), the client section marked as reference,
                         record-keeping sentences that need a shell removed; normalize renders the mode's sections
  solution/              the twin's oracle unchanged (solve_standard.sh) on a client that goes through the MCP tools
                         (oracle/rcb_client_mcp.py, oracle/sitecustomize.py, the MCP client mcp_client.py)

then scripts/task_conventions.py normalize (README, monitor, caps, DIGEST).

    python3 embodied_first_exam/standard/mcp/generate.py --core [--suite S ...] [--task BASE ...] [--dry-run]
"""
from __future__ import annotations
import argparse, json, pathlib, re, shutil, sys, textwrap, tomllib

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(HERE))
import task_conventions as tc     # noqa: E402
import manifest as mf             # noqa: E402
import schema as sch              # noqa: E402

MODE = "standard-mcp"
SHELL = "standard-mcp-shell"          # the same tools + their Python client (client_gen.py) + the task's client + a shell
MODES = (MODE, SHELL)
SERVER_FILES = ("server.py", "rcb_adapter.py", "geom.py", "kin.py", "schema.py", "workspace.py", "schema/tools.v0.json")
SHELL_FILES = ("mcp_client.py",)    # the shell variant's Python client (efe_robot.py) is built on it
SUITE_FILES = ("suites.py",)          # the non-RCB suites' tools, when present
ORACLE_FILES = ("oracle/rcb_client_mcp.py", "oracle/ro_client_mcp.py", "oracle/sitecustomize.py", "mcp_client.py")
CLIENT_DIR = "/opt/efe_mcp_client"    # the server's robot client (rcb_adapter.py finds it there); not on PYTHONPATH
MCP_TOML = """
# Robot control through the efe-robot MCP server only (mode standard-mcp; embodied_first_exam/standard/mcp/)
[[environment.mcp_servers]]
name = "efe-robot"
transport = "stdio"
command = "python3"
args = ["/opt/tools/efe_mcp/server.py"]
"""
CLIENT_HEADING_RE = re.compile(r"(?m)^## (Client\b[^\n]*|Robot service[^\n]*)$")
RECORD_START_RE = re.compile(r"(?:Leave|Keep) (?:your|the)\s+(?:scripts?|controllers?|programs?|code)\b")
CONTEXT_BULLET_RE = re.compile(r"(?ms)^- (?:\*\*Nothing is put into your context automatically\.\*\*|Nothing is put into your context automatically:|Images come back as arrays in a Python object;).*?(?=^- |^\n|^#|\Z)")
CLIENT_GONE = "the client is not installed for your code: the `efe-robot` tools stand for it"
PHRASES = [   # (whitespace-flexible pattern, replacement) in the intro and rules
    (r"You\s+get\s+one\s+client\s+and", "You get the `efe-robot` tools and"),
    (r"you\s+reach\s+it\s+only\s+through\s+a\s+client", "you reach it only through the `efe-robot` tools"),
    (r"you\s+reach\s+it\s+only\s+through\s+its\s+client", "you reach it only through the `efe-robot` tools"),
    (r"you\s+get\s+one\s+Python\s+client\s+and", "you get the `efe-robot` tools and"),
    (r"you\s+get\s+its\s+client,", "you get the `efe-robot` tools,"),
    (r"Your\s+whole\s+interface\s+to\s+the\s+robot\.\s+", ""),
    (r";\s+write\s+your\s+own\s+controller\.", "."),
    (r"`python\s+-c\s+\"import\s+rcb_client;\s+help\(rcb_client\)\"`(?:,\s+readable\s+with\s+your\s+file-reading\s+tool)?",
     CLIENT_GONE),
    (r"`/opt/tools/rcb_client\.py`(?:,\s+readable\s+with\s+your\s+file-reading\s+tool)?", CLIENT_GONE),
]


def core_bases() -> list[str]:
    return [t["task"] for t in tomllib.loads((REPO / "docs/core_set.toml").read_text())["task"]]


def suite_manifest(suite: str) -> dict | None:
    p = HERE / "manifests" / f"{suite}.json"
    return json.loads(p.read_text()) if p.is_file() else None


def agent_ended(task: pathlib.Path) -> bool:
    return tc.agent_end_of(task) is not None


def task_manifest(src: pathlib.Path) -> dict:
    suite = src.parent.name
    sm = suite_manifest(suite)
    if sm is None:
        raise SystemExit(f"{src.name}: no manifests/{suite}.json")
    m = mf.resolve(sm, src.name)
    if m.get("unsupported"):
        return m
    if agent_ended(src) and m.get("kind", "rcb") == "rcb":
        m.setdefault("signals", {})["done"] = {"finish": True}
    errs = mf.check(m)
    if errs:
        raise SystemExit(f"{src.name}: manifest problems: {errs}")
    return m


# ------------------------------------------------------------------------------------------------------- instruction
def wrap(t: str, first: str = "", rest: str = "") -> str:
    t = re.sub(r"`[^`]*`", lambda mm: mm.group(0).replace(" ", "\0"), t)
    return textwrap.fill(t, 120, initial_indent=first, subsequent_indent=rest, break_long_words=False,
                         break_on_hyphens=False).replace("\0", " ")


# owner decision D145: the rule, in these words in every MCP-only task (the audit: scripts/mcp_only.py)
RULE = ("You may write and run code to compute; every robot command and observation must go through the efe-robot "
        "MCP tools; code must not contact the simulator. Each robot command or observation is a tool call you make "
        "yourself: no script starts or calls the `efe-robot` server, and the service's record of its requests is "
        "checked against the server's. To send a trajectory your code computed, save it as a file under `/app` and "
        "pass its path as `rows_file` to `execute_trajectory`.")


SHELL_INTRO = ("Besides the robot service's own client (below), you get the robot through the tools of the MCP "
               "server `efe-robot` (in your tool list as `efe-robot` tools, for example `mcp__efe-robot__{eg}`) and "
               "through the same tools as Python functions: `import efe_robot` (`/opt/tools/efe_robot.py`, on "
               "`PYTHONPATH`; each function has the tool's name, arguments and result, and its docstring is the tool's "
               "description), or `python3 /opt/tools/efe_robot.py <tool> '<JSON arguments>'` from the shell. They all "
               "drive the one robot: use one route at a time.")


def tool_section(m: dict, task: pathlib.Path, mode: str = MODE) -> str:
    """`## Robot tools`: how the agent acts, generated from the task's manifest and the tool list it gets."""
    if m.get("kind", "rcb") != "rcb":
        import suites
        return suites.instruction_section(m) if mode == MODE else suites.shell_section(m, SHELL_INTRO.format(eg="act"))
    tools = {t["name"]: t for t in sch.tools_for(m)}
    parts = sch.part_lines(m)
    cams = ", ".join(f"`{c}`" for c in m.get("cameras") or []) or "see `describe_robot`"
    base_text = (m.get("frame") or {}).get("base_text", "")
    L = []
    if mode == SHELL:
        L.append("## Robot tools (MCP server `efe-robot`) and their Python client `efe_robot`")
        L.append(wrap(SHELL_INTRO.format(eg="move_robot") + " The calls of the service's client and the tools that do "
                      "the same:"))
    else:
        L.append("## Robot tools (MCP server `efe-robot`)")
        L.append(wrap(
            "You act on the robot only through the tools of the MCP server `efe-robot` (in your tool list as "
            "`efe-robot` tools, for example `mcp__efe-robot__move_robot`). " + RULE + " The robot service and its "
            "rules are as described in this text; where it names calls of the Python client `rcb_client.py`, which is "
            "not installed for your code here, use the tool that does the same:"))
    L.append("")
    rows = [("`Robot()`, `r.spec()`", "`describe_robot()`: the robot's parts, joints and limits, cameras, control "
             "period, action types and conventions, and the time left; the full spec is saved as a JSON file "
             "(`spec_file`) you can read"),
            ("`r.get_obs(cameras, seconds, depth)`", "`observe(cameras, seconds, depth)`"),
            ("`r.submit(type, A, dt, interpolate)`", "`execute_trajectory(space=\"native\", action_type=type, "
             "native_rows=A, dt=dt, interpolate=...)`, or `move_robot` / `execute_trajectory` in the conventions "
             "below"),
            ("`r.status()`, `meta[...]`", "every tool result: `time_left_s`, `sim_time_s`, `done`, `reason` and the "
             "service's messages")]
    if "reset_episode" in tools:
        rows.append(("`r.reset()` / `POST /reset`", "`reset_episode()`"))
    sg = (m.get("signals") or {})
    if (sg.get("done") or {}).get("finish"):
        rows.append(("`POST /finish`", "`signal(kind=\"done\")`"))
    extra_kinds = [k for k in sg if k != "done"]
    if extra_kinds:
        rows.append(("the communication actions (" + ", ".join(f"`{k}`" for k in extra_kinds) + ")",
                     "`signal(kind=..., note=...)`"))
    L.append("| Client | Tool |")
    L.append("|---|---|")
    L += [f"| {a} | {b} |" for a, b in rows]
    L.append("")
    conv = ("**Conventions** of `move_robot`, `locomote` and `execute_trajectory` (spaces other than `native`): the "
            "robot base frame at the start of each call (+X forward, +Y left, +Z up), metres and radians, quaternions "
            "`wxyz`, gripper 0 = open to 1 = closed."
            + (f" Base frame of this robot: {base_text.strip().rstrip('.')}." if base_text else "")
            + " Space `native` sends rows in the robot's own action types exactly as the sections below describe them "
            "(their frame, units and gripper values).")
    L.append(wrap(conv))
    L.append("")
    robot = f"**This robot** ({m.get('robot', '')})" if m.get("robot") else "**This robot**"
    if parts:
        L.append(wrap(f"{robot}: {parts}. Cameras: {cams}."))
    else:
        L.append(wrap(f"{robot}: its own action types only (`execute_trajectory` space `native`; `describe_robot` "
                      f"lists them). Cameras: {cams}."))
    L.append("")
    b = []
    b.append("`describe_robot()`: call it first.")
    b.append("`observe(cameras?, depth?, seconds?, save_to?, inline_cameras?)`: images are written as JPEG files under "
             "`/app/obs/` (depth as `.npy`, float32 metres; with `seconds` > 0 a video `.mp4` too); the result has "
             "their paths, each camera's intrinsics `K` and pose in the robot base frame, each part's joints, gripper "
             "and end-effector pose, and `proprio_now` (the robot's own proprioception row; its layout is in the spec "
             "file). Open an image with your file-reading tool; `inline_cameras` also returns small images in the "
             "result.")
    if "locate" in tools:
        b.append("`locate(camera, u, v | pixels, window_px?)`: the 3-D point in the robot base frame that a camera sees "
                 "at pixel (u, v) of its full-size image (u the column, v the row), or one per pixel of `pixels` "
                 "[[u, v], ...]: from a new depth image of that camera and its calibration (no time passes). For a "
                 "camera with depth and a known pose; for any other the error says so.")
    if "move_robot" in tools:
        b.append("`move_robot(goals, duration_s?)`: one goal per part, `{target, position?, quaternion_wxyz?, "
                 "joint_positions?, gripper?}`" + (" (the base: `{target: \"base\", dx, dy, dyaw}`)" if m.get("base")
                                                   else "")
                 + "; the parts move together and the call returns when the motion is done, with `reached` (errors "
                 "per goal), a `failure` category if a goal was not reached, the state and the path of a frame per "
                 "camera.")
    if "locomote" in tools:
        b.append("`locomote(vx, vy, wz, duration_s, height?)`: walk with the robot's own controller (body-frame "
                 "velocities), then stop; returns the displacement.")
    b.append("`execute_trajectory(space, rows | native_rows | rows_file, dt?, interpolate?)`: a dense trajectory, "
             "rows `dt` seconds apart. `rows_file` is the path of a file under `/app` that holds the rows: a `.npy` "
             "(2-D float array) or `.csv` (one row per line, comma-separated) of native rows for space `native` (with "
             "`action_type`), or a `.json` list: of number arrays (native rows) or of row objects as in `rows` (the "
             "other spaces). Long arrays go this way rather than inline.")
    b.append("`wait(seconds?, operation?)`: let time pass holding the current command, or collect a pending "
             "operation.")
    if "reset_episode" in tools:
        b.append("`reset_episode()`: a new episode from the same starting state (it uses one reset of the budget).")
    b.append("`signal(kind, note)`: " + ("end the episode (`done`)" if (sg.get("done") or {}).get("finish")
                                         else "`done` records that you are finished (the episode itself ends as "
                                              "described above)")
             + (", or " + ", ".join(f"`{k}`" for k in extra_kinds) if extra_kinds else "") + ".")
    b.append("One tool call runs at a time. A call still executing after 45 s returns `{\"pending\": true, "
             "\"operation\": id}` while the robot goes on executing it: call `wait(operation=id)` (it waits up to 45 s "
             "more each time) for its result. A result with `\"episode_over\": true` means the episode has ended.")
    if mode == MODE:
        b.append("Nothing needs to be saved: the server records every tool call, and the service records the episode.")
    else:
        b[-1] = b[-1].replace("One tool call runs at a time. ", "One tool call runs at a time (the Python functions "
                              "wait for a pending call themselves). ")
    L += [wrap(x, "- ", "  ") for x in b]
    if m.get("notes"):
        L.append("")
        L.append(wrap("**Notes on this robot.** " + str(m["notes"])))
    return "\n".join(L) + "\n"


def _remove_record_sentences(s: str) -> str:
    """Drop the sentences asking for a script or notes under /app/output (the agent writes no files here)."""
    out, i = [], 0
    for mm in RECORD_START_RE.finditer(s):
        if mm.start() < i:
            continue
        j, tick = mm.start(), False
        end = None
        while j < len(s):
            ch = s[j]
            if ch == "`":
                tick = not tick
            elif ch == "." and not tick and (j + 1 == len(s) or s[j + 1] in " \n"):
                end = j + 1
                break
            j += 1
        if end is None:
            continue
        if "/app/output" not in s[mm.start():end]:
            continue
        out.append(s[i:mm.start()])
        i = end
        while i < len(s) and s[i] == " ":
            i += 1
    out.append(s[i:])
    r = "".join(out)
    r = re.sub(r"(?m)[ \t]+$", "", r)
    r = re.sub(r"(?m)^- *\n", "", r)        # a bullet left empty
    return r


def transform_instruction(s: str, m: dict, task: pathlib.Path, mode: str = MODE) -> str:
    lines = s.split("\n")
    if lines and lines[0].startswith("# "):
        t = lines[0]
        t = t.replace("-standard", "-" + mode) if task.name in t else t
        label = "MCP TOOLS ONLY" if mode == MODE else "MCP TOOLS AND SHELL"
        if "STANDARD MODE" in t:
            t = t.replace("STANDARD MODE", "STANDARD MODE, " + label, 1)
        else:
            t += " — " + ("MCP tools only" if mode == MODE else "MCP tools and shell")
        lines[0] = t
    s = "\n".join(lines)
    if mode == SHELL:            # the standard text stays whole; the tools section goes before its first section
        if m.get("kind", "rcb") != "rcb":
            k = s.find("\n## Interface")
            k = k if k >= 0 else s.find("\n## ")
        else:
            k = s.find("\n## ")
        sec = tool_section(m, task, mode)
        return (s[:k + 1] + sec + "\n" + s[k + 1:]) if k >= 0 else (s.rstrip() + "\n\n" + sec)
    for pat, rep in PHRASES:
        s = re.sub(pat, rep, s)
    s = _remove_record_sentences(s)
    seen = []
    s = CONTEXT_BULLET_RE.sub(lambda mm: "" if seen.append(1) or len(seen) > 1 else (
        "- **Images are files.** The tools write camera images, depth and video under `/app/obs/` and return their "
        "paths with small JSON; open an image with your file-reading tool, or ask for small images in the result "
        "with `inline_cameras`.\n"), s)
    s = CLIENT_HEADING_RE.sub(lambda mm: "## The robot service through its Python client (reference; your code cannot "
                                         "reach it: act through the `efe-robot` tools above)", s, count=1)
    k = s.find("\n## ")
    sec = tool_section(m, task, mode)
    s = (s[:k + 1] + sec + "\n" + s[k + 1:]) if k >= 0 else (s.rstrip() + "\n\n" + sec)
    return s


# ---------------------------------------------------------------------------------------------- instruction, v2 form
# instructions v2 (owner decisions D158-D165): the standard twin's text is in the v2 skeleton (task_conventions
# V2_SECTIONS); its `## Robot Interface` starts with `### Client` (the service's client), then `### Actions` (the robot's
# own action types) and the benchmark's other H3s. The MCP variants keep Task, Goal and Others, put the mode's fixed
# words in (V2_MODE_LINE, V2_HAND_IN, V2_RULE_TOOLS / V2_RULE_ROUTE) and replace `### Client` by `### Tools` (from the
# manifest). MCP-only: `### Actions` goes too where the manifest's notes give the native rows in the tools' terms (D164:
# no client reference). normalize renders `## Limits`.
V2_PHRASES = [   # the standard text's client words, in an MCP-only task's other sections
    (r"`r\.get_obs\(seconds=([^)`]*)\)`", r"`observe(seconds=\1)`"),
    (r"`get_obs\(seconds=([^)`]*)\)`", r"`observe(seconds=\1)`"),
    (r"`r\.get_obs\(\)`", "`observe()`"),
    (r"`r\.spec\(\)`", "the spec file (`describe_robot`)"),
    (r"`spec\(\)\[", "the spec's `["),
    (r"`spec\[", "the spec's `["),
    (r"`meta\[\"([a-z_]+)\"\]`", r"the tool result's `\1`"),
    (r"`obs\.meta\[\"cameras\"\]`", "`observe`'s camera entries"),
    (r"`obs\.meta\[\"proprio\"\]`", "`proprio_now`"),
    (r"through its client", "through the `efe-robot` tools"),
    (r"the service's client", "the `efe-robot` tools"),
    (r"`submit`", "`execute_trajectory`"),
]


V2_PHRASE_STARTS = re.compile(r"(?m)(?:(?<=[.!?] )|(?<=[.!?]\n)|(?<=^- )|(?<=\n\n)|\A)(the spec's|the spec file|the "
                              r"tool result's|the `efe-robot` tools)")


def _v2_phrases(text: str) -> str:
    """V2_PHRASES applied to `text`; a substitution that starts a sentence starts with a capital."""
    for pat, rep in V2_PHRASES:
        text = re.sub(pat, rep, text)
    return V2_PHRASE_STARTS.sub(lambda mm: mm.group(1)[0].upper() + mm.group(1)[1:], text)


def _v2_sections(s: str) -> list[tuple[str, str]]:
    """[(heading line or "" for the title part, text)] of a v2 instruction, H2 by H2."""
    parts = re.split(r"(?m)^(## .+)$", s)
    out = [("", parts[0])]
    for i in range(1, len(parts), 2):
        out.append((parts[i].strip(), parts[i + 1]))
    return out


def _h3_split(body: str) -> list[tuple[str, str]]:
    parts = re.split(r"(?m)^(### .+)$", body)
    out = [("", parts[0])]
    for i in range(1, len(parts), 2):
        out.append((parts[i].strip(), parts[i + 1]))
    return out


def tool_section_v2(m: dict, task: pathlib.Path, mode: str = MODE) -> str:
    """`### Tools` of a v2 MCP instruction: the tools, their conventions and the robot's notes, from the manifest."""
    tools = {t["name"]: t for t in sch.tools_for(m)}
    parts = sch.part_lines(m)
    cams = ", ".join(f"`{c}`" for c in m.get("cameras") or []) or "see `describe_robot`"
    base_text = ((m.get("frame") or {}).get("base_text") or "").strip().rstrip(".")
    sg = (m.get("signals") or {})
    extra_kinds = [k for k in sg if k != "done"]
    if mode == SHELL:
        intro = ("The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__move_robot`), also as Python "
                 "functions: `import efe_robot` (`/opt/tools/efe_robot.py`, on `PYTHONPATH`; each function has the "
                 "tool's name, arguments and result, its docstring the tool's description) or `python3 "
                 "/opt/tools/efe_robot.py <tool> '<JSON arguments>'` from the shell. They and the service's client "
                 "(`### Client`) all drive the one robot.")
    else:
        intro = "The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__move_robot`)."
    conv = (" Their conventions (all but space `native`): "
            + (base_text if base_text.startswith("the robot base frame") else
               f"the robot base frame is {base_text}" if base_text else
               "the robot base frame at the start of each call (+X forward, +Y left, +Z up)")
            + "; metres, radians, quaternions `wxyz`, gripper 0 open .. 1 closed.")
    robot = (f" Parts: {parts}." if parts else " Parts: the robot's own action types only (`execute_trajectory` space "
             "`native`).") + f" Cameras: {cams}."
    L = ["### Tools", wrap(intro + conv + robot), ""]
    b = ["`describe_robot()`: call it first: parts and limits, cameras, control period, action types, the time left; "
         "the full spec as a JSON file (`spec_file`)."]
    b.append("`observe(cameras?, depth?, seconds?, inline_cameras?)`: JPEG images under `/app/obs/` (depth `.npy`, "
             "float32 metres; with `seconds` > 0 an `.mp4` too, the robot held still meanwhile); the result has their "
             "paths, each camera's `K` and pose in the base frame, each part's joints, gripper and end-effector pose, "
             "and `proprio_now` (the robot's own proprioception row; its layout is in the spec file).")
    if "locate" in tools:
        b.append("`locate(camera, u, v | pixels, window_px?)`: the 3-D point in the base frame a depth camera sees at "
                 "pixel (u, v) of its full-size image (u the column, v the row); no time passes.")
    if "move_robot" in tools:
        b.append("`move_robot(goals, duration_s?)`: one goal per part, `{target, position?, quaternion_wxyz?, "
                 "joint_positions?, gripper?}`" + (" (the base: `{target: \"base\", dx, dy, dyaw}`)" if m.get("base")
                                                   else "")
                 + "; the parts move together and the call returns when the motion is done, with `reached` (the error "
                 "per goal), a `failure` category if a goal was not reached, the state and a frame per camera.")
    if "locomote" in tools:
        b.append("`locomote(vx, vy, wz, duration_s, height?)`: walk with the robot's own controller (body-frame "
                 "velocities), then stop; returns the displacement.")
    b.append("`execute_trajectory(space, rows | native_rows | rows_file, dt?, interpolate?)`: dense rows `dt` seconds "
             "apart; long arrays as `rows_file`, a file under `/app` (`.npy` or `.csv` of native rows for space "
             "`native` with `action_type`, or a `.json` list).")
    b.append("`wait(seconds?, operation?)`: let time pass holding the current command, or collect a pending call.")
    if "reset_episode" in tools:
        b.append("`reset_episode()`: a new episode from the same starting state (one reset of the budget).")
    done = sg.get("done") or {}
    b.append("`signal(kind, note)`: " + ("end the episode (`done`)" if done.get("finish") or done.get("type")
                                         else "`done` records that you are finished (the episode itself ends as Goal "
                                              "says)")
             + (", or " + ", ".join(f"`{k}`" for k in extra_kinds) if extra_kinds else "")
             + (" (the tool's description says what each does)" if extra_kinds and m.get("signals_text") else "") + ".")
    b.append(("One call at a time (the Python functions wait for a pending call themselves). " if mode == SHELL else
              "One call at a time. ") + "A call still running after 45 s returns `{\"pending\": true, \"operation\": "
             "id}`: collect it with `wait(operation=id)`. `\"episode_over\": true` means the episode has ended.")
    L += [wrap(x, "- ", "  ") for x in b]
    if m.get("notes"):
        L += ["", wrap("This robot: " + str(m["notes"]).strip())]
    return "\n".join(L) + "\n"


def _swap_v2(text: str, old: str, new: str) -> str:
    """`text` with the fixed phrase `old` replaced by `new` wherever the phrase stands, however the generator wrapped
    it; a prose paragraph it lands in is wrapped again (lists, tables and code are left as they are)."""
    pat = re.compile(r"\s+".join(re.escape(w) for w in old.split()))
    paras = re.split(r"(\n[ \t]*\n)", text)
    for i in range(0, len(paras), 2):
        p = paras[i]
        if not pat.search(p):
            continue
        q = pat.sub(lambda _: new, p)
        body = q.strip("\n")
        if not re.match(r"\s*(- |\d+\. |\||```|#)", body):
            q = q[:len(q) - len(q.lstrip("\n"))] + wrap(" ".join(body.split())) + q[len(q.rstrip("\n")):]
        paras[i] = q
    return "".join(paras)


def _rewrap_long(text: str, width: int = 120) -> str:
    """Wrap again the prose lines and list items a substitution made longer than `width` (code blocks, tables and
    headings stay as they are; items that still fit are not touched)."""
    out, buf, in_code = [], [], False

    def flush() -> None:
        items = []   # [first prefix, rest prefix, words, original lines]
        for ln in buf:
            mm = re.match(r"^(\s*)(- |\d+\. )(.*)$", ln)
            if mm:
                items.append([mm.group(1) + mm.group(2), mm.group(1) + " " * len(mm.group(2)), mm.group(3), [ln]])
            elif items:
                items[-1][2] += " " + ln.strip()
                items[-1][3].append(ln)
            else:
                items.append(["", "", ln.strip(), [ln]])
        for first, rest, words, orig in items:
            if any(len(x) > width for x in orig):
                out.append(wrap(" ".join(words.split()), first, rest))
            else:
                out.extend(orig)
        buf.clear()

    for ln in text.split("\n"):
        if ln.lstrip().startswith("```"):
            flush()
            in_code = not in_code
            out.append(ln)
        elif in_code:
            out.append(ln)
        elif not ln.strip() or ln.lstrip().startswith(("#", "|")):
            flush()
            out.append(ln)
        else:
            buf.append(ln)
    flush()
    return "\n".join(out)


def transform_instruction_v2(s: str, m: dict, task: pathlib.Path, mode: str = MODE) -> str:
    """The MCP variant of a v2 standard instruction (see above)."""
    out = []
    for head, text in _v2_sections(s):
        if head == "":
            text = text.replace("(standard)", f"({mode})", 1)
        elif head == "## Task":
            text = _swap_v2(text, tc.V2_MODE_LINE["standard"], tc.V2_MODE_LINE[mode])
            text = _swap_v2(text, tc.V2_MODE_LINE_RESETS["standard"], tc.V2_MODE_LINE_RESETS[mode])   # a task with resets
        elif head == "## Goal":
            if mode == MODE:
                text = _swap_v2(text, tc.V2_HAND_IN["standard"], tc.V2_HAND_IN[MODE])
                text = _remove_record_sentences(text)
            rule = tc.V2_RULE_TOOLS if mode == MODE else tc.V2_RULE_ROUTE
            k = text.find(tc.V2_RULES_HEAD)
            if k >= 0:      # the rules block: its bullet list ends at the first line that is not a bullet
                lines = text[k:].split("\n")
                j = 1
                while j < len(lines) and (lines[j].startswith("- ") or lines[j].startswith("  ")):
                    j += 1
                lines.insert(j, wrap(rule, "- ", "  "))
                text = text[:k] + "\n".join(lines)
            else:
                text = text.rstrip("\n") + "\n\n" + wrap(rule) + "\n\n"
        elif head == "## Robot Interface":
            h3 = _h3_split(text)
            tools = tool_section_v2(m, task, mode)
            new = [h3[0][1].strip("\n")] if h3[0][1].strip() else []
            if mode == SHELL:
                new.append(tools.rstrip("\n"))
            for h, body in h3[1:]:
                if h == "### Client":
                    if mode == SHELL:
                        new.append(h + body.rstrip("\n"))
                    else:
                        new.append(tools.rstrip("\n"))
                    continue
                if h == "### Actions" and mode == MODE and m.get("notes"):
                    continue
                if h == "### Actions" and mode == MODE:
                    h = "### Native rows (`execute_trajectory` space `native`)"
                if mode == MODE:
                    body = _v2_phrases(body)
                new.append(h + body.rstrip("\n"))
            if not any(x.startswith("### Tools") for x in new):
                new.insert(0, tools.rstrip("\n"))
            text = "\n" + "\n\n".join(new) + "\n\n"
        elif head == "## Limits" and mode == MODE:     # the task's own lines (normalize renders the rest)
            text = text.replace('`spec()["budget"]["reset"]`', "`reset_episode()`")
            text = _v2_phrases(text)
        elif head in ("## Others",) and mode == MODE:
            text = _v2_phrases(text)
            text = _remove_record_sentences(text)
        out.append((head + "\n" if head else "") + text.lstrip("\n") if head else text)
    r = "".join(x if x.endswith("\n") else x + "\n" for x in out)
    return _rewrap_long(re.sub(r"\n{3,}", "\n\n", r))


# -------------------------------------------------------------------------------------------------------- other files
def transform_toml(s: str, mode: str = MODE) -> str:
    label = "MCP TOOLS ONLY" if mode == MODE else "MCP TOOLS AND SHELL"
    s = re.sub(r'(?m)^(description = ")STANDARD MODE \(', r"\1STANDARD MODE, " + label + " (", s, count=1)
    s = re.sub(r'(?m)^(keywords = \[)(.*)\]$', lambda mm: mm.group(1) + mm.group(2) +
               (', "mcp"' if '"mcp"' not in mm.group(2) else "") + "]", s, count=1)
    if "[[environment.mcp_servers]]" not in s:
        s = s.rstrip() + "\n" + (MCP_TOML if mode == MODE else MCP_TOML.replace(
            "Robot control through the efe-robot MCP server only (mode standard-mcp;",
            "The efe-robot MCP server (mode standard-mcp-shell: its tools, their Python client and a shell;"))
    tomllib.loads(s)
    return s


GAME_COPY_RE = re.compile(r"^COPY\s.*\s/usr/local/bin/game\s*$")


def transform_dockerfile(s: str, mode: str = MODE) -> str:
    """`COPY efe_mcp /opt/tools/efe_mcp` after the task's last /opt/tools line; then the robot client copied to
    CLIENT_DIR instead of /opt/tools (the server's, not the agent's), and a match's `game` command left out
    (MCP-only); the shell variant keeps both and gets its Python client at /opt/tools/efe_robot.py."""
    if "efe_mcp" in s:
        return s
    lines = s.rstrip("\n").split("\n")
    at = max((i for i, ln in enumerate(lines) if "/opt/tools/" in ln and ln.lstrip().startswith(("COPY", "/"))),
             default=None)
    if at is None:
        at = next((i for i, ln in enumerate(lines) if ln.startswith("WORKDIR")), len(lines)) - 1
    while at + 1 < len(lines) and lines[at].rstrip().endswith("\\"):
        at += 1
    lines.insert(at + 1, "COPY efe_mcp /opt/tools/efe_mcp")
    if mode == SHELL:
        lines.insert(at + 2, "COPY efe_mcp/efe_robot.py /opt/tools/efe_robot.py")
        return "\n".join(lines) + "\n"
    out = []
    for ln in lines:
        if ln.lstrip().startswith("COPY") and re.search(r"/rcb_client\.py\s", ln) and ln.rstrip().endswith(" /opt/tools/"):
            ln = ln.rstrip()[: -len("/opt/tools/")] + CLIENT_DIR + "/"
        elif GAME_COPY_RE.match(ln.strip()):
            continue
        elif "/usr/local/bin/game" in ln and ln.lstrip().startswith("RUN"):
            ln = re.sub(r"chmod \+x /usr/local/bin/game && ", "", ln)
            assert "/usr/local/bin/game" not in ln, ln
        out.append(ln)
    return "\n".join(out) + "\n"


SOLVE = """#!/bin/bash
# Oracle (standard-mcp): the standard twin's oracle, unchanged (solve_standard.sh), with its robot client replaced by
# one that sends every call through the efe-robot MCP server as tool calls (solution/mcp/rcb_client_mcp.py:
# describe_robot, observe, execute_trajectory space native, wait, reset_episode); sitecustomize.py puts it in place of
# rcb_client in every Python process this script starts. The client's wire format (rcb1.py, which some oracles import
# to build their requests) is in the server's directory /opt/efe_mcp_client.
set -e
export EFE_MCP_ORACLE=1
export PYTHONPATH="/solution/mcp${PYTHONPATH:+:$PYTHONPATH}:/opt/efe_mcp_client"
bash /solution/solve_standard.sh "$@"
"""


def convert_solution(dst: pathlib.Path) -> bool:
    sol = dst / "solution"
    solve = sol / "solve.sh"
    if not solve.is_file():
        return False
    solve.rename(sol / "solve_standard.sh")
    (sol / "mcp").mkdir(exist_ok=True)
    for f in ORACLE_FILES:
        shutil.copy2(HERE / f, sol / "mcp" / pathlib.Path(f).name)
    solve.write_text(SOLVE)
    solve.chmod(0o755)
    return True


def install_server(dst: pathlib.Path, m: dict, mode: str = MODE) -> None:
    d = dst / "environment" / "efe_mcp"
    if d.exists():
        shutil.rmtree(d)
    (d / "schema").mkdir(parents=True)
    for f in SERVER_FILES + tuple(x for x in SUITE_FILES if (HERE / x).is_file() and m.get("kind", "rcb") != "rcb"):
        shutil.copy2(HERE / f, d / f)
    (d / "manifest.json").write_text(json.dumps(m, indent=1, ensure_ascii=False) + "\n")
    if mode == SHELL:            # the same tools as Python functions (/opt/tools/efe_robot.py)
        import client_gen
        for f in SHELL_FILES:
            shutil.copy2(HERE / f, d / f)
        (d / "efe_robot.py").write_text(client_gen.generate(m))


def generate(base: str, dry: bool = False, mode: str = MODE) -> dict:
    src = tc.task_dir(base + "-standard")
    if not (src / "task.toml").is_file():
        raise SystemExit(f"{base}: no standard task dir")
    dst = src.with_name(base + "-" + mode)
    m = task_manifest(src)
    if mode == SHELL:             # what the tools cannot deliver, the shell can
        m.pop("unsupported", None)
    if m.get("unsupported"):
        if dst.exists() and not dry:     # a variant generated before the manifest said otherwise
            shutil.rmtree(dst)
        return {"task": dst.name, "suite": src.parent.name, "unsupported": m["unsupported"]}
    info = {"task": dst.name, "suite": src.parent.name, "tools": [t["name"] for t in sch.tools_for(m)]}
    if dry:
        return info
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (dst / "DIGEST").unlink(missing_ok=True)
    install_server(dst, m, mode)
    df = dst / "environment" / "Dockerfile"
    df.write_text(transform_dockerfile(df.read_text(), mode))
    tt = dst / "task.toml"
    tt.write_text(transform_toml(tt.read_text(), mode))
    ins = dst / "instruction.md"
    if tc.is_v2(ins.read_text()):
        if m.get("kind", "rcb") != "rcb":
            import suites
            ins.write_text(suites.transform_instruction_v2(ins.read_text(), m, dst, mode))
        else:
            ins.write_text(transform_instruction_v2(ins.read_text(), m, dst, mode))
    elif m.get("kind", "rcb") != "rcb" and mode == MODE:
        import suites
        ins.write_text(suites.transform_instruction(ins.read_text(), m, dst))
    else:
        ins.write_text(transform_instruction(ins.read_text(), m, dst, mode))
    # the standard oracle runs unchanged in the shell variant (the service's client is there); MCP-only: through the tools
    info["oracle"] = convert_solution(dst) if mode == MODE else (dst / "solution" / "solve.sh").is_file()
    rd = dst / "README.md"
    if rd.is_file():   # the twin's README rows and sections are kept; normalize re-renders the header
        rd.write_text(rd.read_text().replace(src.name, dst.name))
    tc.normalize(dst)
    if mode == MODE:   # MCP-only: no shell to run the standard text's programs with
        info["leftover_gen_py"] = "gen.py" in ins.read_text()
    return info


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--core", action="store_true", help="every core task (docs/core_set.toml)")
    ap.add_argument("--suite", action="append", default=[], help="only these suites (tasks/ folder names)")
    ap.add_argument("--task", action="append", default=[], help="these bases")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--mode", choices=MODES, default=MODE)
    a = ap.parse_args(argv)
    bases = list(a.task)
    if a.core:
        bases += core_bases()
    if a.suite:
        bases = [b for b in bases if tc.task_dir(b + "-standard").parent.name in a.suite]
    done, skipped = [], []
    for b in dict.fromkeys(bases):
        suite = tc.task_dir(b + "-standard").parent.name
        if suite_manifest(suite) is None:
            skipped.append((b, suite))
            continue
        info = generate(b, a.dry_run, a.mode)
        if info.get("unsupported"):
            skipped.append((b, f"{suite}: {info['task']} has no MCP-only variant"))
            print(json.dumps(info))
            continue
        done.append(info)
        print(json.dumps(info))
    nm = sorted({s for _, s in skipped if ":" not in s})
    un = [s for _, s in skipped if ":" in s]
    print(f"generated {len(done)}; no manifest for {len(skipped) - len(un)} ({', '.join(nm)}); "
          f"no MCP-only variant for {len(un)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
