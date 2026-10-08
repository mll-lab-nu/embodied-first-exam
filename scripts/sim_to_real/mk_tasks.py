#!/usr/bin/env python3
"""Generate the sim_to_real tasks: tasks/sim_to_real-<family>-i00-privileged for every family below.

    python3 scripts/sim_to_real/mk_tasks.py            # (re)write the task directories
    python3 scripts/sim_to_real/mk_tasks.py --check    # exit 1 if tasks/ differs from what this would write

Standard library only (plus scripts/task_conventions.py, which every generator ends with). Inputs:
  scripts/sim_to_real/instances/<family>.json          the frozen instances (make_instances.py, in the image)
  scripts/sim_to_real/oracles/oracle_yam.py            the reference controller; oracles/<family>/oracle_targets.npy
  scripts/sim_to_real/shared/                          the tooling rcb_yam.py and the grader grade.py
The texts are the templates below. docs/benchmarks/sim_to_real.md describes the benchmark.
"""

from __future__ import annotations

import filecmp
import json
import shutil
import stat
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SHARED = HERE / "shared"
sys.path.insert(0, str(ROOT / "scripts"))
from task_conventions import normalize  # noqa: E402

IMAGE = "ghcr.io/mll-lab-nu/eai-sim_to_real:" + (ROOT / "images" / "sim_to_real" / "VERSION").read_text().strip()
AGENT_TIMEOUT = 3600

ROBOT_TEXT = """\
## The robot
An **I2RT YAM bimanual station**: two 6-joint YAM arms with `linear_4310` parallel grippers, mounted on the table top
0.61 m apart and both facing +x, a RealSense D405 on each wrist and a third D405 on the gantry above and behind them
(`top_cam`). This scene is the digital twin of the physical station the task will be reproduced on: the arm model is MuJoCo Menagerie's
`i2rt_yam/yam_linear_4310.xml` (derived from I2RT's SDK, with its PD gains and gravity compensation) and the cameras
sit at I2RT's CAD extrinsics. **The trajectory you hand in is meant to be replayed on the physical robot later**, so
it has to respect the real station's limits below.

World frame = the left arm's base frame: **+x forward, +y to the left, +z up, metres**; the table top is z = 0, the
right arm's base is at (0, -0.61, 0). Both arms start in their rest pose (all joints 0, folded) with the grippers open.

## Controls
One control step = 1/50 s (10 physics steps of 2 ms). Each step takes **14 position targets**, in this order
(`rcb_yam.ACTUATOR_NAMES`): `left/joint1..joint6`, `left/gripper`, `right/joint1..joint6`, `right/gripper`.
Joints in rad (limits `s.lower` / `s.upper`); the gripper is the finger rail travel in m: 0.0475 fully open, 0 closed,
down to -0.005 to squeeze a grasped object (the gap between the finger pads is 2 x travel).
- **Rate limit** (the speed limit the physical station runs with): each step moves every applied target at most
  3.0 rad/s x 0.02 s = 0.06 rad (joints) or 0.25 m/s x 0.02 s = 5 mm (grippers) towards your command. `s.step()`
  applies the limit and records the applied targets, so a recorded trajectory always respects it; the verifier
  rejects a trajectory in which two consecutive rows (or the first row and the start pose) differ by more.
- **The two arms must never touch each other** (any arm-to-arm contact during the trajectory fails it).
- The arms are position-controlled with gravity compensation (the PD gains of I2RT's SDK for this arm), so a joint does not land
  exactly on its target under load; check where the gripper actually is.
"""

TOOLING_TEXT = """\
## Tooling (`/opt/tools/rcb_yam.py`, importable as `rcb_yam`)
```python
import numpy as np, rcb_yam as ry
s = ry.Session("/app/instance.json")   # the frozen instance; s.model / s.data are MuJoCo objects
st = s.state()      # joints, applied targets, objects {name: {pos, quat_wxyz}}, sites (left/right grasp_site position)
                    #   and site_mats (their rotation: z = approach direction, y = finger slide axis), success fields
s.record_start()
r = s.step(targets) # (14,) targets for one control step -> the success fields (see Success)
A = s.record_stop(); s.save_trajectory(A)          # -> /app/output/trajectory.npz
s.replay(A)         # fresh replay from the start (what the verifier does)
s.reset()           # back to the start (as often as you like)
img = s.render("top_cam")                           # also left/wrist_cam, right/wrist_cam (D405s), front_view
```
Everything in `s.model` / `s.data` is readable (privileged mode), e.g. for inverse kinematics with `mujoco.mj_jacSite`
on the `left/grasp_site` / `right/grasp_site` sites (the point between the finger pads).
"""

