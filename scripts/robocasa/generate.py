#!/usr/bin/env python3
"""Generate this benchmark's tasks: tasks/<bench>-<slug>-i00-privileged and tasks/<bench>-<slug>-i00-standard.

    python3 scripts/<bench>/generate.py            # every verified environment in frozen/report.json
    python3 scripts/<bench>/generate.py PreSoakPan
    python3 scripts/<bench>/generate.py --check    # render into a temporary directory and compare with tasks/

Inputs: envs.py, frozen/<slug>/{instance,oracle}.npz and frozen/report.json (import_references.sh), the shared sources
in shared/ (with the collect hook finalize.sh) and the standard-mode service images/<bench>/standard/server_casa.py.
Every task directory is rewritten; shared files are copied byte for byte. Re-running reproduces the tasks exactly.
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(ROOT / "scripts"))
from envs import SOURCES, SUCCESS, slug  # noqa: E402
from task_conventions import cutoff_sec, normalize  # noqa: E402  (protocol v1.0 conventions, as main's generators)

# -- benchmark configuration -----------------------------------------------------------------------------------
BENCH = HERE.name
TITLE = "RoboCasa"
UPSTREAM = "[RoboCasa](https://github.com/robocasa/robocasa) @ 756598a (v0.2; MIT), robosuite 1.5.1, MuJoCo 3.2.6"
ROBOT = "franka-panda-omron"
ROBOT_TEXT = "a **Franka Panda arm on an Omron mobile base** (with a torso lift)"
ENV_DOC = "RoboCasa's `{env}` kitchen task"
SCENE = "works in a kitchen"
KEYWORDS = '"robotics", "robosuite", "{bench}", "mobile-manipulation", "code-as-policy", "trajectory"'
DIFFICULTY_PRIVILEGED = (
    "Full privileged state, unlimited resets and self-replay; a mobile manipulator in a cluttered kitchen, long-horizon\n"
    "contact-rich manipulation with a 20 Hz controller. The standard twin removes the privileged state."
)
DIFFICULTY_STANDARD = (
    "The agent has to find the fixtures and objects in the robot's camera images, drive a mobile manipulator with its "
    "native\ncontroller, and finish in one episode without a reset."
)
# -----------------------------------------------------------------------------------------------------------------

SHARED = HERE / "shared"
FROZEN = HERE / "frozen"
SERVER = ROOT / f"images/{BENCH}/standard/server_casa.py"
VERSION = (ROOT / f"images/{BENCH}/VERSION").read_text().strip()
IMAGE = f"ghcr.io/mll-lab-nu/eai-{BENCH}:{VERSION}"
# Standard-mode client image (agent container and verifier): pinned by digest, pinned pip versions.
CLIENT_BASE = (
    "docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f"
)
CLIENT_PIP = (
    "certifi==2026.7.22 charset-normalizer==3.5.2 idna==3.20 numpy==2.5.3 pillow==12.3.0 requests==2.34.2 "
    "scipy==1.18.1 urllib3==2.8.0"
)
AUTHOR = "Changhe Chen"
ORG = "MLL Lab"
MAX_STEPS = 3000
ALLOWED_HOSTS = (
    '["chatgpt.com", "*.chatgpt.com", "auth.openai.com", "api.openai.com", "*.openai.com", "api.anthropic.com", '
    '"*.anthropic.com", "openrouter.ai", "*.openai.azure.com", "*.cognitiveservices.azure.com", "pypi.org", "files.pythonhosted.org", "deb.debian.org", "security.debian.org", "archive.ubuntu.com", "security.ubuntu.com", "snapshot.ubuntu.com"]'
)
# `[agent] timeout_sec` is the cutoff table's number for the mode (scripts/task_cutoffs.toml, PROTOCOL §2.12);
# normalize writes the same number again, with the instruction's closing `## Time limit` section and the sim service's wall clock.
def agent_block(mode: str) -> str:
    return f"""[agent]
