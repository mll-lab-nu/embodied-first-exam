#!/usr/bin/env python3
"""roboEngineer's shared copies (PROTOCOL §1: copies of shared sources are byte-identical), an ADVISORY benchmark hook.

roboEngineer's tasks carry their evaluator and the public nominal tooling as copies in every task dir: the trusted and
native evaluator modules under environment/sim/scripts/ and the agent's public tooling under environment/public/. Every
copy of one file (the same path relative to the task dir) is byte-identical across the roboengineer-* tasks that carry
it; a change is rolled out to all of them at once. Per-task files are exempt: environment/public/task-spec.json.
ci_checks/run_all.sh runs it with the task dirs in scope; it checks the folder the first roboengineer-* task among them
is in (none among them: the repository's tasks/roboengineer/). Standard library only.
Usage: advisory-shared-copies.py [task dirs...]
"""
import collections
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PREFIX = "roboengineer-"
SHARED = ("environment/sim/scripts", "environment/public")
PER_TASK = {"environment/public/task-spec.json"}


def main(argv: list[str]) -> int:
    folder = ROOT / "tasks" / "roboengineer"
    for a in argv:
        p = Path(a.rstrip("/"))
        if p.name.startswith(PREFIX):
            folder = p.resolve().parent
            break
    seen: dict[str, dict[str, list[str]]] = collections.defaultdict(lambda: collections.defaultdict(list))
    for task in sorted(folder.iterdir()) if folder.is_dir() else []:
        if not task.name.startswith(PREFIX) or not (task / "task.toml").is_file():
            continue
        for sub in SHARED:
            base = task / sub
            for f in sorted(base.rglob("*")) if base.is_dir() else []:
                rel = f.relative_to(task).as_posix()
                if not f.is_file() or "__pycache__" in f.parts or rel in PER_TASK:
                    continue
                seen[rel][hashlib.sha256(f.read_bytes()).hexdigest()[:16]].append(task.name)
    bad = 0
    for rel, versions in sorted(seen.items()):
        if len(versions) > 1:
            bad += 1
            detail = "; ".join(f"{h}: {len(ts)} task(s), e.g. {ts[0]}" for h, ts in sorted(versions.items(), key=lambda kv: -len(kv[1])))
            print(f"FAIL roboengineer shared copy {rel}: {len(versions)} versions ({detail})")
    if bad:
        print(f"FAIL advisory-shared-copies: {bad} shared file(s) differ across the roboEngineer tasks")
        return 1
    print(f"ok roboengineer shared copies: {len(seen)} file(s), one version each")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
