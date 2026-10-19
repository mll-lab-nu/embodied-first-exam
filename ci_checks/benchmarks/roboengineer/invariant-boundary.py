#!/usr/bin/env python3
"""roboEngineer's public/private boundary (PROTOCOL H.2, H.3), a benchmark hook of the required CI job `invariants`.

The agent's container gets only the public nominal tooling, environment/public/ (copied to /app by
environment/Dockerfile); the private evaluator (hidden plant, case banks, scoring, reference searches) lives in
environment/sim/ (the `sim` sidecar) and tests/. For every roboengineer-* task among the arguments (default: every task
dir) this check requires that
  1. the task has no symbolic link;
  2. no file under environment/public/ is a trusted / native evaluator module, an instance, or a solution file;
  3. environment/Dockerfile copies from the build context only public/ and requirements files (the rest of the agent's
     image comes from the pinned base and files-only images);
  4. environment/sim/instance.json and tests/instance.json are one frozen instance (byte-identical).
Standard library only. Usage: invariant-boundary.py [task dirs...]
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import task_conventions as tc  # noqa: E402  (iter_tasks: the task tree)

PREFIX = "roboengineer-"


def files(folder: Path) -> dict[str, bytes]:
    return {p.relative_to(folder).as_posix(): p.read_bytes()
            for p in sorted(folder.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}


def check(task: Path) -> list[str]:
    errors = []
    public = task / "environment/public"
    if any(p.is_symlink() for p in task.rglob("*")):
        errors.append("a symbolic link in the task")
    for rel in files(public) if public.is_dir() else {}:
        parts = Path(rel).parts
        if {"trusted", "native"} & set(parts) or Path(rel).name in ("instance.json", "solve.sh") \
                or "reference" in Path(rel).name:
            errors.append(f"environment/public/{rel}: an evaluator, instance or reference file in the agent's copy")
    a, b = task / "environment/sim/instance.json", task / "tests/instance.json"
    if not (a.is_file() and b.is_file() and a.read_bytes() == b.read_bytes()):
        errors.append("environment/sim/instance.json and tests/instance.json are not one frozen instance")
    df = task / "environment/Dockerfile"
    for src in re.findall(r"(?m)^COPY\s+(?!--from=)(?:--\S+\s+)*(\S+)\s", df.read_text() if df.is_file() else ""):
        if not (src.rstrip("/") == "public" or src.startswith("public/") or "requirements" in src):
            errors.append(f"environment/Dockerfile: copies {src} from the build context (only public/ and requirements)")
    return errors


def main(argv: list[str]) -> int:
    dirs = [Path(a) for a in argv] or tc.iter_tasks()
    tasks = [d for d in dirs if d.name.startswith(PREFIX) and (d / "task.toml").is_file()]
    bad = 0
    for t in tasks:
        for e in check(t):
            print(f"FAIL {t.name}: {e} (PROTOCOL H.2/H.3)")
            bad = 1
    if not bad:
        print(f"ok roboEngineer boundary: {len(tasks)} task(s); the agent's copy holds public tooling only")
    return bad


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
