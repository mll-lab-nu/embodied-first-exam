#!/usr/bin/env python3
"""Generate the AutoBio tasks: tasks/autobio-<family>-i00-privileged and ...-standard (9 families x 2 modes).

    python3 scripts/autobio/generate.py            # every family in instances/
    python3 scripts/autobio/generate.py --check    # exit 1 if tasks/ differs from what this would write

Inputs: instances/<family>.json (the frozen instance: seed, hashes, layout; make_facts.py, run in the image),
oracles/<family>.npz (the reference rows), families.json (the texts), the shared sources in shared/ and the
eai-standard/2.2 layer with the standard client's base image and pins (scripts/eai_standard/), all copied byte for
byte. Each task directory is written from scratch and finished with scripts/task_conventions.py (normalize, PROTOCOL
v1.0.1); an AutoBio task directory this does not write is removed. Only the standard library is needed.
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
from task_conventions import cutoff_sec, normalize  # noqa: E402   (protocol v1.0.1 conventions; the cutoff table)

TASKS_DIR = ROOT / "tasks"
SHARED = HERE / "shared"
LAYER = ROOT / "scripts/eai_standard"
VERSION = (ROOT / "images/autobio/VERSION").read_text().strip()
IMAGE = f"ghcr.io/mll-lab-nu/eai-autobio:{VERSION}"
_ENV = dict(ln.split("=", 1) for ln in (LAYER / "client.env").read_text().splitlines() if "=" in ln and ln[0] != "#")
CLIENT_IMAGE = _ENV["CLIENT_IMAGE"].strip()
AUTHOR = "Canyu Chen"
# The agent's time cutoff per mode: scripts/task_cutoffs.toml, the one table (PROTOCOL §2.12). No copy of the number here:
# normalize writes it into task.toml, the instruction's closing `## Time limit` section, the README row and the sim service's wall clock.
CUTOFF = {m: cutoff_sec("AutoBio", m) for m in ("privileged", "standard")}
# The graders' time (docs/benchmarks/autobio.md, "Time limits of the graders"). The longest episode (600000 rows) replays in
# 1000 s in the slowest family (insert_centrifuge_5430, 600 control steps/s); a verdict replay may take REPLAY_TIMEOUT.
REPLAY_TIMEOUT = 2400     # one verdict replay: shared/grade.py VERDICT_TIMEOUT_S, shared/standard/finalize.sh REPLAY_TIMEOUT_S
VERIFIER_TIMEOUT = 5400   # privileged [verifier]: 2 x REPLAY_TIMEOUT + the video replay (what is left) + 300 s
COLLECT_TIMEOUT = 7200    # standard collect hook: 900 (episode end) + 2 x REPLAY_TIMEOUT + the video (what is left) + 300 s
# README "Change Log" (PROTOCOL §2.8: fixes to published tasks change them in place and say so), by mode (std: True).
CHANGE_LOG = {
    True: (
        "- 2026-10-10: how a trial that could not be graded is recorded, and request checks; the scene, the frozen instance "
        "and the pass rule are unchanged, so the task keeps its name. `tests/grade.py`: a missing, unreadable or unfinished "
        "`final.json` (the collect hook never wrote its verdict) is `infra_error = 1` (was the agent's 0, or no reward at "
        "all); a reward is always written. `environment/sim/finalize.sh`: each verdict replay has a time limit "
        f"({REPLAY_TIMEOUT} s; a replay without a result was and is `infra_error`), the video replay gets what is left, "
        f"`final.json` is written atomically, and the collect hook's `timeout_sec` is {COLLECT_TIMEOUT} s (was 5400 s). "
        "`environment/sim/server.py`: a malformed request field (null or a wrong type for `dt`, `seconds`, `cameras`, "
        "`note`) is a 400 before anything is executed (was a 500 that ended the episode). The instruction and `/spec` `episode` now state that a MuJoCo physics warning (an unstable simulation) ends the episode as a failure; the rule itself is unchanged (AutoBio's evaluator's, in force since the task was added). A pass before this "
        "change is a pass after it; results recorded before it may hold infrastructure failures counted as the agent's 0.\n"
        "- 2026-10-10 (review round 2, board 0067): the client only (`environment/rcb_client.py`). `Robot()` waits up to 3600 s for the service (was 600 s) and prints its progress to stderr once a minute, so the first `Robot()` outlasts the simulator's start (no effect on this benchmark, whose service is up within a minute); `cameras=\"name\"` (a string) is one camera, no longer its characters. The service, the collect hook, the grader, the scene and the pass rule are unchanged.\n"
        "- 2026-10-10 (review round 3, board 0067): the shared service layer and the client only "
        "(`environment/sim/rcb_limited.py`, `environment/rcb_client.py`). A camera named more than once in "
        "`cameras` is rendered and returned once (N copies of one name made the service build N x N images within "
        "the frame budget, which could exhaust its memory). A service that has given up on the episode (it could "
        "not start it, or could not resume it after its crashes) answers every request with 409 and the reason, "
        "and `Robot()` / `wait_ready()` raise `EpisodeOver` at once; before, nothing answered and they waited out "
        "their timeout (up to an hour). The adapter, the collect hook, the grader, the scene and the pass rule are "
        "unchanged.\n"
        "- 2026-10-13 (owner, boards 0085 and 0087): the sim service's clock (`environment/sim/rcb_limited.py`, "
        "`environment/sim/server.py`, the docstring of `environment/rcb_client.py`). `meta[\"time_s\"]` and "
        "`meta[\"time_left_s\"]` count from the agent's first request to the service (any endpoint), and a restarted "
        "service keeps that moment; before, they counted from the service's own start of the episode (when its scene "
        "was ready). Where the service is ready before the agent's phase begins (the harness is installed in "
        "between: a median of 79 s over the recorded standard trials), that clock ran ahead of the agent's and "
        "`time_left_s` reached 0 while the agent still had that time. `/spec` says what the clock counts from "
        "(`budget.clock`), and the instruction's `## Time limit` tells the agent to plan by `time_left_s`. The "
        "service never ended an episode on this clock: the scene, the frozen instance, the pass rule and the grader "
        "are unchanged, so the task keeps its name and earlier results stand."
    ),
    False: (
        "- 2026-10-10: the grader's time limits and flags; the scene, the frozen instance and the pass rule are unchanged, so "
        f"the task keeps its name. `tests/grade.py`: each verdict replay may take {REPLAY_TIMEOUT} s and the video replay gets "
        f"what is left of the verifier's {VERIFIER_TIMEOUT} s (every replay had 1700 s), so a reward is written "
        "before Harbor's timeout whatever the trajectory's length; a replay without a result also sets `infra_error` "
        "(with `grader_error`, as before), every `reward.json` carries `infra_error`, and an error inside the grader "
        "still writes a reward (`grader_error = 1`). A trajectory that was graded before gets the same verdict.\n"
        "- 2026-10-10 (review round 3, board 0067): `tests/grade.py` only. A byte that is not valid UTF-8 in the "
        "session log the agent's tools write (`/app/output/rcb_session_log.jsonl`, read only for the self-reported "
        "`agent_*` cost fields) was graded `grader_error = 1` and `infra_error = 1` with reward 0, whatever the "
        "trajectory; the log is now read tolerantly and can no longer decide anything. A trial whose log is valid "
        "is graded as before; the pass rule is unchanged."
    ),
}
FAMILIES = {k: v for k, v in json.loads((HERE / "families.json").read_text()).items() if not k.startswith("_")}
HOSTS = [
    "chatgpt.com", "*.chatgpt.com", "auth.openai.com", "api.openai.com", "*.openai.com", "api.anthropic.com",
    "*.anthropic.com", "openrouter.ai", "*.openai.azure.com", "*.cognitiveservices.azure.com", "pypi.org", "files.pythonhosted.org", "deb.debian.org", "security.debian.org", "archive.ubuntu.com", "security.ubuntu.com", "snapshot.ubuntu.com",
]  # fmt: skip
# Why a family is hard for a coding agent, beyond AutoBio's own level (facts of the scene and of the check only).
NOTES = {
    "pickup": "The tube is lifted out of its rack slot by its screw cap; the check needs the cap between the fingers while the tube is 9.5 cm up.",
    "thermal_cycler_close": "Two articulated parts have to reach their end stops within 0.01 rad: the hinged lid and the lever on it that locks it.",
    "thermal_cycler_open": "Two articulated parts have to come back to their open end stops within 0.003 rad: the lever that locks the lid, and the lid.",
    "pipette": "Two arms. The pipette tip has to enter a 50 mL tube within 6.5 mm of its axis and reach below the liquid surface, with the plunger pressed before and released there.",
    "screw_loose": "A real thread: the cap separates from the tube only after it has been turned off, and the check needs it held 3 cm up by the first arm.",
    "screw_tighten": "A real thread: the cap has to be picked off the bench, set on the tube within 5 mm of its axis and turned down to within 3.3 mm of fully on.",
    "insert": "The tube is taken out of one slot and seated in a given slot of the other rack, within 15 mm of its centre and 1 mm of the seated height.",
    "thermal_mixer": "Three settings are changed by pressing small panel buttons with the gripper, the right number of times each; the final panel state is what counts, so an overshoot has to be corrected.",
    "insert_centrifuge_5430": "A 1.5 mL tube is taken from a plate and seated within 5 mm in one particular slot of a 30-slot rotor, inside the centrifuge's bowl.",
}

PRIV_ENV_DOCKERFILE = f"""# AutoBio task (privileged): AutoBio on MuJoCo 3.3.0 (images/autobio/), the task's tooling and its frozen instance.
# CPU only. The base image has AutoBio's scripted experts removed (they are this benchmark's reference solutions).
FROM {IMAGE}
COPY instance.json /app/instance.json
COPY rcb_autobio.py /opt/tools/rcb_autobio.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
"""
PRIV_TESTS_DOCKERFILE = f"""# Separate verifier sandbox (PROTOCOL §2.6): the same image with the verifier's own copies of the tooling and the frozen
# instance. Nothing the agent did in its container reaches this one: Harbor uploads only the declared artifacts.
FROM {IMAGE}
COPY grade.py instance.json rcb_autobio.py test.sh /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests
WORKDIR /tests
"""
STD_ENV_DOCKERFILE = f"""# Standard mode: the agent container has NO simulator and no AutoBio code, only Python and the client, on the shared
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
# CPU only: MuJoCo physics and OSMesa rendering; no GPU reservation.
# Crash recovery (docs/STANDARD_MODE.md §13): run.sh exits non-zero when the service crashes, compose restarts the
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
      RCB_INSTANCE: /srv/instance.json
      RCB_TOOL: /srv/rcb_autobio.py
      RCB_DATA: /data
      RCB_WALL_CLOCK_S: "{CUTOFF["standard"]}"
      RCB_STARTUP_TIMEOUT_S: "300"   # the scene builds in a few seconds
      PYTHONPATH: /srv
      RCB_SESSION_LOG: ""           # the sidecar's own Session must not write the agent-side interaction log