timeout_sec = {cutoff_sec(TITLE, mode)}.0
# The benchmark's demonstrations solve these tasks and are publicly downloadable, so egress is closed to everything but the model APIs and the package registries.
network_mode = "allowlist"      # model APIs and package registries (scripts/set_agent_egress.py); PROTOCOL §2.11
allowed_hosts = {ALLOWED_HOSTS}
"""


ACTION_TYPE = {12: "ee_delta", 13: "joint_position", 24: "ee_pose"}
# Standard mode, the sim service's collect hook (shared/finalize.sh): its timeout, and how long it waits for the verdict
# (the script's default RCB_COLLECT_WAIT_S; main() checks that the two agree). A number of its own, not the agent's
# cutoff: it was sized for the replay of an episode as long as a 3600 s agent time limit. Lowering the cutoff
# (scripts/task_cutoffs.toml) keeps it safe; look at it when the cutoff is raised (docs/CUTOFFS.md).
COLLECT_TIMEOUT_S = 3600
COLLECT_WAIT_S = 3450
# README Change Log of the standard tasks (PROTOCOL §2.8: published tasks are fixed in place), oldest first.
CHANGES_STANDARD = [
    "2026-10-10: the sim service writes its verdict together with `finalized` in one atomic step and renders the "
    "replay video only afterwards (the video is optional and can no longer turn a verdict into `infra_error`; a "
    "restart never rewrites a written verdict); the collect hook (`environment/sim/finalize.sh`) waits for that "
    f"verdict for up to {COLLECT_WAIT_S} s of a {COLLECT_TIMEOUT_S} s timeout (before: 980 s of 1500 s, video "
    "included, which lost episodes longer than about 10,000 control steps); a malformed request field (`dt`, "
    "`seconds` or `video_fps` that is not a finite number, `cameras` or `note` of the wrong type, `dt` = 0, ...) is "
    "answered with 400 before any physics instead of 500 and the end of the episode; `time_left_s` counts from the "
    "start of the service's container, not from when its scene was built; the client's docstring describes this "
    "service. The scene, the instance, the success check and the pass rule are unchanged, so the task keeps its name.",
    "2026-10-10 (review round 2, board 0067): `tests/grade.py` only. A `final.json` that cannot be read as a JSON object "
    "(truncated, not JSON, not an object) is graded `infra_error = 1` and `grader_error = 1`; before, the grader raised "
    "and the trial had no reward file. Nothing else changes: a readable `final.json` is graded as before.",
    "2026-10-10 (review round 3, board 0067): the sim service's request handling "
    "(`environment/sim/server_casa.py`) and `tests/grade.py`. A negative or non-numeric `Content-Length` is "
    "answered 400 without reading the body (the service read until the client hung up, without a bound, which "
    "could exhaust its memory); a camera named more than once in `cameras` is rendered and returned once (N copies "
    "of one name made it build N x N images within the frame budget); a port that is still held when the service "
    "restarts is waited for, not counted as a crash; a JSON `true` or `false` where `dt` or `seconds` takes a "
    "number is a 400 (`true` ran as 1 second). The grader: a `final.json` whose evidence fields (`control_steps`, "
    "`calls`, `elapsed_s`, `final_reward`) are not numbers no longer stops it before it writes a reward (they are "
    "reported as 0 and decide nothing). An episode's physics and the pass rule are unchanged.",
    "2026-10-13 (owner, boards 0085 and 0087): the sim service's clock (`environment/sim/server_casa.py`, the "
    "docstring of `environment/rcb_client.py`). `meta[\"time_s\"]` and `meta[\"time_left_s\"]` count from the agent's "
    "first request to the service (any endpoint), and a restarted service keeps that moment; before, they counted "
    "from the first start of the service's container (`time_left_s`) and from when its scene was ready (`time_s`). "
    "Where the service is ready before the agent's phase begins (the harness is installed in between: a median of 79 "
    "s over the recorded standard trials), that clock ran ahead of the agent's and `time_left_s` reached 0 while the "
    "agent still had that time. `/spec` says what the clock counts from (`budget.clock`), and the instruction's `## "
    "Time limit` tells the agent to plan by `time_left_s`. The service never ended an episode on this clock: the "
    "scene, the frozen instance, the pass rule and the grader are unchanged, so the task keeps its name and earlier "
    "results stand.",
    "2026-10-13 (board 0093; found in board 0086): the camera calibration (`environment/sim/server_casa.py`). "
    "`cam2world_gl` held the pose of MuJoCo's left-eye camera (`scene.camera[0]`), 3.4 cm (half the model's 0.068 m "
    "interpupillary distance) to the camera's left of the viewpoint the mono RGB and depth images are rendered from; it "
    "now is that viewpoint (`data.cam_xpos` / `data.cam_xmat`). Checked against MuJoCo's own renders of marker spheres "
    "at known world points, every served camera, before and after the robot moved: the reprojection error was 10.5-10.7 px "
    "median (up to 28 px for near points, always to the same side), now 0.15 px median and at most 0.4 px. The "
    "intrinsics were right (every camera here is given by its `fovy`, none by a sensor size) and are unchanged, as are "
    "the images, the scene, the frozen instance, the pass rule and the grader, so the task keeps its name. **Standard-"
    "mode results from before this date used the offset calibration**: a point located from the images and the "
    "reported calibration came out about 3.4 cm to the side (agents missed a microwave button by 3.5 cm), so they are "
    "not strictly comparable with later ones.",
]


def action_text(dim: int) -> str:
    """The native controller's channels, as both instructions state them."""
    if dim == 12:
        return (
            "12 channels, in order: `arm_dx, arm_dy, arm_dz, arm_drx, arm_dry, arm_drz` -- the end effector's motion "
            "per control step in the robot's base frame, scaled by the controller (1.0 = 5 cm and 0.5 rad per step); "
            "`grip` (+1 closes, -1 opens); `base_x, base_y, base_yaw` -- the mobile base's target velocities in its own "
            "frame (1.0 = 1 m/s for `base_x` / `base_y` and 1.5 rad/s for `base_yaw`; force-limited velocity servos, so "
            "the base may lag the target); `torso` -- the torso lift, a joint-position controller with delta input "
            "(each step sets the lift's height target to its current height + 0.05 m × the value, so 1.0 = 5 cm per "
            "step; lift range 0–0.34 m); `hybrid_mode` (> 0: base mode, the arm's goal moves with the base; "
            "<= 0: arm mode, the default -1). Every channel is clipped to [-1, 1]."
        )
    if dim == 13:
        return (
            "13 channels, in order: `arm_joint1 .. arm_joint7` -- absolute joint position targets (rad, within the "
            "joint limits in `s.action_spec`); `grip` (+1 closes, -1 opens); `base_x, base_y, base_yaw` -- the mobile "
            "base's velocities in its own frame (normalised, [-1, 1]); `torso` -- the torso lift's velocity; "
            "`hybrid_mode` (> 0: base mode; <= 0: arm mode, the default -1). Values are clipped to the limits."
        )
    return (
        "24 channels, in order: the right then the left hand's grip-site pose target `x, y, z, rx, ry, rz` -- absolute, "
        "in the robot's base frame (metres, axis-angle radians), reached by the whole-body inverse-kinematics "
        "controller (mink), limits [-10, 10]; then six commands per hand (right, then left) in the finger order "
        "`little, ring, middle, index, thumb_flexion, thumb_rotation` -- unscaled Fourier hand commands in [-3, 3], not "
        "a binary grip. The GR1 has no mobile base. Values are clipped to the limits."
    )


