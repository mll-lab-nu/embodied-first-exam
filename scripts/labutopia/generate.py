#!/usr/bin/env python3
"""Generate the LabUtopia tasks: tasks/labutopia-<family>-i00-privileged and ...-standard (9 families x 2 modes).

    python3 scripts/labutopia/generate.py            # every family in instances/
    python3 scripts/labutopia/generate.py --check    # exit 1 if tasks/ differs from what this would write

Inputs: instances/<family>.json (the frozen instance: seed, hashes, layout; make_facts.py, run in the image),
oracles/<family>.npz (the reference rows), families.json (the texts), the shared sources in shared/ and the
eai-standard/2.2 layer with the standard client's base image and pins (scripts/eai_standard/), all copied byte for
byte. Each task directory is written from scratch and finished with scripts/task_conventions.py (normalize, PROTOCOL
v1.0.1); a LabUtopia task directory this does not write is removed. Only the standard library is needed.
"""

import filecmp
import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from task_conventions import normalize  # noqa: E402   (protocol v1.0.1 conventions)

TASKS_DIR = ROOT / "tasks"
SHARED = HERE / "shared"
LAYER = ROOT / "scripts/eai_standard"
VERSION = (ROOT / "images/labutopia/VERSION").read_text().strip()
IMAGE = f"ghcr.io/mll-lab-nu/eai-labutopia:{VERSION}"
_ENV = dict(ln.split("=", 1) for ln in (LAYER / "client.env").read_text().splitlines() if "=" in ln and ln[0] != "#")
CLIENT_IMAGE = _ENV["CLIENT_IMAGE"].strip()
AUTHOR = "Canyu Chen"
# Longer than the protocol's default 3600 s (D8), uniform within the benchmark, as for the other Isaac Sim benchmarks:
# the first simulator with its renderer in a container takes 5 to 15 minutes to start (Isaac Sim prepares the stage for
# rendering once), which a standard task pays before its service answers and a privileged agent pays if it looks at
# the scene.
AGENT_TIMEOUT = 5400
STARTUP_TIMEOUT = 2400
# The renderer's first start in a container, by laboratory stage (measured on eight idle cores: 299 s and 803 s).
COLD = {"lab_001": "about 5 minutes", "lab_003": "about 15 minutes"}
FAMILIES = {k: v for k, v in json.loads((HERE / "families.json").read_text()).items() if not k.startswith("_")}
HOSTS = [
    "chatgpt.com", "*.chatgpt.com", "auth.openai.com", "api.openai.com", "*.openai.com", "api.anthropic.com",
    "*.anthropic.com", "openrouter.ai", "*.openai.azure.com", "*.cognitiveservices.azure.com",
]  # fmt: skip
SIM = "LabUtopia on NVIDIA Isaac Sim 6.1.0"