"""


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


def action_text(f: dict) -> str:
    """The action, entry by entry, in words."""
    parts = []
    for a in f["actuators"]:
        lo, hi = a["range"]
        if a["unit"].startswith("0"):
            parts.append(f"`{a['name']}` (the Robotiq gripper: 0 open .. 255 closed)")
        elif a["kind"] == "gripper":
            parts.append(f"`{a['name']}` (the gripper's finger position: {lo:g} m closed .. {hi:g} m open)")
        elif "thj3" in a["name"]:
            parts.append(f"`{a['name']}` (the thumb joint that presses the pipette's plunger: {lo:g} .. {hi:g} rad, larger presses)")
        else:
            parts.append(f"`{a['name']}`")
    return (f"{f['n_action']} position targets per control step, in this order: " + ", ".join(parts) + ". Arm joints "
            "are in rad. Each entry is the target of a PD position drive (stiffness, damping and force limit per entry: "
            "`{where}`); a target outside the entry's range is clipped to it.")


def tcp_text(f: dict) -> str:
    return ", ".join(f"`{a['tcp']}`" for a in f["arms"])


def priv_instruction(fam: str, f: dict, t: dict) -> str:
    n = f["n_action"]
    cam = f["default_cameras"][0]
    up = f["upstream"]
    rule = ("Robot Coding Bench evaluates it after every control step: the first step at which it holds ends the episode "
            "in success (AutoBio's own rule for this task; its time limit is lifted)." if f["rule"] == "first" else
            "Here it returns AutoBio's score in [0, 1]. Robot Coding Bench evaluates it after every control step but the "
            "episode does not end by itself: it is judged in the state after your last row, success iff the score is 1 "
            "(AutoBio's own rule for this task, without its time limit).")
    return f"""# AutoBio · {fam} — frozen instance