def sentence(text: str) -> str:
    """The upstream instruction as a sentence: capital first letter, full stop (RoboCasa's single-stage texts have neither)."""
    text = text.strip()
    text = text[:1].upper() + text[1:]
    return text if text.endswith((".", "!", "?")) else text + "."


def success_text(rec: dict) -> str:
    """What the environment's success check requires, as a list (envs.SUCCESS, from the upstream predicate)."""
    conds = SUCCESS[rec["env"]]
    items = "\n".join(f"- {c[:1].upper() + c[1:]}." for c in conds)
    note = ""
    if any("centre" in c or "touches" in c for c in conds):
        note = 'A "centre" is a body\'s origin; "touches" means a MuJoCo contact.\n'
    return f"What `{rec['env']}`'s check requires (RoboCasa @ 756598a), all on that final state:\n{items}\n{note}"


def hold_note(rec: dict) -> str:
    if rec["success_after_hold"]:
        return ""
    return (
        "\nIn this environment the success state does not persist on its own: after the reference's last action, "
        "holding still for 10 control steps loses it. Graded on the final state, a trajectory must end at that moment.\n"
    )


def privileged_instruction(rec: dict) -> str:
    env, dim = rec["env"], rec["action_dim"]
    return f"""# {TITLE} · {env}

{ROBOT_TEXT[0].upper() + ROBOT_TEXT[1:]} {SCENE}: {ENV_DOC.format(env=env)} (robosuite, MuJoCo).
**Task: {sentence(rec["instruction"])}**
The scene is one frozen instance: the initial state of one of the benchmark's official demonstrations (kitchen
layout, style, fixtures, objects and their poses).

## What you hand in
`/app/output/trajectory.npz` with key `actions`: the robot's native controller commands, shape `(T, {dim})` with
1 ≤ T ≤ {MAX_STEPS}, one row per control step (1/20 s). Write it with `s.save_trajectory()` so the format is right.
Leave the script that produced it at `/app/output/gen.py`.

## Success
The verifier replays your actions from the frozen start in a separate sandbox (twice, in fresh processes; MuJoCo on the
CPU is bit-exact) and applies the environment's own success check for `{env}` (`_check_success`) to the state **after
the last action**. A success reached earlier and then lost does not count: end the trajectory while the task is
achieved. `s.check()` returns the check's latest result.

{success_text(rec)}
## Tooling (`/opt/tools/casa_tool.py`, importable as `casa_tool`)
```python
import numpy as np, casa_tool
s = casa_tool.Session("/app/instance.npz")  # the frozen instance; s.env is the robosuite env, s.model / s.data MuJoCo
s.action_spec        # every channel: name, unit, kind (delta | absolute | grip | mode), lower / upper; frames
st = s.state()       # instruction, qpos, qvel, joint_names, bodies {{name: pos, quat_wxyz}}, objects, proprio, success
r = s.step(action)   # one control step -> {{"success": ..., "control_steps": ..., ...}}
s.check()            # the success check's latest result
s.save_trajectory()  # the actions since the last reset -> /app/output/trajectory.npz
s.replay(A)          # reset, then replay A (what the verifier does) -> {{"success": ..., "state_sha": ...}}
s.reset()            # back to the frozen start, as often as you like (it takes a few seconds)
img = s.render("robot0_agentview_center")   # RGB (240, 320, 3); views in s.camera_views; s.render_grid()
```
- Actions: {action_text(dim)}
- The success check runs twice after every control step and once at reset, in your session exactly as in the
  verifier. Some checks count consecutive successful steps, so calling `s.env._check_success()` yourself changes the
  state of the run you are recording; use `s.check()`.
- World frame: metres, z up; `s.state()["bodies"]` gives every body's position and orientation (quaternions w x y z).
- Everything in `s.env`, `s.model` and `s.data` is readable (privileged mode).

## Rules
- Write your own controller. Do not use the benchmark's demonstrations, trained policies or any published solution.
- Only the actions count: editing `s.data` or the environment while debugging changes nothing in the replay.
- Save a working trajectory early, then improve it; do not stop early.
"""


