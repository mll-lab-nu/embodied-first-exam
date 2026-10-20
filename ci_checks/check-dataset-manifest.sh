#!/usr/bin/env bash
# Task digests (PROTOCOL §2.8): every task carries the digest of its current files in `tasks/<benchmark>/<task>/DIGEST` (one line
# `sha256:<hex>`, written last by scripts/task_conventions.py `normalize`, so every generator and
# every normalize run refresh it). A digest left over from before a change makes the published dataset and
# the repository disagree, so it fails here: refresh with `python3 scripts/task_conventions.py tasks/<benchmark>/<task>` (umask 022).
# The release manifest tasks/dataset.toml is generated from the DIGEST files (scripts/dataset_manifest.py) and is not
# committed: pull requests that change different tasks share no file. This check fails when it is tracked again.
# The digest is recomputed the way Harbor does it (harbor.publisher.packager.Packager.compute_content_hash, Harbor
# 0.23.0), independently of scripts/task_conventions.py and without needing Harbor: sha256 over
# "<relative path>\0<sha256 of the file>\n" of task.toml, instruction.md, README.md, trajectory.json and every file
# under environment/, tests/, solution/ and steps/, sorted by path, with Harbor's default ignores (__pycache__/, *.pyc,
# .DS_Store, *.swp, *.swo, *~). DIGEST is not one of those files.
# Usage: check-dataset-manifest.sh [task dirs]   (default: every task; run_all.sh passes a pull request's scope)
root="$(cd "$(dirname "$0")/.." && pwd)"
if git -C "$root" ls-files --error-unmatch tasks/dataset.toml >/dev/null 2>&1; then
  echo "FAIL tasks/dataset.toml is tracked: it is generated for a release (scripts/dataset_manifest.py write), not committed (git rm --cached tasks/dataset.toml)"; exit 1
fi
# Every directory tasks/<benchmark>/<dir>/ that holds a tracked file is a task: it has its task.toml (a benchmark
# folder holds task dirs and its own pages, tasks/<benchmark>/*.md, which are files, not dirs). Every other check skips a directory without one, so a half-deleted task (36
# DIGEST-only dirs were left on main by a merge) would pass them all. Always over the whole of tasks/
# (git's index: cheap).
orphans=$(git -C "$root" ls-files -- tasks | python3 -c 'import sys
files = {l.rstrip("\n") for l in sys.stdin}
dirs = sorted({"/".join(f.split("/")[1:3]) for f in files if f.count("/") >= 3})
print("\n".join(d for d in dirs if f"tasks/{d}/task.toml" not in files))')
if [ -n "$orphans" ]; then
  echo "FAIL tasks/<benchmark>/<dir> without a task.toml (a task directory removed only in part: remove the rest, or restore task.toml):"
  sed 's#^#  tasks/#' <<< "$orphans" | head -50; exit 1
fi
python3 - "$root" "$@" <<'PY'
import fnmatch, hashlib, pathlib, re, sys
root = pathlib.Path(sys.argv[1])
given = [pathlib.Path(a) for a in sys.argv[2:]]
tasks = sorted({(p if p.is_absolute() else pathlib.Path.cwd() / p).resolve() for p in given if (p / "task.toml").is_file()}) \
    if given else sorted((p.parent for p in (root / "tasks").glob("*/*/task.toml")), key=lambda p: p.name)   # tasks/<benchmark>/<task>/
rc = 0

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


stale, missing = [], []
for task in tasks:
    x = task.name
    if (task / ".gitignore").exists():
        print(f"FAIL {task.parent.name}/{x}: a task-level .gitignore changes what Harbor packages; this check does not read it"); rc = 1
        continue
    f = task / "DIGEST"
    have = f.read_text() if f.is_file() else None
    if have is None or not re.fullmatch(r"sha256:[0-9a-f]{64}\n", have):
        missing.append(x)
    elif have.strip() != digest(task):
        stale.append(x)
for what, xs in (("no DIGEST file (or not one line `sha256:<hex>`)", missing),
                 ("a DIGEST that is not the digest of the task's current files", stale)):
    if xs:
        rc = 1
        print(f"FAIL {len(xs)} task(s) with {what} (refresh: python3 scripts/task_conventions.py tasks/<benchmark>/<task>, umask 022):")
        for x in xs[:20]: print(f"  - {x}")
        if len(xs) > 20: print(f"  ... {len(xs) - 20} more")
if rc == 0:
    print(f"ok task digests: {len(tasks)} task(s), each DIGEST is the digest of its current files")
sys.exit(rc)
PY
