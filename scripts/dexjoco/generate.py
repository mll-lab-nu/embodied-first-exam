#!/usr/bin/env python3
"""Generate the DexJoCo tasks: tasks/dexjoco-<family>-i00-privileged and -standard for the 11 DexJoCo families.

    python3 scripts/dexjoco/generate.py            # (re)write all 22 task directories
    python3 scripts/dexjoco/generate.py --check    # exit 1 if tasks/ differs from what this would write

Standard library only (plus scripts/task_conventions.py, which every generator ends with). Inputs:
  scripts/dexjoco/instances/<family>/{instance.npz, oracle_trajectory.npz, facts.json}   (make_instances.py, in the image)
  scripts/dexjoco/shared/          the tooling rcb_dexjoco.py, the privileged grader, the standard adapter and its hooks
  scripts/eai_standard/            the eai-standard/2.2 layer (client, service layer, run.sh, client image and pins)
The texts are the templates below. docs/benchmarks/dexjoco.md describes the benchmark.
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
LAYER = ROOT / "scripts" / "eai_standard"
sys.path.insert(0, str(ROOT / "scripts"))
from task_conventions import normalize  # noqa: E402

IMAGE = "ghcr.io/mll-lab-nu/eai-dexjoco:" + (ROOT / "images" / "dexjoco" / "VERSION").read_text().strip()
CLIENT_ENV = dict(l.split("=", 1) for l in (LAYER / "client.env").read_text().splitlines() if "=" in l and not l.startswith("#"))
CLIENT_IMAGE = CLIENT_ENV["CLIENT_IMAGE"].strip()
AGENT_TIMEOUT = 5400        # 1.5 h for the whole benchmark (PROTOCOL D8): dexterous control of a 16-DoF hand per arm
ALLOWED_HOSTS = ["chatgpt.com", "*.chatgpt.com", "auth.openai.com", "api.openai.com", "*.openai.com", "api.anthropic.com",
                 "*.anthropic.com", "openrouter.ai", "*.openai.azure.com", "*.cognitiveservices.azure.com"]

# Per family: the goal in words (the standard twin never sees the code, so it is complete), what the scene holds, the
# extra rule robot_coding_bench adds, the static camera the texts name first, the difficulty and the expert time.
FAMILIES: dict[str, dict] = {
    "water_plant": dict(
        goal=("Pick up the spray bottle, point its nozzle at the potted plant and squeeze the trigger. Success: the "
              "trigger is held pulled (trigger joint > 0.34 rad; it counts as released again below 0.25 rad) while the "
              "nozzle reference point is within 0.20 m of the plant horizontally and within +-0.20 m of the plant's "
              "height AND the spray points at the plant, all three for 30 consecutive control steps (0.6 s). The spray "
              "leaves the spray head horizontally forward: perpendicular to the bottle's long axis, on the side the "
              "trigger faces (the bottle's local +z; its long axis, bottom to head, is local +y). It points at the "
              "plant when that direction is within 45 degrees of the line from the nozzle to the plant, e.g. with the "
              "bottle held upright and its trigger side facing the plant. "
              "Pulling the trigger while the nozzle is outside the zone ends the episode as a failure."),
        rcb_rule=("robot_coding_bench adds the aiming condition to DexJoCo's check: upstream's zone + trigger test alone "
                  "passes with the bottle lying on the table and spraying away from the plant. The episode ends in "
                  "success only when `_compute_success`'s zone + trigger condition and the aim below hold together for "
                  "30 consecutive steps (`status()['info']` reports `aim_deg` and `rcb_success_count`); DexJoCo's own "
                  "`succeed` flag alone no longer ends it."),
        scene=("The spray bottle stands on the table to the robot's right-front, the potted plant further along +y. The "
               "trigger is a hinge on the bottle's neck that the index and middle fingers can pull back."),
        difficulty="medium", hours=1.5),
    "click_mouse": dict(
        goal=("Put the computer mouse on the magenta mousepad and click its button. Success: the mouse is on the pad "
              "(its centre within the pad's 0.15 m radius horizontally and within 0.05 m of the pad's height), the "
              "button has been pressed while the mouse was on the pad (button joint more than 0.001 rad past its rest "
              "angle), which turns the monitor blue, and the mouse then stays on the pad for 10 consecutive control "
              "steps. A click while the mouse is off the pad does nothing."),
        scene=("The mouse lies on the table in front of the monitor; the round magenta mousepad is next to it at lower y. "
               "The button is a hinge on the mouse's front half."),
        difficulty="medium", hours=1.5),
    "hammer_nail": dict(
        goal=("Pick up the hammer and drive the nail into the wooden block by striking its head. A strike counts only if "
              "the hammer face was moving down faster than 0.02 m/s just before it touched the nail; each counted "
              "strike drives the nail 8 mm x min(3, speed / 0.02) deeper (at most 7.26 cm). Success: the nail is at "
              "least 4 cm deep."),
        scene=("The hammer lies on the table at the robot's right (low y); the nail stands upright in a wooden block in "
               "front of the robot. The nail is not a free body: it only moves down when struck."),
        difficulty="hard", hours=2.0),
    "bimanual_hanoi": dict(
        goal=("Tower of Hanoi with three disks on three vertical posts in a row along y: the small disk is on post A "
              "(y > 0, the left arm's side), the medium disk on post B (middle), the large disk on post C (y < 0). Build "
              "the full tower on post C: large at the bottom, then medium, then small, posts A and B empty, every disk "
              "at rest and seated on the post (horizontally within 4 cm of it, at its stacking height within 1.2 cm), "
              "held for 20 consecutive control steps. A larger disk resting on a smaller one, or a disk resting on the "
              "table, for 10 consecutive steps ends the episode as a failure."),
        scene=("Two arms with a hand each stand side by side facing the table (right arm at y < 0, left arm at y > 0); the "
               "wooden Hanoi base with its three posts is in front of them. Each disk has a hole and slides over a post."),
        difficulty="medium", hours=2.0),
    "pick_bucket": dict(
        goal=("Put the boxed food into the bucket, then lift the bucket. Success: the boxed food's centre is inside the "
              "bounding box of the bucket's eight reference corners AND the bucket's bottom is at least 0.15 m above "
              "where it started, at the same control step."),
        scene=("The bucket stands on the table with a hinged handle over it; the boxed food lies next to it. The handle "
               "swings on a hinge (`bucket_handle`)."),
        difficulty="medium", hours=2.0),
    "pinch_tongs": dict(
        goal=("Pick up the tongs and open and close them three times while holding them up. A pinch counts each time the "
              "tongs' hinge goes from open (>= 0.1 rad) to closed (<= -0.07 rad). Success: at least three pinches counted "
              "and the tongs at least 0.10 m above the table, held for 30 consecutive control steps."),
        scene="The kitchen tongs lie on the table in front of the robot; their two arms are joined by a hinge (`tongs_hinge`).",
        difficulty="medium", hours=2.0),
    "fold_glasses": dict(
        goal=("Fold both temples of the glasses and put the glasses into the open case. Success: both temple hinges past "
              "1.1 rad AND the glasses' centre inside the case (within 0.145 m of the case centre in x and y, between "
              "0.045 m below and 0.0275 m above it), held for 50 consecutive control steps."),
        scene="Open glasses lie on the table; the open case is next to them. Each temple is a hinge (`temple_0`, `temple_1`).",
        difficulty="hard", hours=2.5),
    "bimanual_microwave_cook": dict(
        goal=("Open the microwave door, put the hot dog inside, close the door and press the start button. Success, at one "
              "control step: the hot dog is inside the cavity (1 cm margin), the door hinge is within 0.01 rad of closed, "
              "and the start button is in contact with something."),
        scene=("The microwave stands on the table with its door closed; the hot dog lies in front of it. The door has a "
               "handle and a hinge (`door_hinge`); the start and stop buttons are on the front panel."),
        difficulty="hard", hours=3.0),
    "bimanual_unlock_ipad": dict(
        goal=("Pick up the iPad and enter the passcode 1-2-3 on its screen. A digit is pressed when a FINGERTIP touches its "
              "button; pressing any other digit than the next one of 1-2-3 ends the episode as a failure. Success: the "
              "screen is unlocked (1, 2, 3 in order) and stays unlocked for 10 consecutive control steps."),
        scene="The iPad rests on a stand on the table, screen facing the robots; its keypad shows the digits.",
        difficulty="hard", hours=2.5),
    "bimanual_assembly": dict(
        goal=("Hold the tray with one hand and insert the round peg into its socket with the other. Success: the peg "
              "touches the socket's bottom for 30 consecutive control steps."),
        scene="The tray with a round socket and the 8 mm round peg lie on the table in front of the robots.",
        difficulty="hard", hours=2.5),
    "bimanual_photograph": dict(
        goal=("Hold the camera with the left hand in front of the logo and press its shutter with the right hand. Success, at "
              "one control step: the camera's view point is inside the target region (0.16 m radius, +-0.10 m height, "
              "0.40 m in front of the logo along -x, i.e. about 0.3 m above the table), the camera's viewing axis is "
              "within 10 degrees of world +x, and the shutter button is touched by something other than the camera."),
        scene="The camera lies on the table between the robots; the logo disk stands at the far side of the table.",
        difficulty="hard", hours=2.5),
}


def dash(fam: str) -> str:
    return fam.replace("_", "-")


def facts(fam: str) -> dict:
    return json.loads((HERE / "instances" / fam / "facts.json").read_text())


def write(path: Path, text: str, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    mode = 0o755 if executable else 0o644
    path.chmod(mode)


def copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    dst.chmod(0o755 if src.suffix == ".sh" else 0o644)


def robot_words(fam: str) -> str:
    return ("two Franka Panda arms, each with a 16-DoF Allegro hand" if fam.startswith("bimanual_")
            else "a Franka Panda arm with a 16-DoF Allegro hand")


def robot_id(fam: str) -> str:
    return "franka-allegro-bimanual" if fam.startswith("bimanual_") else "franka-allegro"


# ------------------------------------------------------------------------------------------------- privileged mode
def priv_instruction(fam: str, F: dict) -> str:
    f = FAMILIES[fam]
    bim = fam.startswith("bimanual_")
    adim = 46 if bim else 23
    arm = '"right"'
    objs = ", ".join(f"`{k}`" for k in F["objects"])
    cam0 = "front" if "front" in F["cameras"] else F["cameras"][0]
    extra = ""
    if f.get("rcb_rule"):
        extra = f"\n\n{f['rcb_rule']}\n```python\nWATER_AIM_MAX_DEG = {F['water_aim_max_deg']}\n\n{F['rcb_src']}\n```"
    frame = (f"The table top is at z = {F['table_top_z']:.3f}. " if F["table_top_z"] is not None else "")
    frame += "Arm base (`link0`): " + ", ".join(f"{n} {v}" for n, v in F["arm_bases"].items()) + "."
    if bim:
        frame += " The right arm works at y < 0, the left arm at y > 0."
    return f"""# DexJoCo · {fam} — frozen instance

