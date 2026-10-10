#!/usr/bin/env python3
"""Generate the MetaWorld+ tasks: tasks/metaworldplus-<env>-i00-privileged and tasks/metaworldplus-<env>-i00-standard.

    python3 scripts/metaworldplus/generate.py            # all fifty environments (envs.py)
    python3 scripts/metaworldplus/generate.py push reach

Inputs: envs.py (goal texts, seeds), frozen/<env>/{instance,oracle}.npz and frozen/report.json (freeze.sh), the
shared sources in shared/, the standard-mode service images/metaworld/standard/server_mw.py and the standard client
image and pins of scripts/eai_standard/. Every task directory is rewritten (shared files copied byte for byte) and
finished with scripts/task_conventions.py `normalize` (PROTOCOL v1.0 conventions: README layout, no results/).
Re-running reproduces the tasks exactly.
"""

import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "scripts"))
from envs import GOALS, SUCCESS  # noqa: E402
from task_conventions import normalize  # noqa: E402

SHARED = HERE / "shared"
FROZEN = HERE / "frozen"
SERVER = ROOT / "images/metaworld/standard/server_mw.py"
VERSION = (ROOT / "images/metaworld/VERSION").read_text().strip()
IMAGE = f"ghcr.io/mll-lab-nu/eai-metaworld:{VERSION}"
# Standard-mode client image (agent container and verifier): the one client base of every standard task, pinned by
# digest, and its pinned pip versions (scripts/eai_standard/client.env, client-requirements.txt; PROTOCOL §2.4).
EAI = ROOT / "scripts/eai_standard"
_CLIENT = dict(ln.split("=", 1) for ln in (EAI / "client.env").read_text().splitlines() if "=" in ln and ln[:1] != "#")
CLIENT_BASE = _CLIENT["CLIENT_IMAGE"].strip()
CLIENT_PIP = " ".join(
    ln.split("#", 1)[0].strip()
    for ln in (EAI / _CLIENT["CLIENT_REQUIREMENTS"].strip()).read_text().splitlines()
    if ln.split("#", 1)[0].strip()
)
AUTHOR = "Changhe Chen"
ORG = "MLL Lab"
MAX_STEPS = 500
ALLOWED_HOSTS = (
    '["chatgpt.com", "*.chatgpt.com", "auth.openai.com", "api.openai.com", "*.openai.com", "api.anthropic.com", '
    '"*.anthropic.com", "openrouter.ai", "*.openai.azure.com", "*.cognitiveservices.azure.com"]'
)
AGENT = f"""[agent]
timeout_sec = 3600.0
# Meta-World's scripted policies solve these tasks and are publicly downloadable, so egress is closed to the model APIs.
network_mode = "allowlist"      # model APIs only (scripts/set_agent_egress.py); PROTOCOL §2.7
allowed_hosts = {ALLOWED_HOSTS}
"""
FRAME = (
    "World frame: metres; x to the robot's right, y forward (away from the robot's base), z up; the table top is at "
    "z = 0. Quaternions are w x y z."
)


