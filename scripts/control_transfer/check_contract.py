"""Exact generated contract check, including public/private copy boundaries."""

import os
import tempfile
from pathlib import Path
from .gen_tasks import render, snapshot
from .packaging import spec_name_of


def check(task):
    task = Path(task)
    errors = []
    try:
        try:   # a task directory (roboengineer-<base>-iNN-standard), else a test's scratch name control-transfer-<spec>-iNN-standard
            name, index = spec_name_of(task.name)
        except ValueError:
            name, index = task.name.removeprefix("control-transfer-").removesuffix("-standard").rsplit("-i", 1)
        with tempfile.TemporaryDirectory() as folder:
            expected = Path(folder) / task.name
            previous_umask = os.umask(0o022)
            try:
                render(expected, name, int(index))
            finally:
                os.umask(previous_umask)
            want = snapshot(expected)
            actual = snapshot(task)
            for p in sorted(set(want) | set(actual)):
                if want.get(p) != actual.get(p):
                    errors.append("generated contract differs: " + p)
        if any(p.is_symlink() for p in task.rglob("*")):
            errors.append("symlink in task payload")
        if any(p.name == "__pycache__" for p in (task / "environment/public").rglob("*")):
            errors.append("cached executable in public payload")
    except (OSError, ValueError, KeyError):
        errors.append("invalid control-transfer task")
    return errors