def standard_instruction(rec: dict) -> str:
    env, dim = rec["env"], rec["action_dim"]
    cams = ", ".join(rec["cameras"])
    return f"""# {TITLE} · {env} — STANDARD MODE (robot as a service)

{ROBOT_TEXT[0].upper() + ROBOT_TEXT[1:]} {SCENE}: {ENV_DOC.format(env=env)} (robosuite, MuJoCo).
**Task: {sentence(rec["instruction"])}**
The scene is one frozen instance: the initial state of one of the benchmark's official demonstrations.

You control the robot **as if it were real hardware**: the simulator runs in a service you cannot open. You get one
client and one episode.

## Rules (real-robot rules)
- **No reset.** What you knock over stays knocked over.
- **No privileged state.** You see what the robot's cameras see (RGB, optional depth, with each camera's
  calibration) and the robot's own state. No object poses, no scene layout, no success signal.
- Your only budget is the time limit (`## Time limit`; `meta["time_left_s"]` is the service's count of it). There is nothing
  to hand in: the service records the episode as the trajectory and grades it. Leave your script at
  `/app/output/gen.py` for the record.
- Do not use the benchmark's demonstrations, trained policies or any published solution; write your own controller.
- Images come back as arrays in a Python object; what you look at and where you store it is up to your code.

## Scoring
The episode runs until your time is up. The service then replays the recorded episode in a fresh simulator and applies
the environment's own success check for `{env}` to the state **after the last executed control step**; it must hold
in the live episode and in the replay. A success reached earlier and then lost does not count: end in the state you
want graded and stop submitting.

{success_text(rec)}
## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`)
```python
from rcb_client import Robot
r = Robot()                                   # connects (waits while the service starts: about a minute)
spec = r.spec()                               # control_dt, action layout + limits + kinds, cameras, proprio layout, budget
cams = list(spec["cameras"])                  # {cams}
obs = r.get_obs(cameras=cams, include_depth=True)   # obs.last[cam] -> uint8 (240, 320, 3); obs.depth[cam] -> metres
obs.meta["proprio"]                           # {{"layout": [...], "now": [...]}}: joints, end effector, last command
obs.meta["cameras"]                           # per camera: intrinsic_cv, cam2world_gl (OpenGL: looks along -z), current
obs = r.get_obs(cameras=cams[:1], seconds=2.0, video="mp4")    # hold still and watch for 2 s (max 30)
res = r.submit("{ACTION_TYPE[dim]}", A, cameras=cams[:1], video="mp4")   # A: (T, {dim}) rows, one per control step
res.meta["done"], res.meta["reason"], res.meta["control_steps"]
res.video[cam]; res.frames[cam]; res.last[cam]; res.proprio; res.save("/app/runs/003")
```
- Action `{ACTION_TYPE[dim]}`: the robot's native controller command, applied once per control step (`control_dt` =
  0.05 s; float64). {action_text(dim)} Rows are `dt` apart (default and minimum: `control_dt`; a chunk covers at
  most 10 s).
- `get_obs(seconds=s)` holds the robot still (delta channels zero, targets, grip and mode kept) while physics runs
  for `s` seconds; those control steps are part of the episode.
- The cameras are mounted on the robot and move with it: use the calibration that comes with each response.
- World frame: metres, z up.
"""


