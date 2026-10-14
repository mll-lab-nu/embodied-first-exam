#!/usr/bin/env python3
"""Generate this benchmark's tasks: tasks/<bench>-<slug>-i00-privileged and tasks/<bench>-<slug>-i00-standard, and
tasks/<bench>-<slug>-i00-standard-realtime for the environments whose scene is dynamic (REALTIME; PROTOCOL §4b, §2.14).

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
TITLE = "RoboCasa365"
UPSTREAM = (
    "[RoboCasa365](https://github.com/robocasa/robocasa) @ 4f8a298 (robocasa 1.0.1; MIT), robosuite @ 5ce6643 (1.5.2), "
    "MuJoCo 3.3.1"
)
ROBOT = "franka-panda-omron"
ROBOT_TEXT = "a **Franka Panda arm on an Omron mobile base** (with a torso lift)"
ENV_DOC = "RoboCasa365's `{env}` kitchen task"
SCENE = "works in a kitchen"
KEYWORDS = '"robotics", "robosuite", "{bench}", "mobile-manipulation", "code-as-policy", "trajectory"'
DIFFICULTY_PRIVILEGED = (
    "Full privileged state, unlimited resets and self-replay; a mobile manipulator in one of RoboCasa365's large,\n"
    "cluttered kitchens, long-horizon contact-rich manipulation with a 20 Hz controller. The standard twin removes the\n"
    "privileged state."
)
DIFFICULTY_STANDARD = (
    "The agent has to find the fixtures and objects in the robot's camera images, drive a mobile manipulator with its "
    "native\ncontroller, and finish in one episode without a reset."
)
# -----------------------------------------------------------------------------------------------------------------

TASKS = ROOT / "tasks"  # check mode renders into a temporary directory instead
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
# README Change Log entries of single tasks (by environment), after those of every task; both modes.
_FAUCET_CHANGE = (
    '2026-10-14 (board 0113, from board 0086): the success text now says that the faucet handle has two hinges at one'
    " pivot: the water on / off hinge (range 0 to 0.5 rad, about the sink's front-to-back axis, so the handle swings "
    'sideways) and a temperature hinge (about ±0.79 rad) that tilts it toward or away from you and never turns the '
    'water on; before, it named only "the handle joint" (board 0086: every standard run of `turn-on-sink-faucet` and '
    '`thaw-in-sink` moved the temperature hinge). Text only: the scene, the frozen instance, the reference solution, '
    "the environment's success check and the verifier are unchanged, so the task keeps its name."
)
CHANGES_TASK = {env: [_FAUCET_CHANGE] for env in ['TurnOnSinkFaucet', 'DrainVeggies', 'ThawInSink']}
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


LIMITS = {
    "privileged": "`s.action_spec`",
    "standard": '`spec["action_types"]["{type}"]` (`lower` / `upper`, from `r.spec()`)',
}


def action_text(dim: int, mode: str) -> str:
    """The native controller's channels, as both instructions state them; `mode` names where the limits are."""
    limits = LIMITS[mode].format(type=ACTION_TYPE[dim])
    if dim == 12:
        return (
            "12 channels, in order: `arm_dx, arm_dy, arm_dz, arm_drx, arm_dry, arm_drz` -- the end effector's motion "
            "per control step in the robot's base frame, scaled by the controller (1.0 = 5 cm and 0.5 rad per step); "
            "`grip` (+1 closes, -1 opens); `base_x, base_y, base_yaw` -- the mobile base's velocities in its own frame; "
            "`torso` -- the torso lift's velocity; `hybrid_mode` (> 0: base mode, the arm's goal moves with the base; "
            "<= 0: arm mode, the default -1). Every channel is clipped to [-1, 1]."
        )
    if dim == 13:
        return (
            "13 channels, in order: `arm_joint1 .. arm_joint7` -- absolute joint position targets (rad, within the "
            "joint limits in " + limits + "); `grip` (+1 closes, -1 opens); `base_x, base_y, base_yaw` -- the mobile "
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


def hold_note(rec: dict) -> str:
    """For the README: the reference's success does not survive holding still (import_references.py, HOLD_STEPS)."""
    if rec["success_after_hold"]:
        return ""
    return (
        "\nIn this environment the success state does not persist on its own: after the reference's last action, "
        "holding still for 10 control steps loses it. Graded on the final state, a trajectory must end at that moment.\n"
    )


def hold_instruction(rec: dict, mode: str) -> str:
    """The same fact for the agent (both modes): end while the success holds."""
    if rec["success_after_hold"]:
        return ""
    end = (
        "end the trajectory on a step where `s.check()` reports success"
        if mode == "privileged"
        else "make the last chunk you submit end in that state, then stop submitting and do not call "
        "`get_obs(seconds=...)` (holding still runs control steps that are part of the episode)"
    )
    return (
        "\n**This task's success does not persist on its own**: the reference solution's success state is lost "
        f"within 10 control steps of holding still after its last action. Since only the final state counts, {end}.\n"
    )


SUCCESS_TERMS = """How RoboCasa365's checks compute these terms (`robocasa/utils/object_utils.py`):
- *the gripper ends more than d m from X*: the distance from the robot's end-effector grip site to X's origin exceeds
  d. Opening the fingers is not enough: release, then move the hand away.
- *X is on / in Y* for an object Y (plate, tray, board, pan, pot, colander, tupperware, glass): X touches Y and their
  centres are within 0.7 × Y's horizontal radius of each other horizontally, unless a distance is given.
- *X touches* a counter, the dining counter or the stove: contact between X and that fixture.
- *X is inside* a fixture (a cabinet, the sink or one of its basins, the microwave): all eight corners of X's bounding
  box are within the fixture's interior region (5 cm tolerance).
"""


def success_text(rec: dict) -> str:
    """What the environment's `_check_success` requires (envs.SUCCESS), with the terms it uses."""
    text = SUCCESS[rec["env"]]
    terms = any(w in text for w in ("gripper ends", "touch", "inside", " on the ", " in the "))
    return f"The check for `{rec['env']}` requires that {text}\n" + (f"\n{SUCCESS_TERMS}" if terms else "")


def privileged_instruction(rec: dict) -> str:
    env, dim = rec["env"], rec["action_dim"]
    return f"""# {TITLE} · {env}

{ROBOT_TEXT[0].upper() + ROBOT_TEXT[1:]} {SCENE}: {ENV_DOC.format(env=env)} (robosuite, MuJoCo).
**Task: {rec["instruction"]}**
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

{success_text(rec)}{hold_instruction(rec, "privileged")}
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
- Actions: {action_text(dim, "privileged")}
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
**Task: {rec["instruction"]}**
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

{success_text(rec)}{hold_instruction(rec, "standard")}
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
  0.05 s; float64). {action_text(dim, "standard")} Rows are `dt` apart (default and minimum: `control_dt`; a chunk covers at
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


METHOD = {
    "joint": "it follows the demonstration's recorded arm joint positions as this controller's absolute joint targets "
    "(PR #4 method `demo_joint`)",
    "feedback": "it follows the demonstration's recorded arm joint positions as this controller's absolute joint "
    "targets, with the base and torso commands corrected by feedback (PR #4 method `demo_feedback`)",
}


def reference_source(rec: dict) -> str:
    """Where the reference comes from, as far as PR #4's authoring record says (import_references.provenance)."""
    demo = rec.get("demonstration") or {}
    method = rec.get("reference_method")
    if demo.get("episode") is None or method not in METHOD:
        return (
            "PR #4's reference for this frozen instance (an official demonstration's initial state; PR #4's authoring "
            "record for this task names neither the demonstration episode nor the retargeting method)"
        )
    return (
        f"Retargeted by PR #4 from official demonstration episode {demo['episode']} (`{demo.get('demo')}`, "
        f"{demo.get('n_actions')} recorded actions; RoboCasa365's demonstrations use a different arm controller): "
        f"{METHOD[method]}"
    )


def instance_source(rec: dict) -> str:
    demo = rec.get("demonstration") or {}
    if demo.get("episode") is None:
        return "the initial state of an official demonstration episode (which one is not in PR #4's authoring record)"
    path = rec.get("demonstration_path")
    return f"the initial state of official demonstration episode {demo['episode']} (`{demo.get('demo')}`" + (
        f", `{path}`)" if path else ")"
    )


def privileged_readme(rec: dict) -> str:
    env = rec["env"]
    cut = " (cut at its first success)" if rec["truncated"] else ""
    task = (
        f"{ENV_DOC.format(env=env)} with {ROBOT_TEXT.replace('**', '')}: {rec['instruction']} Produce one replayable "
        "trajectory of the robot's native controller commands on one frozen instance; graded on the state after the "
        f"last action. Generated by `scripts/{BENCH}/generate.py`; benchmark notes in `docs/benchmarks/{BENCH}.md`."
    )
    reference = (
        f"{reference_source(rec)}. Executed from the frozen scene by the robot's own controller: {rec['n_actions']} "
        f"actions{cut} in `solution/oracle.npz`. Neither the demonstration nor the reference is in the image; the agent "
        "cannot reach them."
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
            f"{instance_source(rec)}; MuJoCo state, model arrays, task state and RNG frozen in `instance.npz` "
            f"(SHA-256 `{rec['instance_sha'][:12]}…`, checked on load)",
        ),
        ("Deliverable", f"`(T, {rec['action_dim']})` native controller commands, 1 ≤ T ≤ {MAX_STEPS}, 20 Hz"),
        ("Success", f"the environment's own check (`_check_success`) on the state after the last action: "
         f"{SUCCESS[env]}"),
    ]
    text = readme(
        readme_head(rec, "privileged"), task, DIFFICULTY_PRIVILEGED.replace("\n", " "), reference, verification, details
    )
    log = CHANGES_TASK.get(rec["env"], [])
    return text + ("\n### Change Log\n" + "".join(f"- {c}\n" for c in log) if log else "")


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
    return text + "\n### Change Log\n" + "".join(f"- {c}\n" for c in CHANGES_STANDARD + CHANGES_TASK.get(rec["env"], []))


