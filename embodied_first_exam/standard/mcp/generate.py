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
SERVER_FILES = ("server.py", "rcb_adapter.py", "geom.py", "kin.py", "schema.py", "workspace.py", "schema/tools.v0.json")
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


def tool_section(m: dict, task: pathlib.Path) -> str:
    """`## Robot tools`: how the agent acts, generated from the task's manifest and the tool list it gets."""
    if m.get("kind", "rcb") != "rcb":
        import suites
        return suites.instruction_section(m)
    tools = {t["name"]: t for t in sch.tools_for(m)}
    parts = sch.part_lines(m)
    cams = ", ".join(f"`{c}`" for c in m.get("cameras") or []) or "see `describe_robot`"
    base_text = (m.get("frame") or {}).get("base_text", "")
    L = []
    L.append("## Robot tools (MCP server `efe-robot`)")
    L.append(wrap(
        "You act on the robot only through the tools of the MCP server `efe-robot` (in your tool list as "
        "`efe-robot` tools, for example `mcp__efe-robot__move_robot`). " + RULE + " The robot service and its rules "
        "are as described in this text; where it names calls of the Python client `rcb_client.py`, which is not "
        "installed for your code here, use the tool that does the same:"))
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
    b.append("Nothing needs to be saved: the server records every tool call, and the service records the episode.")
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


def transform_instruction(s: str, m: dict, task: pathlib.Path) -> str:
    lines = s.split("\n")
    if lines and lines[0].startswith("# "):
        t = lines[0]
        t = t.replace("-standard", "-standard-mcp") if task.name in t else t
        if "STANDARD MODE" in t:
            t = t.replace("STANDARD MODE", "STANDARD MODE, MCP TOOLS ONLY", 1)
        else:
            t += " — MCP tools only"
        lines[0] = t
    s = "\n".join(lines)
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
    sec = tool_section(m, task)
    s = (s[:k + 1] + sec + "\n" + s[k + 1:]) if k >= 0 else (s.rstrip() + "\n\n" + sec)
    return s


# -------------------------------------------------------------------------------------------------------- other files
def transform_toml(s: str) -> str:
    s = re.sub(r'(?m)^(description = ")STANDARD MODE \(', r"\1STANDARD MODE, MCP TOOLS ONLY (", s, count=1)
    s = re.sub(r'(?m)^(keywords = \[)(.*)\]$', lambda mm: mm.group(1) + mm.group(2) +
               (', "mcp"' if '"mcp"' not in mm.group(2) else "") + "]", s, count=1)
    if "[[environment.mcp_servers]]" not in s:
        s = s.rstrip() + "\n" + MCP_TOML
    tomllib.loads(s)
    return s


GAME_COPY_RE = re.compile(r"^COPY\s.*\s/usr/local/bin/game\s*$")


def transform_dockerfile(s: str) -> str:
    """`COPY efe_mcp /opt/tools/efe_mcp` after the task's last /opt/tools line; then the robot client copied to
    CLIENT_DIR instead of /opt/tools (the server's, not the agent's), and a match's `game` command left out."""
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


def install_server(dst: pathlib.Path, m: dict) -> None:
    d = dst / "environment" / "efe_mcp"
    if d.exists():
        shutil.rmtree(d)
    (d / "schema").mkdir(parents=True)
    for f in SERVER_FILES + tuple(x for x in SUITE_FILES if (HERE / x).is_file() and m.get("kind", "rcb") != "rcb"):
        shutil.copy2(HERE / f, d / f)
    (d / "manifest.json").write_text(json.dumps(m, indent=1, ensure_ascii=False) + "\n")


def generate(base: str, dry: bool = False) -> dict:
    src = tc.task_dir(base + "-standard")
    if not (src / "task.toml").is_file():
        raise SystemExit(f"{base}: no standard task dir")
    dst = src.with_name(base + "-" + MODE)
    m = task_manifest(src)
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
    install_server(dst, m)
    df = dst / "environment" / "Dockerfile"
    df.write_text(transform_dockerfile(df.read_text()))
    tt = dst / "task.toml"
    tt.write_text(transform_toml(tt.read_text()))
    ins = dst / "instruction.md"
    if m.get("kind", "rcb") != "rcb":
        import suites
        ins.write_text(suites.transform_instruction(ins.read_text(), m, dst))
    else:
        ins.write_text(transform_instruction(ins.read_text(), m, dst))
    info["oracle"] = convert_solution(dst)
    rd = dst / "README.md"
    if rd.is_file():   # the twin's README rows and sections are kept; normalize re-renders the header
        rd.write_text(rd.read_text().replace(src.name, dst.name))
    tc.normalize(dst)
    s = ins.read_text()
    info["leftover_gen_py"] = "gen.py" in s
    return info


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--core", action="store_true", help="every core task (docs/core_set.toml)")
    ap.add_argument("--suite", action="append", default=[], help="only these suites (tasks/ folder names)")
    ap.add_argument("--task", action="append", default=[], help="these bases")
    ap.add_argument("--dry-run", action="store_true")
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
        info = generate(b, a.dry_run)
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