def readme_head(rec: dict, mode: str) -> list[str]:
    """Title and key table in the standard layout (docs/PROTOCOL.md §2.1; the format of scripts/task_conventions.py)."""
    base = f"{BENCH}-{rec['slug']}-i00"
    name, twin = (
        (f"{base}-privileged", f"{base}-standard")
        if mode == "privileged"
        else (f"{base}-standard", f"{base}-privileged")
    )
    image = IMAGE  # privileged: the environment's FROM; standard: the sim service's image
    rows = [
        ("Benchmark", TITLE),
        ("Mode", "privileged" if mode == "privileged" else "standard (`eai-standard/2.1`)"),
        ("Twin", f"`{twin}`"),
        ("Simulator / robot", f"`robosuite` / `{ROBOT}`"),
        ("Family / instance", f"`{BENCH}/{rec['env']}`"),
        ("Oracle", "`full`"),
        ("Agent time budget", f"{cutoff_sec(TITLE, mode)} s; tokens: protocol default (PROTOCOL §5)"),
        ("Base image", f"`{image}`"),
    ]
    return [f"# {name}", "", "| | |", "|---|---|"] + [f"| {k} | {v} |" for k, v in rows]


def readme(head: list[str], task: str, difficulty: str, reference: str, verification: str, details: list) -> str:
    out = head + ["", "## Task", task.strip(), "", "## Difficulty", difficulty.strip(), "", "## Reference solution"]
    out += [reference.strip(), "", "## Verification", verification.strip(), "", "## Details", "| | |", "|---|---|"]
    out += [f"| {k} | {v} |" for k, v in details]
    return "\n".join(out) + "\n"


def privileged_readme(rec: dict) -> str:
    env = rec["env"]
    demo = rec.get("demonstration") or {}
    cut = " (cut at its first success)" if rec["truncated"] else ""
    task = (
        f"{ENV_DOC.format(env=env)} with {ROBOT_TEXT.replace('**', '')}: {sentence(rec['instruction'])} Produce one replayable "
        "trajectory of the robot's native controller commands on one frozen instance; graded on the state after the "
        f"last action. Generated by `scripts/{BENCH}/generate.py`; benchmark notes in `docs/benchmarks/{BENCH}.md`."
    )
    reference = (
        f"The demonstration's own actions ({rec.get('reference_method')}: {rec['reference_actions']} actions), executed "
        f"from the frozen scene by the robot's own controller: {rec['n_actions']} actions{cut} in `solution/oracle.npz`. "
        "The demonstration is a reference solution: it is not in the image and the agent cannot reach it."
        + hold_note(rec).replace("\n", " ").rstrip()
    )
    verification = (
        "`tests/grade.py` in a separate sandbox without network: two replays in fresh processes from the verifier's own "
        "copy of the instance; `success = deterministic ∧ success on the final state ∧ not solved at the start`. "
        f"Reference: two fresh-process replays end in the live run's state (hash `{rec['live_state_sha'][:12]}…`) and "
        "succeed. `nop`: no trajectory, reward 0; the instance is not solved at the start."
    )
    details = [
        ("Source", f"{UPSTREAM}; [environment source]({rec.get('environment_source')})"),
        (
            "Instance",
            f"the initial state of official demonstration episode {demo.get('episode')} (`{demo.get('demo')}`, "
            f"{rec.get('demonstration_path')}); MuJoCo state, model arrays, task state and RNG frozen in `instance.npz` "
            f"(SHA-256 `{rec['instance_sha'][:12]}…`, checked on load)",
        ),
        ("Deliverable", f"`(T, {rec['action_dim']})` native controller commands, 1 ≤ T ≤ {MAX_STEPS}, 20 Hz"),
        ("Success", "the environment's own check (`_check_success`) on the state after the last action"),
    ]
    return readme(
        readme_head(rec, "privileged"), task, DIFFICULTY_PRIVILEGED.replace("\n", " "), reference, verification, details
    )


