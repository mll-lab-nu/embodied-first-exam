#!/usr/bin/env python3
"""Assemble independently owned task folders into the frozen catalog."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "shared"))
from checker import Checker
from essential import MODULES


def content():
    tasks = []
    for family in MODULES:
        folder = HERE / "task_library" / family
        value = json.loads((folder / "task.json").read_text())
        if value["id"] != family or not (folder / "scene.py").is_file():
            raise ValueError(f"Invalid task folder: {folder}")
        tasks.append(value)
    found = [task["id"] for task in tasks]
    if len(found) != len(set(found)) or set(found) != set(MODULES):
        raise ValueError(f"Expected registered task families {list(MODULES)}; found {found}")
    for task in tasks:
        Checker(task)
        task["parameters"]["locked_wrist"] = True
        task["parameters"].setdefault("finger_velocity_gain", -0.9)
    tasks.sort(key=lambda task: list(MODULES).index(task["id"]))
    return json.dumps({"schema_version": 1, "tasks": tasks}, indent=2) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    destination = HERE / "essential_catalog.json"
    expected = content()
    if args.check:
        if not destination.exists() or destination.read_text() != expected:
            print("Essential catalog differs from its six authoring specifications")
            return 1
        print(f"Essential catalog: {len(MODULES)} specifications match")
    else:
        destination.write_text(expected)
        print(f"Wrote {len(MODULES)} essential dexterity specifications")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