# README Change Log (PROTOCOL §2.8: published tasks fixed in place; results before a change are not retested), oldest
# first. An entry is (text, environments it applies to or None for all).
_HIDDEN = ("stick-push", "stick-pull")
_IMPRECISE = ("hammer", "lever-pull", "door-open", "disassemble")
STD_CHANGES = [
    (
        "2026-10-10 (review 0067): the camera calibration in `meta[\"cameras\"]` now gives the pose of the viewpoint the "
        "image is rendered from. Before, `cam2world_gl` held the position of MuJoCo's left-eye camera, 3.4 cm to the side "
        "of it, so points back-projected from depth were off by that much. This changes what the agent observes: "
        "standard-mode results from before this date are not strictly comparable.",
        None,
    ),
    (
        "2026-10-10 (review 0067): the instruction states this environment's success condition in full. Before, it said "
        "only that the object is compared with the target point \"with a tolerance of a few centimetres\" and left out "
        "that the stick must still be engaged in the final state, so an agent that finished the motion and then let the "
        "stick go scored 0 without having been told. Results from before this date were obtained under the incomplete text.",
        _HIDDEN,
    ),
    (
        "2026-10-10 (review 0067): the instruction states this environment's success condition exactly (the generic "
        "sentence about the object and the target point did not describe this check).",
        _IMPRECISE,
    ),
    (
        "2026-10-10 (review 0067): the instruction states this environment's success condition (what is compared with "
        "the target point, in which axes, with which tolerance) instead of \"a tolerance of a few centimetres\".",
        tuple(e for e in GOALS if e not in _HIDDEN + _IMPRECISE),
    ),
    (
        "2026-10-10 (review 0067): a malformed request (`dt`, `seconds` or `video_fps` not a finite number, `cameras` not "
        "a list of names, actions that are not a numeric array) is answered 400 before any physics; before, some of them "
        "(e.g. `dt = Infinity`) were a 500 that ended the episode. `meta[\"time_left_s\"]` counts from the agent's first "
        "request, not from the service's start. `final.json` is finalized as soon as the verdict is in it (the video is "
        "rendered after it and cannot delay or void it); a missing, unreadable or verdict-less `final.json` is graded "
        "`infra_error = 1`, never a plain 0; the collect hook's wait fits inside its timeout.",
        None,
    ),
]
PRIV_CHANGES = [
    (
        "2026-10-10 (review 0067): the instruction states this environment's success condition in words (it already "
        "pointed to `s.check()` and Meta-World's source, which this mode can read) and the limits on a hand-written "
        "`trajectory.npz`. Nothing in the verifier changed.",
        None,
    ),
]


def change_log(changes: list, env: str) -> str:
    return "".join(f"- {text}\n" for text, envs in changes if envs is None or env in envs)


def box(rec: dict) -> str:
    lo, hi = rec["mocap_low"], rec["mocap_high"]
    return ", ".join(f"{a} ∈ [{lo[i]:g}, {hi[i]:g}]" for i, a in enumerate("xyz"))


def hold_note(rec: dict) -> str:
    if rec["success_after_hold"]:
        return ""
    return (
        "\nIn this environment the success state does not persist on its own: after the oracle's last action, holding "
        "still for 10 control steps loses it. Graded on the final state, a trajectory must end at that moment.\n"
    )