GPU = """    shm_size: "8gb"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
"""
PRIV_ENV_DOCKERFILE = f"""# LabUtopia task (privileged): LabUtopia on Isaac Sim (images/labutopia/), the task's tooling and its frozen instance.
# The base image has LabUtopia's scripted controllers removed (they are this benchmark's reference solutions).
FROM {IMAGE}
COPY instance.json /app/instance.json
COPY rcb_labutopia.py /opt/tools/rcb_labutopia.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
"""
PRIV_COMPOSE = f"""# Isaac Sim needs an RTX-class NVIDIA GPU even headless (PhysX itself runs on the CPU). Harbor's local docker sandbox
# rejects [environment].gpus; merging this onto the main service passes the device through. Kit keeps its caches
# (the stage prepared for rendering, shaders) inside the container, so nothing of them is shared between trials or
# with the verifier: the first Session with cameras in a container takes 5 to 15 minutes to start.
services:
  main:
{GPU}"""
PRIV_TESTS_DOCKERFILE = f"""# Separate verifier sandbox (PROTOCOL §2.6): the same image with the verifier's own copies of the tooling and the frozen
# instance. Nothing the agent did in its container reaches this one: Harbor uploads only the declared artifacts.
FROM {IMAGE}
COPY grade.py instance.json rcb_labutopia.py test.sh /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests
WORKDIR /tests
"""
PRIV_TESTS_COMPOSE = f"""# The verifier replays in Isaac Sim, which needs the GPU. Its Kit caches are its own container's: nothing the agent's
# container cached (Kit keeps generated Python there) reaches the grader.
services:
  main:
{GPU}"""
STD_ENV_DOCKERFILE = f"""# Standard mode: the agent container has NO simulator and no LabUtopia code, only Python and the client, on the shared
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
STD_COMPOSE = f"""# Standard mode: the simulator runs in the `sim` sidecar (the agent cannot open it); the agent only reaches port 8000.
# No `expose`/`ports` on sim: under Harbor's egress control it shares main's network namespace (localhost:8000).
# Isaac Sim needs an RTX-class NVIDIA GPU even headless (PhysX itself runs on the CPU). The sidecar is TRUSTED: Kit's
# caches stay inside its own container, which the agent cannot reach.
# Crash recovery (docs/STANDARD_MODE_2_2.md §13): run.sh exits non-zero when the service crashes, compose restarts the
# container (same container, same /data) and the service replays its journal into the same episode, never a reset.
# RCB_STARTUP_TIMEOUT_S: the startup watchdog, more than twice the slowest measured start with empty caches (the
# service starts with the renderer and renders a first frame before it answers; docs/benchmarks/labutopia.md).
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
      RCB_INSTANCE: /srv/instance.json
      RCB_TOOL: /srv/rcb_labutopia.py
      RCB_DATA: /data
      RCB_WALL_CLOCK_S: "{AGENT_TIMEOUT}"
      RCB_STARTUP_TIMEOUT_S: "{STARTUP_TIMEOUT}"
      PYTHONPATH: /srv
      RCB_SESSION_LOG: ""           # the sidecar's own Session must not write the agent-side interaction log
{GPU}"""


def dash(f: str) -> str:
    return f.replace("_", "-")


def reset_dir(d: Path) -> None:
    """A task directory is written from scratch: what is not rendered here does not belong (no results/, PROTOCOL D3)."""
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


def toml_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def cold(f: dict) -> str:
    return COLD[Path(f["upstream"]["stage"]).parent.name]


def goal_std(f: dict, t: dict) -> str:
    """The standard wording; where the rule has world heights, they are restated relative to where things start."""
    v = f["rule_values"]
    if "{" not in t["goal_std"]:
        return t["goal_std"]
    return t["goal_std"].format(lift_cm=f"{(0.82 - v['beaker_z_m']) * 100:.1f}", top_cm=f"{(0.86 - v['beaker_z_m']) * 100:.1f}",
                                press_mm=f"{(v['button_z_m'] - 0.761) * 1000:.0f}")


def cams_text(f: dict) -> str:
    fixed = [c for c in f["cameras"] if c != "wrist_cam"]
    return (", ".join(f"`{c}`" for c in fixed) + (" are" if len(fixed) > 1 else " is") + " fixed (one looks at the bench from the "
            "front, one straight down from above); `wrist_cam` is mounted on the hand and moves with it")


def priv_instruction(fam: str, f: dict, t: dict) -> str:
    up = f["upstream"]
    cam = f["cameras"][0]
    return f"""# LabUtopia · {fam} — frozen instance

You control {t["robot_text"]}, in LabUtopia's simulated chemistry laboratory (NVIDIA Isaac Sim, PhysX), via Python,
through joint targets.
**Task:** {t["goal"]}

{t["scene"]}

The rule is evaluated after every control step (`s.rule` in the tooling: class `{f["rule_class"]}`, a copy of the success
check of LabUtopia's own controller for this task); the first step at which it is met ends the episode in success.
Positions are LabUtopia's own readings: an object's centre is the centre of its bounding box (`s.centre(path)`), the
hand is the point between the fingertips (`s.hand()`).

This is a *fixed scene instance*: the start pose, the objects and the goal never change between resets. You may reset and
retry as many times as you want. Your deliverable is **one replayable trajectory**, not a general policy.

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below). It is replayed
open-loop from the same initial state in two fresh processes and scored 1 if both episodes end in success in the same
state, else 0. Also leave the script that produced it at `/app/output/gen.py`.

Your time budget is {AGENT_TIMEOUT} s of wall clock. Save a trajectory as soon as you have one that works, improve it while
time remains, and do not stop early.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_labutopia import Session
s = Session(instance="/app/instance.json")   # ONE per process. Simulation only (no renderer): about a minute the first
                                   # time in this container, then about 20 s
# s = Session(instance="/app/instance.json", cameras=True)   # with the renderer and the task's cameras: the first such
                                   # Session in this container takes {cold(f)} (Isaac Sim prepares the stage
                                   # for rendering once; longer on a busy host), later ones about 30 s. The physics
                                   # is the same either way