def privileged_toml(rec: dict) -> str:
    return f"""schema_version = "1.3"
artifacts = ["/app/output/"]

[task]
name = "robot-coding-bench/{BENCH}-{rec["slug"]}-i00-privileged"
description = "{TITLE} ({rec["env"]}, {ROBOT_TEXT.replace("**", "")}): {rec["instruction"]} Produce one replayable trajectory of the robot's native controller commands on a frozen instance; graded on the state after the last action."
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
description = "STANDARD MODE (robot as a service, eai-standard/2.1): {TITLE} ({rec["env"]}, {ROBOT_TEXT.replace("**", "")}): {rec["instruction"]} The agent only gets a client: the robot's calibrated RGB-D cameras, its own joints and end effector, and native controller commands in chunks; no reset, no object poses; the sim service records the episode and grades a fresh replay of it."
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


# -- standard-realtime twins (PROTOCOL §4b; owner 2026-10-14, board 0112) -----------------------------------------
# The dynamic environments (scripts/task_dynamics.toml; PROTOCOL §2.14) get a `-standard-realtime` twin: the same frozen
# instance and success check, served by shared/realtime/server.py (rcb_service.Sim on casa_tool.Session) behind the
# shared eai-standard/2.3 layer (rcb_realtime.py, rcb_service.py, rcb_client.py, grade.py: unchanged copies of
# scripts/humanoidbench/shared/; check-tooling-identity.sh). Per environment: the slowdown S, from the real-time factor
# RTF of that service measured on the reference workstation (PROTOCOL §4b: S = 1 when RTF >= 3, else ~1.5 / RTF
# rounded up), and how it was measured (docs/benchmarks/robocasa365.md, "Standard-realtime").
REALTIME = {
    "TurnOnToasterOven": {
        "slowdown": 2,
        "rtf": "1.27-1.29",
        "measured": "2026-10-14, board 0112, ws-1 (32 cores, load 35-45), the service capped at 4 CPUs: 1.29 with "
                    "the realtime service's clock flat out (RCB_SLOWDOWN = 0.01, 3 episodes of 600 control steps), 1.27 "
                    "for the bare physics holding still; S = ceil(1.5 / 1.29) = 2",
        "why": "the timer knob, once set, turns back by itself (1/3000 of its range per simulated second)",
    },
}
RT_RESET_BUDGET = 10   # PROTOCOL §4b: every standard-realtime task allows resets, 10 by default (owner, 2026-10-14)
RT_MAX_STEPS = MAX_STEPS   # an episode's control steps: the privileged deliverable's cap (150 s of robot time)
RT_REVIEW_PR = "205"   # the pull request that adds the realtime twins (human review, PROTOCOL §2.7)
RT = SHARED / "realtime"


def rt_compose(rec: dict) -> str:
    S = REALTIME[rec["env"]]["slowdown"]
    return f"""# Standard-realtime mode (PROTOCOL §4b): the simulator runs in the `sim` sidecar (the agent cannot open it), on its own clock
