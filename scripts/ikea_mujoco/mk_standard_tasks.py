#!/usr/bin/env python3
"""Render the IKEA MuJoCo STANDARD-mode tasks (robot as a service): tasks/ikea-<task>-i00-standard, the twins of
tasks/ikea-<task>-i00-privileged (scripts/ikea_mujoco/mk_tasks.py) on the same frozen scenes.

usage: python3 scripts/ikea_mujoco/mk_standard_tasks.py [--check] [--refs <dir>] [task ...]
  no task   every task in bindings.json
  --check   write nothing; exit 1 if a task directory would change
  --refs    copy solution/oracle_actions.npz from <dir>/<task>.npz (where present): the standard reference, made by
            standard/std_reference.py from the privileged twin's solution/trajectory.npz (time-dilated to the joint-speed
            rule); without it, the task's existing solution/oracle_actions.npz is kept

Inputs: tasks.json, assets.json, bindings.json (as mk_tasks.py), standard/rigs.json (the camera rig per task) and the files
copied unchanged into every task:
  scripts/eai_standard/v2_4/   rcb_limited.py (the 2.4 service layer), rcb_client.py (the agent's client)
  scripts/eai_standard/        rcb1.py, run.sh, client-requirements.txt
  scripts/ikea_mujoco/shared/  rcb_ikea.py (the scene runtime the service steps)
  scripts/ikea_mujoco/standard/ server.py, ikea_rig.py, finalize.sh (the sim service), grade.py (the verifier: transcribes
                               the live episode's final.json; no grading replay, owner 2026-10-17, board 0150/0151),
                               oracle_replay.py (the reference solution); std_reference.py makes the references
Images: the sim sidecar runs images/ikea-mujoco/sim (eai-ikea-mujoco + Nyx in its own venv, EGL, ffmpeg); the agent and the
verifier the shared standard client base (scripts/eai_standard/client.env)."""
from __future__ import annotations
import argparse, json, math, pathlib, shutil, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import mk_tasks as P  # noqa: E402  texts, bindings, the privileged runtime binding

STD = HERE / "standard"
EAI = ROOT / "scripts/eai_standard"
TC = P.TC
IMAGE = P.IMAGE
SIM_IMAGE = f"ghcr.io/mll-lab-nu/eai-ikea-mujoco-sim:{(ROOT / 'images/ikea-mujoco/sim/VERSION').read_text().strip()}"
CLIENT_IMAGE = dict(l.split("=", 1) for l in (EAI / "client.env").read_text().splitlines() if "=" in l and not l.startswith("#"))["CLIENT_IMAGE"]
RIGS = json.loads((STD / "rigs.json").read_text())
# RoboARC's Nyx driver (its shared/nyx_direct.py, sha256 4809c45a7a5c...), a byte-identical copy kept here so that this
# benchmark builds from its own paths; copied unchanged into every task (ikea_nyx.py uses it)
NYX_DIRECT = STD / "nyx_direct.py"
AGENT_S = P.AGENT_S               # the privileged twin's wall-clock cutoff (PROTOCOL v2.0 H.7): the only hard budget
# The speed rule's numbers, for the texts: THE table is rcb_ikea.JOINT_SPEED_LIMITS_RAD_S / GRIPPER_SPEED_LIMITS (the
# service and the grader read it); checked against its source here, so the texts cannot drift from it.
SPEEDS = {"panda": {"arm": (2.175, 2.175, 2.175, 2.175, 2.61, 2.61, 2.61)}, "viperx": {"arm": (3.14159,) * 6}}   # grippers: none
_RCB_SRC = (P.SHARED / "rcb_ikea.py").read_text()
assert "(2.175, 2.175, 2.175, 2.175, 2.61, 2.61, 2.61)" in _RCB_SRC and "j: 3.14159 for j in" in _RCB_SRC \
    and "\nGRIPPER_SPEED_LIMITS: dict = {}" in _RCB_SRC, "rcb_ikea's speed table changed: update SPEEDS and the texts"
PROTOCOL = "eai-standard/2.4"
# Tasks that ship privileged-only (a privileged task without a standard twin): none. The tasks out of this wave in BOTH
# modes are mk_tasks.WIP (no reference passes under the arm joint-speed clamp; P.task_dir: rendered under
# scripts/ikea_mujoco/wip/tasks/, never under tasks/). Their standard twins render there too, without a reference. The
# scans behind WIP (2026-10-15, fresh replays with final_check): eket, 10 retimings + the original rows on the fix-3b scene
# with the EPA-patched MuJoCo (track at lags 0-0.3, centred, straight-line dilation) all stop before side B's slide;
# vesken, 11 retimings (the same, plus two despike settings) all stop at 6 of the 23 snap connections.
NO_TWIN: dict[str, str] = {}
EVID = json.loads((HERE / "standard_evidence.json").read_text()) if (HERE / "standard_evidence.json").is_file() else {}