s.reset()                          # back to the initial state (unlimited; see "Fresh processes" below)
s.state()                          # joint positions / velocities, the targets in effect, tool pose, gripper opening, what the rule looks at
s.rule.values(); s.rule.text       # the quantities of the rule at the current state, and the rule in words
s.centre(path); s.size(path); s.origin(path); s.pose(path)   # LabUtopia's readings of any prim (USD path, e.g. from s.rule.values());
                                   # s.size is its bounding-box extent as LabUtopia computes it: a component can be negative
s.rigid_bodies()                   # the USD paths of every rigid body of the scene
s.hand(); s.tcp_pose()             # the point between the fingertips: position; x y z + wxyz quaternion
s.task, s.cfg, s.stage, s.robot, s.objects   # LabUtopia's task object and config, the USD stage, the robot, its ObjectUtils: read freely
s.command()                        # the 18 targets in effect (after reset: LabUtopia's initial targets)
s.action_limits()                  # (18, 2): the range of each entry
s.step(q)                          # one control step (1/60 s): 9 position targets; s.step(q, qd) adds 9 velocity targets;
                                   # s.step(q, n=30) holds them 30 steps; False once the episode is over
s.status()                         # {{'success', 'done', 'reason', 'steps', 'state_sha', 'instance_ok', 'rule_state', ...}}
s.record_start(); ...; actions = s.record_stop()   # (T, 18) targets, one row per control step executed
s.replay(actions)                  # from the start (a Session that has stepped is reset first), open-loop, until the
                                   # episode ends or the rows do; returns status
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.fk(q7); s.ik({{"tcp": pose}})      # kinematics of the seven arm joints (numpy: no physics, no collision check)
s.render_frame("{cam}")       # (cameras=True) RGB uint8 (512, 512, 3); cameras: {", ".join(f["cameras"])}; s.render_depth(cam): metres
                                   # (glassware is nearly transparent in RGB and absent from the depth maps)