You control {robot_words(fam)} (DexJoCo on MuJoCo 3.4) via Python. **Task:** {f["goal"]}

{f["scene"]} `s.objects()` gives the live poses of the task objects ({objs}). DexJoCo's success code (from
`/opt/dexjoco/{F["success_path"]}`; `step()` ends the episode on success or on a task failure):
```python
{F["success_src"]}
```{extra}

This is a *fixed scene instance*: object poses, the table height and the robot's start pose never change between
resets. You may reset and retry as many times as you want. Your deliverable is **one replayable trajectory**, not a
general policy.

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below). It is replayed
open-loop from the same initial state in a fresh process and scored 1 if its episode ends in success, else 0. Also
leave the script that produced it at `/app/output/gen.py`. You have {AGENT_TIMEOUT // 60} minutes of wall clock: save a
first trajectory early, improve it, and do not stop before the task is solved.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_dexjoco import Session
s = Session("{fam}", instance="/app/instance.npz")   # ~1 s: builds the env and loads the frozen state
s.reset()                          # back to the frozen initial state (as often as you like; an exact snapshot restore)
s.objects()                        # live task objects: name -> pos, quat_wxyz (bodies) / pos (sites) / qpos (joints)
s.state()                          # DexJoCo's state dict: tcp_pose, gripper_pose (hand joints), INITIAL object poses, table height
p = s.primitives()                 # thin wrappers of the low-level action; each has a docstring: help(p["move_ee"])
p["move_ee"]({arm}, pos, quat_wxyz)      # straight-line + slerp motion of an arm's tcp target, then settle
p["set_hand"]({arm}, q16)                # interpolate the 16 Allegro joint targets
p["hold"](10); p["set_targets"](row, steps)            # keep every target / send one raw action row
p["get_ee_pose"]({arm}); p["get_ee_target"]({arm}); p["get_hand"]({arm}); p["get_body_pose"](name)
s.render_frame("{cam0}")            # RGB uint8 (480, 640, 3); cameras: {F["cameras"]}; s.render_grid()
s.step(action)                     # one control step ({adim} values, below) = 1/50 s; returns False once the episode is over
s.record_start(); ...; actions = s.record_stop()   # (T, {adim}) actions, one row per control step
s.status()                         # {{'success', 'done', 'reason', 'steps', 'resets', 'state_sha', 'info'}}
s.replay(actions)                  # resets, replays open-loop until the episode ends, returns status -> self-check
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_video(actions, "/app/output/check.mp4", cameras=["{cam0}"])   # replays from the frozen state into a video
```
The primitives are deliberately thin (tcp target moves, hand joint targets, hold): grasping, pressing, striking and
every other skill are yours to build from them. `s.bodies()` lists every MuJoCo body for `p["get_body_pose"]`.

CLI equivalent of the grader:
`python /opt/tools/rcb_dexjoco.py replay --task {fam} --instance /app/instance.npz --traj /app/output/trajectory.npz`

## Conventions
- World frame, metres; z up; the robot{"s" if bim else ""} stand{"" if bim else "s"} at low x and reach{"" if bim else "es"} towards +x. {frame} Quaternions are **WXYZ**.
- Action ({adim}): {"per arm, right first: " if bim else ""}tcp target position (3), tcp target orientation (4, wxyz), 16 Allegro
  joint targets (rad). The arm tracks the target through DexJoCo's operational-space controller (it lags a moving
  target and stops where contact blocks it); the hand joints are position-controlled. `s.hold_action()` is the no-op.
  At the start the tcp target is {F["tcp0"]}.
- Allegro joint order{" (right hand)" if bim else ""}: index finger 0-3, middle 4-7, ring 8-11, thumb 12-15 (joint 0 of a finger =
  spread, 1-3 = flexion from the knuckle out; thumb 12 = opposition).{" The LEFT hand's 16 values are mirrored: ring 0-3, middle 4-7, index 8-11, thumb 12-15." if bim else ""}
  Target ranges (rad, same for every finger slot, thumb last): low {F["hand_lo"]}, high {F["hand_hi"]}; the simulator clamps
  targets to them.
- Control runs at 50 Hz (10 physics substeps of 2 ms). DexJoCo's own episode cap and real-time pacing are lifted: there
  is no step budget, your wall-clock time is the limit (~{F["steps_per_s"]} control steps/s here). An episode ends at the
  first success or task failure; `s.step` then refuses further actions until `s.reset()`.
"""


def priv_readme(fam: str, F: dict) -> str:
    f = FAMILIES[fam]
    return f"""# dexjoco-{dash(fam)}-i00-privileged

## Task
DexJoCo `{fam}` ({robot_words(fam)}): {f["goal"]}
Privileged mode: the agent works in the simulator's container with live object poses, unlimited resets and thin motion
primitives, and hands in one trajectory replayed open-loop from the frozen instance.

## Difficulty
First-pass rating: {f["difficulty"]}. Dexterous manipulation with {"two 16-DoF hands on two arms (46 action values per control step)" if fam.startswith("bimanual_") else "a 16-DoF hand on a 7-DoF arm (23 action values per control step)"};
the primitives only move tcp and hand-joint targets, so grasping, pressing and every other skill is the agent's. The
reference (the human teleoperator's demonstration) takes {F["oracle_rows"]} control steps ({F["oracle_rows"] / 50:.1f} s at 50 Hz).

## Reference solution
`solution/oracle_trajectory.npz` = the human demonstration's own actions, rounded to float32 (the standard client's
precision; the rounded rows still succeed) and replayed from the frozen instance until the episode ends in success
({F["oracle_rows"]} rows). The demonstration is public (DexJoCo-Datasets-Raw on Hugging Face), so agent egress is
limited to the model APIs.

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.npz`, twice in a fresh process in the verifier's own
sandbox (no network); pass iff both episodes end in success, their final-state hashes agree and the rebuilt instance
matches its recorded hash (`tests/grade.py`); plus `/logs/verifier/replay.mp4`. Oracle: success after {F["oracle_rows"]} control steps.

## Details
| | |
|---|---|
| Upstream | DexJoCo @ 8d23b0f (brave-eai/dexjoco, MIT) on MuJoCo 3.4.0; CPU physics, OSMesa rendering, no GPU |
| Instance | the initial state of the human demonstration `{F["demo"]}` (DexJoCo-Datasets-Raw), restored with DexJoCo's own state restorer; instance sha `{F["instance_sha"]}` |
| Resources | 4 CPUs, 8 GB, no GPU |

### Tooling notes
DexJoCo's reset samples object poses from the global RNG and its state restorer edits the MuJoCo model (table height,
fixed bodies), so `instance.npz` stores the full physics state (`mjSTATE_INTEGRATION`), the mocap targets, the controls,
every numeric model array a task can change, and the env's Python-side task state. Its per-step camera rendering,
real-time sleep, episode cap and hanoi's wall-clock auto-reset are disabled in the tooling (`rcb_dexjoco.py`).