def name(t: str) -> str:
    return P.name(t, "standard")


def robot(t: str) -> str:
    return P.TEXTS["tasks"][t]["robot"]


def sep(t: str) -> str:
    """The scene's arm-name separator, from the model's actuator names in the binding: `left_` / `right_` in most scenes,
    `left/` / `right/` (MuJoCo Menagerie's attach prefixes) in stegesund and uppsta. server.py derives the same from the model."""
    acts = P.BIND["tasks"][t]["actuators"]
    s = acts[0][len("left")]
    assert s in "_/" and all(a.startswith(("left" + s, "right" + s)) for a in acts), (t, acts)
    return s


def rig(t: str) -> dict:
    d, p = RIGS["defaults"], RIGS["tasks"][t]
    cx, cy, cz = p["center"]; fx, fy = p["front"]; n = math.hypot(fx, fy); fx, fy = fx / n, fy / n; s = p["scale"]
    r = lambda v: [round(x, 4) for x in v]  # noqa: E731
    cams = {
        "cam_high": {"type": "static", "pos": r([cx + fx * 0.30 * s, cy + fy * 0.30 * s, cz + 1.2 * s]),
                     "lookat": r([cx - fx * 0.15 * s, cy - fy * 0.15 * s, cz]), "fovy": d["fovy"]},
        "cam_low": {"type": "static", "pos": r([cx + fx * 0.85 * s, cy + fy * 0.85 * s, cz + 0.18]),
                    "lookat": r([cx - fx * 0.2 * s, cy - fy * 0.2 * s, cz + 0.05]), "fovy": d["fovy"]}}
    for a in ("left", "right"):
        if robot(t) == "viperx":
            cams[f"cam_{a}_wrist"] = {"type": "link", "camera": f"{a}{sep(t)}wrist_cam", "fovy": d["fovy"]}
        else:
            w = d["panda_wrist"]
            cams[f"cam_{a}_wrist"] = {"type": "link", "body": f"{a}{sep(t)}hand", "pos": w["pos"], "lookat": w["lookat"], "up": w["up"],
                                      "fovy": d["fovy"]}
    return {"note": "generated by scripts/ikea_mujoco/mk_standard_tasks.py from scripts/ikea_mujoco/standard/rigs.json",
            "width": d["width"], "height": d["height"], "cameras": cams, "nyx": nyx_look(cx, cy, cz, fx, fy)}


# RoboARC's look (configs/presentation_configs/nyx_lab.yaml, configs/camera_configs/aloha_observation.yaml): 32 spp,
# denoised, the studio HDRI at 1.0 and four point lights at z 2.40 over its table (centre x -0.1356786, top 0.9196429),
# RoboARC's cameras on its -y side. Here the same offsets from the work-surface centre: RoboARC's -y = the rig's front, its
# +x = the cameras' right.
NYX_LIGHTS = [((-0.60, -0.45), 3.0, (1.0, 0.98, 0.94), True), ((-0.60, 0.45), 1.0, (1.0, 0.98, 0.94), False),
              ((0.60, -0.45), 1.0, (0.96, 0.98, 1.0), False), ((0.60, 0.45), 1.0, (0.96, 0.98, 1.0), False)]
NYX_TABLE = (-0.1356786, 0.0, 0.9196429)


def nyx_look(cx, cy, cz, fx, fy) -> dict:
    rx, ry = -fy, fx                       # the cameras' right (they look along -front)
    lights = []
    for (x, y), intensity, color, shadow in NYX_LIGHTS:
        a, b = x - NYX_TABLE[0], -(y - NYX_TABLE[1])        # along the cameras' right, toward the cameras
        lights.append({"type": "point", "pos": [round(cx + a * rx + b * fx, 4), round(cy + a * ry + b * fy, 4),
                                                 round(cz + 2.40 - NYX_TABLE[2], 4)],
                       "intensity": intensity, "color": list(color), "shadow": shadow})
    return {"renderer": "nyx", "spp": 32, "denoise": True, "env_intensity": 1.0, "near": 0.01, "far": 5.0, "far_link": 3.0,
            "lights": lights}


def speed_words(t: str, dt: float, short: bool = False) -> str:
    """The speed rule in words (rcb_ikea's table; server.py builds the same rule from it). Grippers are not limited."""
    if robot(t) == "panda":
        return ("joints 1-4 2.175 rad/s, joints 5-7 2.61 rad/s" if short else
                f"at most {2.175 * dt:g} rad per control step on joints 1-4 (`actuator1`..`actuator4`: 2.175 rad/s) and "
                f"{2.61 * dt:g} rad on joints 5-7 (`actuator5`..`actuator7`: 2.61 rad/s), the Franka Panda's joint velocity "
                "limits")
    v = SPEEDS["viperx"]["arm"][0]
    return (f"{v:g} rad/s on every arm joint" if short else
            f"at most {v * dt:g} rad per control step on every arm joint ({v:g} rad/s, the ViperX 300 s joint velocity limit)")