# once an episode starts (sim/rcb_realtime.py, the shared eai-standard/2.3 layer, with sim/server.py, this benchmark's
# adapter on casa_tool); the agent only reaches port 8000. No `expose`/`ports` on sim: under Harbor's egress control it
# shares main's network namespace (localhost:8000).
# CPU only, as the standard twin (MuJoCo physics, OSMesa rendering, about 0.12 s a 320 x 240 frame): no GPU reservation.
# Crash recovery: compose restarts the service, which resumes the same episode, paused, never a reset.
# Knobs: ${{NAME:-default}} takes NAME from the shell that runs harbor. The defaults are the task's configuration;
# results under other settings are reported separately.
services:
  main:
    depends_on: [sim]
  sim:
    image: {IMAGE}
    volumes:
      - ./sim:/srv:ro
    working_dir: /tmp
    command: python /srv/rcb_realtime.py
    restart: on-failure:6          # a resume continues the episode, paused
    environment:
      RCB_INSTANCE: /srv/instance.npz
      RCB_DATA: /data
      RCB_STARTUP_TIMEOUT_S: "600"
      RCB_MAX_CONTROL_STEPS: "{RT_MAX_STEPS}"     # an episode's control steps ({RT_MAX_STEPS * 0.05:g} s of robot time)
      PYTHONPATH: /srv
      RCB_SLOWDOWN: "${{RCB_SLOWDOWN:-{S}}}"                # S = {S}: the world runs at 1/S of real speed (this task's measured RTF; PROTOCOL §4b)
      RCB_RESET_BUDGET: "${{RCB_RESET_BUDGET:-{RT_RESET_BUDGET}}}"        # {RT_RESET_BUDGET} resets (PROTOCOL §4b default); 0: one episode
