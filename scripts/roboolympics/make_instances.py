#!/usr/bin/env python3
"""Write (or check) the frozen instances, scripts/roboolympics/instances/<family>-i00.json, in the simulator image:

    RFO_RW=1 scripts/roboolympics/dev.sh /rfo/make_instances.py [--only a,b]     # write
    scripts/roboolympics/dev.sh /rfo/make_instances.py --check                   # compare with the committed files

An instance holds the family's parameters, the texts the tasks quote (the rules with their numbers filled in) and the
facts of t = 0 (state hash, action types, cameras, the robot's description)."""
import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "shared"))
from rcb_rfo import make_instance  # noqa: E402


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
        path = HERE / "instances" / f"{fam}-i00.json"
        if a.check:
            same = path.is_file() and path.read_text() == text
            bad += not same
            print(("ok   " if same else "DIFF ") + path.name)
        else:
            path.write_text(text)
            print("wrote", path.name)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