def bullets(items) -> str:
    return "\n".join(f"- {s}" for s in items)


def task_text(t: str) -> dict:
    x, r = P.TEXTS["tasks"][t], P.robot_text(t)
    return {"task_text": (f"IKEA MuJoCo {x['title']} ({x['manual']}) with {r['words']}. {x['goal']} Success requirements: "
                          + " ".join(x["requirements"]) + f" {P.TEXTS['terminal']} Mechanism: {x['mechanism']}")}


# The verifier transcribes the sidecar's final.json and copies the live video: no replay (board 0151), seconds of work.
VERIFIER_S = 600


def step_ms(t: str) -> float | None:
    e = EVID.get(t, {})
    return 1000.0 * e["service_time_s"] / e["rows"] if e.get("service_time_s") and e.get("rows") else None


def task_toml(t: str) -> str:
    x, r = P.TEXTS["tasks"][t], P.robot_text(t)
    arts = ["final.json", "episode.json", "episode.jsonl", "trajectory.npz", "live.mp4", *(f"live.{i}.mp4" for i in range(2, 8)),
            "live.last.png", "server.log",
            "journal.f64", "startups.jsonl", "startup_binding.json"]
    art = "\n".join(f'  {{ source = "/data/{a}", service = "sim" }},' for a in arts)
    return f'''schema_version = "1.3"
artifacts = [
{art}
  "/app/output/",
]

[task]
name = "robot-coding-bench/{name(t)}"
description = "STANDARD MODE (robot as a service, {PROTOCOL}): IKEA MuJoCo {x['title']} ({r['short']}, MuJoCo 3.14.0 CPU) on the same frozen scene as the privileged task. {x['goal']} The agent only gets a client: get_obs (RGB from four ALOHA-style cameras, optional depth, proprioception, calibrated cameras), submit (joint_position chunks, joint targets within the robot's joint velocity limits), stateless kinematics, every pose in the robot's frame. No reset, no privileged state; the sim service records and grades the live episode (no grading replay)."
authors = [{{ name = "Xiaoyu" }}]
keywords = ["robotics", "ikea", "furniture-assembly", "mujoco", "{robot(t)}", "bimanual", "standard-mode", "trajectory"]

[metadata]
author_name = "Xiaoyu"
task_type = "trajectory"
simulator = "mujoco"              # plain MuJoCo 3.14.0, CPU float64, the scene's own runtime and mechanism
robot = "{r['robot']}"            # both arms (docs/TAXONOMY.md)
family = "ikea_{t}"
mode = "standard"                 # RGB + proprioception only; no part poses, no success predicate, no reset
dynamics = "static"               # scene dynamics (docs/protocol/README.md §2): only the robot and gravity do work; springs, latches and threads are passive
protocol = "{PROTOCOL}"           # the shared 2.4 service layer; 2.1 / 2.2 requests are served unchanged
oracle = "full"
grasp = "physical (finger friction; no assisted grasp, no welds to a gripper)"
success_rule = "the scene's success.py + the terminal rules (released, at rest, no breakdown): evaluated by the sim service on the live episode after each call (the first settled success ends the episode) and at its end: at the last row and again after a 1.0 s hold of it (on a copy); no grading replay"
instance_seed = 0                 # one frozen scene: images/ikea-mujoco scene {t}, digest {P.ASSETS['tasks'][t]['digest'][:12]}
expert_time_estimate_hours = {x['hours']}

[verifier]
timeout_sec = {VERIFIER_S}.0
environment_mode = "separate"     # tests/Dockerfile: the shared client base; transcribes the sim service's final.json, no network
network_mode = "no-network"

# The agent's time is up: stop whatever it left running in its container. Harbor stops that container only after
# collecting from it (~12 s), and a script still running there would keep driving the robot past the deadline.
[[verifier.collect]]
service = "main"
command = "kill -9 -1 2>/dev/null; exit 0"
timeout_sec = 30

[[verifier.collect]]
service = "sim"
command = "sh /srv/finalize.sh"   # end (judge the live episode as it stands) + dump + exit the service, write final.json; no replay
timeout_sec = 7200                # the end waits through a call in progress, a crash-recovery resume and the live video's close

[agent]
timeout_sec = {AGENT_S}.0             # Agent wall-clock budget (the privileged twin's; PROTOCOL v2.0 H.7); verifier has its own budget
{P.EGRESS}
[environment]
build_timeout_sec = 1800.0
cpus = 4
memory_mb = 16384

[verifier.environment]
build_timeout_sec = 1800.0
cpus = 2                          # reads final.json, copies the live video: no simulator
memory_mb = 2048
'''


