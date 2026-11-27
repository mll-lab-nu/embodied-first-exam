#!/usr/bin/env python3
"""Task-protocol conformance report (docs/protocol/README.md): the protocol version each mode may declare, the `oracle` fields,
no placeholder solve.sh, base images from the one registry, no results/ in the repository, no personal paths, internal
names or host /data/ paths. Prints
one summary line per rule with a count and a few examples; every rule fails the check. Names, modes and the other
task.toml fields are check-task-layout.py's; that test.sh clears /logs/verifier first is check-verifier-isolation.sh's.

Usage: check-protocol.py [task dirs...]   (default: every task under tasks/ plus repository-wide checks)
"""
import hashlib
import os
import re
import subprocess
import sys
import tomllib
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ("ghcr.io/mll-lab-nu/efe:", "ghcr.io/mll-lab-nu/efe-private:")   # efe:<name>-<version> (public), efe-private:<name>-<version> (BUILD_ONLY)
sys.path.insert(0, str(ROOT / "scripts"))
import task_conventions as tc  # noqa: E402  (the mode registry, PROTOCOL §3)
# the `protocol` values each mode may declare: standard 2.1 / 2.2 / 2.4 (2.4: the operations capability, issue #89),
# realtime 2.3 (the realtime capability, §3), privileged none
MODE_PROTOCOLS = {m: set(d["protocols"]) for m, d in tc.MODE_REGISTRY.items()}
# a benchmark's own exported tasks (ci_checks/benchmarks/<bench>/exported.toml): tc.own_protocols
own_protocols = tc.own_protocols


PERSONAL_PATH = re.compile(rb"/(home|Users)/[A-Za-z0-9_.-]+/")
# the maintainers' internal user names (in paths, logins) never reach a tracked file; the author's name (capitalised) may.
# Matched by the sha256 of each lower-case word of that length, so the check itself does not publish the names.
INTERNAL_NAME_SHA256 = {"788b431f94ca453b95744650bb8de5bba2bfb7fe7194d91289ddf4929080ee96"}
INTERNAL_NAME_WORD = re.compile(rb"(?<![a-z])[a-z]{7}(?![a-z])")


def has_internal_name(data: bytes) -> bool:
    return any(hashlib.sha256(m.group()).hexdigest() in INTERNAL_NAME_SHA256 for m in INTERNAL_NAME_WORD.finditer(data))


# an absolute /data/<dir>/ path is a host path, except the sim sidecar's own data directory inside its container
# (/data/<file>, and its subdirectories calls/, live_video/, operations/)
HOST_DATA_PATH = re.compile(rb"(?<![\w./~-])/data/(?!(?:calls|live_video|operations)/)[A-Za-z0-9_.-]+/")
TEXT_SUFFIXES = {".md", ".toml", ".py", ".sh", ".yaml", ".yml", ".json", ".jsonl", ".txt", ".TXT", ".cfg", ".xml", ".urdf", ".env",
                 ".lock", ".patch", ".in", ".example", ".c", ".svg", ".sha256", ".js", ".html", ".csv", ".ipynb",
                 ".cpp", ".h", ""}

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
    for f in [task / "environment/Dockerfile", task / "tests/Dockerfile",                    # and a sidecar built from its own dir
              task / "environment/sim/Dockerfile", task / "environment/scorer/Dockerfile"]:
        if f.is_file():
            refs += re.findall(r"^FROM\s+(\S+)", f.read_text(), re.M)
    for f in [task / "environment/docker-compose.yaml", task / "tests/docker-compose.yaml"]:
        if f.is_file():
            refs += re.findall(r"^\s*image:\s*(\S+)", f.read_text(), re.M)
    return refs


def check_task(task: Path) -> None:
    name = task.name
    meta = tomllib.loads((task / "task.toml").read_text()).get("metadata", {})
    # the mode is the directory's whole suffix (`-realtime` does not end in `-standard`)
    try:
        named = tc.mode_of(task)
    except ValueError:
        named = None
        warn("the directory name ends in no mode (" + " | ".join(tc.MODES) + ")", name)
    mode = named
    proto = meta.get("protocol")
    if proto is not None and proto in own_protocols(name, mode):
        pass                                   # PROTOCOL §3: the benchmark's own protocol
    elif mode in tc.MODES:
        allowed = MODE_PROTOCOLS[mode]
        if allowed and proto not in allowed:
            warn(f"{mode}-mode `protocol` not in {sorted(allowed)}", f"{name} ({proto})")
        if not allowed and proto is not None:
            warn(f"`protocol` set on a {mode} task", name)

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

    replays = meta.get("replays")              # PROTOCOL §4: up to N fresh replays, any success counts
    if replays is not None:
        test = task / "tests/test.sh"
        if mode != "privileged" or not isinstance(replays, int) or isinstance(replays, bool) or replays < 1:
            warn("`replays` must be an integer >= 1 on a privileged task (PROTOCOL §4)", f"{name} ({replays!r})")
        elif not test.is_file() or not re.search(rf"--repeat {replays}\b", test.read_text()):
            warn("`[metadata] replays` differs from tests/test.sh's `--repeat` (PROTOCOL §4)", f"{name} ({replays})")

    for ref in image_refs(task):
        if ref.startswith("ghcr.io/") and not ref.startswith(REGISTRY):
            warn("base image outside the registry (`ghcr.io/mll-lab-nu/efe:<name>-<version>` or `efe-private:<name>-<version>`, PROTOCOL §1)", f"{name}: {ref}")

    if (task / "results").exists():
        warn("results/ in a task directory (results are published on the results site, PROTOCOL §1)", name)


def check_repository() -> None:
    if (ROOT / "results").is_dir():
        warn("top-level results/ directory (results are published on the results site, PROTOCOL §1)", "results/")
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
        data = p.read_bytes()
        if PERSONAL_PATH.search(data):
            warn("personal absolute path (/home/<user>/ or /Users/<user>/)", f)
        if has_internal_name(data) or has_internal_name(str(f).encode()):
            warn("internal user name", f)
        if HOST_DATA_PATH.search(data):
            warn("host path under /data/ (inside a container only the sim sidecar's /data/ is used)", f)


def main() -> int:
    args = sys.argv[1:]
    tasks = [Path(a).resolve() for a in args] or tc.iter_tasks()
    for t in tasks:
        if (t / "task.toml").is_file():
            check_task(t)
    if not args:
        check_repository()
    if not hits:
        print(f"protocol v{tc.PROTOCOL_VERSION}: {len(tasks)} task(s) conform")
        return 0
    print(f"protocol v{tc.PROTOCOL_VERSION}: violations (docs/protocol/README.md):")
    for rule, where in sorted(hits.items(), key=lambda kv: -len(kv[1])):
        examples = ", ".join(where[:3]) + (", ..." if len(where) > 3 else "")
        print(f"  FAIL {len(where):4d}  {rule}: {examples}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