RULES_TEXT = """\
## What you hand in
`/app/output/trajectory.npz` — the applied targets, shape `(T, 14)` (T ≤ 3000, i.e. at most 60 s), one row per
control step. Record it with the tooling so the layout and the rate limit are right. The verifier replays it from the
frozen start in a separate sandbox (MuJoCo on the CPU is bit-exact). Leave the script that produced it at
`/app/output/gen.py`. Save a trajectory early and improve it; only the last one counts.

## Rules
- Write your own controller; do not use trained policies from anywhere.
- Only the targets count: editing `s.data` while debugging changes nothing in the replay.
- You have 60 minutes of wall-clock time. Do not stop early: use the time to check your trajectory with `s.replay`.
"""

FAMILIES: dict[str, dict] = {
    "cube_stack_three": dict(
        title="Stack three cubes",
        scene=(
            "Three 4 cm wooden cubes (40 g) — **blue**, **green** and **red** — lie on the table in front of the "
            "left arm, each at its own position and yaw."
        ),
        goal=(
            "**Task:** build a tower: **green on top of blue, red on top of green**, with the blue cube where it is "
            "or anywhere else on the table."
        ),
        success=(
            "At the **end of the trajectory**: the blue cube rests on the table (its centre within 1 cm of "
            "z = 0.02), the green cube's centre is within 2 cm horizontally of the blue cube's and 4 cm (± 1 cm) "
            "above it, the red cube likewise on the green one; all three cubes are at rest (speed below 5 cm/s) "
            "and no part of either robot touches any cube. `s.check()` (also returned by `s.step`) computes "
            "exactly this: `blue_on_table`, `green_on_blue`, `red_on_green`, `at_rest`, "
            "`gripper_touches_object`, `arm_collision`, `success`."
        ),
        difficulty=(
            "Two precise pick-and-place moves with one 6-joint arm and no motion primitives: the agent writes "
            "its own inverse kinematics, finds grasps that are reachable (the YAM's top-down workspace is "
            "small: the gripper can point straight down only up to about 0.45 m from the base, and only near "
            "the table), grasps 4 cm cubes between 1.4 x 1.6 cm finger pads, and places each cube within 2 cm on "
            "the one below without knocking the tower over, under a real-robot rate limit. Medium: a "
            "scripted IK controller solves it in about 16 s of robot time."
        ),
        reference=(
            "`solution/oracle_yam.py` (`cube_stack_three`): damped-least-squares IK on the left arm's grasp "
            "site, top-down grasps aligned with each cube's faces, green then red placed 4 mm above their "
            "resting height and released; 785 control steps (15.7 s)."
        ),
        hours=1.5,
    ),
    "handover_to_bin": dict(
        title="Hand the block over and drop it in the bin",
        scene=(
            "An orange **block** (4 x 4 x 10 cm, 80 g) stands upright on the table at the left arm's outer side, "
            "beyond the right arm's reach. An open grey **bin** (16 x 16 cm inside, walls 6 cm high, 1 cm thick) "
            "is fixed to the table at the right arm's outer side, beyond the left arm's reach."
        ),
        goal=(
            "**Task:** get the block into the bin. Neither arm can do it alone: the left arm has to pass the block "
            "to the right arm (a handover in the air, or putting it down where the right arm can reach it), and "
            "the right arm puts it into the bin."
        ),
        success=(
            "At the **end of the trajectory**: the block's centre is inside the bin's inner walls and less than "
            "11 cm above the bin's base (so the block stands or lies on the bin floor), the block is at rest "
            "(speed below 5 cm/s), no part of either robot touches it, and the two arms never touched each other. "
            "`s.check()` (also returned by `s.step`) computes exactly this: `block_in_bin`, `at_rest`, "
            "`gripper_touches_object`, `arm_collision`, `success`."
        ),
        difficulty=(
            "A bimanual task: two arms planned together with no motion primitives, a handover between two "
            "small 6-joint arms whose dexterous workspaces barely overlap (top-down grasps reach only about "
            "0.45 m from each base, the bases are 0.61 m apart), grasps that leave room for the other "
            "gripper, and no arm-to-arm contact ever (the wrist cameras stick out). Medium: a scripted IK "
            "controller solves it in about 16 s of robot time."
        ),
        reference=(
            "`solution/oracle_yam.py` (`handover_to_bin`): the left arm grasps the block's top from above and "
            "carries it to a handover point between the arms; the right arm, waiting beside it, grasps the "
            "lower half from behind (approach +x), the left arm lets go and slides out, the right arm carries "
            "the block over the bin and lets go 4 cm above the rim; 822 control steps (16.4 s)."
        ),
        hours=2.0,
    ),
}