### Provenance
Generated by `scripts/dexjoco/generate.py` from `scripts/dexjoco/instances/{fam}/` (`make_instances.py`).
"""


def priv_toml(fam: str) -> str:
    f = FAMILIES[fam]
    return f"""# Generated by scripts/dexjoco/generate.py -- edit the generator or the instance, not this.
schema_version = "1.3"
artifacts = ["/app/output/"]

[task]
name = "robot-coding-bench/dexjoco-{dash(fam)}-i00-privileged"
description = "DexJoCo {fam} ({robot_words(fam)}, MuJoCo): produce one replayable trajectory. {f["goal"].split(". ")[0]}. Frozen scene instance (the initial state of a DexJoCo human demonstration)."
authors = [{{ name = "Chi Gui" }}]
keywords = ["robotics", "dexjoco", "mujoco", "allegro", "dexterous-manipulation", "code-as-policy", "trajectory", "{fam}"]

[metadata]
author_name = "Chi Gui"
task_type = "trajectory"
simulator = "dexjoco"
robot = "{robot_id(fam)}"
family = "{fam}"
mode = "privileged"
oracle = "full"
expert_time_estimate_hours = {f["hours"]}

[verifier]
timeout_sec = 1800.0
environment_mode = "separate"     # the verifier runs in its own sandbox (tests/Dockerfile); the agent container is gone by then
network_mode = "no-network"

