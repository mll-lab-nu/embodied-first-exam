#!/usr/bin/env python3
"""scripts/stamp_mtimes.py (issue #258: BuildKit reuses another build's same-name context file when size and mtime match).
Standard library only, no docker:

- the stamp is the evaluation pool's function exactly (reference values from the pool's stamp_mtimes.py);
- different content of equal size -> different mtimes; equal content -> one stable mtime in any directory; a second run
  changes nothing; a file rewritten after stamping is restamped (fast path), --full rehashes, --check counts;
- `stage` makes a stamped copy and leaves the source's mtimes alone; the task's DIGEST (paths and contents only) is the
  same for the copy, and still matches the committed DIGEST."""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import stamp_mtimes as sm  # noqa: E402
import task_conventions as tc  # noqa: E402

TOOL = [sys.executable, str(ROOT / "scripts/stamp_mtimes.py")]
TASK = tc.task_dir("robotwin_2_0_stack_blocks_two-privileged")
fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)
        print("FAIL", msg)


def mt(p) -> int:
    return os.stat(p).st_mtime_ns


def fake_task(d: Path, x: bytes) -> Path:
    (d / "tests").mkdir(parents=True)
    (d / "task.toml").write_text("[task]\n")
    (d / "tests/x.txt").write_bytes(x)
    (d / "tests/same.txt").write_bytes(b"shared\n")
    for p in d.rglob("*"):                        # git archive / tar: every file one mtime
        os.utime(p, ns=(1_760_522_400_000_000_000, 1_760_522_400_000_000_000))
    return d


def test_function():
    ref = {b"": 1477501576348643552, b"AAAA\n": 1147780229802288549, b"BBBB\n": 1024681898181870675,
           b"x" * 1000: 1144639656614804944}       # the pool's stamp_mtimes.py stamp_of, 2026-10-15
    for content, want in ref.items():
        got = sm.stamp_of(hashlib.sha256(content).digest())
        check(got == want, f"stamp_of({content[:8]!r}) = {got}, the pool's function gives {want}")
        check(sm.in_range(got), f"stamp of {content[:8]!r} outside the stamp range")
    check(not sm.in_range(1_760_522_400_000_000_000), "a 2025 mtime counts as stamped")


def test_stamp():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        a = fake_task(td / "tasks/a", b"AAAA\n")
        b = fake_task(td / "tasks/b", b"BBBB\n")
        check(mt(a / "tests/x.txt") == mt(b / "tests/x.txt"), "fixture: the two files should start with one mtime")
        r = subprocess.run(TOOL + ["--check", str(td / "tasks")], capture_output=True, text=True)
        check(r.returncode == 1 and "6 unstamped" in r.stdout, f"--check before stamping: {r.returncode} {r.stdout}")
        r = subprocess.run(TOOL + [str(td / "tasks")], capture_output=True, text=True)
        check(r.returncode == 0 and "6 files, 6 hashed, 6 restamped" in r.stdout, f"first stamp: {r.returncode} {r.stdout}")
        check(mt(a / "tests/x.txt") != mt(b / "tests/x.txt"), "equal size, different content: still one mtime")
        check(mt(a / "tests/same.txt") == mt(b / "tests/same.txt"), "equal content got two mtimes")
        check(mt(a / "tests/x.txt") == sm.stamp_of(hashlib.sha256(b"AAAA\n").digest()), "the mtime is not the content's stamp")
        r = subprocess.run(TOOL + ["--check", str(td / "tasks")], capture_output=True, text=True)
        check(r.returncode == 0 and "0 unstamped" in r.stdout, f"--check after stamping: {r.returncode} {r.stdout}")
        r = subprocess.run(TOOL + [str(td / "tasks")], capture_output=True, text=True)
        check("0 hashed, 0 restamped" in r.stdout, f"a second run should change nothing: {r.stdout}")
        (a / "tests/x.txt").write_bytes(b"CCCC\n")            # a new write: current mtime, outside the range
        r = subprocess.run(TOOL + [str(a)], capture_output=True, text=True)
        check("1 hashed, 1 restamped" in r.stdout and mt(a / "tests/x.txt") == sm.stamp_of(hashlib.sha256(b"CCCC\n").digest()),
              f"a rewritten file was not restamped: {r.stdout}")
        os.utime(a / "tests/same.txt", ns=(0, sm.stamp_of(hashlib.sha256(b"other").digest())))   # in range, wrong
        r = subprocess.run(TOOL + [str(a)], capture_output=True, text=True)
        check("0 restamped" in r.stdout, f"the fast path should skip an in-range mtime: {r.stdout}")
        r = subprocess.run(TOOL + ["--full", str(a)], capture_output=True, text=True)
        check("1 restamped" in r.stdout and mt(a / "tests/same.txt") == mt(b / "tests/same.txt"), f"--full did not rehash: {r.stdout}")
        (a / "jobs").mkdir(); (a / "jobs/r.txt").write_text("result\n")
        before = mt(a / "jobs/r.txt")
        subprocess.run(TOOL + ["--full", str(a)], capture_output=True)
        check(mt(a / "jobs/r.txt") == before, "a jobs/ directory was stamped")


def test_stage_and_digest():
    with tempfile.TemporaryDirectory() as td:
        before = {p: mt(p) for p in TASK.rglob("*") if p.is_file()}
        r = subprocess.run(TOOL + ["stage", str(TASK), td], capture_output=True, text=True)
        dst = Path(td) / TASK.name
        check(r.returncode == 0 and r.stdout.strip() == str(dst), f"stage: {r.returncode} {r.stdout} {r.stderr}")
        r = subprocess.run(TOOL + ["--check", str(dst)], capture_output=True, text=True)
        check(r.returncode == 0, f"the staged copy is not stamped: {r.stdout}")
        check({p: mt(p) for p in TASK.rglob("*") if p.is_file()} == before, "stage changed the source's mtimes")
        d_src, d_copy = tc.digest(TASK), tc.digest(dst)
        check(d_src == d_copy, f"DIGEST changed by stamping: {d_src} vs {d_copy}")
        check((TASK / "DIGEST").read_text().strip() == d_copy, "the stamped copy's digest is not the committed DIGEST")
        check(all(os.stat(dst / p.relative_to(TASK)).st_mode == os.stat(p).st_mode for p in before), "stage changed a mode")
        r = subprocess.run(TOOL + ["stage", str(TASK), td], capture_output=True, text=True)
        check(r.returncode != 0 and "exists" in r.stderr, f"stage over an existing copy was not refused: {r.returncode} {r.stderr}")
        r = subprocess.run(TOOL + ["stage", str(TASK / "tests"), td], capture_output=True, text=True)
        check(r.returncode != 0 and "not a task dir" in r.stderr, "stage of a non-task dir was not refused")
        shutil.rmtree(dst)


if __name__ == "__main__":
    test_function()
    test_stamp()
    test_stage_and_digest()
    if fails:
        print(f"{len(fails)} failure(s)")
        sys.exit(1)
    print("ok: stamp_mtimes = the pool's stamp; distinct content -> distinct mtimes, stable, fast path, --full, --check; "
          "stage leaves the source and DIGEST unchanged")