"""


def realtime_instruction(rec: dict) -> str:
    env, dim, rt = rec["env"], rec["action_dim"], REALTIME[rec["env"]]
    S, cams, typ = rt["slowdown"], ", ".join(rec["cameras"]), ACTION_TYPE[dim]
    return f"""# {TITLE} · {env} — STANDARD-REALTIME MODE (robot as a service; time does not stop)

{ROBOT_TEXT[0].upper() + ROBOT_TEXT[1:]} {SCENE}: {ENV_DOC.format(env=env)} (robosuite, MuJoCo).
**Task: {rec["instruction"]}**
The scene is one frozen instance: the initial state of one of the benchmark's official demonstrations.

You control the robot **as if it were real hardware**: the simulator runs in a service you cannot open, you reach it
only through a client, and like real hardware it does not wait for you: once an episode is running, the robot (and the
kitchen: {rt["why"]}) moves on while you think.

**Slowdown: S = {S}.** The world runs at 1/S of real speed: one control step (0.05 s of robot time) every
S x 0.05 s = {0.05 * S:g} s of wall-clock time. `spec()["timing"]["slowdown"]` states it.

## Rules (real-robot rules)
- **Time does not stop.** An episode starts paused, on the frozen starting state, holding still. Its clock starts at
  your first `submit` (or `get_obs(seconds=s)`) and from then on the robot runs one control step every {0.05 * S:g} s of
  wall-clock time, whether or not you send anything, until the episode ends. Between your commands it executes what you
  planned; when the plan runs out it holds still (velocity channels zero, targets, grip and mode kept). Nothing pauses
  for you, not your thinking, not your tool calls.