def privileged_instruction(env: str, rec: dict) -> str:
    return f"""# MetaWorld+ · {env}

A **Sawyer** arm stands at a table: Meta-World's `{env}-v3` environment (MuJoCo). **Task: {GOALS[env]}**
The scene is one frozen instance of Meta-World's own randomization (object and goal positions; seed {rec["seed"]}).

## What you hand in
`/app/output/trajectory.npz` with key `actions`: Meta-World's native actions, shape `(T, 4)` with 1 ≤ T ≤ {MAX_STEPS}
(Meta-World's episode length), one row per control step (1/80 s). Write it with `s.save_trajectory()` so the format
is right: the verifier reads a plain `.npz` of at most 2 MB that holds arrays only (no pickled objects, at most 64
members), and grades anything else as an invalid trajectory. Leave the script that produced it at `/app/output/gen.py`.

## Success
The verifier replays your actions from the frozen start in a separate sandbox (twice, in fresh processes; MuJoCo on the
CPU is bit-exact) and applies Meta-World's own success check for `{env}-v3` (`evaluate_state`) to the state **after
the last action**. A success reached earlier and then lost does not count: end the trajectory while the task is
achieved. `s.check()` computes exactly this check on the current state.

For `{env}-v3` the check is: {SUCCESS[env]} ("The target point" is `s.state()["target_pos"]`.)

## Tooling (`/opt/tools/mw_tool.py`, importable as `mw_tool`)
```python
import numpy as np, mw_tool
s = mw_tool.Session("/app/instance.npz")  # the frozen instance; s.env is the Meta-World env, s.model / s.data MuJoCo
st = s.state()        # tcp, gripper_opening, mocap_pos, target_pos, object_pos / object_quat_wxyz, object2_*,
                      #   observation (Meta-World's 39-d), qpos, qvel, bodies {{name: pos, quat_wxyz}}, success
r = s.step([dx, dy, dz, grip])   # one control step -> {{"success": ..., "control_steps": ..., ...}}
s.check()             # Meta-World's success check on the current state
s.save_trajectory()   # the actions since the last reset -> /app/output/trajectory.npz
s.replay(A)           # reset, then replay A (what the verifier does) -> {{"success": ..., "state_sha": ...}}
s.reset()             # back to the frozen start, as often as you like
img = s.render("front")   # RGB (240, 320, 3); views front, left, right, topview; s.render_grid() shows all four
```
- Action `[dx, dy, dz, grip]`, each clipped to [-1, 1]. The hand's target (a mocap body) moves by `[dx, dy, dz]` × 1 cm
  per control step and stays inside {box(rec)}; the hand follows it through a weld constraint. `grip` drives the two
  fingers (+1 closes, -1 opens). The wrist does not rotate.
- {FRAME}
- Everything in `s.env`, `s.model` and `s.data` is readable (privileged mode), including Meta-World's source.

## Rules
- Write your own controller. Do not use Meta-World's scripted policies or any published solution for this benchmark.
- Only the actions count: editing `s.data` or the environment while debugging changes nothing in the replay.
- You have 60 minutes of wall-clock time. Save a working trajectory early, then improve it; do not stop early.
"""


def standard_instruction(env: str, rec: dict) -> str:
    return f"""# MetaWorld+ · {env} — STANDARD MODE (robot as a service)

A **Sawyer** arm stands at a table: Meta-World's `{env}-v3` environment (MuJoCo). **Task: {GOALS[env]}**
The scene is one frozen instance of Meta-World's own randomization.

You control the robot **as if it were real hardware**: the simulator runs in a service you cannot open. You get one
client and one episode.

## Rules (real-robot rules)
- **No reset.** What you knock over stays knocked over.
- **No privileged state.** You see what the cameras see (RGB, optional depth, with each camera's calibration), the
  robot's own state and the task's target point. No object poses, no success signal.
- Your wall-clock budget is 60 minutes. `meta["time_left_s"]` is counted from your first request to the service;
  approximate — the harness's own deadline is authoritative. There is nothing to hand in: the service records the
  episode as the trajectory and grades it. Leave your script at `/app/output/gen.py` for the record.
- Do not use Meta-World's scripted policies or any published solution for this benchmark; write your own controller.
- Images come back as arrays in a Python object; what you look at and where you store it is up to your code.

## Scoring
The episode runs until your time is up. The service then replays the recorded episode in a fresh simulator and applies
Meta-World's own success check for `{env}-v3` to the state **after the last executed control step**; it must hold in
the live episode and in the replay. A success reached earlier and then lost does not count: end in the state you want
graded and stop submitting.

For `{env}-v3` the check is: {SUCCESS[env]} ("The target point" is `meta["task"]["target_pos"]`; everything the
check needs to hold must hold in that final state.)

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`)
```python
from rcb_client import Robot
r = Robot()                                   # connects (waits while the service starts)
spec = r.spec()                               # control_dt, action layout + limits, cameras, proprio layout, budget
cams = list(spec["cameras"])                  # front, left, right, topview
obs = r.get_obs(cameras=cams, include_depth=True)   # obs.last[cam] -> uint8 (240, 320, 3); obs.depth[cam] -> metres
obs.meta["proprio"]                           # {{"layout": [...], "now": [...]}}
obs.meta["cameras"]                           # per camera: intrinsic_cv, cam2world_gl (OpenGL: looks along -z)
obs.meta["task"]["target_pos"]                # the task's target point (world frame)
obs = r.get_obs(cameras=cams[:1], seconds=2.0, video="mp4")    # hold still and watch for 2 s (max 30)
res = r.submit("ee_delta", A, dt=spec["control_dt"], cameras=cams[:1], video="mp4")   # A: (T, 4)
res.meta["done"], res.meta["reason"], res.meta["control_steps"]
res.video[cam]; res.frames[cam]; res.last[cam]; res.proprio; res.save("/app/runs/003")
```
- Action `ee_delta` (4: `dx, dy, dz, grip`, float64, each clipped to [-1, 1]) is Meta-World's native action, applied
  once per control step (`control_dt` = 0.0125 s). The hand's target moves by `[dx, dy, dz]` × 1 cm per control step
  and stays inside {box(rec)}; the hand follows it. `grip` drives the two fingers (+1 closes, -1 opens). The wrist does
  not rotate. Rows are `dt` apart (a multiple of `control_dt`); with `dt = control_dt` each row is one native action.
  A chunk covers at most 10 s.
- `get_obs(seconds=s)` holds the hand still (zero motion, same grip) while physics runs for `s` seconds; those control
  steps are part of the episode.
- Proprioception (`meta["proprio"]["layout"]`): `tcp_x/y/z` (the point between the fingertips), `gripper_opening`
  (0 closed … 1 open), `mocap_x/y/z` (the hand's target), the arm joints' positions and velocities, the finger joints'
  positions, and `cmd_*` (the last action).
- {FRAME} The four cameras are fixed.
- Calibration: `meta["cameras"][cam]` holds `intrinsic_cv` (pinhole, pixels) and `cam2world_gl` (4x4 camera-to-world,
  OpenGL axes: x right, y up, the camera looks along -z; the viewpoint the image is rendered from). Depth is the
  distance along the viewing axis, in metres.
"""