def standard_readme(rec: dict) -> str:
    base = f"{BENCH}-{rec['slug']}-i00"
    task = (
        f"Standard mode (robot as a service, `eai-standard/2.1`) of `{base}-privileged`: the same frozen instance and "
        f"success check, served by the `sim` sidecar (`images/{BENCH}/standard/server_casa.py`, tool module "
        "`casa_tool`), which records the episode, replays it in a fresh simulator and judges it; the verifier grades "
        "the sidecar's record in a container of its own. The agent sees the robot's cameras (RGB-D, calibrated), its "
        "own joints and end effector, and the instruction."
    )
    reference = (
        f"`solution/`: the privileged reference's {rec['n_actions']} actions submitted through the client, one row per "
        "control step." + hold_note(rec).replace("\n", " ").rstrip()
    )
    verification = (
        "The sim service replays the recorded episode in a fresh simulator and writes the verdict, final at once; "
        "`tests/grade.py` (separate sandbox, no network) reads its `final.json`: `success = replay_success ∧ "
        "deterministic ∧ live_success`. The replay video is rendered after the verdict and never decides it."
    )
    details = [
        ("Action type", f"`{ACTION_TYPE[rec['action_dim']]}` ({rec['action_dim']} channels, `control_dt` 0.05 s)"),
        ("Cameras", ", ".join(f"`{c}`" for c in rec["cameras"]) + " (robot-mounted; calibration in every response)"),
    ]
    text = readme(
        readme_head(rec, "standard"), task, DIFFICULTY_STANDARD.replace("\n", " "), reference, verification, details
    )
    return text + "\n### Change Log\n" + "".join(f"- {c}\n" for c in CHANGES_STANDARD)


def privileged_toml(rec: dict) -> str:
    return f"""schema_version = "1.3"
artifacts = ["/app/output/"]

[task]
name = "robot-coding-bench/{BENCH}-{rec["slug"]}-i00-privileged"
description = "{TITLE} ({rec["env"]}, {ROBOT_TEXT.replace("**", "")}): {sentence(rec["instruction"])} Produce one replayable trajectory of the robot's native controller commands on a frozen instance; graded on the state after the last action."
authors = [{{ name = "{AUTHOR}" }}]
keywords = [{KEYWORDS.format(bench=BENCH)}, "privileged"]

[metadata]
author_name = "{AUTHOR}"
author_org = "{ORG}"
task_type = "trajectory"
simulator = "robosuite"
robot = "{ROBOT}"
family = "{BENCH}/{rec["env"]}"
mode = "privileged"
oracle = "full"
expert_time_estimate_hours = 2.0

[verifier]
timeout_sec = 1800.0
environment_mode = "separate"
network_mode = "no-network"

{agent_block("privileged")}
[environment]
build_timeout_sec = 1800.0
cpus = 4
memory_mb = 16384

[verifier.environment]
build_timeout_sec = 1800.0
cpus = 4
memory_mb = 16384
"""