def dirname(fam: str) -> str:
    return f"sim_to_real-{fam.replace('_', '-')}-i00-privileged"


def instruction(fam: str, f: dict) -> str:
    return f"""# Sim-to-real · YAM · {f["title"].lower()}

{f["scene"]}
{f["goal"]}

{ROBOT_TEXT}
## Success
{f["success"]}

{TOOLING_TEXT}
{RULES_TEXT}"""


def task_toml(fam: str, f: dict, inst: dict) -> str:
    return f"""schema_version = "1.3"
artifacts = ["/app/output/", "/logs/agent/rcb/"]

[task]
name = "robot-coding-bench/{dirname(fam)}"
description = "Sim-to-real on the I2RT YAM bimanual station (MuJoCo digital twin): {f["title"].lower()}; produce one replayable, rate-limited joint trajectory from a frozen instance (seed {inst["seed"]})."
authors = [{{ name = "kangrui" }}]
keywords = ["robotics", "mujoco", "sim-to-real", "i2rt-yam", "bimanual", "code-as-policy", "trajectory"]

[metadata]
author_name = "kangrui"
task_type = "trajectory"
simulator = "mujoco"
robot = "i2rt-yam-bimanual"
family = "{fam}"
mode = "privileged"
oracle = "full"
instance_seed = {inst["seed"]}
expert_time_estimate_hours = {f["hours"]}

[verifier]
timeout_sec = 1200.0
environment_mode = "separate"

[agent]
timeout_sec = {AGENT_TIMEOUT:.1f}
# egress: Harbor default (public); no reference solution for these scenes exists outside solution/.

[environment]
build_timeout_sec = 1800.0
cpus = 4
memory_mb = 8192

[verifier.environment]
build_timeout_sec = 1800.0
"""


def readme(fam: str, f: dict, inst: dict) -> str:
    o = inst["objects"]
    goal = f["goal"].replace("**Task:** ", "")
    poses = "; ".join(f"{k} at ({v['xy'][0]}, {v['xy'][1]}) yaw {v['yaw']} rad" for k, v in o.items())
    return f"""# {dirname(fam)}

## Task
{f["scene"]} {goal[0].upper() + goal[1:]} The scene is the MuJoCo digital twin of a physical I2RT YAM
bimanual station; the deliverable is a rate-limited joint trajectory meant to be replayed on the real robot later.

## Difficulty
{f["difficulty"]}

## Reference solution
{f["reference"]}

## Verification
`tests/grade.py` replays `/app/output/trajectory.npz` twice from the frozen instance in fresh sessions. Success =
{f["success"].split(" `s.check()`")[0][0].lower() + f["success"].split(" `s.check()`")[0][1:]} Also required: every row within the joint limits and
the rate limit, and both replays ending in the same state hash.

## Details
| | |
|---|---|
| source | robot_coding_bench (this repository): scene and success rule written for this benchmark; YAM arm from [MuJoCo Menagerie](https://github.com/google-deepmind/mujoco_menagerie) @ f054586 `i2rt_yam/yam_linear_4310.xml` (MIT); station extrinsics from [i2rt-robotics/i2rt](https://github.com/i2rt-robotics/i2rt) v1.3.6 `yam_station_linear_4310_d405` (MIT) |
| physics | MuJoCo 3.3.7, 500 Hz, implicitfast; control 50 Hz (10 substeps); rate limit 3 rad/s (joints), 0.25 m/s (grippers) |
| instance | seed {inst["seed"]} (`rcb_yam.make_instance`): {poses}; initial-state hash {inst["state_sha"]} |
| deliverable | `(T, 14)` applied position targets per control step, T ≤ 3000; bit-exact replay |
| sim-to-real | the instance's object poses are what a physical setup reproduces (a printed placement mat in the left arm's base frame); the recorded targets go to the I2RT SDK's joint-position command unchanged (gripper: travel / 0.0475 → the SDK's 0–1) |
"""


ENV_DOCKERFILE = f"""FROM {IMAGE}
COPY instance.json /app/instance.json
COPY rcb_yam.py /opt/tools/rcb_yam.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
"""

TESTS_DOCKERFILE = f"""# Separate verifier sandbox (PROTOCOL §2.6): the base image with the verifier's own copies of the tooling and the
# frozen instance; only the declared artifacts (/app/output/, /logs/agent/rcb/) arrive from the agent.
FROM {IMAGE}
COPY grade.py instance.json rcb_yam.py test.sh /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests
WORKDIR /tests
"""

