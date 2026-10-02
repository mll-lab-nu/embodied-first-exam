#!/usr/bin/env python3
"""Generate this benchmark's tasks: tasks/<bench>-<slug>-i00-privileged and tasks/<bench>-<slug>-i00-standard.

    python3 scripts/<bench>/generate.py            # every verified environment in frozen/report.json
    python3 scripts/<bench>/generate.py PreSoakPan
    python3 scripts/<bench>/generate.py --check    # write nothing; exit 1 if tasks/ differs from a fresh render

Inputs: envs.py, frozen/<slug>/{instance,oracle}.npz and frozen/report.json (import_references.sh), the shared sources
in shared/ and the standard-mode service images/<bench>/standard/server_casa.py. Every task directory is rewritten;
shared files are copied byte for byte. Re-running reproduces the tasks exactly.
"""

import ast
import json
import math
import re
import shutil
import struct
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(ROOT / "scripts"))
from envs import SOURCES, slug  # noqa: E402
from task_conventions import normalize  # noqa: E402  (protocol v1.0 conventions, as main's generators)

# -- benchmark configuration -----------------------------------------------------------------------------------
BENCH = HERE.name
TITLE = "RoboCasa-GR1"
UPSTREAM = (
    "[RoboCasa GR1 tabletop tasks](https://github.com/robocasa/robocasa-gr1-tabletop-tasks) @ 4840e67 (MIT), "
    "robosuite @ 51cc017 (1.5.1) with its whole-body mink IK controller, MuJoCo 3.2.6"
)
ROBOT = "fourier-gr1"
ROBOT_TEXT = "a **Fourier GR1 humanoid** (arms, waist and two dexterous six-command Fourier hands; fixed base)"
ENV_DOC = "RoboCasa's GR1 tabletop `{env}` task"
SCENE = "works at a kitchen counter"
KEYWORDS = '"robotics", "robosuite", "{bench}", "humanoid", "dexterous-hands", "code-as-policy", "trajectory"'
DIFFICULTY_PRIVILEGED = (
    "Full privileged state, unlimited resets and self-replay; a humanoid's two arms and dexterous hands driven through a\n"
    "whole-body IK controller (absolute grip-site poses, six commands per hand), pick-and-place with containers and\n"
    "doors. The standard twin removes the privileged state."
)
DIFFICULTY_STANDARD = (
    "The agent has to find the objects in the humanoid's camera images, coordinate two arms and two dexterous hands\n"
    "through the IK controller, and finish in one episode without a reset."
)
# -----------------------------------------------------------------------------------------------------------------

SHARED = HERE / "shared"
FROZEN = HERE / "frozen"
TASKS = ROOT / "tasks"  # --check renders into a temporary directory instead
SERVER = ROOT / f"images/{BENCH}/standard/server_casa.py"
VERSION = (ROOT / f"images/{BENCH}/VERSION").read_text().strip()
IMAGE = f"ghcr.io/embodied-agent-interface-v2-internal/eai-{BENCH}:{VERSION}"
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
    '"*.anthropic.com", "openrouter.ai", "*.openai.azure.com", "*.cognitiveservices.azure.com"]'
)
AGENT = f"""[agent]
timeout_sec = 3600.0
# The benchmark's demonstrations solve these tasks and are publicly downloadable, so egress is closed to the model APIs.
network_mode = "allowlist"      # model APIs only (scripts/set_agent_egress.py); PROTOCOL §2.7
allowed_hosts = {ALLOWED_HOSTS}
"""
ACTION_TYPE = {12: "ee_delta", 13: "joint_position", 24: "ee_pose"}

# Upstream success checks (robocasa-gr1-tabletop-tasks @ 4840e67, robocasa/environments/tabletop/): the
# PosttrainPnPNovel* tasks use tabletop_24dc.py `_check_success`; PnP*Close use tabletop_{cabinet,drawer,microwave}_pnp.py.
# Posttrain source/target pairs whose distractor config includes "distractor_obj" (tabletop_24dc.py
# distractor_config_for_posttrain): a second object starts on the source container and must not end in the target.
DISTRACTOR_OBJ = {
    "placemat-to-plate", "plate-to-cardboardbox", "plate-to-pan", "placemat-to-bowl", "plate-to-bowl",
    "cuttingboard-to-tieredbasket", "cuttingboard-to-cardboardbox", "tray-to-tieredshelf", "placemat-to-tieredshelf",
}
TIERED = ("tiered basket", "tiered shelf")  # the only containers with spawn regions upstream (the top tier counts)