def compose(t: str) -> str:
    return f'''# Standard mode: the simulator runs in the `sim` sidecar (the agent cannot open it); the agent only reaches port 8000.
# No `expose`/`ports` on sim: under Harbor's egress control it shares main's network namespace (localhost:8000).
# Physics: MuJoCo 3.14.0 on the CPU (the scene's own runtime). Cameras: RGB from Nyx (RoboARC's renderer, Vulkan; a
# separate render process, environment/sim/ikea_nyx.py), depth from MuJoCo's EGL raster, on the one GPU reserved below;
# NVIDIA_DRIVER_CAPABILITIES=all makes the container toolkit mount the driver's Vulkan and EGL libraries, which the image's
# ICD / vendor files name (images/ikea-mujoco/sim/Dockerfile). No `runtime: nvidia`.
# Crash recovery: run.sh exits non-zero when the service crashes, compose restarts the container (same container, same
# /data) and the service replays its journal into the same episode, never a reset.
services:
  main:
    depends_on: [sim]
  sim:
    image: {SIM_IMAGE}
    volumes:
      - ./sim:/srv:ro
    working_dir: /tmp
    command: sh /srv/run.sh
    restart: on-failure:6          # N >= 3 (PROTOCOL §4.1); a resume continues the episode
    environment:
      RCB_TASK: {t}
      RCB_DATA: /data
      RCB_WALL_CLOCK_S: "{AGENT_S}"   # the agent's wall clock, from its first request (= [agent] timeout_sec), server.py
      RCB_STARTUP_TIMEOUT_S: "900"
      PYTHONPATH: /srv
      RCB_SESSION_LOG: ""
      MUJOCO_GL: egl
      PYOPENGL_PLATFORM: egl
      OMP_NUM_THREADS: "1"
      NVIDIA_DRIVER_CAPABILITIES: all
    shm_size: "1gb"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
'''


ENV_DOCKERFILE = f'''# Standard mode: the agent container has NO simulator and no scene files — only Python and the client, on the shared
# pinned client base with the shared pins (scripts/eai_standard/client.env, client-requirements.txt).
FROM {CLIENT_IMAGE}
COPY client-requirements.txt /tmp/client-requirements.txt
RUN pip install --no-cache-dir -r /tmp/client-requirements.txt
COPY rcb_client.py rcb1.py /opt/tools/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
'''

TESTS_DOCKERFILE = f'''# Separate verifier sandbox: grades the sim service's own artifacts (/data/final.json, the live episode's verdict);
# needs nothing but python (no simulator: nothing is replayed, board 0151).
FROM {CLIENT_IMAGE}
COPY grade.py test.sh /tests/
RUN chmod +x /tests/test.sh && mkdir -p /logs/verifier
WORKDIR /tests
'''



def test_sh(t: str) -> str:
    return f'''#!/bin/bash
# Verifier (separate sandbox, no network): the sim sidecar's artifacts were uploaded to /data by Harbor. grade.py
# transcribes final.json, the live episode's verdict (no grading replay), into reward.json / reward.txt.
rm -rf /logs/verifier/*   # verdicts from an earlier run never survive (docs/protocol/README.md §2.6)
# The agent's files are untrusted input (PROTOCOL v2.0 H.1): no link out of /app/output, no FIFO, socket or device.
find /app/output -mindepth 1 \\( -type l -o -type p -o -type s -o -type b -o -type c \\) -delete 2>/dev/null || true
mkdir -p /logs/verifier
python /tests/grade.py {t} 2> /logs/verifier/grade.log
chmod 0644 /logs/verifier/reward.txt /logs/verifier/reward.json
'''


SOLVE = '''#!/bin/bash
# Oracle (standard mode): submits the standard reference's control steps (solution/oracle_actions.npz: the privileged
# reference slowed down to the joint-speed rule) through the client, one control step per row (hold), as float64.
# Uses no privileged information at run time (only the pre-recorded rows).
set -e
mkdir -p /app/output
cp /solution/oracle_replay.py /app/output/gen.py
python /solution/oracle_replay.py
'''


