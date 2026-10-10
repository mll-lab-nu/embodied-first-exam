#!/usr/bin/env bash
# tasks/dataset.toml (PROTOCOL §2.8): every task dir under tasks/ is listed and vice versa, and every listed digest is the
# digest of the task's files as they are now. A digest left over from before a change makes the published dataset and
# the repository disagree, so it fails here: refresh with `cd tasks && harbor add --scan .` (umask 022).
# The digest is recomputed the way Harbor does it (harbor.publisher.packager.Packager.compute_content_hash, Harbor
# 0.23.0), without needing Harbor: sha256 over "<relative path>\0<sha256 of the file>\n" of task.toml, instruction.md,
# README.md, trajectory.json and every file under environment/, tests/, solution/ and steps/, sorted by path, with
# Harbor's default ignores (__pycache__/, *.pyc, .DS_Store, *.swp, *.swo, *~).
# Usage: check-dataset-manifest.sh            (repo-level; run_all.sh calls it once)
root="$(cd "$(dirname "$0")/.." && pwd)"; python3 - "$root" <<'PY'
import fnmatch, hashlib, pathlib, sys, tomllib
root = pathlib.Path(sys.argv[1]); d = tomllib.load(open(root / "tasks" / "dataset.toml", "rb"))
name_of = lambda t: t["name"].split("/")[-1] if "/" in t.get("name", "") else pathlib.Path(t.get("path", t.get("name"))).name  # noqa: E731
listed = {name_of(t): t.get("digest") for t in d.get("tasks", [])}
present = {p.name for p in (root / "tasks").iterdir() if p.is_dir() and (p / "task.toml").exists()}
rc = 0
for x in sorted(present - set(listed)): print(f"FAIL tasks/{x}: not in tasks/dataset.toml"); rc = 1
for x in sorted(set(listed) - present): print(f"FAIL dataset.toml lists missing task {x}"); rc = 1
if len(d.get("tasks", [])) != len(listed): print("FAIL dataset.toml lists a task more than once"); rc = 1

IGNORE_NAMES = ("*.pyc", ".DS_Store", "*.swp", "*.swo", "*~")


def ignored(rel: pathlib.PurePosixPath) -> bool:
    return "__pycache__" in rel.parts[:-1] or any(fnmatch.fnmatchcase(rel.name, p) for p in IGNORE_NAMES)


def file_sha(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def digest(task: pathlib.Path) -> str:
    files = [task / n for n in ("task.toml", "instruction.md", "README.md", "trajectory.json") if (task / n).exists()]
    for sub in ("environment", "tests", "solution", "steps"):
        if (task / sub).exists():
            files += [p for p in (task / sub).rglob("*") if p.is_file()]
    rels = sorted({p.relative_to(task).as_posix() for p in files if not ignored(pathlib.PurePosixPath(p.relative_to(task).as_posix()))})
    outer = hashlib.sha256()
    for rel in rels:
        outer.update(f"{rel}\0{file_sha(task / rel)}\n".encode())
    return "sha256:" + outer.hexdigest()


stale = []
for x in sorted(present & set(listed)):
    task = root / "tasks" / x
    if (task / ".gitignore").exists():
        print(f"FAIL tasks/{x}: a task-level .gitignore changes what Harbor packages; this check does not read it"); rc = 1
        continue
    if digest(task) != listed[x]:
        stale.append(x)
if stale:
    rc = 1
    print(f"FAIL tasks/dataset.toml: {len(stale)} digest(s) are not the digest of the task's current files "
          "(refresh: cd tasks && harbor add --scan .):")
    for x in stale[:20]: print(f"  - {x}")
    if len(stale) > 20: print(f"  ... {len(stale) - 20} more")
sys.exit(rc)
PY
