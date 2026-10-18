#!/usr/bin/env python3
"""Write scripts/bigym2/instances/<family>-i00.json: the frozen instance of a task in tasks.json (seed 0), made in the
image the tasks run (docs/benchmarks/bigym2.md). Needs an NVIDIA GPU (EGL); from the repository root:

    docker run --rm --gpus all --network none -e NVIDIA_DRIVER_CAPABILITIES=all -v "$PWD:/w" \
        -w /w/scripts/bigym2 ghcr.io/mll-lab-nu/eai-bigym2:$(cat images/bigym2/VERSION) python make_instances.py --only <family>

The written file is a new family's instance: gen_tasks.py reads it while it exists; once the family's task dirs are
committed, delete it (tasks/bigym2-<family>-i00-privileged/environment/instance.json is the copy kept).
--check rebuilds every instance and compares it with the committed one (instances/<family>-i00.json when present, else the
task dir's; the state hash included); it writes nothing."""

import argparse, json, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE / "shared"))
from rcb_bigym2 import make_instance  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--only", nargs="*", help="families")
    a = ap.parse_args()
    tasks = json.loads((HERE / "tasks.json").read_text())["tasks"]
    bad = 0
    for fam, t in tasks.items():
        if a.only and fam not in a.only:
            continue
        inst = {"family": fam, "instance": "i00", **make_instance(t["upstream_task"], t["seed"], t.get("scene"))}
        path = HERE / "instances" / f"{fam}-i00.json"
        text = json.dumps(inst, indent=1) + "\n"
        if a.check:
            if not path.is_file():
                path = ROOT / "tasks" / f"bigym2-{fam}-i00-privileged" / "environment/instance.json"
            same = path.is_file() and path.read_text() == text
            bad += not same
            print(f"{'ok  ' if same else 'DIFF'} {fam}", flush=True)
        else:
            path.parent.mkdir(exist_ok=True)
            path.write_text(text)
            print(f"wrote {path.name} {inst['t0']['state_sha']}", flush=True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