def instruction(t: str) -> str:
    x, r, b = P.TEXTS["tasks"][t], P.robot_text(t), P.BIND["tasks"][t]
    vx = robot(t) == "viperx"
    nj = 6 if vx else 7
    dt_ms = 4e3 * b["timestep"]
    sp = sep(t)
    root = f"left{sp}base_link" if vx else f"left{sp}link0"
    ms = step_ms(t)
    timing = (f"One control step takes about {ms:.1f} ms of wall clock here (the simulation runs at about {dt_ms / ms:.2f}x real "
              f"time), so a `submit` of the maximum 10 s chunk takes about {1e4 / dt_ms * ms / 1000:.0f} s."
              if ms else "One control step takes a few ms of wall clock (the simulation runs slower than real time).")
    return f'''# IKEA MuJoCo · {x['title']} — STANDARD MODE (robot as a service, {PROTOCOL})

You control a robot (**{r['words']}**; plain MuJoCo 3.14.0 on the CPU) **as if it were real hardware**: the simulator
runs in a service you cannot open. You get one client and one episode: cameras, proprioception and joint commands.
**Task:** {x['goal']}

## Success requirements

{bullets(x['requirements'])}

{P.TEXTS['terminal']}

Here the service checks (1)-(4) after every `submit` and every `get_obs(seconds > 0)`. When they all hold, it also checks
them after holding your last row 1.0 s more, on a copy (the robot is not moved): if that settled check passes too, the
episode ends with success (`meta["reason"]` is `success`); if not, the episode goes on and you can still fix it
(`meta["settle_failed"]` counts such checks). A breakdown ends the episode at once (`meta["reason"]` is
`sim_breakdown`), with no success. An episode that ends otherwise (your time is up) is judged as it stands by the same
two checks. The task is scored 1 only if the live episode succeeded; nothing is replayed afterwards.

## Physics and mechanism

- Parts move only through contact with the robot, gravity and the scene's own mechanism. {x['mechanism']}
- Grasps are physical: friction from the finger contacts. Nothing attaches a part to a gripper, and there is no assist.

## Rules (real-robot rules)
- **No reset.** The episode ends on success (above), on a simulator breakdown, when your time is up, or on a simulator
  error. What you do to the scene stays done: plan, observe, then act in small chunks.
- **No privileged state.** You see what the cameras see (RGB, and depth when you ask for it) plus the robot's own state:
  joint positions, velocities and actuator forces, gripper openings, tool-frame poses. Nothing tells you where the parts,
  the table or the work surface are (no poses, positions or heights of the scene). The success check is not exposed; the
  requirements above still apply in full.
- **Your only budget is the time limit (`## Time limit`)**; there is no step budget. The service also ends the episode
  itself (`meta["reason"]` is `timeout`; it is graded as it stands) when its own count of that limit,
  `meta["time_left_s"]`, reaches 0. That count starts at your first request to the service, so it never reaches 0 before
  your time is up.
- There is nothing to hand in: the service records your episode as the trajectory and grades it. Leave the script that
  drove the robot at `/app/output/gen.py`, and save useful frames and scripts under `/app/output/` as you go.

## Client (already installed; `python` from any directory)
```python
from rcb_client import Robot
r = Robot()                                    # finds the service (sim:8000 / localhost:8000), waits until it is ready
spec = r.spec()                                # action layout and limits, cameras (intrinsics, mounts), proprio layout, world frame, budget
obs = r.get_obs()                              # current frames: obs.last[cam] -> uint8 (480, 848, 3)
obs = r.get_obs(depth=True)                    # + obs.last_depth[cam] -> float32 (480, 848) z-depth in metres (0 = no reading)
obs.meta["cameras"][cam]                       # intrinsic_cv, extrinsic_cv (world -> camera, OpenCV axes), cam2world_gl
obs.group("tcp_pose", now=True)                # proprio groups: joint_pos, joint_vel, gripper_opening, tcp_pose, joint_cmd, joint_effort
res = r.submit("joint_position", rows, dt={dt_ms / 1e3:g}, interpolate="linear", cameras=["cam_high"], video="mp4")
res.meta["executed_rows"], res.meta["clipped"], res.meta["done"], res.meta["reason"], res.meta["time_left_s"]
res.video["cam_high"]                          # mp4 bytes of the chunk; video="frames" gives res.frames[cam] (N, H, W, 3)
obs = r.get_obs(seconds=2.0)                   # hold the last command, simulate 2 s and return the video (<= 30 s, and
                                               # at most spec()["max_frames_per_call"] frames: cameras x (fps x s + 2),
                                               # x 6 with per-frame depth, x 4 with legacy depth)
r.fk(q); r.ik({{"{f'left{sp}gripper' if vx else f'left{sp}tcp'}": [x, y, z, qw, qx, qy, qz]}})   # stateless kinematics on the robot's model
r.status()                                     # calls, control steps, done, reason, time left
```
A connection error means the service crashed and is resuming the SAME episode: call `r.wait_ready()` and check
`r.status()` before you continue (`spec()["on_service_error"]`).

## Robot, actions, observations
- **Action** `joint_position`: rows of {b['nu']} values, float32 or float64, layout `spec()["action_types"]["joint_position"]["layout"]`:
  {r['action']}. One control step is {dt_ms:g} ms ({1e3 / dt_ms:.0f} Hz: the row is applied for 4 physics steps of
  {1e3 * b['timestep']:g} ms). `dt` must be a multiple of {dt_ms / 1e3:g} s (at most 0.5 s); `hold` keeps each row for
  its `dt`, `linear` interpolates the arm targets. A chunk covers at most 10 s. Out-of-range values are clipped to the
  actuator's control range and reported in `meta["clipped"]`. Speed rule (the robot's real limits; clamp, not fail): arm joint targets move {speed_words(t, dt_ms / 1e3)}
  (`spec()["robot_spec"]["controller"]`); a row that asks for more takes the control steps it needs, and
  `meta["clipped"]` says so. The gripper command is not limited: it switches at the row. The arms are position servos with the scene's
  gains and force limits; use `obs.group("joint_cmd", now=True)` as the starting row to move smoothly.
- **Cameras** (ALOHA-style, 848 x 480, vertical field of view 58 deg): `cam_high` (static, above the front of the work
  area, looking down), `cam_low` (static, low at the front), `cam_left_wrist` and `cam_right_wrist` (on each hand, looking
  at the fingers; they move, so use the pose that comes with each frame). Intrinsics and mounts in `spec()["cameras"]`,
  the per-frame world -> camera pose in every response; depth on request.
- **Proprioception** (`spec()["proprio_layout"]`, groups in `spec()["proprio_groups"]`): per arm the {nj} joint positions
  and velocities, the gripper opening (m), the tool-frame pose ({r['tcp']}: x y z + qw qx qy qz, world frame), the
  applied commands and the actuator forces.
- **World frame**: origin at the left arm's base link (`{root}`) on its mounting, +z up, x along that arm's forward
  direction; metres, quaternions **WXYZ**. The proprio tool-frame poses, the camera extrinsics and mounts and `/kinematics`
  are all in it; no positions of the scene are given. `spec()["robot_spec"]["base"]` gives the right arm's base pose in it
  (the rig's fixed geometry).
- Not available (simulator privilege): part poses, positions of anything in the scene, the scene files, contact forces on
  parts, the success check itself.

## Time per call
{timing} The client waits long enough for any call; a client timeout or a connection error means the connection or the
service failed (see above), not that the call is still on its way: do not resend it blindly. `r.operation_status()`
(the last call's operation, or `r.operation_status(operation_id)`) asks the service what became of a call.

## Time limit
You have {AGENT_S} seconds ({AGENT_S // 60} min) to complete this task. This is wall-clock time from the start of your
session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the
episode is graded as it stands at that moment. The service's `meta["time_left_s"]` counts the same limit from your first
request to the service, so your real time left is `time_left_s` minus the time you spent before that request. Plan by it.
'''


