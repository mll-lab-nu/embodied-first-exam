"""Generate a Harbor task directory for one (family, instance).

    python -m rcb.new_task --family cube_stack --seed 7                 # new frozen instance
    python -m rcb.new_task --family cube_stack --seed 7 --instance x.npz  # reuse an existing instance file
    python -m rcb.new_task --family cube_stack --seed 7 --render        # only rewrite templates (keep instance)

Produces tasks/<simulator>-<family-with-dashes>-i<NN>/ with instruction.md, task.toml, README.md,
environment/{Dockerfile,instance.npz}, tests/{test.sh,instance.npz}, solution/solve.sh.
Instance files are the task identity: regenerating with the same seed gives a DIFFERENT instance
(robosuite's robot initialization noise is unseeded), so never regenerate a shipped task's instance.
"""
from __future__ import annotations
import argparse, hashlib, json, os, shutil, subprocess, sys
from pathlib import Path

from rcb.adapters.capx_robosuite import TASKS

ROOT = Path(__file__).resolve().parent.parent
CAPX = ROOT / "third_party" / "cap-x"
IMAGE_REGISTRY = os.environ.get("RCB_IMAGE_REGISTRY", "ghcr.io/jameskrw")
IMAGE_VERSION = (ROOT / "images" / "VERSION").read_text().strip() if (ROOT / "images" / "VERSION").exists() else "0.1.0"

INSTRUCTION = """# {title}

You control a simulated {robot} arm ({simulator} / MuJoCo) via Python. **Task:** {text}

This is a *fixed scene instance*: object poses never change between resets. You may reset and retry as many
times as you want. Your deliverable is **one replayable trajectory**, not a general policy.

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below).
It is replayed open-loop from the same initial state in a fresh process and scored 1 if the task is
completed at the end of the replay, else 0. Also leave the script that produced it at `/app/output/gen.py`.

## Tooling (already installed; run `python` from any directory)
```python
from rcb.traj import Session
s = Session("{family}", instance="/app/instance.npz")   # builds the env, starts the IK server if needed
s.reset()                          # back to the frozen initial state (unlimited)
p = s.primitives()                 # dict of callables, e.g. p["goto_pose"](pos, quat_wxyz, z_approach=0.1)
help(p["goto_pose"])               # every primitive has a docstring; read them
s.low                              # low-level cap-x env (robosuite env at s.low.robosuite_env) for closed-loop control
s.record_start(); ...; actions = s.record_stop()   # actions: (T, 9) joint targets + gripper, one row per sim step
s.status()                         # {{'success': bool, 'reward': float, 'sim_steps': int, ...}}
s.replay(actions)                  # resets, replays open-loop, returns status  -> use this to self-check
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
CLI equivalent of the grader:
`python -m rcb.traj replay --task {family} --instance /app/instance.npz --traj /app/output/trajectory.npz`

Optional rendering: `Session("{family}", instance=..., enable_render=True)` then `s.low.render()` returns an RGB
array (software rendering, slow). Coordinates are in the robot base frame; quaternions are WXYZ.
"""

TASK_TOML = """schema_version = "1.3"
artifacts = ["/app/output/"]

[task]
name = "robot-coding-bench/{slug}"
description = "{simulator} {family}: produce one replayable trajectory for frozen scene instance {seed:02d}."
authors = [{{ name = "{author}" }}]
keywords = ["robotics", "{simulator}", "{robot}", "code-as-policy", "trajectory", "{family}"]

[metadata]
author_name = "{author}"
task_type = "trajectory"          # trajectory | policy   (see docs/PROTOCOL.md)
simulator = "{simulator}"
robot = "{robot}"
family = "{family}"
tier = "privileged"               # privileged (state-based perception) | perception (RGB-D models)
instance_seed = {seed}
instance_sha256 = "{inst_sha}"    # sha256 of tests/instance.npz; CI checks it
image = "{image}"
expert_time_estimate_hours = 0.5

[verifier]
timeout_sec = 900.0

[agent]
timeout_sec = 3600.0

[environment]
build_timeout_sec = 1800.0
cpus = 4
memory_mb = 16384
"""