def privileged_readme(env: str, rec: dict) -> str:
    return f"""# metaworldplus-{env}-i00-privileged

## Task
A Sawyer arm at a table, Meta-World's `{env}-v3` (reward v2) on one frozen instance: {GOALS[env]} The agent writes a
trajectory of Meta-World's native actions with full privileged state and unlimited resets; it is graded by replay on
the state after the last action. Generated by `scripts/metaworldplus/generate.py`; benchmark notes in
`docs/benchmarks/metaworldplus.md`.

## Difficulty
Full privileged state, unlimited resets and self-replay: this mode is the control for the standard twin
(`metaworldplus-{env}-i00-standard`). It is reported, but not in the main (standard-mode) table, because it is
saturated under final-state grading (decision on the benchmark proposal, #10). What remains hard here is planning the
contacts (grasp, push, turn) with a mocap-driven hand whose wrist does not rotate, within {MAX_STEPS} actions.

## Reference solution
Meta-World's scripted policy for `{env}-v3` (`metaworld/policies/`, removed from the image), run on this instance up to
its first success: {rec["n_actions"]} actions in `solution/oracle.npz` (recorded by `scripts/metaworldplus/freeze.sh`).
{hold_note(rec)}
## Verification
`tests/grade.py` in a separate sandbox without network: two replays in fresh processes from the verifier's own copy of
the instance; `success = deterministic ∧ success on the final state`. Oracle: two fresh-process replays end in the
live episode's state (hash `{rec["live_state_sha"][:12]}…`) and succeed. `nop`: no trajectory, reward 0; the instance is
not solved at the start.

## Details
| | |
|---|---|
| source | [Meta-World](https://github.com/Farama-Foundation/Metaworld) @ 59fc34d (MIT) on MuJoCo 3.3.0; image `eai-metaworld:{VERSION}` |
| instance | Meta-World's reset randomization with seed {rec["seed"]}; MuJoCo state, model arrays, env caches and RNG frozen in `instance.npz` (SHA-256 `{rec["instance_sha"][:12]}…`, checked on load) |
| deliverable | `(T, 4)` native actions `[dx, dy, dz, grip]`, 1 ≤ T ≤ {MAX_STEPS} (Meta-World's `max_path_length`) |
| success | Meta-World's own check (`evaluate_state`) on the state after the last action. {SUCCESS[env]} |
| actions | no `joint_position`: Meta-World's Sawyer has no arm actuators (the hand is a mocap body, the arm follows it) |

## Change Log
{change_log(PRIV_CHANGES, env)}"""


