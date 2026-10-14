#!/usr/bin/env python3
"""Task-protocol conformance report (docs/PROTOCOL.md): the protocol version each mode may declare, the `oracle` fields,
no placeholder solve.sh, base images from the one registry, no results/ in the repository, no personal paths. Prints
one summary line per rule with a count and a few examples; every rule fails the check. Names, modes and the other
task.toml fields are check-task-fields.sh's; that test.sh clears /logs/verifier first is check-verifier-isolation.sh's.

Usage: check-protocol.py [task dirs...]   (default: every task under tasks/ plus repository-wide checks)
"""
import os
import re
import subprocess
import sys
import tomllib
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = "ghcr.io/mll-lab-nu/eai-"
sys.path.insert(0, str(ROOT / "scripts"))
import task_conventions as tc  # noqa: E402  (the mode registry, PROTOCOL §2.16)
# the `protocol` values each mode may declare: standard 2.1 / 2.2 / 2.4 (2.4: the operations capability, issue #89),
# standard-realtime 2.3 (the realtime capability, §4b), privileged none
MODE_PROTOCOLS = {m: set(d["protocols"]) for m, d in tc.MODE_REGISTRY.items()}
PERSONAL_PATH = re.compile(rb"/(home|Users)/[A-Za-z0-9_.-]+/")
TEXT_SUFFIXES = {".md", ".toml", ".py", ".sh", ".yaml", ".yml", ".json", ".jsonl", ".txt", ".cfg", ".xml", ".urdf", ""}

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
    if mode is None:
        warn("missing `mode` (" + " | ".join(tc.MODES) + ")", name)
    # whole suffixes only (`-standard-realtime` does not end in `-standard`), and `mode` is compared exactly
    try:
        named = tc.mode_of(task)
    except ValueError:
        named = None
    if name.endswith("-realtime") and not name.endswith("-standard-realtime") or mode == "realtime":
        warn("mode name `realtime` / `-realtime` (the third mode is `standard-realtime`, PROTOCOL D12)", name)
    proto = meta.get("protocol")
    for m in {mode, named} & set(tc.MODES):
        allowed = MODE_PROTOCOLS[m]
        if allowed and proto not in allowed:
            warn(f"{m}-mode `protocol` not in {sorted(allowed)}", f"{name} ({proto})")
        if not allowed and proto is not None:
            warn(f"`protocol` set on a {m} task", name)

    oracle = meta.get("oracle")
    if oracle is None:
        warn("missing `oracle` (full | partial | none)", name)
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
            warn("base image outside the registry (`ghcr.io/mll-lab-nu/eai-<name>`, PROTOCOL §2.4)", f"{name}: {ref}")

    if (task / "results").exists():
        warn("results/ in a task directory (results are published on the results site, PROTOCOL D3)", name)


def check_repository() -> None:
    if (ROOT / "results").is_dir():
        warn("top-level results/ directory (results are published on the results site, PROTOCOL D3)", "results/")
    try:
        files = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True, text=True, check=True).stdout.split("\0")
    except (OSError, subprocess.CalledProcessError):
        files = [rel(p) for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts]
    for f in files:
        p = ROOT / f
        if f.startswith("third_party/") or not p.is_file() or p.suffix not in TEXT_SUFFIXES or p.stat().st_size > 5_000_000:
            continue
        if f == "ci_checks/check-protocol.py":
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
        print(f"protocol v1.2-rc: {len(tasks)} task(s) conform")
        return 0
    print("protocol v1.2-rc: violations (docs/PROTOCOL.md):")
    for rule, where in sorted(hits.items(), key=lambda kv: -len(kv[1])):
        examples = ", ".join(where[:3]) + (", ..." if len(where) > 3 else "")
        print(f"  FAIL {len(where):4d}  {rule}: {examples}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