def std_ref_text(t: str, ref: dict) -> str:
    if P.ref_words(t):
        return (f"The rows are the task's one reference, the same file as the privileged twin's `solution/trajectory.npz`: "
                f"{P.ref_words(t)}")
    return ("The rows are the privileged twin's reference trajectory brought within the joint-speed rule by "
            f"`scripts/ikea_mujoco/standard/std_reference.py` ({ref_words(ref)})")


def ref_words(ref: dict) -> str:
    """How the standard reference was made from the privileged one (standard_evidence.json reference)."""
    head = (f"`make --method {ref.get('method')}" + (f" --lag {ref.get('lag_rad'):g}" if ref.get("method") == "track" else "")
            + "`: target glitches of one to a few control steps, which the servos never followed, replaced by the running "
            f"median ({ref.get('despiked_rows', '?')} rows); then ")
    if ref.get("method") == "track":
        return head + ("every privileged row in order through a slew-limited tracker: each control step an arm joint target "
                       "moves toward the current row by at most its limit, and the next row is taken once every joint is within "
                       f"{ref.get('lag_rad', '?'):g} rad of it, so time is stretched only where the rows are faster than the limits "
                       f"({ref.get('rows_in', '?')} privileged rows, {ref.get('steps_added', '?')} control steps added, "
                       f"{ref.get('rows_out', '?')} in all)")
    if ref.get("method") == "centred":
        return head + ("every row keeps its time: per arm joint the mean of a forward and a backward slew-limited pass, so a move "
                       "faster than the limits starts a little earlier and ends a little later, centred on the original "
                       f"({ref.get('rows_out', '?')} control steps; largest target deviation {ref.get('max_abs_dev_rad', '?')} rad)")
    return head + f"{ref.get('method')} ({ref.get('rows_out', '?')} control steps)"