def standard_readme(env: str, rec: dict) -> str:
    return f"""# metaworldplus-{env}-i00-standard

## Task
Standard-mode twin of `metaworldplus-{env}-i00-privileged`: the same instance and success check ({GOALS[env]}), served
as a robot service (`images/metaworld/standard/server_mw.py`, protocol eai-standard/2.1, tool module `mw_tool`). The
agent sees camera RGB-D, the robot's own state and the target point; no object poses, no reset; one episode.

## Difficulty
The agent has to find the objects in the images, place a mocap-driven hand whose wrist does not rotate, close the loop
through the cameras and finish in one episode without a reset: a pushed-away object or a dropped part stays where it
is. Success is judged on the final state, so the agent must also end the episode while the task is achieved.

## Reference solution
`solution/`: the privileged oracle's {rec["n_actions"]} actions (Meta-World's scripted policy, recorded offline)
submitted through the client, one row per control step.
{hold_note(rec)}
## Verification
The sim service replays the recorded episode in a fresh simulator; `tests/grade.py` (separate sandbox, no network)
reads its `final.json`: `success = replay_success ∧ deterministic ∧ live_success`.

## Details
| | |
|---|---|
| actions | `ee_delta` = Meta-World's native `[dx, dy, dz, grip]` (no `joint_position`: the Sawyer has no arm actuators) |
| observations | four fixed cameras (RGB-D, calibration), proprioception, `meta.task.target_pos`; no object poses |
| episode | no step limit; runs until the agent's time is up; the state after the last control step is graded |
| success | Meta-World's own check (`evaluate_state`). {SUCCESS[env]} |

## Change Log
{change_log(STD_CHANGES, env)}"""


def privileged_toml(env: str, rec: dict) -> str:
    return f"""schema_version = "1.3"
artifacts = ["/app/output/"]

[task]
name = "robot-coding-bench/metaworldplus-{env}-i00-privileged"
description = "MetaWorld+ (Meta-World v3 {env}, Sawyer arm): {GOALS[env]} Produce one replayable trajectory of Meta-World's native actions on a frozen instance; graded on the state after the last action."
authors = [{{ name = "{AUTHOR}" }}]
keywords = ["robotics", "mujoco", "metaworld", "sawyer", "code-as-policy", "trajectory", "privileged"]

[metadata]
author_name = "{AUTHOR}"
author_org = "{ORG}"
task_type = "trajectory"
simulator = "mujoco"
robot = "sawyer"
family = "metaworld/{env}"
mode = "privileged"
oracle = "full"
instance_seed = {rec["seed"]}             # Meta-World's reset randomization (object and goal positions)
expert_time_estimate_hours = 0.5

[verifier]
timeout_sec = 1200.0
environment_mode = "separate"
network_mode = "no-network"

{AGENT}
[environment]
build_timeout_sec = 1800.0
cpus = 4
memory_mb = 8192

[verifier.environment]
build_timeout_sec = 1800.0
"""