COMPOSE = """# MuJoCo physics is CPU-only; the GPU is only for EGL rendering (camera frames, videos; OSMesa without one). Harbor's
# local docker sandbox rejects [environment].gpus, so the device is passed through by merging this onto the main service.
services:
  main:
    shm_size: "8gb"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
"""

TEST_SH = """#!/bin/bash
# Verifier (separate sandbox): replay /app/output/trajectory.npz from the frozen start state (tests/ copies of the
# tooling and instance) and write /logs/verifier/reward.txt (1/0) + reward.json.
rm -rf /logs/verifier/*   # verdicts from an earlier run never survive (docs/PROTOCOL.md §2.6)
mkdir -p /logs/verifier
python /tests/grade.py 2> /logs/verifier/grade.log
"""

SOLVE_SH = """#!/bin/bash
# Oracle: replay the scripted IK controller's recorded targets (solution/oracle_yam.py, run offline on this instance).
set -e
mkdir -p /app/output
python - <<'PY'
import numpy as np, rcb_yam as ry
A = np.load("/solution/oracle_targets.npy"); s = ry.Session("/app/instance.json"); print(s.replay(A))
s.save_trajectory(A, "/app/output/trajectory.npz", meta={"source": "oracle replay (scripted IK)"})
PY
cp /solution/oracle_yam.py /app/output/gen.py
"""


def write(p: Path, s: str | bytes, exe: bool = False) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(s if isinstance(s, bytes) else s.encode())
    p.chmod(0o755 if exe else 0o644)


def render(out: Path) -> list[str]:
    names = []
    for fam, f in FAMILIES.items():
        inst = json.loads((HERE / "instances" / f"{fam}.json").read_text())
        t = out / dirname(fam)
        inst_b = (HERE / "instances" / f"{fam}.json").read_bytes()
        tool = (SHARED / "rcb_yam.py").read_bytes()
        write(t / "task.toml", task_toml(fam, f, inst))
        write(t / "instruction.md", instruction(fam, f))
        write(t / "README.md", readme(fam, f, inst))
        write(t / "environment/Dockerfile", ENV_DOCKERFILE)
        write(t / "environment/docker-compose.yaml", COMPOSE)
        write(t / "environment/instance.json", inst_b)
        write(t / "environment/rcb_yam.py", tool)
        write(t / "tests/Dockerfile", TESTS_DOCKERFILE)
        write(t / "tests/docker-compose.yaml", COMPOSE)
        write(t / "tests/test.sh", TEST_SH, exe=True)
        write(t / "tests/grade.py", (SHARED / "grade.py").read_bytes())
        write(t / "tests/instance.json", inst_b)
        write(t / "tests/rcb_yam.py", tool)
        write(t / "solution/solve.sh", SOLVE_SH, exe=True)
        write(t / "solution/oracle_yam.py", (HERE / "oracles" / "oracle_yam.py").read_bytes())
        write(t / "solution/oracle_targets.npy", (HERE / "oracles" / fam / "oracle_targets.npy").read_bytes())
        normalize(t)
        names.append(t.name)
    return names


def same(a: Path, b: Path) -> list[str]:
    diffs = []
    fa = {p.relative_to(a) for p in a.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    fb = (
        {p.relative_to(b) for p in b.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
        if b.is_dir()
        else set()
    )
    for r in sorted(fa | fb):
        pa, pb = a / r, b / r
        if r not in fa or r not in fb or not filecmp.cmp(pa, pb, shallow=False):
            diffs.append(str(r))
        elif stat.S_IMODE(pa.stat().st_mode) & 0o111 != stat.S_IMODE(pb.stat().st_mode) & 0o111:
            diffs.append(f"{r} (mode)")
    return diffs


def main(argv: list[str]) -> int:
    check = "--check" in argv
    with tempfile.TemporaryDirectory() as tmp:
        names = render(Path(tmp))
        bad = 0
        for n in names:
            dst = ROOT / "tasks" / n
            d = same(Path(tmp) / n, dst)
            if not d:
                continue
            if check:
                print(f"FAIL {n}: " + ", ".join(d[:10]))
                bad += 1
            else:
                shutil.rmtree(dst, ignore_errors=True)
                shutil.copytree(Path(tmp) / n, dst)
                print(f"wrote tasks/{n}")
    if check:
        print(
            f"{'FAIL' if bad else 'ok'}: {len(names) - bad}/{len(names)} sim_to_real task dirs are what mk_tasks.py writes"
        )
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