- **Drive it with a program.** One turn of yours (a model response, a tool call) takes seconds: write a controller (Python
  in your container, with numpy and the client) that plans or streams the commands, in the background
  (`nohup python /app/output/gen.py > /app/output/run.log 2>&1 &`) or in the foreground; use your turns to start
  episodes, read what happened, and improve the program.
- **Episodes and resets.** An episode ends at the first control step after which the environment's success check holds
  (success), after {RT_MAX_STEPS} control steps ({RT_MAX_STEPS * 0.05:g} s of robot time; failed), when your time is up, or
  on a simulator error. You have **{RT_RESET_BUDGET} resets** (`spec()["budget"]["reset"]`, which is authoritative: if it
  says 0, there is no reset and the one episode is the run). `r.reset(cameras=[])` rebuilds the same frozen starting state
  (it takes about 15-20 s) and starts a new episode, paused until your next `submit`, either abandoning the running
  episode or after one has ended. Reset with `cameras=[]` and ask for images afterwards: the service holds image
  requests back for about four times as long as the last request that rendered took, and a reset that renders counts
  as one (so after `r.reset()` with cameras, images come back only about a minute later). Once an episode has ended, `submit` raises `EpisodeOver` (its message gives `resets_left`) until
  you reset. **Only the last episode is graded**: an episode you reset away is never graded, a success ends the run at
  once (no reset after it), and when your time is up the episode then running is the one graded.
- **No privileged state.** You see what the robot's cameras see (RGB, optional depth) and the robot's own state:
  joints, end effector, the command in force, and each camera's current pose. No object poses, no scene layout, no
  success signal: the service judges the episode and only tells you that it ended and why (`meta["done"]`,
  `meta["reason"]`: `"success"`, `"failed"`, `"error"`).
- There is nothing to hand in: the service records every control step it ran, replays the last episode in a fresh
  simulator and grades the replay. Keep the controller at `/app/output/gen.py` for the record.
- Do not use the benchmark's demonstrations, trained policies or any published solution; write your own controller.
- Do not stop early: while the episode runs, or a reset is left, the run can still pass.

## Scoring
The episode is graded by the environment's own success check for `{env}` (`_check_success`, run twice after every
control step, as in the privileged verifier) on the state after its last control step; the episode ends the moment it
holds. The fresh replay of the recorded episode, the commands the robot actually executed at each control step, must
succeed as well and end in the same state.

{success_text(rec)}
## Time and streaming
- `submit` answers at once, with the robot as it is now: the rows you sent have not run yet. They become the plan from
  control step `at` (an episode step number; by default the next step), replacing whatever was planned from `at` on.
  `res.meta["control_steps"]` is the number of steps run so far in this episode, `res.meta["plan_end_step"]` where the
  plan now ends. A chunk covers at most 10 s of robot time; `at` may be up to `spec()["timing"]["max_ahead_steps"]`
  steps ahead, so plan a longer movement in several chunks (`at=0`, `at=200`, ...).
- A row whose step has already run when the request arrives is dropped (`res.meta["late_steps"]`); in a gap before
  `at` the last row in force is repeated, velocity channels included.
- `get_obs()` reads the robot now; `get_obs(seconds=s)` (at most 30) waits while s seconds of robot time run and
  returns what the cameras saw meanwhile. `cameras=[]` skips the images (the fastest call); rendering takes about 0.12
  s a camera on the service's CPU and the robot does not wait for it.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.3`, standard-realtime mode)
Its docstring is the full reference (`python -c "import rcb_client; help(rcb_client)"`).

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects and waits until the scene is ready (about a minute) |
| `r.spec()` | `GET /spec` | `control_dt` (0.05 s), `timing`, the action layout and limits, the cameras (intrinsics), `proprio_layout`, `budget` |
| `r.status()` | `GET /status` | `control_steps`, `done`, `reason`, `running`, `planned_steps`, `lag_s`, `episode`, `resets_left` |
| `r.submit("{typ}", A, dt=0.05, interpolate="linear", at=None, cameras=None)` | `POST /submit` | plans `A`, rows of {dim} channels `dt` apart, from step `at`; answers at once; the first one starts the clock |
| `r.get_obs(cameras=None, seconds=0, include_depth=False, video="frames")` | `POST /observe` | the robot now, or what the cameras saw over the next `seconds` |
| `r.reset(cameras=[])` | `POST /reset` | a new episode from the frozen starting state, paused (at most {RT_RESET_BUDGET} in all); `cameras=[]`: no images (see Rules) |