def sentence(rec: dict) -> str:
    """The task instruction as a sentence (the upstream language annotation has no full stop)."""
    t = rec["instruction"].strip()
    return t if t.endswith(".") else t + "."


def success_text(rec: dict) -> str:
    """What the upstream `_check_success` requires, in words (both instructions)."""
    t = rec["instruction"].strip().rstrip(".")
    m = re.fullmatch(r"pick the (.+) from the (.+) and place it in the (.+)", t)
    if m:
        obj, src, tgt = m.groups()
        if tgt in TIERED:
            inside = f"at least two of its bounding-box keypoints inside the {tgt}'s top tier (its highest spawn region)"
        else:
            inside = (
                f"touching the {tgt}, with its centre horizontally within 0.7 x the {tgt}'s horizontal radius of the "
                f"{tgt}'s centre"
            )
        lines = [
            f"- the {obj} is in the {tgt}: {inside};",
            f"- the {obj} does not touch the counter;",
            f"- the {tgt} is upright (its z axis has a world-z component above 0.8);",
            f"- **both hands are clear**: each grip site (left and right) is more than 0.25 m from the {obj}'s origin and "
            f"more than 0.25 m from the {tgt}'s origin (`any_gripper_obj_far`, th = 0.25) -- release the {obj} and move "
            "both hands away before the end;",
        ]
        if rec["slug"] in DISTRACTOR_OBJ:
            lines.append(f"- the distractor object that starts on the {src} with the {obj} is not in the {tgt};")
        lines[-1] = lines[-1].rstrip(";") + "."
        return "All of these hold on the graded state (upstream `_check_success`, `tabletop_24dc.py`):\n" + "\n".join(lines)
    m = re.fullmatch(r"pick up the (.+), place it into the (\w+) and close the \w+", t)
    if not m:
        raise SystemExit(f"{rec['env']}: no success text for instruction {t!r}")
    obj, fix = m.groups()
    door = "door" if fix != "drawer" else "drawer"
    return (
        f"Both of these hold on the graded state (upstream `_check_success`, `tabletop_{fix}_pnp.py`):\n"
        f"- the {obj}'s centre (its body origin) is inside the {fix}'s interior;\n"
        f"- the {door} is shut: upstream's opening fraction is at most 0.005 (0 = shut, 1 = fully open).\n\n"
        "Where the hands end up is not checked."
    )


def _npy(zf: zipfile.ZipFile, name: str) -> tuple[dict, bytes]:
    """One array of an .npz without NumPy: (header, raw data)."""
    b = zf.read(name)
    if b[:6] != b"\x93NUMPY":
        raise ValueError(f"{name}: not an .npy file")
    n, off = (struct.unpack("<H", b[8:10])[0], 10) if b[6] == 1 else (struct.unpack("<I", b[8:12])[0], 12)
    return ast.literal_eval(b[off : off + n].decode("latin1")), b[off + n :]


def base_pose(rec: dict) -> tuple[list[float], list[float]]:
    """World pose (position, quaternion w x y z) of the robot's base body `robot0_base` in the frozen instance: the
    instance's model_body_pos / model_body_quat (what a reset wrote), indexed in the frozen XML's body order."""
    with zipfile.ZipFile(FROZEN / rec["slug"] / "instance.npz") as zf:
        hx, bx = _npy(zf, "xml.npy")
        xml = bx.decode("utf-32-le" if hx["descr"].startswith("<U") else "utf-8").rstrip("\x00")
        order = ["world"] + [b.get("name") for b in ET.fromstring(xml).find("worldbody").iter("body")]
        top = [b.get("name") for b in ET.fromstring(xml).find("worldbody").findall("body")]
        if "robot0_base" not in top:
            raise SystemExit(f"{rec['env']}: robot0_base is not fixed to the world")
        i = order.index("robot0_base")
        out = []
        for key, k in (("model_body_pos.npy", 3), ("model_body_quat.npy", 4)):
            h, b = _npy(zf, key)
            if h["descr"] != "<f8" or h["fortran_order"] or tuple(h["shape"]) != (len(order), k):
                raise SystemExit(f"{rec['env']}: unexpected {key} {h}")
            out.append(list(struct.unpack_from(f"<{k}d", b, 8 * k * i)))
    return out[0], out[1]


