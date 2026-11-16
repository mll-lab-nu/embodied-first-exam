#!/usr/bin/env python3
"""Privileged graders refuse a zip bomb in the agent's trajectory.npz before anything is unpacked (needs numpy).

np.load's NpzFile opens an entry named exactly `actions` (no `.npy`) before `actions.npy`, so a grader that bounds the
unpacked size of the expected names only lets a bomb under the bare name through. Each grader here must check the
unpacked size of every entry (from the zip directory) first; extra entries of normal size stay allowed (the tooling's
save_trajectory writes some). For each grader:

- a file with valid `task.npy` / `actions.npy` plus a ~300 MiB entry named `actions`, `task`, or an unrelated name, is
  refused, and the big entry is never opened;
- a normal trajectory, with the extra entries the tooling writes, is accepted."""
import contextlib
import glob
import importlib.util
import io
import os
import shutil
import sys
import tempfile
import types
import zipfile
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True   # the graders are imported from the source tree: leave no __pycache__ there
ROOT = Path(__file__).resolve().parents[2]
B = ROOT / "embodied_first_exam" / "benchmarks"
BOMB_BYTES = 300 << 20        # unpacked; above every bound below (RoboWits allows 256 MiB per entry)
OPENED_LIMIT = 64 << 20       # an entry this large opened for reading = the bomb was unpacked
fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


def load(name, path, stub=()):
    for s in stub:
        sys.modules.setdefault(s, types.ModuleType(s))
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@contextlib.contextmanager
def guard(opened):
    """Record (and refuse) every read of a zip entry larger than OPENED_LIMIT while a grader runs."""
    real = zipfile.ZipFile.open

    def guarded(self, name, mode="r", pwd=None, **kw):
        if mode == "r":
            info = name if isinstance(name, zipfile.ZipInfo) else self.getinfo(name)
            if info.file_size > OPENED_LIMIT:
                opened.append(info.filename)
                raise MemoryError(f"bomb entry {info.filename!r} opened")
        return real(self, name, mode, pwd, **kw)

    zipfile.ZipFile.open = guarded
    try:
        yield
    finally:
        zipfile.ZipFile.open = real