def standard_toml(env: str, rec: dict) -> str:
    # The sim's collect hook: wait (at most 180 s) for the service's PID file, then send SIGUSR1 every 30 s until
    # final.json says video_done (the verdict is `finalized` before the video is rendered; video_done follows), all
    # inside one 840 s deadline, so the loop always ends before the hook's timeout_sec = 900. A hook that stops early
    # leaves the verdict on disk as it is.
    collect = (
        "t0=$(date +%s); left() { echo $(( 840 - $(date +%s) + t0 )); }; while [ ! -f /data/server.pid ] && "
        "[ $(left) -gt 660 ]; do sleep 2; done; i=0; while [ $(left) -gt 0 ]; do grep -q "
        "'\\\"video_done\\\": true' /data/final.json 2>/dev/null && break; [ $((i % 15)) -eq 0 ] && kill -USR1 $(cat "
        "/data/server.pid) 2>/dev/null; i=$((i+1)); sleep 2; done; cat /data/final.json"
    )
    return f"""schema_version = "1.3"
artifacts = [
  {{ source = "/data/final.json", service = "sim" }},
  {{ source = "/data/episode.jsonl", service = "sim" }},
  {{ source = "/data/trajectory.npz", service = "sim" }},
  {{ source = "/data/replay.mp4", service = "sim" }},
  {{ source = "/data/replay.last.png", service = "sim" }},
  {{ source = "/data/calls/", service = "sim" }},
  "/app/output/",
]

[task]
name = "robot-coding-bench/metaworldplus-{env}-i00-standard"
description = "STANDARD MODE (robot as a service, eai-standard/2.1): MetaWorld+ (Meta-World v3 {env}, Sawyer arm): {GOALS[env]} The agent only gets a client: camera RGB-D, the robot's own state and the target point, and Meta-World's native actions in chunks; no reset, no object poses; the sim service records the episode and grades a fresh replay of it."
authors = [{{ name = "{AUTHOR}" }}]
keywords = ["robotics", "mujoco", "metaworld", "sawyer", "code-as-policy", "trajectory", "standard-mode"]

[metadata]
author_name = "{AUTHOR}"
author_org = "{ORG}"
task_type = "trajectory"
simulator = "mujoco"
robot = "sawyer"
family = "metaworld/{env}"
mode = "standard"
protocol = "eai-standard/2.1"
oracle = "full"
instance_seed = {rec["seed"]}
expert_time_estimate_hours = 1.0

[verifier]
timeout_sec = 1200.0
environment_mode = "separate"
network_mode = "no-network"

[[verifier.collect]]
service = "sim"
command = "{collect}"
timeout_sec = 900

{AGENT}
[environment]
build_timeout_sec = 1800.0
cpus = 4
memory_mb = 8192

[verifier.environment]
build_timeout_sec = 600.0
"""


PRIV_ENV_DOCKERFILE = f"""# MetaWorld+ privileged task: the Meta-World image, the task's tooling and its frozen instance.
FROM {IMAGE}
COPY instance.npz /app/instance.npz
COPY mw_tool.py /opt/tools/mw_tool.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
"""
PRIV_TESTS_DOCKERFILE = f"""# Separate verifier sandbox: the same image with the verifier's own copies of the tooling and the frozen instance;
# only the declared artifacts (/app/output/) arrive from the agent.
FROM {IMAGE}
COPY test.sh grade.py mw_tool.py instance.npz /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests
WORKDIR /tests
"""
STD_ENV_DOCKERFILE = f"""# Standard mode: the agent container has no simulator and no task code, only Python and the client.
FROM {CLIENT_BASE}
RUN pip install --no-cache-dir {CLIENT_PIP}
COPY rcb_client.py rcb1.py /opt/tools/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
"""
STD_TESTS_DOCKERFILE = f"""# Separate verifier sandbox: grades the sim service's own artifacts; the client base image, nothing else.
FROM {CLIENT_BASE}
COPY test.sh grade.py /tests/
RUN chmod +x /tests/test.sh
"""
STD_COMPOSE = f"""# Standard mode: the simulator runs in the `sim` sidecar (the agent cannot open it); the agent only reaches port 8000.
# No `expose`/`ports` on sim: under Harbor's egress control it shares main's network namespace (localhost:8000).
# CPU only (MuJoCo physics, OSMesa rendering): no GPU reservation.
services:
  main:
    depends_on: [sim]
  sim:
    image: {IMAGE}
    volumes:
      - ./sim:/srv:ro
    working_dir: /srv
    command: python /srv/server_mw.py
    restart: on-failure:6
    environment:
      RCB_TOOL: mw_tool
      RCB_INSTANCE: /srv/instance.npz
      PYTHONPATH: /srv
"""