def standard_toml(rec: dict) -> str:
    return f"""schema_version = "1.3"
artifacts = [
  {{ source = "/data/final.json", service = "sim" }},
  {{ source = "/data/episode.jsonl", service = "sim" }},
  {{ source = "/data/trajectory.npz", service = "sim" }},
  {{ source = "/data/replay.mp4", service = "sim" }},
  {{ source = "/data/replay.last.png", service = "sim" }},
  {{ source = "/data/calls/", service = "sim" }},
  {{ source = "/data/startups.jsonl", service = "sim" }},
  "/app/output/",
]

[task]
name = "robot-coding-bench/{BENCH}-{rec["slug"]}-i00-standard"
description = "STANDARD MODE (robot as a service, eai-standard/2.1): {TITLE} ({rec["env"]}, {ROBOT_TEXT.replace("**", "")}): {sentence(rec["instruction"])} The agent only gets a client: the robot's calibrated RGB-D cameras, its own joints and end effector, and native controller commands in chunks; no reset, no object poses; the sim service records the episode and grades a fresh replay of it."
authors = [{{ name = "{AUTHOR}" }}]
keywords = [{KEYWORDS.format(bench=BENCH)}, "standard-mode"]

[metadata]
author_name = "{AUTHOR}"
author_org = "{ORG}"
task_type = "trajectory"
simulator = "robosuite"
robot = "{ROBOT}"
family = "{BENCH}/{rec["env"]}"
mode = "standard"
protocol = "eai-standard/2.1"
oracle = "full"
expert_time_estimate_hours = 4.0

[verifier]
timeout_sec = 1800.0
environment_mode = "separate"
network_mode = "no-network"

# The agent's time is up: stop whatever it left running in its container, so nothing drives the robot past the deadline.
[[verifier.collect]]
service = "main"
command = "kill -9 -1 2>/dev/null; exit 0"
timeout_sec = 30

# Then the episode ends: environment/sim/finalize.sh sends SIGUSR1 to the service (re-sent every 30 s, in case it was
# restarting), which replays the episode in a fresh simulator and writes the verdict with "finalized": true. The hook
# waits for that verdict (up to {COLLECT_WAIT_S} s), then, bounded, for the optional replay video, which decides nothing.
# timeout_sec was sized for an episode as long as a 3600 s agent time limit: the replay runs the episode's own physics
# once more, without its cameras, so it cannot take longer than the episode did (about 0.035 s per control step + one
# scene build; finalize.sh has the sums). Look at it when the agent's cutoff is raised.
[[verifier.collect]]
service = "sim"
command = "sh /srv/finalize.sh"
timeout_sec = {COLLECT_TIMEOUT_S}

{agent_block("standard")}
[environment]
build_timeout_sec = 1800.0
cpus = 4
memory_mb = 16384

[verifier.environment]
build_timeout_sec = 600.0
"""


PRIV_ENV_DOCKERFILE = f"""# {TITLE} privileged task: the benchmark image, the task's tooling and its frozen instance.
FROM {IMAGE}
COPY instance.npz /app/instance.npz
COPY casa_tool.py /opt/tools/casa_tool.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
"""
PRIV_TESTS_DOCKERFILE = f"""# Separate verifier sandbox: the same image with the verifier's own copies of the tooling and the frozen instance;
# only the declared artifacts (/app/output/) arrive from the agent.
FROM {IMAGE}
COPY test.sh grade.py casa_tool.py instance.npz /tests/
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
    command: python /srv/server_casa.py
    restart: on-failure:6
    environment:
      RCB_TOOL: casa_tool
      RCB_INSTANCE: /srv/instance.npz
      RCB_STARTUP_TIMEOUT_S: "600"
      PYTHONPATH: /srv
"""


def reset_dir(d: Path) -> None:
    """Start from an empty directory (agent results are not kept in the repository: PROTOCOL D3)."""
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