[agent]
timeout_sec = {float(AGENT_TIMEOUT)}
network_mode = "allowlist"        # the reference demonstrations are public on Hugging Face (PROTOCOL §2.7)
allowed_hosts = {json.dumps(ALLOWED_HOSTS)}

[environment]
build_timeout_sec = 1800.0
cpus = 4
memory_mb = 8192

[verifier.environment]
build_timeout_sec = 1800.0
"""


PRIV_ENV_DOCKERFILE = f"""# Base image = DexJoCo on MuJoCo 3.4.0 (images/dexjoco/). Everything task-specific is copied here. CPU only.
FROM {IMAGE}
COPY instance.npz /app/instance.npz
COPY rcb_dexjoco.py /opt/tools/rcb_dexjoco.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
"""

PRIV_TESTS_DOCKERFILE = f"""# Separate verifier sandbox (PROTOCOL §2.6): the same simulator image with the verifier's own copies of the tooling and
# the frozen instance baked in. Nothing the agent did in its container reaches this one: Harbor uploads only the declared
# artifacts (/app/output/), so a patched success check in the agent container cannot count.
FROM {IMAGE}
COPY grade.py instance.npz rcb_dexjoco.py test.sh /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests
WORKDIR /tests
"""


def priv_test_sh(fam: str) -> str:
    return f"""#!/bin/bash