def reset_dir(d: Path) -> None:
    """Remove the task directory's old contents (results are not kept in the repository, PROTOCOL D3)."""
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)


def put(path: Path, text: str | None = None, src: Path | None = None, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if src is not None:
        shutil.copyfile(src, path)
    else:
        path.write_text(text)
    path.chmod(mode)


def make(env: str, rec: dict) -> None:
    fz = FROZEN / env
    p = ROOT / "tasks" / f"metaworldplus-{env}-i00-privileged"
    reset_dir(p)
    put(p / "task.toml", privileged_toml(env, rec))
    put(p / "instruction.md", privileged_instruction(env, rec))
    put(p / "README.md", privileged_readme(env, rec))
    put(p / "environment/Dockerfile", PRIV_ENV_DOCKERFILE)
    put(p / "environment/mw_tool.py", src=SHARED / "mw_tool.py")
    put(p / "environment/instance.npz", src=fz / "instance.npz")
    put(p / "tests/Dockerfile", PRIV_TESTS_DOCKERFILE)
    put(p / "tests/test.sh", src=SHARED / "test.sh", mode=0o755)
    put(p / "tests/grade.py", src=SHARED / "grade_privileged.py")
    put(p / "tests/mw_tool.py", src=SHARED / "mw_tool.py")
    put(p / "tests/instance.npz", src=fz / "instance.npz")
    put(p / "solution/solve.sh", src=SHARED / "solve_privileged.sh", mode=0o755)
    put(p / "solution/oracle_replay.py", src=SHARED / "oracle_privileged.py")
    put(p / "solution/oracle.npz", src=fz / "oracle.npz")

    s = ROOT / "tasks" / f"metaworldplus-{env}-i00-standard"
    reset_dir(s)
    put(s / "task.toml", standard_toml(env, rec))
    put(s / "instruction.md", standard_instruction(env, rec))
    put(s / "README.md", standard_readme(env, rec))
    put(s / "environment/Dockerfile", STD_ENV_DOCKERFILE)
    put(s / "environment/docker-compose.yaml", STD_COMPOSE)
    put(s / "environment/rcb_client.py", src=SHARED / "rcb_client.py")
    put(s / "environment/rcb1.py", src=SHARED / "rcb1.py")
    put(s / "environment/sim/server_mw.py", src=SERVER)
    put(s / "environment/sim/mw_tool.py", src=SHARED / "mw_tool.py")
    put(s / "environment/sim/rcb1.py", src=SHARED / "rcb1.py")
    put(s / "environment/sim/instance.npz", src=fz / "instance.npz")
    put(s / "tests/Dockerfile", STD_TESTS_DOCKERFILE)
    put(s / "tests/test.sh", src=SHARED / "test.sh", mode=0o755)
    put(s / "tests/grade.py", src=SHARED / "grade_standard.py")
    put(s / "solution/solve.sh", src=SHARED / "solve_standard.sh", mode=0o755)
    put(s / "solution/oracle_replay.py", src=SHARED / "oracle_standard.py")
    put(s / "solution/oracle.npz", src=fz / "oracle.npz")
    for t in (p, s):  # after both exist: each README's key table names its twin
        normalize(t)


def main(envs: list[str]) -> None:
    report = json.loads((FROZEN / "report.json").read_text())
    for env in envs:
        rec = report[env]
        ok = rec["oracle_success"] and rec["deterministic"] and rec["replay_success"] and rec["reset_exact"]
        if not ok or rec["initial_success"]:
            raise SystemExit(f"{env}: frozen instance or oracle not verified (re-run freeze.sh {env})")
        make(env, rec)
    print(f"generated {2 * len(envs)} task directories")


if __name__ == "__main__":
    main(sys.argv[1:] or sorted(GOALS))