def readme(t: str) -> str:
    x, r, b = P.TEXTS["tasks"][t], P.robot_text(t), P.BIND["tasks"][t]
    e = EVID.get(t, {})
    checks = e.get("checks")
    ver = (f"Before 2026-10-17 (graded then by the verifier's two replays; history, not re-run since): Harbor checks on {e['host']} ({e['date']}): " + "; ".join(f"`{c['agent']}` scored {c['reward']}" + (f" ({c['note']})" if c.get("note") else "")
                                                                     for c in checks) + ".") if checks else "Harbor oracle / nop checks: pending."
    ref = e.get("reference", {})
    return f'''# {name(t)}

| | |
|---|---|
| Benchmark | IKEA MuJoCo |
| Mode | standard |
| Twin | `{P.name(t)}` |
| Simulator / robot | `mujoco` / `{r['robot']}` |
| Family / instance | `ikea_{t}` / seed 0 |
| Oracle | `full` |
| Agent time budget | {AGENT_S} s wall clock (the privileged twin's); tokens: protocol default (PROTOCOL §5) |
| Base image | `{SIM_IMAGE}` (sim), the shared client base (agent, verifier) |

## Task
{x['manual']} in plain MuJoCo 3.14.0 (CPU, float64) with {r['words']}, through the robot service ({PROTOCOL}; 2.1 / 2.2
requests are served unchanged): RGB from four ALOHA-style cameras (optional depth), proprioception, `joint_position`
chunks, stateless kinematics, every pose in the robot's frame; no reset and no privileged state. {x['goal']}

## Difficulty
The privileged twin's bimanual assembly with physical grasps, from cameras and proprioception only, in one episode
without reset; {b['nu']}-D actuator action at {1 / (4 * b['timestep']):.0f} Hz, joint targets within the robot's joint
velocity limits ({speed_words(t, 0, True)}). The reference needs {e.get('rows', '?')} control steps ({e.get('sim_time_s', '?')} s of simulated
time).

## Reference solution
{f"None yet: this task is work in progress ({P.WIP[t]}); `solution/solve.sh` needs a `solution/oracle_actions.npz` that passes. " if t in P.WIP else ""}`solution/solve.sh` runs `solution/oracle_replay.py`: it submits the control steps of `solution/oracle_actions.npz` through
the client as `joint_position` chunks of 10 s, `hold`, one control step per row, as float64 (the client's transport;
`Robot.submit` sends float32), so the service executes exactly those rows. {std_ref_text(t, ref)},
so the service's speed limiter never has to act (`n_clipped` 0).

## Verification
The sim service (`environment/sim/server.py`) steps the scene's own runtime (`rcb_ikea.Session.step`: `data.ctrl[:] =
row; S.step(4)`), applies the joint-speed rule, evaluates the grader's terminal rules (`rcb_ikea.Session.status()`:
success.py, released, at rest, no breakdown) after every call and, when they hold, `Session.final_check()` (the same after
a 1.0 s hold of the last row), both on a snapshot restored bit-exactly afterwards, ends the episode at the first settled
success or at a breakdown, and journals every executed control step; at the end it writes
`/data/trajectory.npz` (all executed control steps, float64: the replayable deliverable) and the final state hash; an
episode that ends otherwise (timeout) is judged as it stands by the same two checks. Before the episode the service checks
the scene file by file against `runtime_binding.json` and by its initial-state hash (`instance_mismatch`, infrastructure).
The verifier (`tests/grade.py`, separate sandbox, no network, the shared client base) transcribes `final.json`: pass iff
the live episode succeeded (`graded_by_live` 1, `replays` 0). No grading replay runs (owner, 2026-10-17, board 0151).

{ver}

## Details
| | |
|---|---|
| Grasping | physical (finger friction), no assist |
| Success rule | the scene's `success.py` + the terminal rules (released, at rest, no breakdown), on the live episode: after every call and at its end, at the last row and again after a 1.0 s hold of it (on a copy) |
| Frame | every pose the agent gets or gives is in the robot frame: origin at the left arm's base link, +z up (`spec.world`); the scene's own world frame never leaves the sim service |
| Speed rule | targets within the robot's real limits ({speed_words(t, 0, True)}; the table and its sources: `rcb_ikea.JOINT_SPEED_LIMITS_RAD_S` / `GRIPPER_SPEED_LIMITS`), clamped per control step, as the privileged twin's Session; faster rows take the control steps they need (`meta.clipped`), as RoboARC's rule |
| Cameras | `cam_high`, `cam_low` (static), `cam_left_wrist`, `cam_right_wrist` (on the hands); 848 x 480, fovy 58 deg; added at service start (`environment/sim/ikea_rig.py`, `rig.json`), the model is unchanged; RGB: Nyx, RoboARC's renderer and look (path tracer, 32 spp, denoised; studio HDRI and point lights; `environment/sim/ikea_nyx.py` with RoboARC's `nyx_direct.py`); depth: MuJoCo's raster; on the sidecar's GPU |
| Video | `/data/live.mp4` (cam_high, 10 frames per simulated second, recorded during the live episode), copied to the verifier logs; never affects the verdict |
| Scene | `/opt/ikea/scenes/{t}/` in the images; digest `{P.ASSETS['tasks'][t]['digest'][:16]}…` |
| Initial state | sha256 `{b['initial_state_sha256'][:16]}…` of the mjSTATE_INTEGRATION vector |

### Budget
The wall clock only, the privileged twin's cutoff (PROTOCOL v2.0 H.7): `[agent] timeout_sec` = {AGENT_S} s. The service
counts the same limit from the agent's first request (`spec.budget.wall_clock_s`, `meta.time_left_s`) and ends the
episode with reason `timeout` when it runs out; that count never runs out before Harbor's.

### Deviations
- `ee_pose` is not offered (only `joint_position`, the scene's actuator layout); `/kinematics` gives FK / IK.
- Graded by the live episode (the settled check on the live simulator); no grading replay, in the sidecar or the
  verifier (owner, 2026-10-17, board 0150/0151).

### Goal
{x['goal']}

### Success requirements
{bullets(x['requirements'])}

{P.TEXTS['terminal']}

### Mechanism
{x['mechanism']}
'''