The answers come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`, `clipped`), `res.last[camera]`,
`res.frames` / `res.video`, `res.depth`, `res.proprio`.
- Action `{typ}`: the robot's native controller command, one row per control step (`control_dt` = 0.05 s).
  {action_text(dim, "standard")}
- Cameras: {cams} (320 x 240, mounted on the robot; intrinsics in `spec()["cameras"]`). Each proprioception row ends with
  every camera's current pose, `cam_<camera>_x, _y, _z` (position, m) and `_r00 .. _r22` (the camera-to-world rotation,
  row by row; OpenGL axes: x right, y up, looking along -z).
- World frame: metres, z up.
"""


def realtime_readme(rec: dict) -> str:
    env, rt = rec["env"], REALTIME[rec["env"]]
    base, S = f"{BENCH}-{rec['slug']}-i00", rt["slowdown"]
    head = [line.replace(f"`{base}-privileged`", f"`{base}-privileged`") for line in readme_head(rec, "standard")]
    head[0] = f"# {base}-standard-realtime"
    head = [h.replace("standard (`eai-standard/2.1`)", "standard-realtime (`eai-standard/2.3`)") for h in head]
    task = (
        f"Standard-realtime mode (`eai-standard/2.3`, slowdown S = {S}) of `{base}-privileged`: the same frozen instance "
        "and success check, served by the `sim` sidecar on a clock that does not stop (the shared realtime layer of "
        "HumanoidBench, BiGym 2.0 and RoboOlympics with `environment/sim/server.py`, this benchmark's adapter on "
        "`casa_tool`). The scene is dynamic (scripts/task_dynamics.toml): " + rt["why"] + ". The agent sees the robot's "
        "cameras (RGB-D; intrinsics, and each camera's pose in every proprioception row), its own joints and end effector, "
        f"and the instruction; {RT_RESET_BUDGET} resets, only the last episode graded."
    )
    reference = (
        f"`solution/`: none for this mode. Solvability: the privileged reference's {rec['n_actions']} actions planned "
        "from step 0 (`submit(..., at=0)`, then `at=200`) through this service at S = 2 succeed live (at control step 256) "
        "and in the fresh replay, deterministic, with no stall (board 0112, 2026-10-14)."
    )
    verification = (
        "The sim service judges the episode live (it ends at the first step after which the success check holds), "
        "records every control step it ran, and after the agent's time replays the graded episode in a fresh simulator "
        "and writes `final.json`; `tests/grade.py` (separate sandbox, no network) passes iff the live episode succeeded, "
        "the replay succeeds and ends in the same state. The clock's record (`stalls`, `max_lag_s`, ...) is copied into "
        "`reward.json` and decides nothing. `nop`: the episode never starts (its clock starts at the first submit), "
        "reward 0."
    )
    details = [
        ("Slowdown", f"S = {S} (`RCB_SLOWDOWN`'s default): measured RTF {rt['rtf']} ({rt['measured']})"),
        ("Episode", f"at most {RT_MAX_STEPS} control steps ({RT_MAX_STEPS * 0.05:g} s of robot time; the privileged "
                    "deliverable's cap); ends at the first success"),
        ("Reset budget", f"{RT_RESET_BUDGET} (`RCB_RESET_BUDGET`; PROTOCOL §4b); a reset rebuilds the scene (about 20 s)"),
        ("Action type", f"`{ACTION_TYPE[rec['action_dim']]}` ({rec['action_dim']} channels, `control_dt` 0.05 s)"),
        ("Cameras", ", ".join(f"`{c}`" for c in rec["cameras"]) + " (robot-mounted; poses in the proprioception)"),
    ]
    text = readme(head, task, DIFFICULTY_STANDARD.replace("\n", " ").replace("finish in one episode without a reset",
                  "act on a clock that does not stop, with resets"), reference, verification, details)
    return text + ("\n### Change Log\n- 2026-10-14 (owner, board 0112): added. The scene is dynamic (PROTOCOL §2.14), so "
                   f"the task gets a standard-realtime twin, S = {S}, {RT_RESET_BUDGET} resets.\n")


def realtime_toml(rec: dict) -> str:
    rt = REALTIME[rec["env"]]
    ev = ("the privileged reference planned from step 0 through this service at S = 2 succeeds live and in the fresh "
          f"replay, deterministic, no stall (board 0112, 2026-10-14); human review in PR #{RT_REVIEW_PR}")
    return f"""schema_version = "1.3"
artifacts = [
  {{ source = "/data/final.json", service = "sim" }},
  {{ source = "/data/episode.jsonl", service = "sim" }},
  {{ source = "/data/trajectory.npz", service = "sim" }},
  {{ source = "/data/trajectory_live.f64", service = "sim" }},
  {{ source = "/data/replay.mp4", service = "sim" }},
  {{ source = "/data/replay.last.png", service = "sim" }},
  {{ source = "/data/ticks.f64", service = "sim" }},
  {{ source = "/data/calls.jsonl", service = "sim" }},
  {{ source = "/data/submitted.f64", service = "sim" }},
  {{ source = "/data/startups.jsonl", service = "sim" }},
  "/app/output/",
]

[task]
name = "robot-coding-bench/{BENCH}-{rec["slug"]}-i00-standard-realtime"
description = "STANDARD-REALTIME MODE (robot as a service on a clock that does not stop, eai-standard/2.3, slowdown S = {rt["slowdown"]}): {TITLE} ({rec["env"]}, {ROBOT_TEXT.replace("**", "")}): {rec["instruction"]} The robot and the kitchen move on while the agent thinks ({rt["why"]}), so the agent plans or streams native controller commands from a program of its own through the client (calibrated RGB-D cameras, the robot's own joints and end effector); {RT_RESET_BUDGET} resets, only the last episode graded; no object poses; the sim service records every executed control step and grades a fresh replay of the last episode."
authors = [{{ name = "{AUTHOR}" }}]
keywords = [{KEYWORDS.format(bench=BENCH)}, "standard-realtime-mode"]

[metadata]
author_name = "{AUTHOR}"
author_org = "{ORG}"
task_type = "trajectory"
simulator = "robosuite"
robot = "{ROBOT}"
family = "{BENCH}/{rec["env"]}"
mode = "standard-realtime"
protocol = "eai-standard/2.3"
oracle = "none"
oracle_evidence = "{ev}"
expert_time_estimate_hours = 6.0

[verifier]
timeout_sec = 900.0
environment_mode = "separate"
network_mode = "no-network"

# The agent's time is up: stop whatever it left running in its container, so nothing drives the robot past the deadline.
[[verifier.collect]]
service = "main"
command = "kill -9 -1 2>/dev/null; exit 0"
timeout_sec = 30

# Then the episode ends: SIGUSR1 to the service (re-sent every 30 s, in case it was restarting), which replays the graded
# episode (at most {RT_MAX_STEPS} control steps) in a fresh simulator and writes the verdict ("finalized": true) before any
# video; the hook waits for it until 840 s, then for the replay video ("video_pending") until 870 s.
[[verifier.collect]]
service = "sim"
command = "t0=$(date +%s); while [ ! -f /data/server.pid ] && [ $(( $(date +%s) - t0 )) -lt 120 ]; do sleep 2; done; i=0; while [ $(( $(date +%s) - t0 )) -lt 840 ] && ! grep -q '\\"finalized\\": true' /data/final.json 2>/dev/null; do [ $((i % 15)) -eq 0 ] && kill -USR1 $(cat /data/server.pid 2>/dev/null) 2>/dev/null; i=$((i + 1)); sleep 2; done; while [ $(( $(date +%s) - t0 )) -lt 870 ] && grep -q '\\"video_pending\\": true' /data/final.json 2>/dev/null; do sleep 2; done; cat /data/final.json"
timeout_sec = 900

{agent_block("standard-realtime")}
[environment]
build_timeout_sec = 1800.0
cpus = 4
memory_mb = 16384

[verifier.environment]
build_timeout_sec = 600.0
"""


def make_realtime(rec: dict) -> Path:
    fz = FROZEN / rec["slug"]
    r = TASKS / f"{BENCH}-{rec['slug']}-i00-standard-realtime"
    reset_dir(r)
    put(r / "task.toml", realtime_toml(rec))
    put(r / "instruction.md", realtime_instruction(rec))
    put(r / "README.md", realtime_readme(rec))
    put(r / "environment/Dockerfile", STD_ENV_DOCKERFILE)
    put(r / "environment/docker-compose.yaml", rt_compose(rec))
    put(r / "environment/rcb_client.py", src=RT / "rcb_client.py")
    put(r / "environment/rcb1.py", src=SHARED / "rcb1.py")
    for name in ("rcb_realtime.py", "rcb_service.py", "server.py"):
        put(r / "environment/sim" / name, src=RT / name)
    put(r / "environment/sim/casa_tool.py", src=SHARED / "casa_tool.py")
    put(r / "environment/sim/rcb1.py", src=SHARED / "rcb1.py")
    put(r / "environment/sim/instance.npz", src=fz / "instance.npz")
    put(r / "tests/Dockerfile", STD_TESTS_DOCKERFILE)
    put(r / "tests/test.sh", src=SHARED / "test.sh", mode=0o755)
    put(r / "tests/grade.py", src=RT / "grade.py")
    normalize(r)
    return r


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


def make(rec: dict) -> None:
    fz = FROZEN / rec["slug"]
    p = TASKS / f"{BENCH}-{rec['slug']}-i00-privileged"
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

    s = TASKS / f"{BENCH}-{rec['slug']}-i00-standard"
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
    if rec["env"] in REALTIME:
        make_realtime(rec)


def verified(rec: dict) -> bool:
    keys = ("reset_exact", "oracle_success", "deterministic", "replay_success")
    return all(rec.get(k) for k in keys) and not rec.get("initial_success")


def main(envs: list[str]) -> None:
    report = json.loads((FROZEN / "report.json").read_text())
    hook = (SHARED / "finalize.sh").read_text()
    if f'WAIT_S="${{RCB_COLLECT_WAIT_S:-{COLLECT_WAIT_S}}}"' not in hook or COLLECT_WAIT_S >= COLLECT_TIMEOUT_S:
        raise SystemExit("shared/finalize.sh: RCB_COLLECT_WAIT_S's default must be COLLECT_WAIT_S, below COLLECT_TIMEOUT_S")
    n = 0
    for env in envs:
        rec = report.get(slug(env))
        if rec is None or not verified(rec):
            if envs is not ALL:
                raise SystemExit(f"{env}: frozen instance or reference not verified (re-run import_references.sh)")
            continue
        make(rec)
        n += 1
    print(f"generated {2 * n + sum(1 for e in envs if e in REALTIME)} task directories")


def tree(d: Path) -> dict:
    return {str(f.relative_to(d)): (f.read_bytes(), f.stat().st_mode & 0o777) for f in sorted(d.rglob("*")) if f.is_file()}


def check() -> int:
    """Render every task into a temporary directory and compare it (contents and file modes) with tasks/."""
    global TASKS
    with tempfile.TemporaryDirectory() as td:
        TASKS = Path(td)
        main(ALL)
        fresh = sorted(d.name for d in TASKS.iterdir())
        have = sorted(d.name for d in (ROOT / "tasks").glob(f"{BENCH}-*") if d.is_dir())
        bad = sorted(set(fresh) ^ set(have))
        bad += [n for n in fresh if n in have and tree(TASKS / n) != tree(ROOT / "tasks" / n)]
    for n in bad:
        print(f"FAIL tasks/{n}: differs from a fresh render (run scripts/{BENCH}/generate.py)")
    print(f"{len(fresh) - len(bad)}/{len(fresh)} task directories match a fresh render")
    return 1 if bad else 0


ALL = sorted(SOURCES)
if __name__ == "__main__":
    if sys.argv[1:] == ["--check"]:
        sys.exit(check())
    main(sys.argv[1:] or ALL)
