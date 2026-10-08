#!/usr/bin/env python3
"""Freeze the sim_to_real instances and record the reference solutions, inside the base image:

    docker run --rm -v $PWD:/repo -w /repo ghcr.io/mll-lab-nu/eai-sim_to_real:$(cat images/sim_to_real/VERSION) \
        python scripts/sim_to_real/make_instances.py [family ...]

Per family: draws the instance from its seed (rcb_yam.make_instance), stores its initial-state hash in
instances/<family>.json, runs oracles/oracle_yam.py on it (oracles/<family>/oracle_targets.npy) and replays the targets
in two fresh processes, which must agree on the final state hash and score success.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEEDS = {"cube_stack_three": 1101, "handover_to_bin": 2202}
ENV = {**os.environ, "PYTHONPATH": f"{HERE}/shared:{HERE}/oracles", "RCB_SESSION_LOG": "", "RCB_AGENT_TRACE_DIR": ""}
REPLAY = (
    "import json, sys, numpy as np, rcb_yam as ry; s = ry.Session(sys.argv[1]); "
    "r = s.replay(np.load(sys.argv[2])); print(json.dumps({k: r[k] for k in ('success', 'state_sha', 'steps')}))"
)


def py(*args) -> str:
    return (
        subprocess.run([sys.executable, *args], env=ENV, check=True, capture_output=True, text=True)
        .stdout.strip()
        .splitlines()[-1]
    )


def main(families) -> None:
    for fam in families:
        path = HERE / "instances" / f"{fam}.json"
        inst = json.loads(
            py("-c", f"import json, rcb_yam as ry; print(json.dumps(ry.make_instance({fam!r}, {SEEDS[fam]})))")
        )
        path.write_text(json.dumps(inst, indent=1) + "\n")
        sha = json.loads(py(str(HERE / "shared" / "rcb_yam.py"), str(path)))["state_sha"]
        inst["state_sha"] = sha
        path.write_text(json.dumps(inst, indent=1) + "\n")
        out = HERE / "oracles" / fam / "oracle_targets.npy"
        out.parent.mkdir(parents=True, exist_ok=True)
        print(fam, py(str(HERE / "oracles" / "oracle_yam.py"), str(path), str(out)))
        reps = [json.loads(py("-c", REPLAY, str(path), str(out))) for _ in range(2)]
        assert reps[0] == reps[1] and reps[0]["success"], reps
        print(fam, "instance", sha, "fresh replays", reps[0])


if __name__ == "__main__":
    main(sys.argv[1:] or list(SEEDS))