def render(t: str, out: pathlib.Path, refs: pathlib.Path | None) -> None:
    files = {"task.toml": task_toml(t), "instruction.md": instruction(t), "environment/Dockerfile": ENV_DOCKERFILE,
             "environment/docker-compose.yaml": compose(t), "tests/Dockerfile": TESTS_DOCKERFILE, "tests/test.sh": test_sh(t),
             "solution/solve.sh": SOLVE, "environment/sim/runtime_binding.json": P.binding(t),
             "environment/sim/rig.json": json.dumps(rig(t), indent=1) + "\n",
             "environment/sim/task_text.json": json.dumps(task_text(t), indent=1) + "\n",
             "solution/oracle_meta.json": json.dumps({"K": 1, "interpolate": "hold", "dtype": "float64",
                                                      "rows": "the privileged twin's solution/trajectory.npz, time-dilated to the joint-speed "
                                                              "rule by scripts/ikea_mujoco/standard/std_reference.py",
                                                      **EVID.get(t, {}).get("reference", {})}, indent=1) + "\n"}
    for rel, s in files.items():
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(s)
        if rel.endswith(".sh"):
            p.chmod(0o755)
    copies = {"environment/rcb_client.py": EAI / "v2_4/rcb_client.py", "environment/rcb1.py": EAI / "rcb1.py",
              "environment/client-requirements.txt": EAI / "client-requirements.txt",
              "environment/sim/rcb_limited.py": EAI / "v2_4/rcb_limited.py", "environment/sim/rcb1.py": EAI / "rcb1.py",
              "environment/sim/run.sh": EAI / "run.sh", "environment/sim/rcb_ikea.py": P.SHARED / "rcb_ikea.py",
              "environment/sim/server.py": STD / "server.py", "environment/sim/ikea_rig.py": STD / "ikea_rig.py",
              "environment/sim/finalize.sh": STD / "finalize.sh", "tests/grade.py": STD / "grade.py",
              "solution/oracle_replay.py": STD / "oracle_replay.py",
              "environment/sim/ikea_nyx.py": STD / "ikea_nyx.py", "environment/sim/nyx_direct.py": NYX_DIRECT}
    for rel, src in copies.items():
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, out / rel)
        if rel.endswith(".sh"):
            (out / rel).chmod(0o755)
    acts = out / "solution/oracle_actions.npz"
    src = refs / f"{t}.npz" if refs is not None and (refs / f"{t}.npz").is_file() else P.task_dir(t, "standard") / "solution/oracle_actions.npz"
    if P.closed_loop_ref(t) is not None:     # the task's closed-loop reference (scripts/ikea_mujoco/oracles/<task>/)
        src = P.closed_loop_ref(t)
    if src.is_file() and src.resolve() != acts.resolve():
        shutil.copyfile(src, acts)
    (out / "README.md").write_text(readme(t))
    TC.normalize(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tasks", nargs="*")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--refs", type=pathlib.Path, default=None)
    a = ap.parse_args()
    bad = [t for t in a.tasks if t in NO_TWIN]
    if bad:
        ap.error(f"{bad}: privileged-only in this wave (NO_TWIN)")
    tasks = a.tasks or [t for t in P.default_tasks() if t not in NO_TWIN]
    changed = []
    for t in sorted(set(NO_TWIN) | set(P.WIP)) if not a.tasks else []:
        dst = P.TASKS / name(t)                 # a twin-less or WIP task has no standard dir under tasks/
        if dst.is_dir():
            changed.append(f"{name(t)} (removed from tasks/: {'NO_TWIN' if t in NO_TWIN else 'WIP'})")
            if not a.check:
                shutil.rmtree(dst)
    for t in tasks:
        dst = P.task_dir(t, "standard")
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / name(t)
            render(t, out, a.refs)
            if dst.is_dir() and P.same(out, dst):
                continue
            changed.append(name(t))
            if not a.check:
                shutil.rmtree(dst, ignore_errors=True)
                shutil.copytree(out, dst)
    print(("would change: " if a.check else "wrote: ") + (", ".join(changed) or "nothing"))
    return 1 if a.check and changed else 0


if __name__ == "__main__":
    sys.exit(main())
