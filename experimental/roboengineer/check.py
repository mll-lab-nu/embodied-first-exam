#!/usr/bin/env python3
"""Explicit experimental package checks; never reports main-protocol compliance."""

import json
from pathlib import Path
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.control_transfer.check_proposal import check  # noqa: E402


def main():
    commands = [
        [sys.executable, "-m", "scripts.control_transfer.gen_tasks", "check"],
        [sys.executable, "-m", "scripts.quadrotor_landing.gen_tasks", "check"],
        [sys.executable, "-m", "unittest", "discover", "-s", "experimental/roboengineer/tests", "-v"],
    ]
    for command in commands:
        subprocess.run(command, cwd=ROOT, check=True)
    tasks = sorted((Path(__file__).parent / "tasks").glob("*-standard"))
    expected = json.loads((Path(__file__).parent / "migration.json").read_text())["tasks"]
    if {t.name for t in tasks} != {r["id"] for r in expected}:
        raise SystemExit("Experimental package inventory differs from migration.json")
    for task in tasks:
        meta = tomllib.loads((task / "task.toml").read_text())["metadata"]
        if meta.get("experimental") is not True or meta.get("proposal") != "roboengineer-policy-adaptation":
            raise SystemExit(f"Missing experimental marker: {task.name}")
        errors = check(task)
        if errors:
            raise SystemExit(f"{task.name}: {errors}")
    subprocess.run([sys.executable, str(ROOT / "ci_checks/check-seeds.py"), *map(str, tasks)], check=True)
    print(f"{len(tasks)} experimental policy packages checked; NOT accepted eai-standard protocol tasks")


if __name__ == "__main__":
    main()