# Verifier: replay /app/output/trajectory.npz from the frozen instance (the tests/ copy) in a fresh process.
# Writes /logs/verifier/reward.txt (1/0) and reward.json (numeric fields, docs/PROTOCOL.md §2.6).
# Harbor also mounts /logs/verifier into the agent's container: start from an empty directory, so nothing the agent
# left there (a planted reward, a symlink) can count. rm never follows symlinks.
rm -rf /logs/verifier/*   # verdicts from an earlier run never survive (docs/PROTOCOL.md §2.6)
mkdir -p /logs/verifier
python /tests/grade.py --family {fam} --instance /tests/instance.npz --traj /app/output/trajectory.npz --repeat 2 \\
  2> /logs/verifier/grade.log
"""


PRIV_SOLVE = """#!/bin/bash
# Reference solution: the human demonstration's actions (float32), replayed through the task tooling until success.
set -e
mkdir -p /app/output
cp /solution/oracle_trajectory.npz /app/output/trajectory.npz
cp /solution/gen.py /app/output/gen.py
"""

PRIV_ORACLE_GEN = """# How solution/oracle_trajectory.npz was made (scripts/dexjoco/make_instances.py): the DexJoCo human demonstration's
# own actions (replay.zarr data/action), rounded to float32, replayed from the frozen instance with Session.replay until
# the episode ended in success (holding the last row a few steps where the rounded rows ended short of a hold count),
# truncated there and saved with Session.save_trajectory.
"""


# ------------------------------------------------------------------------------------------------- standard mode
def task_text(fam: str) -> str:
    f = FAMILIES[fam]
    return f"{f['goal']}\n\n{f['scene']}\n"


def std_instruction(fam: str, F: dict) -> str:
    f = FAMILIES[fam]
    bim = fam.startswith("bimanual_")
    dim = 46 if bim else 23
    hand_cams = [c for c in F["cameras"] if c.startswith("handcam")]
    static = [c for c in F["cameras"] if not c.startswith("handcam")]
    cam0 = "front" if "front" in static else static[0]
    tcp = "`tcp_right`, `tcp_left`" if bim else "`tcp`"
    return f"""# DexJoCo · {fam} — STANDARD MODE (robot as a service, eai-standard/2.2)

You control {robot_words(fam)}, **as if it were real hardware**: the simulator runs in a service you cannot open. You get
one client and one episode. **Task:** {f["goal"]}

{f["scene"]}

## Rules (real-robot rules)
- **No reset.** The episode starts when the service comes up and ends on success, on a task failure (see the task), when
  your time is up, or on a simulator error. Knocked-over objects stay knocked over.
- **No privileged state.** You see what the cameras see (RGB, and depth on request, with each camera's calibration) plus
  the robot's own proprioception (joints, tcp poses, the current targets). No object poses, no success check:
  `meta["done"]` / `meta["reason"]` tell you when the episode is over and why.
- Steps are unlimited; your wall-clock budget ({AGENT_TIMEOUT // 60} minutes) is the limit (`meta["time_left_s"]`). Actions and
  simulated time are reported as cost. Do not stop before the task is solved.
- There is nothing to hand in: the service records your episode as the trajectory and grades it. Leave your script at
  `/app/output/gen.py` for the record (save it early, update it as you go).
- **Nothing is put into your context automatically.** Images and videos come back as arrays/bytes in a Python object;
  what you look at and where you store it is your code's decision.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`)
```python
from rcb_client import Robot
r = Robot()                                   # connects (waits while the service starts)
spec = r.spec()                               # action types, cameras (+ calibration), proprio layout, robot_spec, kinematics, budget
obs = r.get_obs()                             # current frames of spec["default_cameras"]: obs.last[cam] -> uint8 (480, 640, 3)
obs = r.get_obs(cameras=["{cam0}"{', "' + hand_cams[0] + '"' if hand_cams else ""}], depth=True)   # + obs.last_depth[cam] -> float32 (480, 640) z-depth (m)
obs.meta["proprio"]                           # {{"layout": [...], "now": [...]}}; obs.group("tcp_pose", now=True)
obs.meta["cameras"]                           # per camera intrinsic_cv / extrinsic_cv / cam2world_gl for these frames
obs = r.get_obs(seconds=2.0, video="mp4")     # hold the current targets and watch for 2 s (max 30): obs.video[cam] = mp4 bytes

res = r.submit("ee_pose", rows, dt=0.1)       # rows: (T, {dim}) targets dt seconds apart, executed at 50 Hz with interpolation
res = r.submit("joint_position", q_rows, dt=0.1)   # (T, {dim}) joint targets instead (see below)
res.meta["done"], res.meta["reason"], res.meta["clipped"], res.meta["control_steps_chunk"]
res.video["{cam0}"]; res.last["{cam0}"]; res.proprio   # mp4 of the chunk, last frame, float32 (N, P) proprio per frame
res.save("/app/runs/003")                     # meta.json, <cam>.mp4, last/<cam>.jpg, proprio.npy, ...
r.fk(q); r.ik({{"{"tcp_right" if bim else "tcp"}": pose}}, seed=q)  # kinematics of the robot (stateless: no physics, no time)
r.status()                                    # calls, control steps, done, reason, elapsed time
```
Cameras: {", ".join(f"`{c}`" for c in static)} (static), {", ".join(f"`{c}`" for c in hand_cams)} (on the hand mount{"s" if bim else ""}; they move,
so use the calibration that comes with each response; `spec["cameras"][cam]["mount"]` gives the static pose or the mount
link). Resolution 640x480. Rendering runs on the CPU: ask only for the cameras you need; `video="none"` makes a chunk
fastest. If a call fails with a connection error the service may have crashed: it resumes the same episode;
`r.wait_ready()`, then check `r.status()` (`spec["on_service_error"]`).

### Action type `ee_pose` ({dim}) — DexJoCo's own action
{"Per arm, right first: " if bim else ""}tcp target position (3, metres, world frame), tcp target orientation (4, quaternion wxyz), 16
Allegro joint targets (rad). The arm tracks the target through DexJoCo's operational-space controller (it lags a moving
target and stops where contact blocks it); the hand joints are position-controlled. Rows are `dt` apart (a whole multiple
of 1/50 s, at most 0.5 s); between rows positions and joints move linearly and orientations by slerp
(`interpolate="linear"`) or jump (`"hold"`); a chunk may cover at most 10 s. Hand targets outside the ranges
(`spec["action_types"]["ee_pose"]["hand_limits"]`) are clamped by the simulator and listed in `meta["clipped"]`. Build
the next row from the `tcp_target` and `hand_target` proprio groups to move smoothly.

### Action type `joint_position` ({dim})
{"Per arm, right first: " if bim else ""}7 Panda joint targets, then the 16 Allegro joint targets (rad). The service turns the arm's targets
into a tcp target by forward kinematics and the same controller tracks it: the tcp reaches FK(q), but the measured arm
joints may differ from q in the arm's redundant direction (the controller's null space pulls towards a home posture).
Out-of-limit values are clipped and reported.

## Conventions
- World frame, metres, z up; the robot{"s" if bim else ""} stand{"" if bim else "s"} at low x and reach{"" if bim else "es"} towards +x{" (right arm at y < 0, left arm at y > 0)" if bim else ""}; each
  arm's base pose is in `spec["robot_spec"]["base"]`. No other world coordinates are given (D7: the cameras are
  calibrated, depth is available). Quaternions are **WXYZ**.
- The tcp ({tcp}) is the hand's mounting flange (`spec["robot_spec"]["tcp"]`), not the fingertips. Allegro joint
  order{" (right hand)" if bim else ""}: index finger 0-3, middle 4-7, ring 8-11, thumb 12-15 (joint 0 of a finger = spread, 1-3 = flexion
  from the knuckle out; thumb 12 = opposition).{" The LEFT hand's 16 values are mirrored: ring 0-3, middle 4-7, index 8-11, thumb 12-15 (the joint names in `spec[\"proprio_layout\"]` say which)." if bim else ""}
- Control runs at 50 Hz (10 physics substeps of 2 ms). There is no step budget: your wall-clock time is the limit.
"""


def std_readme(fam: str, F: dict) -> str:
    f = FAMILIES[fam]
    return f"""# dexjoco-{dash(fam)}-i00-standard

## Task
DexJoCo `{fam}` ({robot_words(fam)}) on the same frozen instance as `dexjoco-{dash(fam)}-i00-privileged`: {f["goal"]}
Standard mode (eai-standard/2.2): the agent drives the robot through a client in one episode, with the robot's own
sensors, calibrated cameras (RGB, optional depth) and the robot's kinematics.

## Difficulty
Same instance and success check as `dexjoco-{dash(fam)}-i00-privileged`. In standard mode the agent loses resets, the
simulator and the object poses: it sees camera images and proprioception, acts in chunks of tcp-target + hand-joint rows
(or joint targets), and gets one episode, so it has to close the loop on what the cameras show and recover from its own
mistakes without starting over.

## Reference solution
`solution/oracle_stream.py` streams the privileged reference's rows (`solution/oracle_trajectory.npz`, {F["oracle_rows"]} rows, float32-exact)
through the client as `ee_pose` chunks; it uses no privileged information at run time. The service's recorded
trajectory is then exactly the privileged reference, and the episode ends with success after {F["oracle_rows"]} control steps.

## Verification
The sim service judges the episode live and records every executed control step; the collect hook
(`environment/sim/finalize.sh`) ends the service, replays the recorded trajectory in two fresh processes and writes
`final.json`; `tests/grade.py` (separate sandbox, no network) passes iff the live check succeeded, both replays succeed,
and they end in the same state. Oracle: success after {F["oracle_rows"]} control steps.

## Details
| | |
|---|---|
| Upstream | DexJoCo @ 8d23b0f (brave-eai/dexjoco, MIT) on MuJoCo 3.4.0; CPU physics, OSMesa rendering, no GPU |
| Instance | the initial state of the human demonstration `{F["demo"]}` (DexJoCo-Datasets-Raw); instance sha `{F["instance_sha"]}` |
| Service | `environment/sim/server.py` (the adapter) on the shared 2.2 layer `rcb_limited.py` (`scripts/eai_standard/`); action types `ee_pose` and `joint_position`; cameras {", ".join(f"`{c}`" for c in F["cameras"])} (640 x 480); `/kinematics` for the arm links, the hand mount and the tcp; crash recovery class `exact` |
| Resources | 4 CPUs, 8 GB, no GPU |

### Provenance
Generated by `scripts/dexjoco/generate.py`, as its privileged twin.
"""


def std_toml(fam: str) -> str:
    f = FAMILIES[fam]
    return f"""# Generated by scripts/dexjoco/generate.py -- edit the generator or the instance, not this.
schema_version = "1.3"
artifacts = [
  {{ source = "/data/final.json", service = "sim" }},
  {{ source = "/data/episode.jsonl", service = "sim" }},
  {{ source = "/data/trajectory.npz", service = "sim" }},
  {{ source = "/data/replay.mp4", service = "sim" }},
  {{ source = "/data/server.log", service = "sim" }},            # the service's own output (Harbor keeps none)
  {{ source = "/data/journal.f64", service = "sim" }},           # crash recovery: every executed control step (float64 rows)
  {{ source = "/data/startups.jsonl", service = "sim" }},        # crash recovery: one line per service start
  {{ source = "/data/replay1.log", service = "sim" }},           # the collect hook's two fresh-process replays
  {{ source = "/data/replay2.log", service = "sim" }},
  {{ source = "/data/replay3.log", service = "sim" }},           # and its third, which renders replay.mp4
  "/app/output/",
]

[task]
name = "robot-coding-bench/dexjoco-{dash(fam)}-i00-standard"
description = "STANDARD MODE (robot as a service, eai-standard/2.2): DexJoCo {fam} ({robot_words(fam)}) on the same frozen instance as dexjoco-{dash(fam)}-i00-privileged. {f["goal"].split(". ")[0]}. The agent only gets a client: calibrated cameras (RGB, optional depth), the robot's joints and tcp poses, tcp-target + hand-joint chunks at 50 Hz, the robot's kinematics; one episode, no reset, no object state; the sim service records the episode, replays it in fresh processes and grades it."
authors = [{{ name = "Chi Gui" }}]
keywords = ["robotics", "dexjoco", "mujoco", "allegro", "dexterous-manipulation", "standard-mode", "robot-as-a-service", "{fam}"]

[metadata]
author_name = "Chi Gui"
task_type = "trajectory"
simulator = "dexjoco"
robot = "{robot_id(fam)}"
family = "{fam}"
mode = "standard"
protocol = "eai-standard/2.2"
oracle = "full"
expert_time_estimate_hours = {f["hours"]}

[verifier]
timeout_sec = 600.0
environment_mode = "separate"
network_mode = "no-network"

[[verifier.collect]]
service = "sim"
command = "sh /srv/finalize.sh"   # end + dump + exit the service, replay twice in fresh processes, write final.json, video
timeout_sec = 3600

[agent]
timeout_sec = {float(AGENT_TIMEOUT)}
network_mode = "allowlist"        # the reference demonstrations are public on Hugging Face (PROTOCOL §2.7)
allowed_hosts = {json.dumps(ALLOWED_HOSTS)}

[environment]
build_timeout_sec = 1800.0
cpus = 4
memory_mb = 8192
"""


def std_compose(fam: str) -> str:
    return f"""# Standard mode: the simulator runs in the `sim` sidecar (the agent cannot open it); the agent only reaches port 8000.
# No `expose`/`ports` on sim: under Harbor's egress control it shares main's network namespace (localhost:8000).
# CPU only: MuJoCo physics and OSMesa rendering; no GPU reservation.
# Crash recovery (docs/STANDARD_MODE_2_2.md §13): run.sh exits non-zero when the service crashes, compose restarts the
# container (same container, same /data) and the service replays its journal into the same episode, never a reset.
services:
  main:
    depends_on: [sim]
  sim:
    image: {IMAGE}
    volumes:
      - ./sim:/srv:ro
    working_dir: /tmp
    command: sh /srv/run.sh
    restart: on-failure:6          # N >= 3 (PROTOCOL §4.1); a resume continues the episode
    environment:
      RCB_TASK: {fam}
      RCB_INSTANCE: /srv/instance.npz
      RCB_TOOL: /srv/rcb_dexjoco.py
      RCB_DATA: /data
      RCB_WALL_CLOCK_S: "{AGENT_TIMEOUT}"
      RCB_STARTUP_TIMEOUT_S: "300"   # the scene builds in a few seconds
      PYTHONPATH: /srv
      RCB_SESSION_LOG: ""           # the sidecar's own Session must not write the agent-side interaction log
"""


STD_ENV_DOCKERFILE = f"""# Standard mode: the agent container has NO simulator and no DexJoCo code, only Python and the client, on the shared
# pinned client base with the shared pins (scripts/eai_standard/client.env, client-requirements.txt).
FROM {CLIENT_IMAGE}
COPY client-requirements.txt /tmp/client-requirements.txt
RUN pip install --no-cache-dir -r /tmp/client-requirements.txt
COPY rcb_client.py rcb1.py /opt/tools/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
"""

STD_TESTS_DOCKERFILE = f"""# Separate verifier sandbox: grades the sim service's own artifacts; needs nothing but python (the shared client base).
FROM {CLIENT_IMAGE}
COPY test.sh /tests/test.sh
COPY grade.py /tests/grade.py
RUN chmod +x /tests/test.sh
"""

STD_TEST_SH = """#!/bin/bash
# Verifier (separate sandbox): the sim sidecar's artifacts were uploaded to /data by Harbor.
# Harbor also mounts /logs/verifier into the agent's container: start from an empty directory, so nothing the agent
# left there (a planted reward, a symlink) can count. rm never follows symlinks.
rm -rf /logs/verifier/*   # verdicts from an earlier run never survive (docs/PROTOCOL.md §2.6)
mkdir -p /logs/verifier
python /tests/grade.py 2> /logs/verifier/grade.log
"""

STD_SOLVE = """#!/bin/bash
# Oracle (standard mode): streams the reference trajectory's rows (solution/oracle_trajectory.npz, one row per control
# step) as `ee_pose` chunks through the client. Uses no privileged information at run time (only the pre-recorded rows);
# the service's recorded trajectory is then exactly the privileged reference.
set -e
mkdir -p /app/output
cp /solution/oracle_stream.py /app/output/gen.py
python /solution/oracle_stream.py
"""


# ------------------------------------------------------------------------------------------------- rendering
def render(root: Path) -> list[Path]:
    out = []
    for fam in FAMILIES:
        F = facts(fam)
        inst = HERE / "instances" / fam
        # privileged
        t = root / f"dexjoco-{dash(fam)}-i00-privileged"
        if t.exists():
            shutil.rmtree(t)
        write(t / "task.toml", priv_toml(fam))
        write(t / "instruction.md", priv_instruction(fam, F))
        write(t / "README.md", priv_readme(fam, F))
        write(t / "environment" / "Dockerfile", PRIV_ENV_DOCKERFILE)
        write(t / "tests" / "Dockerfile", PRIV_TESTS_DOCKERFILE)
        write(t / "tests" / "test.sh", priv_test_sh(fam), executable=True)
        write(t / "solution" / "solve.sh", PRIV_SOLVE, executable=True)
        write(t / "solution" / "gen.py", PRIV_ORACLE_GEN)
        for sub in ("environment", "tests"):
            copy(inst / "instance.npz", t / sub / "instance.npz")
            copy(SHARED / "rcb_dexjoco.py", t / sub / "rcb_dexjoco.py")
        copy(SHARED / "grade.py", t / "tests" / "grade.py")
        copy(inst / "oracle_trajectory.npz", t / "solution" / "oracle_trajectory.npz")
        out.append(t)
        # standard
        t = root / f"dexjoco-{dash(fam)}-i00-standard"
        if t.exists():
            shutil.rmtree(t)
        write(t / "task.toml", std_toml(fam))
        write(t / "instruction.md", std_instruction(fam, F))
        write(t / "README.md", std_readme(fam, F))
        write(t / "environment" / "Dockerfile", STD_ENV_DOCKERFILE)
        write(t / "environment" / "docker-compose.yaml", std_compose(fam))
        copy(LAYER / CLIENT_ENV.get("CLIENT_REQUIREMENTS", "client-requirements.txt").strip(), t / "environment" / "client-requirements.txt")
        for f in ("rcb_client.py", "rcb1.py"):
            copy(LAYER / f, t / "environment" / f)
        sim = t / "environment" / "sim"
        for f in ("rcb_limited.py", "rcb1.py", "run.sh"):
            copy(LAYER / f, sim / f)
        for f in ("server.py", "finalize.sh"):
            copy(SHARED / "standard" / f, sim / f)
        copy(SHARED / "rcb_dexjoco.py", sim / "rcb_dexjoco.py")
        copy(inst / "instance.npz", sim / "instance.npz")
        write(sim / "task_text.txt", task_text(fam))
        write(t / "tests" / "Dockerfile", STD_TESTS_DOCKERFILE)
        write(t / "tests" / "test.sh", STD_TEST_SH, executable=True)
        copy(SHARED / "standard" / "grade.py", t / "tests" / "grade.py")
        write(t / "solution" / "solve.sh", STD_SOLVE, executable=True)
        copy(SHARED / "standard" / "oracle_stream.py", t / "solution" / "oracle_stream.py")
        copy(inst / "oracle_trajectory.npz", t / "solution" / "oracle_trajectory.npz")
        out.append(t)
    for t in out:
        normalize(t)
    return out


def tree(d: Path) -> dict:
    # contents and the executable bit (git keeps only that; the rest of the mode follows the checkout's umask)
    return {str(p.relative_to(d)): (p.read_bytes(), bool(p.stat().st_mode & 0o100)) for p in sorted(d.rglob("*")) if p.is_file()}


def main() -> int:
    if "--check" in sys.argv[1:]:
        with tempfile.TemporaryDirectory() as td:
            got = render(Path(td))
            bad = [t.name for t in got if tree(t) != (tree(ROOT / "tasks" / t.name) if (ROOT / "tasks" / t.name).is_dir() else {})]
            extra = sorted(p.name for p in (ROOT / "tasks").glob("dexjoco-*") if p.name not in {t.name for t in got})
        for n in bad:
            print(f"FAIL tasks/{n}: differs from the generator's output (run scripts/dexjoco/generate.py)")
        for n in extra:
            print(f"FAIL tasks/{n}: not written by the generator")
        print(f"checked {len(got)} DexJoCo task dirs: {len(bad) + len(extra)} difference(s)")
        return 1 if bad or extra else 0
    got = render(ROOT / "tasks")
    print(f"wrote {len(got)} task dirs")
    return 0


if __name__ == "__main__":
    filecmp.clear_cache()
    sys.exit(main())