def make(rec: dict, out: Path = ROOT / "tasks") -> None:
    fz = FROZEN / rec["slug"]
    p = out / f"{BENCH}-{rec['slug']}-i00-privileged"
    reset_dir(p)
    put(p / "task.toml", privileged_toml(rec))
    put(p / "instruction.md", privileged_instruction(rec))
    put(p / "README.md", privileged_readme(rec))
    put(p / "environment/Dockerfile", PRIV_ENV_DOCKERFILE)
    put(p / "environment/casa_tool.py", src=SHARED / "casa_tool.py")
    put(p / "environment/instance.npz", src=fz / "instance.npz")
    put(p / "tests/Dockerfile", PRIV_TESTS_DOCKERFILE)
    put(p / "tests/test.sh", src=SHARED / "test.sh", mode=0o755)
    put(p / "tests/grade.py", src=SHARED / "grade_privileged.py")
    put(p / "tests/casa_tool.py", src=SHARED / "casa_tool.py")
    put(p / "tests/instance.npz", src=fz / "instance.npz")
    put(p / "solution/solve.sh", src=SHARED / "solve_privileged.sh", mode=0o755)
    put(p / "solution/oracle_replay.py", src=SHARED / "oracle_privileged.py")
    put(p / "solution/oracle.npz", src=fz / "oracle.npz")

    s = out / f"{BENCH}-{rec['slug']}-i00-standard"
    reset_dir(s)
    put(s / "task.toml", standard_toml(rec))
    put(s / "instruction.md", standard_instruction(rec))
    put(s / "README.md", standard_readme(rec))
    put(s / "environment/Dockerfile", STD_ENV_DOCKERFILE)
    put(s / "environment/docker-compose.yaml", STD_COMPOSE)
    put(s / "environment/rcb_client.py", src=SHARED / "rcb_client.py")
    put(s / "environment/rcb1.py", src=SHARED / "rcb1.py")
    put(s / "environment/sim/server_casa.py", src=SERVER)
    put(s / "environment/sim/finalize.sh", src=SHARED / "finalize.sh")
    put(s / "environment/sim/casa_tool.py", src=SHARED / "casa_tool.py")
    put(s / "environment/sim/rcb1.py", src=SHARED / "rcb1.py")
    put(s / "environment/sim/instance.npz", src=fz / "instance.npz")
    put(s / "tests/Dockerfile", STD_TESTS_DOCKERFILE)
    put(s / "tests/test.sh", src=SHARED / "test.sh", mode=0o755)
    put(s / "tests/grade.py", src=SHARED / "grade_standard.py")
    put(s / "solution/solve.sh", src=SHARED / "solve_standard.sh", mode=0o755)
    put(s / "solution/oracle_replay.py", src=SHARED / "oracle_standard.py")
    put(s / "solution/oracle.npz", src=fz / "oracle.npz")
    normalize(p)
    normalize(s)


def verified(rec: dict) -> bool:
    keys = ("reset_exact", "oracle_success", "deterministic", "replay_success")
    return all(rec.get(k) for k in keys) and not rec.get("initial_success")


def files(d: Path) -> dict[str, tuple[bytes, int]]:
    return {str(f.relative_to(d)): (f.read_bytes(), f.stat().st_mode & 0o777) for f in sorted(d.rglob("*")) if f.is_file()}


def main(envs: list[str], check: bool = False) -> None:
    report = json.loads((FROZEN / "report.json").read_text())
    hook = (SHARED / "finalize.sh").read_text()
    if f'WAIT_S="${{RCB_COLLECT_WAIT_S:-{COLLECT_WAIT_S}}}"' not in hook or COLLECT_WAIT_S >= COLLECT_TIMEOUT_S:
        raise SystemExit("shared/finalize.sh: RCB_COLLECT_WAIT_S's default must be COLLECT_WAIT_S, below COLLECT_TIMEOUT_S")
    out = Path(tempfile.mkdtemp(prefix=f"{BENCH}-check-")) if check else ROOT / "tasks"
    n = 0
    for env in envs:
        rec = report.get(slug(env))
        if rec is None or not verified(rec):
            if envs is not ALL:
                raise SystemExit(f"{env}: frozen instance or reference not verified (re-run import_references.sh)")
            continue
        make(rec, out)
        n += 1
    if not check:
        print(f"generated {2 * n} task directories")
        return
    bad = []
    for d in sorted(out.iterdir()):
        mine = ROOT / "tasks" / d.name
        if not mine.is_dir() or files(d) != files(mine):
            bad.append(d.name)
    if envs is ALL:  # a task directory of this benchmark that the generator no longer writes (RoboCasa-GR1 is another one)
        ours = {d.name for d in out.iterdir()}
        bad += sorted(
            d.name
            for d in (ROOT / "tasks").glob(f"{BENCH}-*")
            if d.is_dir() and not d.name.startswith(f"{BENCH}-gr1-") and d.name not in ours
        )
    shutil.rmtree(out)
    if bad:
        raise SystemExit("differs from a fresh render (re-run generate.py): " + ", ".join(bad))
    print(f"ok: {2 * n} task directories match a fresh render")


ALL = sorted(SOURCES)
if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--check"]
    main(args or ALL, check="--check" in sys.argv[1:])