def frame_text(rec: dict) -> str:
    """The base frame's pose in the world (fixed: the GR1 has no mobile base)."""
    (x, y, z), (qw, qx, qy, qz) = base_pose(rec)
    if abs(qx) > 1e-6 or abs(qy) > 1e-6:
        raise SystemExit(f"{rec['env']}: the base is tilted; describe its full rotation")
    yaw = math.degrees(2 * math.atan2(qz, qw))
    c, s_ = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    r = [[c, -s_, 0.0], [s_, c, 0.0], [0.0, 0.0, 1.0]]
    rt = "[" + ", ".join("[" + ", ".join(f"{v:g}" for v in (round(e, 4) + 0.0 for e in row)) + "]" for row in r) + "]"
    return (
        f"The robot's base frame (body `robot0_base`, fixed in the world) has its origin at world "
        f"({x:.5f}, {y:.5f}, {z:.5f}) m and is turned {yaw:+.1f} deg about z (quaternion w x y z "
        f"({qw:.5f}, {qx:g}, {qy:g}, {qz:.5f})): `p_world = R @ p_base + t` with R = {rt}."
    )


def action_text(dim: int) -> str:
    """The native controller's channels, as both instructions state them."""
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
**Task: {sentence(rec)}**
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
  The action's pose targets are in the robot's base frame. {frame_text(rec)}
- Everything in `s.env`, `s.model` and `s.data` is readable (privileged mode).

## Rules
- Write your own controller. Do not use the benchmark's demonstrations, trained policies or any published solution.
- Only the actions count: editing `s.data` or the environment while debugging changes nothing in the replay.
- You have 60 minutes of wall-clock time. Save a working trajectory early, then improve it; do not stop early.
"""


def standard_instruction(rec: dict) -> str:
    env, dim = rec["env"], rec["action_dim"]
    cams = ", ".join(rec["cameras"])
    return f"""# {TITLE} · {env} — STANDARD MODE (robot as a service)

{ROBOT_TEXT[0].upper() + ROBOT_TEXT[1:]} {SCENE}: {ENV_DOC.format(env=env)} (robosuite, MuJoCo).
**Task: {sentence(rec)}**
The scene is one frozen instance: the initial state of one of the benchmark's official demonstrations.

You control the robot **as if it were real hardware**: the simulator runs in a service you cannot open. You get one
client and one episode.

## Rules (real-robot rules)
- **No reset.** What you knock over stays knocked over.
- **No privileged state.** You see what the robot's cameras see (RGB, optional depth, with each camera's
  calibration) and the robot's own state. No object poses, no scene layout, no success signal.
- Your wall-clock budget is 60 minutes (`meta["time_left_s"]`). There is nothing to hand in: the service records the
  episode as the trajectory and grades it. Leave your script at `/app/output/gen.py` for the record.
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
- `get_obs(seconds=s)` keeps applying the last command (before the first one: both grip sites' current poses and the
  current hand commands) while physics runs for `s` seconds; those control steps are part of the episode. Every
  channel is an absolute target, so the grip sites stay within about a millimetre, but the IK's posture term can still
  move the waist and elbows by a few hundredths of a radian while you watch.
