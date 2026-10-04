#!/usr/bin/env python3
"""Reference trajectory of maniguard jar_transport/task_0002 (oracle side only: solution/, never in the agent's reach).

It is one of ManiGuard's public demonstrations of this task, time-resampled to the evaluator's rate:
episode 80 of the Hugging Face dataset IDEAS-Lab-Northwestern/datagen-jar-v1-joint-5cam (LeRobot v2.1, 30 Hz, revision
080dddb4f51ab060e9127e322c06e8ba4147d83c; (c) IDEAS Lab, Northwestern University, CC BY-NC 4.0,
https://creativecommons.org/licenses/by-nc/4.0/). The trajectory derived from it is under the same licence.

    uv run --no-project --with pyarrow --with numpy python oracle_gen.py --out oracle_trajectory.npz [--parquet episode_000080.parquet]

Resampling: the demo's `actions_commanded` (the joint targets its data generator sent at 30 Hz, gripper +1 open / -1
closed) are read at the midpoint of each 20 Hz control step, (k + 0.5) / 20 s (zero-order hold, as a controller sees
them), giving 545 rows; 40 copies of the last row follow (the goal must hold for 10 control steps). Result: (585, 8)
float32 rows for env.step, which this task's verifier scores 1 (strict goal held at step 514, no safety rule broken).
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import urllib.request

import numpy as np

TASK = "jar_transport/task_0002"
REPO = "IDEAS-Lab-Northwestern/datagen-jar-v1-joint-5cam"
REVISION = "080dddb4f51ab060e9127e322c06e8ba4147d83c"
EPISODE = 80
PATH = f"data/chunk-000/episode_{EPISODE:06d}.parquet"
SHA256 = "09032db9f6ee3e0acbaa05bcb05f50f512091125df01d72aca830ada4e88ba78"
HZ_IN, HZ_OUT, HOLD = 30.0, 20.0, 40


def resample(cmd: np.ndarray) -> np.ndarray:
    n = len(cmd); m = int(math.floor(n / HZ_IN * HZ_OUT))
    out = np.zeros((m, 8), np.float32)
    for k in range(m):
        i = min(n - 1, int(math.floor((k + 0.5) / HZ_OUT * HZ_IN + 1e-9)))
        out[k, :7] = cmd[i, :7]
        out[k, 7] = 1.0 if cmd[i, 7] > 0 else -1.0
    return np.concatenate([out, np.repeat(out[-1:], HOLD, axis=0)])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--parquet", help="a local copy of the episode (default: download it from the pinned revision)")
    a = ap.parse_args()
    if a.parquet:
        raw = open(a.parquet, "rb").read()
    else:
        raw = urllib.request.urlopen(f"https://huggingface.co/datasets/{REPO}/resolve/{REVISION}/{PATH}", timeout=60).read()
    if hashlib.sha256(raw).hexdigest() != SHA256:
        raise SystemExit("the episode's sha256 does not match the pinned one")
    import pyarrow.parquet as pq
    cols = pq.read_table(io.BytesIO(raw)).to_pydict()
    assert set(cols["episode_index"]) == {EPISODE}
    acts = resample(np.array(cols["actions_commanded"], np.float32))
    meta = {"source": f"hf://datasets/{REPO}@{REVISION}/{PATH}", "license": "CC BY-NC 4.0", "column": "actions_commanded",
            "resampling": "30 Hz -> 20 Hz, zero-order hold read at each control step's midpoint", "hold": HOLD,
            "frames_in": len(cols["actions_commanded"])}
    np.savez(a.out, actions=acts, task=TASK, control_hz=20, meta=json.dumps(meta))
    print(json.dumps({"out": a.out, "rows": int(len(acts)), **meta}))


if __name__ == "__main__":
    main()