You control {t["robot_text"]}, in AutoBio's simulated biology laboratory (MuJoCo 3.3.0), via Python, through joint
position targets.
**Task:** {t["goal"]}

{t["scene"]}

AutoBio's own success test is `s.task.check()`: class `{up["class"]}` in `/opt/AutoBio/autobio/{up["module"]}.py`.
{rule}

This is a *fixed scene instance*: the start pose, the objects and the goal never change between resets. You may reset and
retry as many times as you want. Your deliverable is **one replayable trajectory**, not a general policy.

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below). It is replayed
open-loop from the same initial state in two fresh processes and scored 1 if both episodes end in success in the same
state, else 0. Also leave the script that produced it at `/app/output/gen.py`.

Save a trajectory as soon as you have one that works, improve it while time remains, and do not stop early.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_autobio import Session
s = Session(instance="/app/instance.json")   # a few seconds
s.reset()                          # back to the frozen initial state (unlimited)
s.state()                          # privileged view: qpos, qvel, ctrl, the targets in effect, tool poses, gripper openings, score
s.task, s.model, s.data            # AutoBio's task object (its scene helpers and check()), MuJoCo model / data: read them freely
s.actuators()                      # the {n} controlled actuators in action order: name, unit, range, kp, kv, force range
s.command()                        # the targets in effect (after reset: the ones that hold the initial pose)
s.step(a)                          # one control step (2 ms) with {n} targets; s.step(a, n=25) holds them 25 steps; False once the episode is over
s.status()                         # {{'success', 'done', 'reason', 'score', 'steps', 'state_sha', 'instance_ok', ...}}
s.record_start(); ...; actions = s.record_stop()   # (T, {n}) targets, one row per control step executed
s.replay(actions)                  # resets, replays open-loop until the episode ends or the rows do, returns status -> self-check
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.tcp_poses()                      # tool frames ({tcp_text(f)}): x y z + wxyz quaternion, world frame
s.fk(q); s.ik({{frame: pose}})       # kinematics of the arm joints (s.kinematic_joints()), no physics, no collision check
s.render_frame("{cam}")   # RGB uint8 (480, 640, 3); cameras: {", ".join(f["cameras"])}; s.render_depth(cam): metres
s.render_video(actions, "/app/output/check.mp4", cameras=["{cam}"])
s.close()                          # release the renderer when you are done with a Session
```
There are no ready-made motions: AutoBio's scripted experts are not in this image. Its other code is, under
`/opt/AutoBio/autobio` (importable once a Session exists): the scene helpers `s.task` is built from, its inverse
kinematics (`kinematics.py`) and its path timing (`topp.py`).

CLI equivalent of the grader:
`python /opt/tools/rcb_autobio.py replay --instance /app/instance.json --traj /app/output/trajectory.npz --repeat 2`

## Conventions
- Action: {action_text(f).format(where="s.actuators()")}
- One control step is one physics step, 2 ms: a row is executed for exactly one step, so a motion lasting 1 s is 500
  rows (repeat a row to hold a target). Your wall-clock time is the budget (the reference replays at about
  {f["steps_per_s"]} control steps/s here); the one technical cap is 600000 rows per trajectory (1200 s of simulated
  time). A MuJoCo physics warning (an unstable simulation) ends the episode as a failure.
- World frame: z up, metres; poses are x y z + wxyz quaternion; angles in rad.
- Only the rows are replayed: anything else you change in `s.model` or `s.data` is lost in the grader's fresh process.
"""


def std_instruction(fam: str, f: dict, t: dict) -> str:
    n = f["n_action"]
    cams = f["cameras"]
    wrist = [c for c in cams if "wrist" in c]
    end = ("the moment the goal is reached (success)" if f["rule"] == "first" else
           'when you end it with `r.submit("done", [])` (it is judged in the state it is in then)')
    done = ('`r.submit("done", [])` ends the episode in its current state; before the goal is reached that is a failure.'
            if f["rule"] == "first" else
            '`r.submit("done", [])` ends the episode: do it once the panel shows the target values. If you never do, the '
            "episode is judged in the state it is in when your time is up.")
    grip = [k for k in ("gripper_opening",) if any(a["kind"] == "gripper" for a in f["actuators"])]
    return f"""# AutoBio · {fam} — STANDARD MODE (robot as a service, eai-standard/2.2)

You control {t["robot_text"]}, **as if it were real**: the simulator (AutoBio's biology laboratory on MuJoCo 3.3.0) runs
in a service you cannot open. You get one client and one episode.
**Task:** {t["goal_std"]}

{t["scene"]}

## Rules
- **No reset.** The episode starts when the service comes up and ends {end}, when your time is up, or on a simulator
  error. A MuJoCo physics warning (an unstable simulation, for instance after the robot was driven hard into
  something) also ends it at once, as a failure: `meta["reason"]` is then `"failure: simulator warning (unstable state)"`.
- **No privileged state.** You see what the cameras see (RGB, and depth on request, with each camera's calibration) and
  the robot's own proprioception: joint positions, velocities and drive efforts{", gripper openings" if grip else ""}, the
  poses of its tool frames and the targets in effect. No poses of tubes, racks or instruments, no instrument state, no
  success check: `meta["done"]` / `meta["reason"]` tell you when the episode is over and why.
- Steps are unlimited; your only budget is the time limit (`## Time limit`; `meta["time_left_s"]` is the service's count of it).
  Simulated time only advances with your commands (and `get_obs(seconds=...)`, which holds the last targets). Do not stop early.
