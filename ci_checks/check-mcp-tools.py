#!/usr/bin/env python3
"""The robot's MCP tools (docs/protocol/eai-standard.md "MCP tools"): every standard and realtime task offers its
robot service through its client (HTTP) and through the `efe-robot` MCP server, and every agent-facing endpoint has a
tool.

  1. Every agent-facing endpoint the protocol layers and the service adapters serve is in the endpoint table
     (embodied_first_exam/standard/mcp/inject.py ENDPOINTS) with its tool, or with the reason it has none (GET /status:
     its fields come back in every result; GET /operations/<id>: the server re-queries it). A route found in a layer
     or adapter source and missing from the table fails: a served endpoint without a tool. Each table tool exists in
     schema/tools.json, and the schema's own `endpoints` map is the table's.
     The match extension likewise: every endpoint its layer serves (embodied-olympics-match/eai_std/serve.py STD_GET,
     STD_POST; NOT_OFFERED are its 404s) is in inject.EO_ENDPOINTS with its tool (inject.EO_TOOLS, EO_TEAM_TOOLS) or the
     reason it has none (inject.EO_NO_TOOL), and the endpoints the layer's /spec lists (adapter.py ENDPOINTS) too.
  2. Per task: a standard or realtime task has environment/efe_mcp/manifest.json (what inject.manifest gives, the
     directory's only file), the Dockerfile lines (inject.docker_lines: the server files from the pinned files-only
     image standard-files at /opt/tools/efe_mcp/, which scripts/files_image.py resolves to their one source in
     embodied_first_exam/standard/mcp/, then `COPY efe_mcp /opt/tools/efe_mcp`), the task.toml entry and `### MCP tools`
     in Robot Interface; a task inject.EXCEPTIONS names (RoboEngineer, the matchlow matches, an exported match without the
     match extension) has none of them. A manifest's tools: spec, observe, submit and finish, reset where the task
     declares a reset budget, kinematics where its service serves it; a match (kind eo-match): spec, observe, submit
     and the extension's calls, no finish, and its service is the extension's (environment/sim/eai_std/).

    python3 ci_checks/check-mcp-tools.py [task dirs]      # default: every task
Standard library only.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import task_conventions as tc  # noqa: E402
import files_image  # noqa: E402  (the server's files come from the files-only image standard-files)

I = tc.efe_mcp_inject
MCP = ROOT / "embodied_first_exam/standard/mcp"
# endpoints some sources serve that are not the agent's: (path, the source file's name, why)
NOT_AGENT_FACING = {
    ("/health", "rcb_scorer.py"): "RoboPaint's scorer sidecar, for the verifier",
    ("/score", "rcb_scorer.py"): "RoboPaint's scorer sidecar, for the verifier",
}
ROUTE_CMP = re.compile(r'\b(?:self\.path|path|route|ep|endpoint)\s*(?:==|!=|in|not in)\s*\(?\s*((?:"/[a-z_]+/?"\s*,?\s*)+)')
ROUTE_PREFIX = re.compile(r'\b(?:self\.path|path|route)\.startswith\(\s*"(/[a-z_]+/)"')
ROUTE_DICT = re.compile(r'"(/[a-z_]+)"\s*:\s*self\._')


def sources() -> list[Path]:
    pats = ["embodied_first_exam/standard/*.py", "embodied_first_exam/standard/**/*.py",
            "embodied_first_exam/benchmarks/**/sim/*.py", "embodied_first_exam/benchmarks/**/standard/*.py",
            "images/*/tools/**/*.py"]
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", *pats], capture_output=True, text=True,
                         check=True).stdout.split()
    found = [ROOT / f for f in out if "/mcp/" not in f and "privileged" not in f and "test" not in Path(f).name]
    if not found:                # no checkout to read: the route scan would pass on nothing
        raise SystemExit("FAIL check-mcp-tools: git ls-files found no service sources to scan")
    return found


def served_routes() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for f in sources():
        for ln in (tc.read_text(f) or "").splitlines():
            rs = [r for g in ROUTE_CMP.findall(ln) for r in re.findall(r'"(/[a-z_]+/?)"', g)]
            rs += ROUTE_PREFIX.findall(ln) + ROUTE_DICT.findall(ln)
            for r in rs:
                found.setdefault(r, set()).add(f.relative_to(ROOT).as_posix())
    return found


def table_paths() -> dict[str, str]:
    """route as sources spell it ("/spec", "/operations/") -> the ENDPOINTS key"""
    out = {}
    for k in I.ENDPOINTS:
        p = k.split(" ", 1)[1]
        out[p.split("<")[0] if "<" in p else p] = k
    return out


def check_table() -> list[str]:
    errs = []
    paths = table_paths()
    for r, files in sorted(served_routes().items()):
        if r in paths:
            continue
        if all((r, Path(f).name) in NOT_AGENT_FACING for f in files):
            continue
        errs.append(f"{r}: served ({', '.join(sorted(files)[:3])}) but not in the endpoint table "
                    "(embodied_first_exam/standard/mcp/inject.py ENDPOINTS): an endpoint without a tool")
    schema = json.loads((MCP / "schema/tools.json").read_text())
    names = {t["name"] for t in schema["tools"]}
    want = {k: v for k, v in I.ENDPOINTS.items() if v}
    if schema.get("endpoints") != want:
        errs.append(f"schema/tools.json endpoints {schema.get('endpoints')} != inject.ENDPOINTS' tools {want}")
    for k, v in I.ENDPOINTS.items():
        if v is None and k not in I.NO_TOOL:
            errs.append(f"{k}: no tool and no reason (inject.NO_TOOL)")
        if v is not None and v not in names:
            errs.append(f"{k}: its tool {v!r} is not in schema/tools.json")
    return errs


EAI_STD = ROOT / "embodied_first_exam/benchmarks/embodied-olympics-match/eai_std"


def _literal(path: Path, name: str):
    """A module-level literal assignment of a source file, read without importing it."""
    import ast
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise KeyError(f"{path.name}: no {name}")


def check_match_table() -> list[str]:
    """Rule 1 for the match extension (Part 5)."""
    if not EAI_STD.is_dir():
        return []
    errs = []
    try:
        served = {f"GET /{e}" for e in _literal(EAI_STD / "serve.py", "STD_GET")}
        served |= {f"POST /{e}" for e in _literal(EAI_STD / "serve.py", "STD_POST")}
        served |= set(_literal(EAI_STD / "adapter.py", "ENDPOINTS"))
    except (OSError, KeyError, ValueError, SyntaxError) as e:
        return [f"the match extension's endpoints could not be read: {e}"]
    paths = {k.split(" ", 1)[1] for k in I.EO_ENDPOINTS}
    for ep in sorted(served):
        if ep not in I.EO_ENDPOINTS and ep.split(" ", 1)[1] not in paths:
            errs.append(f"{ep}: served by the match extension (eai_std/) but not in inject.EO_ENDPOINTS: an endpoint "
                        "without a tool")
    tools = set(I.EO_TOOLS) | set(I.EO_TEAM_TOOLS)
    for k, v in I.EO_ENDPOINTS.items():
        if v is None and k not in I.EO_NO_TOOL:
            errs.append(f"{k}: a match endpoint with no tool and no reason (inject.EO_NO_TOOL)")
        if v is not None and v not in tools:
            errs.append(f"{k}: its tool {v!r} is not a match tool (inject.EO_TOOLS, EO_TEAM_TOOLS)")
    return errs


def check_task(task: Path) -> list[str]:
    errs = []
    m = tc.efe_mcp_manifest(task)
    d = task / I.DIR
    df = tc.read_text(task / "environment/Dockerfile") or ""
    toml = tc.read_text(task / "task.toml") or ""
    ins = tc.read_text(task / "instruction.md") or ""
    if m is None:
        why = I.exception(tc.bench_dir(task), task.name, str(tc.metadata_of(task).get("protocol") or ""), task)
        if tc.mode_of(task) in ("standard", "realtime") and not why:
            errs.append(f"{task.name}: a standard or realtime task with no MCP tools and no exception (inject.EXCEPTIONS)")
        if d.exists() or I.DOCKER_LINE in df or "/opt/tools/efe_mcp/" in df or I.TOML_MARK in toml or I.SECTION in ins:
            errs.append(f"{task.name}: has MCP tool files or text but no MCP tools ({why or 'not a standard mode'})")
        return errs
    if not d.is_dir():
        return [f"{task.name}: no {I.DIR}/ (python3 scripts/task_conventions.py {task})"]
    got, problems = files_image.copied_from(task / "environment/Dockerfile")
    errs += [f"{task.name}: {p}" for p in problems]
    for f in I.files_for(m):
        src = got.get(I.DEST + f)
        if src is None or src.resolve() != (MCP / f).resolve():
            errs.append(f"{task.name}: environment/Dockerfile does not take {I.DEST}{f} from the pinned standard-files "
                        f"image (embodied_first_exam/standard/mcp/{f}; python3 scripts/task_conventions.py {task})")
    try:
        have = json.loads((d / "manifest.json").read_text())
    except (OSError, ValueError):
        have = None
    if have != m:
        errs.append(f"{task.name}: {I.DIR}/manifest.json is not what inject.manifest gives")
    extra = sorted(p.relative_to(d).as_posix() for p in d.rglob("*")
                   if p.is_file() and p.relative_to(d).as_posix() != "manifest.json")
    if extra:
        errs.append(f"{task.name}: {I.DIR}/ has files besides manifest.json (the server comes from standard-files): {extra}")
    want = I.docker_lines(m)
    have = [ln.strip() for ln in df.splitlines()]
    at = next((k for k in range(len(have)) if have[k:k + len(want)] == want), None)
    if at is None:
        errs.append(f"{task.name}: environment/Dockerfile lacks the MCP lines of inject.docker_lines (`{I.DOCKER_LINE}` "
                    "after the server's files from the pinned standard-files image)")
    try:
        servers = (tomllib.loads(toml).get("environment") or {}).get("mcp_servers") or []
    except ValueError:
        servers = []
    if not any(s.get("name") == "efe-robot" and s.get("args") == ["/opt/tools/efe_mcp/server.py"] for s in servers):
        errs.append(f"{task.name}: task.toml has no [[environment.mcp_servers]] efe-robot entry")
    ri = tc.section(ins, "Robot Interface")
    if ri is None or I.SECTION not in ri:
        errs.append(f"{task.name}: instruction.md has no `{I.SECTION}` in Robot Interface")
    t = m.get("tools") or []
    if m.get("kind") == "rcb":
        if t[:3] != ["spec", "observe", "submit"] or t[-1] != "finish":
            errs.append(f"{task.name}: tools {t}: spec, observe, submit, ..., finish expected")
        if ("reset" in t) != bool(tc.reset_budget_of(task)):
            errs.append(f"{task.name}: a reset tool {'without' if 'reset' in t else 'missing for'} a reset budget")
        if "status" in t or "operations" in t:
            errs.append(f"{task.name}: no status or operations tool (inject.NO_TOOL)")
    elif m.get("kind") == "eo-match":
        if t[:3] != ["spec", "observe", "submit"] or set(t) & {"finish", "reset", "kinematics", "act", "wait", "status"}:
            errs.append(f"{task.name}: tools {t}: a match has spec, observe, submit and its extension's calls "
                        "(start, ready; say, team), no finish")
        if not (task / "environment/sim/eai_std").is_dir():
            errs.append(f"{task.name}: a match's tools without the match extension (environment/sim/eai_std/): the "
                        "endpoints they call are not served")
    return errs


def main(argv: list[str]) -> int:
    dirs = [Path(a) for a in argv] or tc.iter_tasks()
    errs = check_table() + check_match_table()
    n = 0
    for task in dirs:
        if tc.mode_of(task) in ("standard", "realtime"):
            n += 1
        errs += check_task(task)
    if errs:
        print("FAIL MCP tools (docs/protocol/eai-standard.md \"MCP tools\": every standard and realtime task has them; "
              "every agent-facing endpoint has a tool):")
        for e in errs[:60]:
            print("  -", e)
        if len(errs) > 60:
            print(f"  ... {len(errs) - 60} more")
        return 1
    print(f"check-mcp-tools: the endpoint table covers every served route; {n} standard/realtime task(s) OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
