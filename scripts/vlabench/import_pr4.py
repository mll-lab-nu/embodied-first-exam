"""One-off import of the frozen instances and recorded expert controls from PR #4 (commit ad3c5109 on its branch
dev/changhe; the PR was closed without merging and GitHub keeps the commit as refs/pull/4/head).

PR #4 froze each VLABench task's episode configuration (instance.json: VLABench's episode config, seed, and the hashes
of the compiled model and of the initial state) and recorded VLABench's own expert (`get_expert_skill_sequence`, run
in an image that still had it) as control steps (solution/oracle.npz). This copies, for every candidate in
tasks.json, the instance byte for byte and the oracle's `actions` array into frozen/<task>/; freeze.py then
re-verifies both in the current image. Reads through git, so the source is exactly the commit:

    git fetch origin refs/pull/4/head    # PR #4 (closed without merging) keeps the commit
    python3 scripts/vlabench/import_pr4.py [--ref ad3c5109]
"""

import argparse
import io
import json
import subprocess
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def show(ref: str, path: str) -> bytes:
    return subprocess.run(["git", "show", f"{ref}:{path}"], check=True, capture_output=True, cwd=HERE).stdout


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--ref", default="ad3c5109ca6716d33521714faf5d65209a6efd85")
    a = p.parse_args()
    tasks = json.loads((HERE / "tasks.json").read_text())["candidates"]
    for task in tasks:
        src = f"unlimited_tasks/vlabench/vlabench-{task.replace('_', '-')}-unlimited60min-v3-i00"
        out = HERE / "frozen" / task
        out.mkdir(parents=True, exist_ok=True)
        (out / "instance.json").write_bytes(show(a.ref, f"{src}/environment/instance.json"))
        actions = np.load(io.BytesIO(show(a.ref, f"{src}/solution/oracle.npz")))["actions"]
        np.save(out / "oracle.npy", np.asarray(actions, dtype=np.float64))
        print(task, len(actions))


if __name__ == "__main__":
    main()