def bomb_member(path, name):
    """An archive holding one entry `name`: a valid .npy header and BOMB_BYTES of zeros, deflated to a few hundred KB."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z, z.open(name, "w", force_zip64=True) as f:
        np.lib.format.write_array_header_1_0(f, {"descr": "<f8", "fortran_order": False, "shape": (BOMB_BYTES // 8,)})
        chunk = bytes(16 << 20)
        for _ in range(BOMB_BYTES // len(chunk)):
            f.write(chunk)


def npy(value) -> bytes:
    b = io.BytesIO()
    np.save(b, np.asarray(value), allow_pickle=False)
    return b.getvalue()


def make(path, members: dict, bomb: str | None = None, bombs: dict | None = None):
    """An .npz of the given {key: array} (as `<key>.npy`), plus the bomb entry copied from bombs[bomb]."""
    if bomb:
        shutil.copy(bombs[bomb], path)
    with zipfile.ZipFile(path, "a" if bomb else "w", zipfile.ZIP_DEFLATED) as z:
        for k, v in members.items():
            z.writestr(k + ".npy", npy(v))


def graders():
    """(label, normal members, bomb names, call(path) -> True when the file is accepted)."""
    out = []
    extra = {"instance_sha": "0" * 64, "meta": "{}"}     # what the tooling's save_trajectory adds besides task / actions

    m = load("dexjoco_grade", B / "dexjoco/privileged/tests/grade.py")

    def dexjoco(p):
        try:
            m.load_deliverable(p, 1000)
            return True
        except ValueError:
            return False
    out.append(("dexjoco", {"task": "t", "actions": np.zeros((10, 46), np.float32), **extra}, dexjoco))

    r = load("robopaint_grade", B / "robopaint/privileged/grade.py")

    def robopaint(p):
        try:
            r.load_deliverable(p, 1000, 7)
            return True
        except ValueError:
            return False
    out.append(("robopaint", {"task": "t", "actions": np.zeros((10, 7), np.float32), **extra}, robopaint))

    w = load("robowits_grade", B / "robowits/privileged/tests/grade.py")

    def robowits(p):
        try:
            w.load_trajectory(p)
            return True
        except Exception:  # noqa: BLE001 -- the grader books any exception here as bad_trajectory
            return False
    out.append(("robowits", {"task": "t", "actions": np.zeros((10, 7), np.float32), **extra}, robowits))

    robolab = sorted(glob.glob(str(ROOT / "tasks/robolab/*-privileged/tests/grade.py")))
    for label, path in (("maniguard", B / "maniguard/privileged/tests/grade.py"),
                        ("yamlab", B / "yamlab/privileged/tests/grade.py"),
                        ("robolab", Path(robolab[0])),
                        ("robodojo", B / "robodojo/privileged/tests/grade.py")):
        g = load(f"{label}_grade", path)

        def call(p, g=g):
            acts, bad = g.load_trajectory(p, "t", 7, 1000)
            return bad is None and acts is not None and acts.shape == (10, 7)
        out.append((label, {"task": "t", "actions": np.zeros((10, 7), np.float32), **extra}, call))

    i = load("ispatialgym_grade", B / "ispatialgym/privileged/tests/grade.py")

    def ispatialgym(p):
        try:
            return i.check_trajectory(p, 1000).shape == (10, 23)
        except Exception:  # noqa: BLE001 -- the grader books any exception here as bad_trajectory
            return False
    out.append(("ispatialgym", {"actions": np.zeros((10, 23), np.float32), "subtask": "s", **extra}, ispatialgym))

    mm = load("molmospaces_grade", B / "molmospaces/privileged/tests/grade.py")
    out.append(("molmospaces", {"family": "t", "actions": np.zeros((10, 7)), "layout": "l"},
                lambda p: not mm.too_large(mm.member_sizes(p), 7)))

    my = load("myosuite_grade", B / "myosuite/privileged/tests/grade.py")
    out.append(("myosuite", {"task": "t", "actions": np.zeros((10, 7)), **extra},
                lambda p: not my.too_large(dict((x.filename, x.file_size) for x in zipfile.ZipFile(p).infolist()), 1000, 7)))

    t = load("rcb_topogym_test", B / "roboarc/rcb_topogym.py")

    def topogym(p):
        try:
            return t.load_trajectory(p, "t", 7)[0].shape == (10, 7)
        except t.InvalidTrajectory:
            return False
    out.append(("roboarc", {"task": "t", "actions": np.zeros((10, 7), np.float32), **extra}, topogym))

    k = load("rcb_ikea_test", B / "roboarc/ikea/privileged/environment/rcb_ikea.py", stub=("mujoco",))

    def ikea(p):
        try:
            return k.load_trajectory(p, 8, None, 1000).shape == (10, 8)
        except k.InvalidTrajectory:
            return False
    # no `substeps.npy` here: the bomb under the bare name `substeps` is the case (both names at once are refused anyway)
    out.append(("roboarc-ikea", {"ctrl": np.zeros((10, 8)), "timestep": np.float64(0.002),
                                 "actuators": np.array(["a"] * 8)}, ikea))
    return out


def run(accepts, path):
    """(accepted, the big entries opened) for one file; an exception escaping the grader's loader is a refusal here
    (the guard's MemoryError is one: `opened` records it)."""
    opened = []
    with guard(opened), contextlib.redirect_stderr(io.StringIO()):
        try:
            ok = bool(accepts(path))
        except Exception:  # noqa: BLE001
            ok = False
    return ok, opened


def main():
    names = ("actions", "task", "substeps", "extra_entry")
    with tempfile.TemporaryDirectory() as td:
        bombs = {}
        for n in names:
            bombs[n] = os.path.join(td, f"bomb_{n}.zip")
            bomb_member(bombs[n], n)
        for label, members, accepts in graders():
            p = os.path.join(td, f"{label}.npz")
            make(p, members)
            ok, opened = run(accepts, p)
            check(ok and not opened, f"{label}: a normal trajectory was refused (opened {opened})")
            for n in names:
                p = os.path.join(td, f"{label}_{n}.npz")
                make(p, members, n, bombs)
                ok, opened = run(accepts, p)
                check(not ok, f"{label}: a zip bomb entry {n!r} was accepted")
                check(not opened, f"{label}: the zip bomb entry {n!r} was opened before it was refused")
                os.remove(p)
    if fails:
        print("\n".join(fails))
        print(f"{len(fails)} failure(s)")
        sys.exit(1)
    print("ok: 11 privileged graders refuse an oversized entry under any name (`actions`, `task`, `substeps`, another) "
          "before unpacking it, and accept a normal trajectory with extra entries")


if __name__ == "__main__":
    main()
