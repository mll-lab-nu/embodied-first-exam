#!/usr/bin/env python3
"""Write (or check) the frozen instances in the simulator image:

    RFO_RW=1 scripts/roboolympics/dev.sh /rfo/make_instances.py [--only a,b]     # write
    scripts/roboolympics/dev.sh /rfo/make_instances.py --check                   # compare with the committed files

The committed instance of a family is its privileged task's environment/instance.json
(tasks/roboolympics-<family>-i00-privileged/; dev.sh mounts tasks/ at /tasks). Writing puts a new or remade one at
scripts/roboolympics/instances/<family>-i00.json, which gen_tasks.py reads instead while it exists: render the tasks,
then delete it there. --check compares with that file when it exists, else with the committed one.

An instance holds the family's parameters, the texts the tasks quote (the rules with their numbers filled in) and the
facts of t = 0 (state hash, action types, cameras, the robot's description)."""
import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "shared"))
from rcb_rfo import make_instance  # noqa: E402


def instance_path(fam: str) -> pathlib.Path:
    """The family's frozen instance: instances/<f>-i00.json while it exists (a new or remade one), else the committed
    privileged task's environment/instance.json (in the image: /tasks, which dev.sh mounts)."""
    new = HERE / "instances" / f"{fam}-i00.json"
    return new if new.is_file() else HERE.parents[1] / "tasks" / f"roboolympics-{fam}-i00-privileged/environment/instance.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    fams = json.loads((HERE / "families.json").read_text())["families"]
    only = [f for f in a.only.split(",") if f]
    bad = 0
    for fam, spec in fams.items():
        if only and fam not in only:
            continue
        text = json.dumps(make_instance(fam, spec.get("seed", 0)), indent=1) + "\n"
        path = instance_path(fam) if a.check else HERE / "instances" / f"{fam}-i00.json"
        if a.check:
            same = path.is_file() and path.read_text() == text
            bad += not same
            print(("ok   " if same else "DIFF ") + path.name)
        else:
            path.parent.mkdir(exist_ok=True)
            path.write_text(text)
            print("wrote", path.name)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