- The cameras are mounted on the robot and move with it: use the calibration that comes with each response.
- World frame: metres, z up. In the proprio, `eef_left_*` / `eef_right_*` are the grip sites' positions in the world
  frame; the action's pose targets and the `cmd_*` entries (the last command) are in the robot's base frame.
  {frame_text(rec)}
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
        ("Agent time budget", "3600 s; tokens: protocol default (PROTOCOL §5)"),
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
        f"{ENV_DOC.format(env=env)} with {ROBOT_TEXT.replace('**', '')}: {sentence(rec)} Produce one replayable "
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
        "The sim service replays the recorded episode in a fresh simulator; `tests/grade.py` (separate sandbox, no "
        "network) reads its `final.json`: `success = replay_success ∧ deterministic ∧ live_success`."
    )
    details = [
        ("Action type", f"`{ACTION_TYPE[rec['action_dim']]}` ({rec['action_dim']} channels, `control_dt` 0.05 s)"),
        ("Cameras", ", ".join(f"`{c}`" for c in rec["cameras"]) + " (robot-mounted; calibration in every response)"),
    ]
    return readme(
        readme_head(rec, "standard"), task, DIFFICULTY_STANDARD.replace("\n", " "), reference, verification, details
    )


def privileged_toml(rec: dict) -> str:
    return f"""schema_version = "1.3"
artifacts = ["/app/output/"]

[task]
name = "robot-coding-bench/{BENCH}-{rec["slug"]}-i00-privileged"
description = "{TITLE} ({rec["env"]}, {ROBOT_TEXT.replace("**", "")}): {sentence(rec)} Produce one replayable trajectory of the robot's native controller commands on a frozen instance; graded on the state after the last action."
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

{AGENT}
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
    collect = (
        "for i in $(seq 1 90); do [ -f /data/server.pid ] && break; sleep 2; done; for i in $(seq 1 400); do grep -q "
        "'\\\"finalized\\\": true' /data/final.json 2>/dev/null && break; [ $((i % 15)) -eq 1 ] && kill -USR1 $(cat "
        "/data/server.pid) 2>/dev/null; sleep 2; done; cat /data/final.json"
    )
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
description = "STANDARD MODE (robot as a service, eai-standard/2.1): {TITLE} ({rec["env"]}, {ROBOT_TEXT.replace("**", "")}): {sentence(rec)} The agent only gets a client: the robot's calibrated RGB-D cameras, its own joints and end effector, and native controller commands in chunks; no reset, no object poses; the sim service records the episode and grades a fresh replay of it."
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

# Then the episode ends: SIGUSR1 to the service (re-sent every 30 s, in case it was restarting), which grades it.
[[verifier.collect]]
service = "sim"
command = "{collect}"
timeout_sec = 1500

{AGENT}
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


def main(envs: list[str]) -> None:
    report = json.loads((FROZEN / "report.json").read_text())
    n = 0
    for env in envs:
        rec = report.get(slug(env))
        if rec is None or not verified(rec):
            if envs is not ALL:
                raise SystemExit(f"{env}: frozen instance or reference not verified (re-run import_references.sh)")
            continue
        make(rec)
        n += 1
    print(f"generated {2 * n} task directories")


def snapshot(d: Path) -> dict[str, tuple[bytes, int]]:
    return {str(f.relative_to(d)): (f.read_bytes(), f.stat().st_mode & 0o777) for f in sorted(d.rglob("*")) if f.is_file()}


def check() -> int:
    """Render every task into a temporary directory and compare with tasks/ (no simulator needed)."""
    global TASKS
    real = TASKS
    with tempfile.TemporaryDirectory() as td:
        TASKS = Path(td)
        main(ALL)
        TASKS = real
        fresh = {d.name for d in Path(td).iterdir()}
        have = {d.name for d in real.glob(f"{BENCH}-*") if (d / "task.toml").is_file()}
        bad = sorted(have - fresh)
        for name in sorted(fresh):
            if name not in have or snapshot(Path(td) / name) != snapshot(real / name):
                bad.append(name)
    for name in bad:
        print(f"FAIL tasks/{name}: differs from the generator's output (run scripts/{BENCH}/generate.py)")
    print(f"{len(fresh) - len(bad)}/{len(fresh)} task directories match" if not bad else f"{len(bad)} mismatched")
    return 1 if bad else 0


ALL = sorted(SOURCES)
if __name__ == "__main__":
    if "--check" in sys.argv[1:]:
        sys.exit(check())
    main(sys.argv[1:] or ALL)
