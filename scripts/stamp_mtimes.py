#!/usr/bin/env python3
"""Give every file of a task a mtime derived from its content, before any image is built from it (issue #258).

    python3 scripts/stamp_mtimes.py [--full] [--check] <tasks dir | task dir> ...   # stamp in place
    python3 scripts/stamp_mtimes.py stage <task dir> <out dir>                      # -> <out dir>/<task>, a stamped copy

Why: Docker's BuildKit keeps one synced copy of a local build context per context directory NAME and client (Harbor's
contexts are always `environment/` and `tests/`), and re-sends a file only when its relative path, size, mode or mtime
(to the nanosecond) changed. Two tasks whose same-path files have equal size and equal mtime (git checkout, git archive,
tar, cp -r and sed loops leave many files with one mtime) can therefore build one task's image with the OTHER task's
file, silently, `--no-cache` or not, `docker build` and `docker compose build` alike. A file whose mtime is a function of
its content cannot be taken for another: two files with different content never share a mtime (a 59-bit space), and
identical content keeps one stable mtime wherever it is, so cache reuse, rsync's size+mtime quick check and `cp -a`
copies stay correct. Content, modes and DIGESTs are not touched (DIGEST hashes paths and contents only); git ignores
mtimes (its index refreshes once).

The mtime: sha256(content) -> seconds from its first 29 bits in 2001-09 .. 2018-07 (1e9 .. 1e9 + 2**29), nanoseconds
from the next 30 bits mod 1e9 (the same function as the evaluation pool's own stamp_mtimes.py). No
checkout, sed or cp writes a mtime in that range, so a file already in it is taken as stamped (fast path) unless
--full; every write of new content sets a current-time mtime, outside the range. --check only counts the files whose
mtime is not their stamp (exit 1 if any). `stage` copies one task dir (symlinks kept, as `cp -a`) into a new directory
and stamps the copy with --full: what every repo path that builds a task image runs from (docs/protocol/running.md). Directories
named .git and jobs are skipped. Standard library only, Python 3.6+.
"""
import hashlib
import os
import shutil
import stat
import sys

LO, SPAN = 1_000_000_000, 1 << 29


def stamp_of(h: bytes) -> int:
    """content hash -> mtime in ns (seconds from the first 29 bits, nanoseconds from the next 30 mod 1e9)"""
    v = int.from_bytes(h[:8], "big")
    return (LO + (v >> 35)) * 1_000_000_000 + ((v >> 5) & ((1 << 30) - 1)) % 1_000_000_000


def in_range(ns: int) -> bool:
    return LO <= ns // 1_000_000_000 < LO + SPAN


def sha(p: str) -> bytes:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.digest()


def roots(arg: str):
    """one task dir, or a tree of them: a benchmark folder or a job copy (children with task.toml), or the repository's
    tasks/ (tasks/<benchmark>/<task>/: grandchildren)"""
    if os.path.isfile(os.path.join(arg, "task.toml")):
        yield arg
        return
    for n in sorted(os.listdir(arg)):
        d = os.path.join(arg, n)
        if os.path.isfile(os.path.join(d, "task.toml")):
            yield d
        elif os.path.isdir(d) and n not in (".git", "jobs"):
            for m in sorted(os.listdir(d)):
                if os.path.isfile(os.path.join(d, m, "task.toml")):
                    yield os.path.join(d, m)


def stamp_tree(t: str, full: bool = False, check: bool = False) -> dict:
    """Stamp (or --check) every regular file under the directory t, task dir or not. Counts: files, hashed, changed,
    bad (unstamped, with check), err; the first errors go to stderr."""
    c = dict(files=0, hashed=0, changed=0, bad=0, err=0)
    for dp, dns, fns in os.walk(t):
        dns[:] = [d for d in dns if d not in (".git", "jobs")]
        for fn in fns:
            p = os.path.join(dp, fn)
            try:
                st = os.lstat(p)
                if not stat.S_ISREG(st.st_mode):
                    continue
                c["files"] += 1
                if not full and not check and in_range(st.st_mtime_ns):
                    continue
                want = stamp_of(sha(p))
                c["hashed"] += 1
                if st.st_mtime_ns != want:
                    if check:
                        c["bad"] += 1
                        continue
                    os.utime(p, ns=(st.st_atime_ns, want), follow_symlinks=False)
                    c["changed"] += 1
            except OSError as e:
                c["err"] += 1
                if c["err"] <= 5:
                    print(f"stamp_mtimes: {p}: {e}", file=sys.stderr)
    return c


def stage(task: str, out: str) -> str:
    """<out>/<task name> = a copy of the task dir (symlinks kept, modes and mtimes copied), every file stamped; the copy's
    path. Refuses an existing destination and a source that is not a task dir."""
    task = os.path.abspath(task.rstrip("/"))
    if not os.path.isfile(os.path.join(task, "task.toml")):
        raise SystemExit(f"stamp_mtimes stage: {task} is not a task dir (no task.toml)")
    dst = os.path.join(os.path.abspath(out), os.path.basename(task))
    if os.path.lexists(dst):
        raise SystemExit(f"stamp_mtimes stage: {dst} exists: stage into a new directory")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copytree(task, dst, symlinks=True, ignore=shutil.ignore_patterns(".git", "jobs"))
    c = stamp_tree(dst, full=True)
    if c["err"]:
        raise SystemExit(f"stamp_mtimes stage: {c['err']} error(s) stamping {dst}")
    return dst


def main(argv) -> int:
    if argv[:1] == ["stage"]:
        if len(argv) != 3:
            print("usage: stamp_mtimes.py stage <task dir> <out dir>", file=sys.stderr)
            return 2
        print(stage(argv[1], argv[2]))
        return 0
    full = "--full" in argv
    check = "--check" in argv
    args = [a for a in argv if not a.startswith("--")]
    tot = dict(files=0, hashed=0, changed=0, bad=0, err=0)
    for a in args:
        if not os.path.isdir(a):
            continue
        for t in roots(a):
            for k, v in stamp_tree(t, full, check).items():
                tot[k] += v
    print(f"stamp_mtimes: {tot['files']} files, {tot['hashed']} hashed, {tot['changed']} restamped, {tot['bad']} unstamped, "
          f"{tot['err']} errors")
    return 1 if (tot["bad"] or tot["err"]) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