- {done}
- Nothing to hand in: the service records your episode and grades it. Leave your script at `/app/output/gen.py`.
- **If the service crashes**, a call fails with a connection error: it restarts and resumes the SAME episode (never a
  reset) in the state after the last call it completed. `r.wait_ready()` waits for it; then check `r.status()`.
- **Nothing is put into your context automatically.** Images and videos come back as arrays/bytes in a Python object.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`)
```python
from rcb_client import Robot
r = Robot()                                    # connects (waits while the service starts)
spec = r.spec()                                # action layout and limits, robot_spec, cameras (+ intrinsics, mounting), proprio layout, kinematics, budget
obs = r.get_obs()                              # obs.last[cam] -> uint8 (480, 640, 3) (default cameras: {", ".join(f["default_cameras"])})
obs = r.get_obs(cameras=["{cams[0]}"], depth=True)   # + obs.last_depth[cam] -> float32 (480, 640), metres
obs.meta["proprio"]                            # {{"layout": [...], "now": [...]}}: q_*, qd_*, *_opening, <tcp>_x..qz, effort_*, cmd_*
obs.meta["cameras"]                            # per camera intrinsic_cv / extrinsic_cv / cam2world_gl at the last frame
res = r.submit("joint_position", rows, dt=0.02)   # rows: (T, {n}) targets, here one every 20 ms, reached linearly in 2 ms steps
res.meta["done"], res.meta["reason"], res.meta["control_steps_chunk"], res.meta["clipped"]; res.video[cam]; res.last[cam]; res.proprio
obs = r.get_obs(seconds=1.0, video="mp4")      # hold the last targets and watch for 1 s (max 30)
r.fk(q); r.ik({{frame: pose}})                   # kinematics of the arm joints (spec["kinematics"]): no physics, no collision check
r.submit("done", [])                           # ends the episode now, in its current state
r.status()                                     # calls, control steps, done, reason, elapsed time
```
Cameras ({", ".join(f"`{c}`" for c in cams)}; 640x480): `table_cam_front` and `table_cam_left` are fixed and look at the bench from two sides;
{", ".join(f"`{c}`" for c in wrist)} {"is" if len(wrist) == 1 else "are"} mounted on the {"arm's" if len(wrist) == 1 else "arms'"} last
link{"" if len(wrist) == 1 else "s"} and move{"s" if len(wrist) == 1 else ""} with {"it" if len(wrist) == 1 else "them"}. `spec["cameras"]` gives each camera's mounting and intrinsics, and every response carries each
frame's pose. Rendering is on the CPU: ask only for the cameras you need; `video="none"` makes a chunk fastest.
Proprioception (`spec["proprio_groups"]`): `joint_pos` (`q_<joint>`), `joint_vel` (`qd_<joint>`), `gripper_opening`
(metres between the fingertips, per parallel gripper), `tcp_pose` (each tool frame, {tcp_text(f)}: x y z + wxyz
quaternion in the world frame), `joint_effort` (`effort_<joint>`), `command` (`cmd_<entry>`, the targets in effect).
`spec["robot_spec"]` is the robot's spec sheet: where each arm's base stands, joint limits, the drives' gains, the
grippers' commands, the tool frames.

### Action type `joint_position` ({n})
{action_text(f).format(where='spec["robot_spec"]["controller"]["gains"]')} Columns in
`spec["action_types"]["joint_position"]["layout"]` order. Rows are `dt` apart (a whole multiple of the 2 ms control
period, at most 0.5 s; a chunk covers at most 10 s), `interpolate="linear"` (default, from the previous target) or
`"hold"`; the client sends them as float32. The control rate is 500 Hz (one physics step per control step). There is
no step budget: the one technical cap is `spec["max_control_steps"]`, 600000 (1200 s of simulated time), at which the
episode ends. A response carries at most 3000 frames per camera (`video_fps` up to 50, default 10).
"""


def task_toml(fam: str, f: dict, t: dict, std: bool) -> str:
    first = t["goal_std" if std else "goal"].split(". ")[0]
    keywords = ["robotics", "autobio", "mujoco", "laboratory", "biology", t["robot"], "code-as-policy", "trajectory", fam,
                "standard-mode" if std else "privileged"]
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
            f"STANDARD MODE (robot as a service, eai-standard/2.2): AutoBio {fam} ({t['title']}) on the same frozen "
            f"instance as autobio-{dash(fam)}-i00-privileged: {first}. The agent only gets a client: cameras (RGB, "
            "optional depth, calibration), the robot's proprioception, joint position chunks, arm kinematics; one "
            "episode, no reset, no object or instrument state; the sim service records the episode, replays it in "
            "fresh processes and grades it."
        )
    else:
        head = 'artifacts = ["/app/output/"]'
        desc = (
            f"AutoBio {fam} ({t['title']}; a biology laboratory bench on MuJoCo): produce one replayable trajectory of "
            f"joint position targets. {first}. Frozen scene instance (AutoBio's reset, seed 0); graded by two "
            "fresh-process replays with AutoBio's own check."
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
timeout_sec = {COLLECT_TIMEOUT}                # 900 (episode end) + 2 x 2400 (verdict replays, each limited) + the video (the rest) + 300: finalize.sh
""".replace("{COLLECT_TIMEOUT}", str(COLLECT_TIMEOUT))
        if std
        else """[verifier]
timeout_sec = {VERIFIER_TIMEOUT}.0               # 2 x 2400 (verdict replays, each limited) + the video (the rest) + 300: tests/grade.py
environment_mode = "separate"
network_mode = "no-network"

[verifier.environment]
build_timeout_sec = 1800.0
cpus = 4
memory_mb = 8192
""".replace("{VERIFIER_TIMEOUT}", str(VERIFIER_TIMEOUT))
    )
    return f"""# Generated by scripts/autobio/generate.py -- edit the generator, the shared sources, families.json or the instance, not this.
schema_version = "1.3"
{head}

[task]
name = "robot-coding-bench/autobio-{dash(fam)}-i00-{'standard' if std else 'privileged'}"
description = {toml_str(desc)}
authors = [{{ name = "{AUTHOR}" }}]
keywords = [{", ".join(toml_str(k) for k in keywords)}]

[metadata]
author_name = "{AUTHOR}"
task_type = "trajectory"
simulator = "autobio"             # AutoBio @ {f["upstream"]["commit"][:7]} on MuJoCo 3.3.0 (CPU)
robot = "{t["robot"]}"
family = "{fam}"
mode = "{'standard' if std else 'privileged'}"
{meta_extra}oracle = "full"
difficulty = "{t["level"]}"              # AutoBio's own level for the task
success_rule = "{f["rule"]}"
instance_seed = {f["seed"]}                 # AutoBio's reset(seed={f["seed"]}) of {f["upstream"]["class"]}
expert_time_estimate_hours = {t["hours"] + (1.0 if std else 0.0)}

{verifier}
[agent]
timeout_sec = {CUTOFF["standard" if std else "privileged"]}.0
# AutoBio's scripted experts are in its public repository and its recorded demonstrations on Hugging Face (and a
# standard-mode agent could rebuild the simulator from the repository): the agent reaches the model APIs and the package registries, nothing
# else (scripts/set_agent_egress.py HOSTS).
network_mode = "allowlist"
allowed_hosts = [{", ".join(toml_str(h) for h in HOSTS)}]

[environment]
build_timeout_sec = 1800.0
cpus = 4
memory_mb = 8192
"""


def readme(fam: str, f: dict, t: dict, std: bool) -> str:
    name = f"autobio-{dash(fam)}-i00-{'standard' if std else 'privileged'}"
    twin = f"autobio-{dash(fam)}-i00-{'privileged' if std else 'standard'}"
    up = f["upstream"]
    rule = ("the first control step at which AutoBio's check holds ends the episode in success" if f["rule"] == "first"
            else "the episode is judged in the state in which it ends, success iff AutoBio's score is 1")
    if std:
        task = (
            f"AutoBio's `{fam}` ({t['title']}) on the same frozen instance as `{twin}`: {t['goal_std']}\n{t['scene']} "
            "Standard mode (eai-standard/2.2): the agent drives the robot through a client in one episode, with only "
            "its proprioception and the scene's cameras."
        )
        diff = (
            f"Same instance and success rule as `{twin}` (AutoBio's level: {t['level']}). {NOTES[fam]} In standard mode "
            "the agent loses resets, the simulator and the state of the tubes and instruments: it sees camera images "
            "and the robot's proprioception, acts in joint-position chunks, and gets one episode, so it has to find "
            "the things it handles in the images and recover from its own mistakes without starting over."
        )
        ref = (
            f"`solution/oracle_stream.py` streams the privileged reference's rows (`solution/oracle.npz`, "
            f"{f['reference_rows']} rows, float32-exact) through the client in `hold` chunks"
            + ("" if f["rule"] == "first" else " and ends the episode with `done`")
            + "; it uses no privileged information at run time. The service's recorded trajectory is then exactly the "
            f"privileged reference: success after {f['reference_steps']} control steps."
        )
        ver = (
            "The sim service judges the episode live and records every executed control step; the collect hook "
            "(`environment/sim/finalize.sh`) ends the service, replays the recorded trajectory in two fresh processes "
            "and writes `final.json`; `tests/grade.py` (separate sandbox, no network) passes iff the live episode "
            "succeeded, both replays succeed, and they end in the same state. A missing or unfinished `final.json` "
            "(the hook never wrote its verdict) and a replay that gave no result are `infra_error = 1`, never the "
            "agent's 0. `nop`: the episode times out, reward 0."
        )
        details = [
            ("Service", "`environment/sim/server.py` (the adapter) on the shared 2.2 layer `rcb_limited.py` "
                        "(`scripts/eai_standard/`); cameras " + ", ".join(f"`{c}`" for c in f["cameras"]) + " (640 x 480); "
                        "action types `joint_position` and `done`; forward and inverse kinematics of the arm joints"),
            ("Resources", "4 CPUs, no GPU (CPU physics, OSMesa rendering)"),
        ]
    else:
        task = (
            f"AutoBio's `{fam}` ({t['title']}), with {t['robot_text'].replace('**', '')}: {t['goal']}\n{t['scene']} The "
            f"deliverable is one replayable trajectory of joint position targets (`/app/output/trajectory.npz`, "
            f"`(T, {f['n_action']})`, one row per 2 ms control step)."
        )
        diff = (
            f"AutoBio's level: {t['level']}. {NOTES[fam]} The agent has full access to the simulator and to AutoBio's "
            "task code, but not to its scripted expert: it has to build the motion itself from joint position targets "
            "at the physics rate."
        )
        ref = (
            f"{f['reference_source']}: the position targets it sends, recorded at every physics step, clipped to the "
            f"actuators' ranges, rounded to float32 (so the standard twin's client executes the same rows)"
            + (", cut at the first success" if f["rule"] == "first" else "")
            + f": `solution/oracle.npz`, {f['reference_rows']} rows, success after {f['reference_steps']} control steps. "
            "Replayed and saved by `solution/solve.sh`; re-checked by `scripts/autobio/make_facts.py --check` (two fresh "
            "processes, same final state)."
        )
        ver = (
            "`tests/grade.py` in a separate sandbox without network: two replays of `/app/output/trajectory.npz`, each in "
            "a fresh process, from the verifier's own copy of the instance (`tests/instance.json`; the compiled model and "
            f"the rebuilt start state are checked against its recorded hashes); pass iff both episodes succeed ({rule}) "
            "in the same state (`deterministic`). `nop`: no trajectory, reward 0."
        )
        details = [
            ("Instance", f"`{up['class']}` (`{up['module']}.py`) after AutoBio's `reset(seed={f['seed']})`; model hash "
                         f"`{f['model_sha']}`, start-state hash `{f['init_sha']}`, checked on every load"),
            ("Actions", f"{f['n_action']} position targets per control step (2 ms, one physics step); success rule "
                        f"`{f['rule']}` (docs/benchmarks/autobio.md)"),
            ("Resources", "4 CPUs, no GPU (CPU physics, OSMesa rendering)"),
        ]
    details.insert(0, ("Upstream", f"AutoBio (github.com/{up['repo']} @ {up['commit'][:7]}, no licence stated: the image "
                                   "is built locally, images/autobio/BUILD_ONLY) on MuJoCo 3.3.0"))
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
Generated by `scripts/autobio/generate.py` from `scripts/autobio/instances/{fam}.json` (`make_facts.py`),
`scripts/autobio/oracles/{fam}.npz` and `scripts/autobio/families.json`; see `docs/benchmarks/autobio.md`.

### Change Log
{CHANGE_LOG[std]}
{t.get("change_log", {}).get("std" if std else "priv", "")}"""


def make(fam: str, out: Path) -> tuple[Path, Path]:
    inst = HERE / "instances" / f"{fam}.json"
    f = json.loads(inst.read_text())
    t = FAMILIES[fam]
    oracle = HERE / "oracles" / f"{fam}.npz"

    p = out / f"autobio-{dash(fam)}-i00-privileged"
    reset_dir(p)
    put(p / "task.toml", task_toml(fam, f, t, False))
    put(p / "instruction.md", priv_instruction(fam, f, t))
    put(p / "README.md", readme(fam, f, t, False))
    put(p / "environment/Dockerfile", PRIV_ENV_DOCKERFILE)
    put(p / "environment/instance.json", src=inst)
    put(p / "environment/rcb_autobio.py", src=SHARED / "rcb_autobio.py")
    put(p / "tests/Dockerfile", PRIV_TESTS_DOCKERFILE)
    put(p / "tests/test.sh", src=SHARED / "test.sh", mode=0o755)
    put(p / "tests/grade.py", src=SHARED / "grade.py")
    put(p / "tests/rcb_autobio.py", src=SHARED / "rcb_autobio.py")
    put(p / "tests/instance.json", src=inst)
    put(p / "solution/solve.sh", src=SHARED / "solve.sh", mode=0o755)
    put(p / "solution/oracle_replay.py", src=SHARED / "oracle_replay.py")
    put(p / "solution/oracle.npz", src=oracle)

    s = out / f"autobio-{dash(fam)}-i00-standard"
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
    put(s / "environment/sim/rcb_autobio.py", src=SHARED / "rcb_autobio.py")
    put(s / "environment/sim/instance.json", src=inst)
    put(s / "environment/sim/task.json", json.dumps(
        {"task_text": t["goal_std"], "default_cameras": f["default_cameras"], "static": {"inventory": t["inventory"]}},
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


def limits_agree() -> None:
    """The graders' time limits are the ones task.toml is written with (one statement of each, checked here)."""
    fin, gr = (SHARED / "standard/finalize.sh").read_text(), (SHARED / "grade.py").read_text()
    want = [
        (fin, f"RCB_COLLECT_BUDGET_S:-{COLLECT_TIMEOUT}}}"),
        (fin, f"RCB_REPLAY_TIMEOUT_S:-{REPLAY_TIMEOUT}}}"),
        (gr, f"VERIFIER_TIMEOUT_S = {VERIFIER_TIMEOUT}\n"),
        (gr, f"VERDICT_TIMEOUT_S = {REPLAY_TIMEOUT}\n"),
    ]
    missing = [w for text, w in want if w not in text]
    if missing:
        raise SystemExit(f"generate.py and the shared graders disagree on a time limit: {missing}")


def render_all(out: Path) -> list[str]:
    limits_agree()
    done = []
    for inst in sorted((HERE / "instances").glob("*.json")):
        done += [d.name for d in make(inst.stem, out)]
    return done


def ours(d: Path) -> bool:
    return d.is_dir() and d.name.startswith("autobio-")


def check() -> int:
    """tasks/ must be exactly what render_all writes (contents and modes), with no other AutoBio task directory."""
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
        print(f"FAIL tasks/{name}: differs from scripts/autobio/generate.py (re-run it)")
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
