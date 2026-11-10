#!/usr/bin/env python3
"""INVARIANT hook (docs/protocol/README.md Appendix H.8: a task runs the files it was frozen against), this benchmark's own:
ci_checks/run_invariants.sh runs every ci_checks/benchmarks/*/invariant-* hook with the task directories in scope.

A RoboARC topological task's runtime_binding.json (environment/, environment/sim/, tests/) pins the sha256 of the tooling
its container loads: `tooling_sha256` (rcb_topogym.py), `render_bridge_sha256` (render_bridge.py) and
`nyx_direct_sha256` (nyx_direct.py). The simulator refuses a session whose loaded file differs (BindingMismatch), so a
byte change to one of these files, a comment included, makes every such task unrunnable. For each binding, the files the
Dockerfile of the same directory takes from the files-only image (scripts/files_image.py copied_from), or a copy in that
directory, must hash to the pinned values; a directory that loads none of them (a standard verifier) is not checked.
Standard library only.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import files_image  # noqa: E402

PREFIX = "roboarc-"
KEYS = {"tooling_sha256": "rcb_topogym.py", "render_bridge_sha256": "render_bridge.py", "nyx_direct_sha256": "nyx_direct.py"}
DIRS = ("environment", "environment/sim", "tests")


def problems(task: Path) -> list[str]:
    out = []
    for sub in DIRS:
        lock_path = task / sub / "runtime_binding.json"
        if not lock_path.is_file():
            continue
        lock = json.loads(lock_path.read_text())
        wanted = {k: v for k, v in KEYS.items() if lock.get(k) is not None}
        if not wanted:
            continue
        copied, bad = files_image.copied_from(task / sub / "Dockerfile")
        out += bad
        by_name = {}
        for dest, src in copied.items():
            by_name.setdefault(Path(dest).name, src)
        for key, name in wanted.items():
            src = by_name.get(name)
            if src is None:
                local = task / sub / name
                src = local if local.is_file() else None
            if src is None:          # this container loads no such file (a standard verifier only transcribes)
                continue
            got = hashlib.sha256(src.read_bytes()).hexdigest()
            if got != lock[key]:
                out.append(f"{lock_path}: {key} = {lock[key][:16]}..., but the {name} {sub}/Dockerfile copies "
                           f"({src.relative_to(ROOT)}) hashes to {got[:16]}...: the simulator refuses this session")
    return out


def main(argv: list[str]) -> int:
    tasks = [Path(a) for a in argv if Path(a).name.startswith(PREFIX) and Path(a).is_dir()]
    bad = [p for t in tasks for p in problems(t.resolve())]
    for p in bad:
        print(f"FAIL {p}")
    if bad:
        return 1
    print(f"INVARIANT-PASS hook:ci_checks/benchmarks/roboarc/invariant-runtime-binding.py ({len(tasks)} roboarc task(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
