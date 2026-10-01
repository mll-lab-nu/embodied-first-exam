#!/usr/bin/env python3
"""Protocol v1.0 conformance report (docs/PROTOCOL.md). Warn-only during the migration (§7): prints one summary line per
rule with a count and a few examples and exits 0. Set RCB_PROTOCOL_STRICT=1 to exit 1 when any rule is violated.

Rules tagged "legacy" are the ones expected until the migration lands (old names, old registry); every other rule must
be clean for new tasks.

Usage: check-protocol-v1.py [task dirs...]   (default: every task under tasks/ plus repository-wide checks)
"""
import os
import re
import subprocess
import sys
import tomllib
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = "ghcr.io/embodied-agent-interface-v2-internal/eai-"
PROTOCOLS = {"eai-standard/2.1"}
LEGACY_PROTOCOLS = {"rcb-limited/2.1"}
EFFORTS = "none|minimal|low|medium|high|xhigh|max|default"
RUN_ID = re.compile(rf"^[a-z0-9_]+-[a-z0-9_]+-({EFFORTS})$")
MAX_RESULT_BYTES = 2_000_000
PERSONAL_PATH = re.compile(rb"/(home|Users)/[A-Za-z0-9_.-]+/")
TEXT_SUFFIXES = {".md", ".toml", ".py", ".sh", ".yaml", ".yml", ".json", ".jsonl", ".txt", ".cfg", ".xml", ".urdf", ""}
# `test.sh` must clear the verifier log directory before anything else (first non-comment command after `set`/`mkdir`).
CLEAR_LOGS = re.compile(r"^(rm\s+-[rRf]+\s+/logs/verifier/\*|find\s+/logs/verifier\s+-mindepth\s+1\b.*(-delete|-exec\s+rm))")

hits: dict[str, list[str]] = defaultdict(list)


def rel(p: Path) -> str:
    return os.path.relpath(p, ROOT)


def warn(rule: str, where: str) -> None:
    hits[rule].append(where)


def commands(path: Path) -> list[str]:
    """Non-empty, non-comment lines of a shell script."""
    return [ln.strip() for ln in path.read_text().splitlines() if ln.strip() and not ln.strip().startswith("#")]


def image_refs(task: Path) -> list[str]:
    refs = []
    for f in [task / "environment/Dockerfile", task / "tests/Dockerfile"]:
        if f.is_file():
            refs += re.findall(r"^FROM\s+(\S+)", f.read_text(), re.M)
    for f in [task / "environment/docker-compose.yaml", task / "tests/docker-compose.yaml"]:
        if f.is_file():
            refs += re.findall(r"^\s*image:\s*(\S+)", f.read_text(), re.M)
    return refs


def check_task(task: Path) -> None:
    name = task.name
    meta = tomllib.loads((task / "task.toml").read_text()).get("metadata", {})
    mode = meta.get("mode")
    if name.endswith("-limited") or mode == "limited":
        warn("legacy: mode name `limited` / `-limited` (use `standard` / `-standard`)", name)
    if mode is None:
        warn("legacy: missing `mode` (privileged | standard)", name)
    if "tier" in meta:
        warn("legacy: deprecated `tier` field (use `mode`)", name)
    standard = mode in ("standard", "limited") or name.endswith(("-limited", "-standard"))
    proto = meta.get("protocol")
    if standard and proto in LEGACY_PROTOCOLS:
        warn("legacy: protocol spelled `rcb-limited/2.1` (use `eai-standard/2.1`)", name)
    elif standard and proto not in PROTOCOLS:
        warn(f"standard-mode `protocol` not in {sorted(PROTOCOLS)}", f"{name} ({proto})")
    if not standard and proto is not None:
        warn("`protocol` set on a privileged task", name)

    oracle = meta.get("oracle")
    if oracle is None:
        warn("legacy: missing `oracle` (full | partial | none)", name)
    elif oracle not in ("full", "partial", "none"):
        warn("`oracle` must be full | partial | none", name)
    if oracle in ("partial", "none") and not meta.get("oracle_evidence"):
        warn("`oracle_evidence` missing for a non-full oracle", name)
    solve = task / "solution/solve.sh"
    if solve.is_file():
        cmds = commands(solve)
        if cmds and re.fullmatch(r"exit\s+1", cmds[-1]) and not any(re.search(r"\b(python|harbor|cp|bash)\b", c) for c in cmds):
            warn("`solve.sh` is an `exit 1` placeholder (declare `oracle = \"none\"` and remove it)", name)

    for ref in image_refs(task):
        if ref.startswith("ghcr.io/") and not ref.startswith(REGISTRY):
            warn("legacy: base image outside the EAI registry (`eai-<sim>`)", f"{name}: {ref}")

    test_sh = task / "tests/test.sh"
    if test_sh.is_file():
        cmds = [c for c in commands(test_sh) if not re.match(r"(set\s|mkdir\s+-p\s+/logs/verifier\s*$)", c)]
        if not cmds or not CLEAR_LOGS.match(cmds[0]):
            warn("`tests/test.sh` does not clear /logs/verifier first (`rm -rf /logs/verifier/*`)", name)

    results = task / "results"
    if results.is_dir():
        for run in sorted(p for p in results.iterdir() if p.is_dir()):
            if not RUN_ID.match(run.name):
                warn("results folder is not a run id `<harness>-<model>-<effort>`", f"{name}/results/{run.name}")
        for f in results.rglob("*"):
            if f.is_file() and f.stat().st_size > MAX_RESULT_BYTES:
                warn("result file over 2 MB (videos go to Hugging Face)", f"{rel(f)} ({f.stat().st_size / 1e6:.1f} MB)")


def check_repository() -> None:
    if (ROOT / "results").is_dir():
        warn("top-level results/ directory (results live in tasks/<task>/results/<run_id>/)", "results/")
    try:
        files = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True, check=True).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        files = [rel(p) for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts]
    for f in files:
        p = ROOT / f
        if f.startswith("third_party/") or not p.is_file() or p.suffix not in TEXT_SUFFIXES or p.stat().st_size > 5_000_000:
            continue
        if f.startswith("ci_checks/check-protocol-v1.py"):
            continue
        if PERSONAL_PATH.search(p.read_bytes()):
            warn("personal absolute path (/home/<user>/ or /Users/<user>/)", f)


def main() -> int:
    args = sys.argv[1:]
    tasks = [Path(a).resolve() for a in args] or sorted(p for p in (ROOT / "tasks").iterdir() if (p / "task.toml").is_file())
    for t in tasks:
        if (t / "task.toml").is_file():
            check_task(t)
    if not args:
        check_repository()
    if not hits:
        print(f"protocol v1.0: {len(tasks)} task(s) conform")
        return 0
    strict = os.environ.get("RCB_PROTOCOL_STRICT") == "1"
    print(f"protocol v1.0 {'violations' if strict else 'warnings (migration pending, docs/PROTOCOL.md §7)'}:")
    for rule, where in sorted(hits.items(), key=lambda kv: (not kv[0].startswith("legacy"), -len(kv[1]))):
        examples = ", ".join(where[:3]) + (", ..." if len(where) > 3 else "")
        print(f"  WARN {len(where):4d}  {rule}: {examples}")
    return 1 if strict else 0


if __name__ == "__main__":
    sys.exit(main())
