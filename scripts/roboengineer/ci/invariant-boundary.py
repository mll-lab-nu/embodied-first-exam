#!/usr/bin/env python3
"""roboEngineer's public/private boundary (PROTOCOL H.2, H.3), a benchmark hook of the required CI job `invariants`.

The agent's container gets only the public nominal tooling, environment/public/ (copied to /app by
environment/Dockerfile); the private evaluator (hidden plant, case banks, scoring, reference searches) lives in
environment/sim/ (the `sim` sidecar) and tests/. For every roboengineer-* task among the arguments this check renders
the task again from its generator into a scratch directory and requires that
  1. environment/public/ holds exactly the files, with exactly the bytes, the generator's public copy writes (the
     generators copy an explicit allowlist of public modules: nothing private becomes public by being added beside them);
  2. environment/Dockerfile is the generator's (it copies public/ and the pinned nominal requirements only);
  3. no file under environment/public/ is a trusted / native evaluator module, an instance, or a solution file;
  4. environment/sim/instance.json and tests/instance.json are one frozen instance (byte-identical).
Standard library only (the generators need no simulator). Usage: invariant-boundary.py [task dirs...]
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from scripts.control_transfer.packaging import LANDING_NAME, PREFIX, spec_name_of  # noqa: E402


def files(folder: Path) -> dict[str, bytes]:
    return {p.relative_to(folder).as_posix(): p.read_bytes()
            for p in sorted(folder.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}


def render(task: Path, out: Path) -> None:
    if task.name.startswith(PREFIX + LANDING_NAME + "-"):
        from scripts.quadrotor_landing.gen_tasks import render as landing
        landing(out, int(task.name.removesuffix("-standard").rsplit("-i", 1)[1]))
    else:
        from scripts.control_transfer.gen_tasks import render as transfer
        name, index = spec_name_of(task.name)
        transfer(out, name, index)


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
    previous = os.umask(0o022)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            fresh = Path(tmp) / task.name
            render(task, fresh)
            want, have = files(fresh / "environment/public"), files(public) if public.is_dir() else {}
            for rel in sorted(set(want) | set(have)):
                if want.get(rel) != have.get(rel):
                    errors.append(f"environment/public/{rel}: not the generator's public copy "
                                  f"({'extra' if rel not in want else 'missing' if rel not in have else 'differs'})")
            if (fresh / "environment/Dockerfile").read_bytes() != (task / "environment/Dockerfile").read_bytes():
                errors.append("environment/Dockerfile: not the generator's (the agent's image copies public/ only)")
    except Exception as e:   # any failure to render is a finding with a FAIL line, never a bare traceback
        errors.append(f"cannot render the task again: {e!r}")
    finally:
        os.umask(previous)
    return errors


def main(argv: list[str]) -> int:
    dirs = [Path(a) for a in argv] or sorted((ROOT / "tasks").iterdir())
    tasks = [d for d in dirs if d.name.startswith(PREFIX) and (d / "task.toml").is_file()]
    bad = 0
    for t in tasks:
        for e in check(t):
            print(f"FAIL {t.name}: {e} (PROTOCOL H.2/H.3)")
            bad = 1
    if not bad:
        print(f"ok roboEngineer boundary: {len(tasks)} task(s); the agent's copy is the generators' public allowlist")
    return bad


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