README = """# {slug}

| | |
|---|---|
| Simulator / robot | {simulator} / {robot} |
| Family / instance | `{family}` / seed {seed:02d} |
| Task type / tier | trajectory / privileged |
| Base image | `{image_ref}` |
| Agent budget | 3600 s |

## Difficulty
<!-- Why is this instance non-trivial for a coding agent? Which primitive interactions matter? -->

## Reference solution
cap-x's human-written oracle for `{family}` (`solution/solve.sh` records it into a trajectory).

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.npz` in a fresh process, twice;
pass iff the task predicate holds after every replay and the final-state hashes agree (`rcb.grade`).
"""

DOCKERFILE = """FROM {image_ref}
COPY instance.npz /app/instance.npz
RUN mkdir -p /app/output
WORKDIR /app
"""

TEST_SH = """#!/bin/bash
# Grader: replay the agent's trajectory from the frozen instance (tests/ copy) in a fresh process.
cd /opt/cap-x
python -m rcb.grade --family {family} --instance /tests/instance.npz --traj /app/output/trajectory.npz --repeat 2 \\
  2> /logs/verifier/grade.log
"""

SOLVE_SH = """#!/bin/bash
# Oracle: record cap-x's human-written reference code into a trajectory.
set -e
mkdir -p /app/output
cd /opt/cap-x
python -m rcb.traj run-oracle --task {family} --instance /app/instance.npz --out /app/output/trajectory.npz
cp /opt/rcb/rcb/traj.py /app/output/gen.py
"""


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def make_instance(family: str, seed: int, out: Path) -> None:
    cmd = ["uv", "run", "--no-sync", "python", "-m", "rcb.traj", "make-instance", "--task", family, "--seed", str(seed), "--out", str(out)]
    env = dict(os.environ, MUJOCO_GL="egl", PYTHONPATH=str(ROOT))
    subprocess.run(cmd, cwd=CAPX, env=env, check=True, stdout=subprocess.DEVNULL)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", required=True, choices=sorted(TASKS))
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--instance", help="reuse this instance.npz instead of generating one")
    ap.add_argument("--render", action="store_true", help="only rewrite template files; keep existing instance")
    ap.add_argument("--author", default=os.environ.get("RCB_AUTHOR", "unknown"))
    ap.add_argument("--out", default=str(ROOT / "tasks"))
    a = ap.parse_args()
    f = TASKS[a.family]
    slug = f"{f['simulator']}-{a.family.replace('_', '-')}-i{a.seed:02d}"
    d = Path(a.out) / slug
    for sub in ("environment", "tests", "solution"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    inst = d / "tests" / "instance.npz"
    if a.render:
        assert inst.exists(), "no existing instance to keep"
    elif a.instance:
        shutil.copy(a.instance, inst)
    else:
        make_instance(a.family, a.seed, inst)
    shutil.copy(inst, d / "environment" / "instance.npz")
    image_ref = f"{IMAGE_REGISTRY}/rcb-{f['image']}:{IMAGE_VERSION}"
    ctx = dict(slug=slug, family=a.family, seed=a.seed, author=a.author, simulator=f["simulator"], robot=f["robot"],
               image=f["image"], image_ref=image_ref, inst_sha=sha256(inst), text=f["text"],
               title=f"{a.family} — instance {a.seed:02d}")
    (d / "instruction.md").write_text(INSTRUCTION.format(**ctx))
    (d / "task.toml").write_text(TASK_TOML.format(**ctx))
    if not (d / "README.md").exists() or not a.render:
        (d / "README.md").write_text(README.format(**ctx))
    (d / "environment" / "Dockerfile").write_text(DOCKERFILE.format(**ctx))
    (d / "tests" / "test.sh").write_text(TEST_SH.format(**ctx)); os.chmod(d / "tests" / "test.sh", 0o755)
    (d / "solution" / "solve.sh").write_text(SOLVE_SH.format(**ctx)); os.chmod(d / "solution" / "solve.sh", 0o755)
    print(json.dumps({"task": str(d), "instance_sha256": ctx["inst_sha"], "image": image_ref}))


if __name__ == "__main__":
    main()