s.camera_info(cam)                 # (cameras=True) intrinsics and pose of a camera
s.render_video(actions, "/app/output/check.mp4", cameras=["{cam}"])   # (cameras=True)
```
Isaac Sim prints a lot when it starts; without cameras that includes Vulkan errors (`vkCreateInstance failed`, `GPU
Foundation is not initialized`): expected, the simulation-only Session runs without the renderer. Your own `print`
output comes through as usual, and an uncaught exception still ends your script with a non-zero status.

There are no ready-made motions: LabUtopia's scripted controllers and their motion primitives are not in this image.
The rest of LabUtopia is, under `/opt/labutopia` (importable once a Session exists), and so is Isaac Sim's own motion
generation for the Franka (RMPflow and the Lula kinematics, `isaacsim.robot_motion.motion_generation`; LabUtopia's
wrapper is `/opt/labutopia/robots/franka/rmpflow_controller.py`). Import `pxr`, `omni.*` and `isaacsim.*` modules only
after the Session exists: Isaac Sim loads its own build of USD when the application starts, and with a `pxr` imported
earlier some of its extensions fail to start (at worst the process ends with a symbol lookup error). Do not name a
script after a standard-library module (`inspect.py`, `types.py`): Isaac Sim imports those as it starts.

**Fresh processes.** Isaac Sim repeats an episode bit for bit only in a fresh process: after `s.reset()` the start
state differs from the first one by about 1e-5, which a contact-rich motion can amplify. The grader replays your
trajectory in fresh processes, so check the final one the same way before you stop:
`python /opt/tools/rcb_labutopia.py replay --instance /app/instance.json --traj /app/output/trajectory.npz`
(prints `RESULT {{...}}` with `success` and `state_sha`; two runs of it must agree; `--video FILE` also renders it).

## Conventions
- Action: 18 numbers per control step: a position target for each of the 9 joints (`panda_joint1` .. `panda_joint7`
  in rad, then `panda_finger_joint1`, `panda_finger_joint2` in m from the gripper's centre line), then a velocity
  target for each (rad/s; m/s; zeros if you give only positions). Each joint has a drive: effort = stiffness x
  (position target - q) + damping x (velocity target - qdot), limited (`s.robot_spec()["controller"]["gains"]`,
  `["joints"]`). `panda_finger_joint2` mirrors `panda_finger_joint1`: its targets are ignored.
- The fingers travel from 0 (closed) to 0.04 m (open) each. A position target may lie beyond a joint's range (arm:
  by 0.1 rad; fingers: -0.1 .. 0.1 m): the joint stops and the drive keeps pushing, so a finger target below the
  point where the finger meets an object squeezes it (400 N/m of error, at most 7.2 N). Targets outside
  `s.action_limits()` are clipped, and all targets are stored as float32.
- One control step is one physics step, 1/60 s (LabUtopia's own rate): a row is executed for exactly one step, so a
  motion lasting 1 s is 60 rows (repeat a row to hold a target). Your wall-clock time is the budget (a replay runs at
  about {f["steps_per_s"]} control steps/s here); the one technical cap is 36000 rows per trajectory (600 s of simulated
  time).
- At the start the arm is not at rest: LabUtopia's reset leaves it straight up, moving towards its home pose (the
  targets in effect, `s.command()`); holding them brings it there in about two seconds.
- World frame: z up, metres; poses are x y z + wxyz quaternion; angles in rad. The arm's base is at
  `s.robot_spec()["base"]["pose"]`.
- Only the rows are replayed: anything else you change in the scene is lost in the grader's fresh process.
"""


def std_instruction(fam: str, f: dict, t: dict) -> str:
    cams = f["cameras"]
    return f"""# LabUtopia · {fam} — STANDARD MODE (robot as a service, eai-standard/2.2)

You control {t["robot_text"]}, **as if it were real**: the simulator (LabUtopia's chemistry laboratory on NVIDIA Isaac
Sim) runs in a service you cannot open. You get one client and one episode.
**Task:** {goal_std(f, t)}

{t["scene"]}

## Rules
- **No reset.** The episode starts when the service comes up and ends the moment the goal is reached (success), when
  your time is up, or on a simulator error.
- **No privileged state.** You see what the cameras see (RGB, and depth on request, with each camera's calibration) and
  the robot's own proprioception: joint positions, velocities and drive efforts, the gripper's opening, the pose of its
  tool frame and the targets in effect. No poses of the objects or instruments, no success check: `meta["done"]` /
  `meta["reason"]` tell you when the episode is over and why.
- Your wall-clock budget is {AGENT_TIMEOUT} s from your start (`meta["time_left_s"]`); steps are unlimited. **The service
  needs {cold(f)} to come up** (Isaac Sim prepares the stage for its renderer once; longer on a busy host):
  `Robot(timeout=2400)` waits for it, and that wait is part of your budget. Simulated time only advances with your commands (and `get_obs(seconds=...)`, which
  holds the last targets). Do not stop early.
- Nothing to hand in: the service records your episode and grades it. Leave your script at `/app/output/gen.py`.
- **If the service crashes**, a call fails with a connection error: it restarts and resumes the SAME episode (never a
  reset) in the state after the last call it completed. `r.wait_ready()` waits for it; then check `r.status()`.
- **Nothing is put into your context automatically.** Images and videos come back as arrays/bytes in a Python object.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`)
```python
from rcb_client import Robot
r = Robot(timeout=2400)                        # connects; waits while the service starts ({cold(f)}; the default timeout is 600 s)
spec = r.spec()                                # action layouts and limits, robot_spec, cameras (+ intrinsics, mounting), proprio layout, kinematics, budget
obs = r.get_obs()                              # obs.last[cam] -> uint8 (512, 512, 3) (cameras: {", ".join(cams)})
obs = r.get_obs(cameras=["{cams[0]}"], depth=True)   # + obs.last_depth[cam] -> float32 (512, 512), metres
obs.meta["proprio"]                            # {{"layout": [...], "now": [...]}}: q_*, qd_*, gripper_opening, tcp_x..qz, effort_*, cmd_*
obs.meta["cameras"]                            # per camera intrinsic_cv / extrinsic_cv / cam2world_gl at the last frame
res = r.submit("joint_position", rows, dt=0.05)   # rows: (T, 9) position targets, here one every 50 ms, reached linearly in 1/60 s steps
res.meta["done"], res.meta["reason"], res.meta["control_steps_chunk"], res.meta["clipped"]; res.video[cam]; res.last[cam]; res.proprio
obs = r.get_obs(seconds=1.0, video="mp4")      # hold the last targets and watch for 1 s (max 30)
r.fk(q); r.ik({{"tcp": pose}})                   # kinematics of the seven arm joints (spec["kinematics"]): no physics, no collision check
r.status()                                     # calls, control steps, done, reason, elapsed time
```
Cameras ({", ".join(f"`{c}`" for c in cams)}; 512x512): {cams_text(f)}. `spec["cameras"]` gives each camera's mounting and
intrinsics, and every response carries each frame's pose. Glassware is glass: nearly transparent in the RGB images
(an outline and reflections), and absent from the depth maps, which show what is behind it. Ask only for the cameras
you need; `video="none"` makes a chunk fastest.
Proprioception (`spec["proprio_groups"]`): `joint_pos` (`q_<joint>`: the seven arm joints, then the two fingers),
`joint_vel` (`qd_<joint>`), `gripper_opening` (metres between the fingers), `tcp_pose` (the tool frame `tcp`, the point
between the fingertips: x y z + wxyz quaternion in the world frame), `joint_effort` (`effort_<joint>`: what each drive
asks for by its own law, which grows when the arm or a finger pushes on something), `command` (`cmd_*`, the 18 targets
in effect). `spec["robot_spec"]` is the robot's spec sheet: where the arm's base stands, joint
limits, the drives' gains, the gripper's command, the tool frame.

### Action type `joint_position` (9)
Position targets of the joints' drives: `panda_joint1` .. `panda_joint7` (rad), then `panda_finger_joint1`,
`panda_finger_joint2` (m from the gripper's centre line: 0 closed .. 0.04 open; the second finger mirrors the first,
its target is ignored). The velocity targets are zero. Rows are `dt` apart (a whole multiple of the 1/60 s control
period, at most 0.5 s; a chunk covers at most 10 s), `interpolate="linear"` (default, from the previous target) or
`"hold"`; values outside the joints' ranges are clipped and reported; the client sends float32.

### Action type `joint_position_velocity` (18)
A position target and a velocity target for every joint's drive (effort = stiffness x (position target - q) + damping
x (velocity target - qdot), limited: `spec["robot_spec"]["controller"]`): 9 position targets as above, then 9 velocity
targets (rad/s; m/s). Here a position target may lie beyond a joint's range (`spec["action_types"]
["joint_position_velocity"]["limits"]`): the joint stops and the drive keeps pushing, so a finger target below the
point where the finger meets an object squeezes it (400 N/m of error, at most 7.2 N). Rows and `dt` as above; the
velocity targets of a row hold for its whole interval.

The control rate is 60 Hz (one physics step per control step). At the start the arm is not at rest: it stands
straight up and is moving towards its home pose (the targets in effect, `cmd_*` in the proprioception); holding them,
e.g. with `r.get_obs(seconds=2)`, brings it there in about two seconds. There is no step budget: the
one technical cap is `spec["max_control_steps"]`, 36000 (600 s of simulated time), at which the episode ends. A
response carries at most 300 frames per camera (`video_fps` up to 30, default 10).
"""


def task_toml(fam: str, f: dict, t: dict, std: bool) -> str:
    first = (goal_std(f, t) if std else t["goal"]).split(". ")[0]
    keywords = ["robotics", "labutopia", "isaac-sim", "laboratory", "chemistry", t["robot"], "code-as-policy", "trajectory", fam,
                "standard-mode" if std else "privileged"]
    title = t["title"].split(" (")[0]
    if std:
        head = """artifacts = [
  { source = "/data/final.json", service = "sim" },
  { source = "/data/episode.jsonl", service = "sim" },
  { source = "/data/trajectory.npz", service = "sim" },
  { source = "/data/replay.mp4", service = "sim" },
  { source = "/data/server.log", service = "sim" },            # the service's own output (Harbor keeps none)
  { source = "/data/journal.f64", service = "sim" },           # crash recovery: every executed control step (float64 rows)
  { source = "/data/startups.jsonl", service = "sim" },        # crash recovery: one line per service start
  { source = "/data/replay1.log", service = "sim" },           # the collect hook's two fresh-process replays
  { source = "/data/replay2.log", service = "sim" },
  { source = "/data/replay3.log", service = "sim" },           # and its third, which renders replay.mp4
  "/app/output/",
]"""
        desc = (
            f"STANDARD MODE (robot as a service, eai-standard/2.2): LabUtopia {fam} ({title}) on the same frozen "
            f"instance as labutopia-{dash(fam)}-i00-privileged: {first}. The agent only gets a client: cameras (RGB, "
            "optional depth, calibration), the robot's proprioception, joint target chunks, arm kinematics; one "
            "episode, no reset, no object or instrument state; the sim service records the episode, replays it in "
            "fresh processes and grades it."
        )
    else:
        head = 'artifacts = ["/app/output/"]'
        desc = (
            f"LabUtopia {fam} ({title}; a chemistry laboratory with a Franka Panda on Isaac Sim): produce one "
            f"replayable trajectory of joint targets. {first}. Frozen scene instance (LabUtopia's reset, seed "
            f"{f['seed']}); graded by two fresh-process replays with a copy of LabUtopia's own success check."
        )
    meta_extra = 'protocol = "eai-standard/2.2"\n' if std else ""
    verifier = (
        """[verifier]
timeout_sec = 600.0
environment_mode = "separate"
network_mode = "no-network"

[[verifier.collect]]
service = "sim"
command = "sh /srv/finalize.sh"   # end + dump + exit the service, replay twice in fresh processes, write final.json, video
timeout_sec = 5400
"""
        if std
        else """[verifier]
timeout_sec = 3600.0              # two replays of about a minute, then the video replay, whose renderer starts cold (5 to 15 minutes)
environment_mode = "separate"
network_mode = "no-network"

[verifier.environment]
build_timeout_sec = 1800.0
cpus = 8
memory_mb = 32768
"""
    )
    return f"""# Generated by scripts/labutopia/generate.py -- edit the generator, the shared sources, families.json or the instance, not this.
schema_version = "1.3"
{head}

[task]
name = "robot-coding-bench/labutopia-{dash(fam)}-i00-{'standard' if std else 'privileged'}"
description = {toml_str(desc)}
authors = [{{ name = "{AUTHOR}" }}]
keywords = [{", ".join(toml_str(k) for k in keywords)}]

[metadata]
author_name = "{AUTHOR}"
task_type = "trajectory"
simulator = "labutopia"           # LabUtopia @ {f["upstream"]["commit"][:7]} on NVIDIA Isaac Sim 6.1.0 (PhysX on the CPU, RTX cameras)
robot = "{t["robot"]}"
family = "{fam}"
mode = "{'standard' if std else 'privileged'}"
{meta_extra}oracle = "full"
level = {t["level"]}                         # LabUtopia's own level for the task (config {f["upstream"]["config"]})
instance_seed = {f["seed"]}                 # numpy's and Python's random generators before LabUtopia's reset
expert_time_estimate_hours = {t["hours"] + (1.0 if std else 0.0)}

{verifier}
[agent]
timeout_sec = {AGENT_TIMEOUT}.0              # LabUtopia's budget, both modes (docs/benchmarks/labutopia.md): a container's first simulator with its renderer takes 5 to 15 minutes to start
# LabUtopia's scripted controllers are in its public repository (and a standard-mode agent could rebuild the simulator
# from it): the agent reaches the model APIs and nothing else (scripts/set_agent_egress.py HOSTS).
network_mode = "allowlist"
allowed_hosts = [{", ".join(toml_str(h) for h in HOSTS)}]

[environment]
build_timeout_sec = 1800.0
cpus = 8
memory_mb = 32768
"""


def readme(fam: str, f: dict, t: dict, std: bool) -> str:
    name = f"labutopia-{dash(fam)}-i00-{'standard' if std else 'privileged'}"
    twin = f"labutopia-{dash(fam)}-i00-{'privileged' if std else 'standard'}"
    up = f["upstream"]
    held = (f" followed by its last row repeated {f['held_rows']} times (the rule asks for a condition to last; the controller ends before)"
            if f["held_rows"] else "")
    if std:
        task = (
            f"LabUtopia's `{fam}` ({t['title']}) on the same frozen instance as `{twin}`: {goal_std(f, t)}\n{t['scene']} "
            "Standard mode (eai-standard/2.2): the agent drives the robot through a client in one episode, with only "
            "its proprioception and the scene's cameras."
        )
        diff = (
            f"Same instance and success rule as `{twin}` (LabUtopia's level {t['level']}). {t['note']} In standard mode "
            "the agent loses resets, the simulator and the state of the objects: it sees camera images (glassware is "
            "nearly transparent in them and absent from the depth maps) and the robot's proprioception, acts in joint "
            "target chunks, and gets "
            "one episode, so it has to find the things it handles in the images and recover from its own mistakes "
            "without starting over."
        )
        ref = (
            f"`solution/oracle_stream.py` streams the privileged reference's rows (`solution/oracle.npz`, "
            f"{f['reference_rows']} rows, float32) through the client as `joint_position_velocity` chunks; it uses no "
            "privileged information at run time. The service's recorded trajectory is then exactly the privileged "
            f"reference: success after {f['reference_steps']} control steps."
        )
        ver = (
            "The sim service judges the episode live and records every executed control step; the collect hook "
            "(`environment/sim/finalize.sh`) ends the service, replays the recorded trajectory in two fresh processes "
            "and writes `final.json`; `tests/grade.py` (separate sandbox, no network) passes iff the live episode "
            "succeeded, both replays succeed, and they end in the same state. `nop`: the episode times out, reward 0."
        )
        details = [
            ("Service", "`environment/sim/server.py` (the adapter) on the shared 2.2 layer `rcb_limited.py` "
                        "(`scripts/eai_standard/`); cameras " + ", ".join(f"`{c}`" for c in f["cameras"]) + " (512 x 512); "
                        "action types `joint_position` (9) and `joint_position_velocity` (18); forward and inverse "
                        "kinematics of the arm"),
            ("Resources", "an RTX-class NVIDIA GPU for the `sim` sidecar (Isaac Sim), 8 CPUs, 32 GB of RAM"),
        ]
    else:
        task = (
            f"LabUtopia's `{fam}` ({t['title']}), with {t['robot_text'].replace('**', '')}: {t['goal']}\n{t['scene']} The "
            f"deliverable is one replayable trajectory of joint targets (`/app/output/trajectory.npz`, "
            f"`(T, {f['n_action']})`, one row per 1/60 s control step: 9 position targets, then 9 velocity targets)."
        )
        diff = (
            f"LabUtopia's level {t['level']}. {t['note']} The agent has full access to the simulator and to LabUtopia's "
            "scene and task code, but not to its scripted controller or its motion primitives: it has to build the "
            "motion itself from joint targets at 60 Hz."
        )
        ref = (
            f"{f['reference_source']}: the joint targets it sends, one row per control step (float32, as PhysX holds "
            f"them), cut at the first step at which the rule is met{held}: `solution/oracle.npz`, {f['reference_rows']} "
            f"rows, success after {f['reference_steps']} control steps. Replayed and saved by `solution/solve.sh`; "
            "re-checked by `scripts/labutopia/make_facts.py --check` (two fresh processes, same final state)."
        )
        ver = (
            "`tests/grade.py` in a separate sandbox without network: two replays of `/app/output/trajectory.npz`, each in "
            "a fresh process, from the verifier's own copy of the instance (`tests/instance.json`; the rebuilt "
            "placements are checked against its recorded hash); pass iff both episodes succeed (the first control step "
            "at which the rule is met ends the episode) in the same state (`deterministic`). `nop`: no trajectory, "
            "reward 0."
        )
        details = [
            ("Instance", f"config `{up['config']}` (task `{up['task_type']}`, stage `{up['stage']}`) after LabUtopia's reset "
                         f"with seed {f['seed']} and {5} physics steps; placement hash `{f['placement_sha']}` (checked on "
                         f"every load), start-state hash `{f['init_sha']}`"),
            ("Rule", f"`{f['rule_class']}` in `rcb_labutopia.py`: {f['rule_text']}"),
            ("Actions", f"{f['n_action']} joint targets per control step (1/60 s, one physics step); the first step at "
                        "which the rule is met ends the episode (docs/benchmarks/labutopia.md)"),
            ("Resources", "an RTX-class NVIDIA GPU (Isaac Sim), 8 CPUs, 32 GB of RAM"),
        ]
    details.insert(0, ("Upstream", f"LabUtopia (github.com/{up['repo']} @ {up['commit'][:7]}; code MIT, assets CC BY-NC "
                                   "4.0) on NVIDIA Isaac Sim 6.1.0 (LabUtopia pins 5.1.0; the image is built locally, "
                                   "images/labutopia/BUILD_ONLY)"))
    rows = "\n".join(f"| {k} | {v} |" for k, v in details)
    return f"""# {name}

## Task
{task}

## Difficulty
{diff}

## Reference solution
{ref}

## Verification
{ver}

## Details
| | |
|---|---|
{rows}

### Provenance
Generated by `scripts/labutopia/generate.py` from `scripts/labutopia/instances/{fam}.json` (`make_facts.py`),
`scripts/labutopia/oracles/{fam}.npz` and `scripts/labutopia/families.json`; see `docs/benchmarks/labutopia.md`.
"""


def make(fam: str, out: Path) -> tuple[Path, Path]:
    inst = HERE / "instances" / f"{fam}.json"
    f = json.loads(inst.read_text())
    t = FAMILIES[fam]
    oracle = HERE / "oracles" / f"{fam}.npz"

    p = out / f"labutopia-{dash(fam)}-i00-privileged"
    reset_dir(p)
    put(p / "task.toml", task_toml(fam, f, t, False))
    put(p / "instruction.md", priv_instruction(fam, f, t))
    put(p / "README.md", readme(fam, f, t, False))
    put(p / "environment/Dockerfile", PRIV_ENV_DOCKERFILE)
    put(p / "environment/docker-compose.yaml", PRIV_COMPOSE)
    put(p / "environment/instance.json", src=inst)
    put(p / "environment/rcb_labutopia.py", src=SHARED / "rcb_labutopia.py")
    put(p / "tests/Dockerfile", PRIV_TESTS_DOCKERFILE)
    put(p / "tests/docker-compose.yaml", PRIV_TESTS_COMPOSE)
    put(p / "tests/test.sh", src=SHARED / "test.sh", mode=0o755)
    put(p / "tests/grade.py", src=SHARED / "grade.py")
    put(p / "tests/rcb_labutopia.py", src=SHARED / "rcb_labutopia.py")
    put(p / "tests/instance.json", src=inst)
    put(p / "solution/solve.sh", src=SHARED / "solve.sh", mode=0o755)
    put(p / "solution/oracle_replay.py", src=SHARED / "oracle_replay.py")
    put(p / "solution/oracle.npz", src=oracle)

    s = out / f"labutopia-{dash(fam)}-i00-standard"
    reset_dir(s)
    put(s / "task.toml", task_toml(fam, f, t, True))
    put(s / "instruction.md", std_instruction(fam, f, t))
    put(s / "README.md", readme(fam, f, t, True))
    put(s / "environment/Dockerfile", STD_ENV_DOCKERFILE)
    put(s / "environment/docker-compose.yaml", STD_COMPOSE)
    put(s / "environment/client-requirements.txt",
        src=LAYER / _ENV.get("CLIENT_REQUIREMENTS", "client-requirements.txt").strip())
    put(s / "environment/rcb_client.py", src=LAYER / "rcb_client.py")
    put(s / "environment/rcb1.py", src=LAYER / "rcb1.py")
    for name in ("rcb_limited.py", "rcb1.py"):
        put(s / "environment/sim" / name, src=LAYER / name)
    put(s / "environment/sim/run.sh", src=LAYER / "run.sh", mode=0o755)
    put(s / "environment/sim/server.py", src=SHARED / "standard/server.py")
    put(s / "environment/sim/finalize.sh", src=SHARED / "standard/finalize.sh", mode=0o755)
    put(s / "environment/sim/rcb_labutopia.py", src=SHARED / "rcb_labutopia.py")
    put(s / "environment/sim/instance.json", src=inst)
    put(s / "environment/sim/task.json", json.dumps(
        {"task_text": goal_std(f, t), "default_cameras": f["cameras"], "static": {"inventory": t["inventory"]}},
        indent=1, ensure_ascii=False) + "\n")
    put(s / "tests/Dockerfile", STD_TESTS_DOCKERFILE)
    put(s / "tests/test.sh", src=SHARED / "standard/test.sh", mode=0o755)
    put(s / "tests/grade.py", src=SHARED / "standard/grade.py")
    put(s / "solution/solve.sh", src=SHARED / "standard/solve.sh", mode=0o755)
    put(s / "solution/oracle_stream.py", src=SHARED / "standard/oracle_stream.py")
    put(s / "solution/oracle.npz", src=oracle)
    normalize(p)
    normalize(s)
    return p, s


def render_all(out: Path) -> list[str]:
    done = []
    for inst in sorted((HERE / "instances").glob("*.json")):
        done += [d.name for d in make(inst.stem, out)]
    return done


def ours(d: Path) -> bool:
    return d.is_dir() and d.name.startswith("labutopia-")


def check() -> int:
    """tasks/ must be exactly what render_all writes (contents and modes), with no other LabUtopia task directory."""
    with tempfile.TemporaryDirectory() as tmp:
        names = set(render_all(Path(tmp)))
        have = {d.name for d in TASKS_DIR.iterdir() if ours(d)}
        bad = sorted(have ^ names)
        for name in sorted(names & have):
            stack = [filecmp.dircmp(TASKS_DIR / name, Path(tmp) / name, ignore=["__pycache__"])]
            while stack:
                c = stack.pop()
                diff = filecmp.cmpfiles(c.left, c.right, c.common_files, shallow=False)[1]
                modes = [
                    x for x in c.common_files if (Path(c.left) / x).stat().st_mode != (Path(c.right) / x).stat().st_mode
                ]
                if c.left_only or c.right_only or c.funny_files or diff or modes:
                    bad.append(name)
                    break
                stack += list(c.subdirs.values())
    for name in sorted(set(bad)):
        print(f"FAIL tasks/{name}: differs from scripts/labutopia/generate.py (re-run it)")
    if not bad:
        print(f"{len(names)} task directories match")
    return 1 if bad else 0


def main(args: list[str]) -> int:
    if args == ["--check"]:
        return check()
    names = render_all(TASKS_DIR)
    for d in sorted(TASKS_DIR.iterdir()):
        if ours(d) and d.name not in names:
            shutil.rmtree(d)
            print(f"removed stale {d.relative_to(ROOT)}")
    print(f"generated {len(names)} task directories")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
