#!/usr/bin/env python3
"""Generate the MyoSuite tasks: tasks/myosuite-<family>-i00-privileged and ...-standard (10 families x 2 modes).

    python3 scripts/myosuite/generate.py            # every family in instances/
    python3 scripts/myosuite/generate.py --check    # exit 1 if tasks/ differs from what this would write

Inputs: instances/<family>.npz (the frozen instance) and instances/<family>.json (the numbers and texts the task texts
quote: make_facts.py, run in the image), oracles/<family>.npy (the reference rows, where there is one), the shared
sources in shared/ and the eai-standard/2.2 layer with the standard client's base image and pins (scripts/eai_standard/),
all copied byte for byte. Each task directory is written from scratch and finished with scripts/task_conventions.py
(normalize, PROTOCOL v1.0.1); a MyoSuite task directory this does not write is removed. Only the standard library is
needed.
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
VERSION = (ROOT / "images/myosuite/VERSION").read_text().strip()
IMAGE = f"ghcr.io/mll-lab-nu/eai-myosuite:{VERSION}"
_ENV = dict(ln.split("=", 1) for ln in (LAYER / "client.env").read_text().splitlines() if "=" in ln and ln[0] != "#")
CLIENT_IMAGE = _ENV["CLIENT_IMAGE"].strip()
AUTHOR = "Chi Gui"
AGENT_TIMEOUT = 5400  # uniform within the benchmark; why not 3600: docs/benchmarks/myosuite.md
REVIEW_PR = "TBD"  # the number of the pull request that adds the benchmark (human review, PROTOCOL §2.7)
HOSTS = [
    "chatgpt.com", "*.chatgpt.com", "auth.openai.com", "api.openai.com", "*.openai.com", "api.anthropic.com",
    "*.anthropic.com", "openrouter.ai", "*.openai.azure.com", "*.cognitiveservices.azure.com",
]  # fmt: skip
BODY = {
    "hand": ("MyoHand", "myohand", "a musculoskeletal model of a human forearm and hand"),
    "arm": ("MyoArm", "myoarm", "a musculoskeletal model of a human shoulder, arm and hand"),
}
CAMERAS_STD = (
    "`hand_top` and `hand_side_inter` are close-ups of the hand, **mounted on the forearm** (the radius): they "
    "move with it (pronation turns them), so use the pose returned with each frame; `front_view` and `side_view` "
    "are static and show the whole body, where the hand is small"
)
# Solvability evidence for the families without a reference solution (PROTOCOL §2.7): a successful model trial on the
# privileged task (the same frozen instance), re-graded by today's verifiers: docs/benchmarks/myosuite.md, Evidence.
# Run ids as in TAXONOMY; trials are Harbor trial names. `standard`: the same rows sent through the client.
OPUS = "Claude Code + Claude Opus 5.5 (run `claude_code-claude_opus_5_5-default`, 2026-09-28)"
LUNA = "Codex + GPT-6 Luna (run `codex-gpt6_luna-high`, via an OpenRouter adapter before protocol v1.0, 2026-09-29)"
EVIDENCE = {
    "baoding": (OPUS, "myosuite-baoding-i00__J6BJVtG", 215, False),
    "die_reorient": (OPUS, "myosuite-die-reorient-i00__EtyJ3X7", 225, True),
    "pen_twirl": (OPUS, "myosuite-pen-twirl-i00__UtTYzQE", 513, True),
    "hand_pose": (LUNA, "myosuite-hand-pose-i00__fC7US9G", 360, True),
    "hand_reach": (LUNA, "myosuite-hand-reach-i00__w2ryUU7", 70, True),
    "obj_reorient": (LUNA, "myosuite-obj-reorient-i00__5dLP3ah", 305, True),
    "relocate": (LUNA, "myosuite-relocate-i00__PjqTvZ2", 231, True),
}
REFERENCE = (
    "MyoSuite's own NPG baseline policy for `{env}` (`myosuite/agents/baslines_NPG/`, shipped in the MyoSuite "
    "wheel and removed from the image), rolled out from the frozen instance and cut at the first success"
)

PRIV_ENV_DOCKERFILE = f"""# MyoSuite task (privileged): MyoSuite 2.12.2 on MuJoCo (images/myosuite/), the task's tooling and its frozen instance.
# CPU only. The base image has MyoSuite's trained baselines removed (they are this benchmark's reference solutions).
FROM {IMAGE}
COPY instance.npz /app/instance.npz
COPY rcb_myosuite.py /opt/tools/rcb_myosuite.py
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
"""
PRIV_TESTS_DOCKERFILE = f"""# Separate verifier sandbox (PROTOCOL §2.6): the same image with the verifier's own copies of the tooling and the frozen
# instance. Nothing the agent did in its container reaches this one: Harbor uploads only the declared artifacts.
FROM {IMAGE}
COPY grade.py instance.npz rcb_myosuite.py test.sh /tests/
RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier
ENV PYTHONPATH=/tests
WORKDIR /tests
"""
STD_ENV_DOCKERFILE = f"""# Standard mode: the agent container has NO simulator and no MyoSuite code, only Python and the client, on the shared
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
      RCB_INSTANCE: /srv/instance.npz
      RCB_TOOL: /srv/rcb_myosuite.py
      RCB_DATA: /data
      RCB_WALL_CLOCK_S: "{AGENT_TIMEOUT}"
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
    return json.dumps(s)


def oracle_meta(fam: str, f: dict, std: bool) -> tuple[str, str]:
    """(oracle, oracle_evidence) for task.toml."""
    if "reference_rows" in f:
        return "full", ""
    who, trial, rows, through_client = EVIDENCE[fam]
    if not std:
        ev = (
            f"a successful model trial on this frozen instance: {who}, trial `{trial}` ({rows} rows); today's verifier "
            f"scores its trajectory 1 in two fresh trials (docs/benchmarks/myosuite.md); human review in PR #{REVIEW_PR}"
        )
    elif through_client:
        ev = (
            f"the privileged twin's positive example ({who}, trial `{trial}`, {rows} rows) rounded to float32, as the "
            f"client sends it, and streamed through the client: the service scores it 1 live and in both replays, in two "
            f"fresh trials (docs/benchmarks/myosuite.md); human review in PR #{REVIEW_PR}"
        )
    else:
        ev = (
            f"no positive example in standard mode yet: the privileged twin's ({who}, trial `{trial}`) fails once its "
            f"rows are rounded to the client's float32 (a ball drops after 206 control steps; 400 random float32 roundings "
            f"of its rows fail too); the family's solvability rests on the privileged twin; human review in PR #{REVIEW_PR}"
        )
    return "none", ev


def priv_instruction(fam: str, f: dict) -> str:
    b = BODY[f["body"]]
    ms = round(f["dt"] * 1000)
    return f"""# MyoSuite · {fam} — frozen instance

You control the **{b[0]}**, {b[2]} (MyoSuite 2.12.2 on MuJoCo), via Python, by **exciting its {f["nu"]} muscles**: there
is no joint-level command. **Task:** {f["goal"]}

{f["scene"]} `s.state()` gives the task's observation dict (privileged): {", ".join(f"`{k}`" for k in f["obs_keys"])}.
MyoSuite's reward code (from `/usr/local/lib/python3.11/site-packages/{f["reward_path"]}`; `solved` is the goal test,
`done` the failure test):
```python
{f["reward_src"]}
```
Robot Coding Bench counts the goal only when `solved` holds for {f["hold_steps"]} consecutive control steps ({f["hold_s"]} s);
`done` ends the episode as a failure. MyoSuite's step budget is lifted.

This is a *fixed scene instance*: the limb's start pose, the object and the goal never change between resets. You may
reset and retry as many times as you want. Your deliverable is **one replayable trajectory**, not a general policy.

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below). It is replayed
open-loop from the same initial state in two fresh processes and scored 1 if both episodes end in success in the same
state, else 0. Also leave the script that produced it at `/app/output/gen.py`.

Your time budget is {AGENT_TIMEOUT} s of wall clock. Save a trajectory as soon as you have one that works, improve it while
time remains, and do not stop early.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_myosuite import Session
s = Session("{fam}", instance="/app/instance.npz")   # ~1 s
s.reset()                          # back to the frozen initial state (unlimited; an exact snapshot restore)
s.state()                          # the task's observation dict (privileged; see above)
s.muscles(); s.joints()            # {f["nu"]} muscles (index, name, ctrl range); hinge joints (name, qpos/dof address, range, qpos)
s.moment_arms()                    # ({f["nu"]}, nv) muscle moment arms at the current pose
s.model, s.data                    # MuJoCo model / data: read them freely; only the actions you record are replayed
s.excitation(a); s.command_for(u)  # command a -> excitation u = 1/(1+exp(-5(a-0.5))) and its inverse
s.step(a)                          # one control step ({ms} ms): {f["nu"]} muscle commands; False once the episode is over
s.rest_action()                    # every muscle relaxed (a = -1)
s.status()                         # {{'success', 'done', 'reason', 'steps', 'resets', 'solved_run', 'hold_steps', 'state_sha', 'info'}}
s.record_start(); ...; actions = s.record_stop()   # (T, {f["nu"]}) commands, one row per control step
s.replay(actions)                  # resets, replays open-loop until the episode ends, returns status -> self-check
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_frame("hand_top")         # RGB uint8 (480, 640, 3); cameras: {", ".join(f["cameras"])} (hand_top / hand_side_inter: hand close-ups)
s.render_video(actions, "/app/output/check.mp4")
```
There are no motion primitives: moving a finger, grasping and every other skill are yours to build from muscle commands.

CLI equivalent of the grader:
`python /opt/tools/rcb_myosuite.py replay --instance /app/instance.npz --traj /app/output/trajectory.npz --repeat 2`

## Conventions
- Action: {f["nu"]} real numbers, one per muscle in `s.muscles()` order. MyoSuite maps each to an excitation
  u = 1 / (1 + exp(-5 (a - 0.5))) and does not clip a (a = -1: u ~ 0.0006, a = 0.5: 0.5, a = 1: 0.92, a = 2: 0.9994).
  Activation follows excitation with a first-order delay (~10 ms up, ~40 ms down); muscles only pull; one muscle can
  cross several joints; its force also depends on its length and velocity (MuJoCo muscle model).
- Control step {ms} ms ({f["frame_skip"]} physics substeps). There is no step budget: your wall-clock time is the limit
  (~{f["steps_per_s"]} control steps/s here). An episode ends at success or at a task failure; `s.step` then refuses further
  actions until `s.reset()`.
"""


def std_instruction(fam: str, f: dict) -> str:
    b = BODY[f["body"]]
    hz = round(1 / f["dt"])
    return f"""# MyoSuite · {fam} — STANDARD MODE (robot as a service, eai-standard/2.2)

You control the **{b[0]}**, {b[2]}, **as if it were a real limb**: the simulator (MyoSuite 2.12.2 on MuJoCo) runs in a
service you cannot open. You get one client and one episode, and you act only by exciting its {f["nu"]} muscles.
**Task:** {f["goal"]}

{f["scene"]}

## Rules
- **No reset.** The episode starts when the service comes up and ends on success (the goal held {f["hold_steps"]} control
  steps, {f["hold_s"]} s), on the task's failure (see the task), when your time is up, or on a simulator error.
- **No privileged state.** You see what the cameras see (RGB, and depth on request, with each camera's calibration) and
  the limb's own proprioception: joint angles, velocities and muscle torques, muscle activations and lengths. No object
  or goal poses, no success check: `meta["done"]` / `meta["reason"]` tell you when the episode is over and why.
- Your wall-clock budget is {AGENT_TIMEOUT} s from your start (`meta["time_left_s"]`); steps are unlimited. Simulated time
  only advances with your commands (and `get_obs(seconds=...)`, which holds the last command). Do not stop early.
- Nothing to hand in: the service records your episode and grades it. Leave your script at `/app/output/gen.py`.
- **If the service crashes**, a call fails with a connection error: it restarts and resumes the SAME episode (never a
  reset) in the state after the last call it completed. `r.wait_ready()` waits for it; then check `r.status()`.
- **Nothing is put into your context automatically.** Images and videos come back as arrays/bytes in a Python object.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`)
```python
from rcb_client import Robot
r = Robot()                                    # connects (waits while the service starts)
spec = r.spec()                                # muscles, joints, cameras (+ intrinsics, mounting), proprio layout, kinematics, budget
obs = r.get_obs()                              # obs.last[cam] -> uint8 (480, 640, 3) (default camera: hand_top)
obs = r.get_obs(cameras=["hand_top", "front_view"], depth=True)   # + obs.last_depth[cam] -> float32 (480, 640), metres
obs.meta["proprio"]                            # {{"layout": [...], "now": [...]}}: q_*, qd_*, act_*, len_*, effort_*
obs.meta["cameras"]                            # per camera intrinsic_cv / extrinsic_cv / cam2world_gl at the last frame
res = r.submit("muscle", rows, dt={f["dt"]:g})          # rows: (T, {f["nu"]}) muscle commands, one row per control step
res.meta["done"], res.meta["reason"], res.meta["control_steps_chunk"]; res.video[cam]; res.last[cam]; res.proprio
obs = r.get_obs(seconds=1.0, video="mp4")      # hold the last command and watch for 1 s (max 30)
r.fk(q); r.ik({{"IFtip": [x, y, z, 1, 0, 0, 0]}}, seed=q)   # fingertips <-> joint angles, world frame (no physics)
r.status()                                     # calls, control steps, done, reason, elapsed time
```
Cameras (640x480): {CAMERAS_STD}. Rendering is on the CPU: ask only for the cameras you need; `video="none"` makes a
chunk fastest. Proprioception (`spec["proprio_groups"]`): `joint_pos` (`q_<joint>`, rad), `joint_vel` (`qd_<joint>`),
`muscle_activation` (`act_<muscle>`), `muscle_length` (`len_<muscle>`, m), `joint_effort` (`effort_<joint>`, the muscles'
generalized force on each joint, N m). `/kinematics` gives the fingertip sites and the camera mounts for any joint angles.

### Action type `muscle` ({f["nu"]})
One real number a per muscle, in `spec["action_types"]["muscle"]["layout"]` order. The excitation is
u = 1 / (1 + exp(-5 (a - 0.5))) and a is not clipped (a = -1: u ~ 0.0006, a = 0.5: 0.5, a = 1: 0.92, a = 2: 0.9994).
Activation follows excitation with a first-order delay (~10 ms up, ~40 ms down); muscles only pull; one muscle can cross
several joints; its force depends on its length and velocity. Rows are `dt` apart (a whole multiple of the
{1000 / hz:g} ms control period, at most 0.5 s; a chunk covers at most 10 s), `interpolate="linear"` (default, from the
previous command) or `"hold"`; the client sends them as float32. The control rate is {hz} Hz ({f["frame_skip"]} physics
substeps); there is no step budget.
"""


def task_toml(fam: str, f: dict, std: bool) -> str:
    b = BODY[f["body"]]
    oracle, ev = oracle_meta(fam, f, std)
    first = f["goal"].split(". ")[0]
    keywords = [
        "robotics",
        "myosuite",
        "mujoco",
        "musculoskeletal",
        b[1],
        "code-as-policy",
        "trajectory",
        fam,
        "standard-mode" if std else "privileged",
    ]
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
            f"STANDARD MODE (robot as a service, eai-standard/2.2): MyoSuite {fam} ({b[0]}, {f['nu']} muscles) on the "
            f"same frozen instance as myosuite-{dash(fam)}-i00-privileged: {first}. The agent only gets a client: "
            "cameras (RGB, optional depth, calibration), the limb's joints and muscles, muscle command chunks, "
            "fingertip kinematics; one episode, no reset, no object state; the sim service records the episode, "
            "replays it in fresh processes and grades it."
        )
    else:
        head = 'artifacts = ["/app/output/"]'
        desc = (
            f"MyoSuite {fam} ({b[0]}, {f['nu']} muscles, MuJoCo): produce one replayable trajectory of muscle commands. "
            f"{first}. Frozen scene instance ({f['env_id']}, reset seed 0); graded by two fresh-process replays."
        )
    meta_extra = 'protocol = "eai-standard/2.2"\n' if std else ""
    oracle_lines = f'oracle = "{oracle}"\n' + (f"oracle_evidence = {toml_str(ev)}\n" if ev else "")
    verifier = (
        """[verifier]
timeout_sec = 600.0
environment_mode = "separate"
network_mode = "no-network"

[[verifier.collect]]
service = "sim"
command = "sh /srv/finalize.sh"   # end + dump + exit the service, replay twice in fresh processes, write final.json, video
timeout_sec = 1800
"""
        if std
        else """[verifier]
timeout_sec = 1800.0
environment_mode = "separate"
network_mode = "no-network"

[verifier.environment]
build_timeout_sec = 1800.0
cpus = 4
memory_mb = 8192
"""
    )
    return f"""# Generated by scripts/myosuite/generate.py -- edit the generator, the shared sources or the instance facts, not this.
schema_version = "1.3"
{head}

[task]
name = "robot-coding-bench/myosuite-{dash(fam)}-i00-{'standard' if std else 'privileged'}"
description = {toml_str(desc)}
authors = [{{ name = "{AUTHOR}" }}]
keywords = [{", ".join(toml_str(k) for k in keywords)}]

[metadata]
author_name = "{AUTHOR}"
task_type = "trajectory"
simulator = "myosuite"            # MyoSuite 2.12.2 on MuJoCo 3.6.0 (CPU)
robot = "{b[1]}"
family = "{fam}"
mode = "{'standard' if std else 'privileged'}"
{meta_extra}{oracle_lines}instance_seed = 0                 # {f['env_id']}: seed(0), then reset(seed=0)
expert_time_estimate_hours = {f['hours'] + (1.0 if std else 0.0)}

{verifier}
[agent]
timeout_sec = {AGENT_TIMEOUT}.0
# MyoSuite's trained baselines ship in its PyPI wheel (and a standard-mode agent could rebuild the simulator from it):
# the agent reaches the model APIs and nothing else (scripts/set_agent_egress.py HOSTS).
network_mode = "allowlist"
allowed_hosts = [{", ".join(toml_str(h) for h in HOSTS)}]

[environment]
build_timeout_sec = 1800.0
cpus = 4
memory_mb = 8192
"""


def readme(fam: str, f: dict, std: bool) -> str:
    b = BODY[f["body"]]
    name = f"myosuite-{dash(fam)}-i00-{'standard' if std else 'privileged'}"
    twin = f"myosuite-{dash(fam)}-i00-{'privileged' if std else 'standard'}"
    oracle, ev = oracle_meta(fam, f, std)
    if std:
        task = (
            f"MyoSuite `{f['env_id']}` ({b[0]}, {f['nu']} muscles) on the same frozen instance as `{twin}`: {f['goal']}\n"
            f"{f['scene']} Standard mode (eai-standard/2.2): the agent drives the limb through a client in one episode, "
            "with only the limb's own proprioception and four cameras (two on the forearm)."
        )
        diff = (
            f"Same instance and success rule as `{twin}` (first-pass rating: {f['difficulty']}). In standard mode the "
            "agent loses resets, the simulator and the object state: it sees camera images and the limb's "
            "proprioception, acts in muscle-command chunks, and gets one episode, so it has to close the loop on what "
            "it sees and recover from its own mistakes without starting over."
        )
        if oracle == "full":
            ref = (
                f"`solution/oracle_stream.py` streams the privileged reference's rows (`solution/oracle.npy`, "
                f"{f['reference_rows']} rows, float32-exact) through the client in `hold` chunks; it uses no privileged "
                "information at run time. The service's recorded trajectory is then exactly the privileged reference: "
                f"success after {f['reference_steps']} control steps."
            )
        else:
            ref = f"None. Solvability evidence: {ev}."
        ver = (
            "The sim service judges the episode live and records every executed control step; the collect hook "
            "(`environment/sim/finalize.sh`) ends the service, replays the recorded trajectory in two fresh processes "
            "and writes `final.json`; `tests/grade.py` (separate sandbox, no network) passes iff the live episode "
            "succeeded, both replays succeed, and they end in the same state. "
            + (
                "`nop`: the episode times out, reward 0."
                if oracle == "full"
                else f"No oracle; human review in PR #{REVIEW_PR}. `nop`: the episode times out, reward 0."
            )
        )
        details = [
            (
                "Service",
                "`environment/sim/server.py` (the adapter) on the shared 2.2 layer `rcb_limited.py` "
                "(`scripts/eai_standard/`); cameras `hand_top`, `hand_side_inter` (on the forearm), `front_view`, "
                "`side_view` (static), 640 x 480; fingertip kinematics in the world frame",
            ),
            ("Resources", "4 CPUs, no GPU (CPU physics, OSMesa rendering)"),
        ]
    else:
        task = (
            f"MyoSuite `{f['env_id']}` ({b[0]}, {b[2]}, {f['nu']} muscles): {f['goal']}\n{f['scene']} The deliverable "
            f"is one replayable trajectory of muscle commands (`/app/output/trajectory.npz`, `(T, {f['nu']})`, one row "
            f"per {round(f['dt'] * 1000)} ms control step)."
        )
        diff = (
            f"First-pass rating: {f['difficulty']}. The action is muscle-level only ({f['nu']} muscles, each only "
            "pulling, several crossing more than one joint, with activation delays): the agent has to build its own "
            "joint or fingertip control from muscle excitations, and MyoSuite's goal has to hold for "
            f"{f['hold_s']} s, so passing through the goal does not count."
        )
        if oracle == "full":
            ref = (
                REFERENCE.format(env=f["env_id"])
                + f": `solution/oracle.npy`, {f['reference_rows']} rows (float32-exact, "
                f"so the standard twin's client executes the same rows), success after {f['reference_steps']} control "
                "steps. Replayed and saved by `solution/solve.sh`; re-checked by `scripts/myosuite/make_facts.py "
                "--oracles` (two fresh sessions, same final state)."
            )
        else:
            ref = f"None. Solvability evidence: {ev}."
        ver = (
            "`tests/grade.py` in a separate sandbox without network: two replays of `/app/output/trajectory.npz`, each in "
            "a fresh process, from the verifier's own copy of the instance (`tests/instance.npz`; the rebuilt start state "
            "is checked against its recorded hash); pass iff both episodes end in success (the goal held "
            f"{f['hold_steps']} control steps) in the same state (`deterministic`). "
            + (
                "`nop`: no trajectory, reward 0."
                if oracle == "full"
                else f"No oracle; human review in PR #{REVIEW_PR}. `nop`: no trajectory, reward 0."
            )
        )
        details = [
            (
                "Instance",
                f"`{f['env_id']}` after `seed(0)` and `reset(seed=0)` (`rcb_myosuite.py make-instance`); "
                f"state hash `{f['instance_sha']}`, checked on every load",
            ),
            (
                "Actions",
                f"{f['nu']} muscle commands per control step ({round(f['dt'] * 1000)} ms, "
                f"{f['frame_skip']} physics substeps); success = MyoSuite's `solved` held {f['hold_steps']} steps",
            ),
            ("Resources", "4 CPUs, no GPU (CPU physics, OSMesa rendering)"),
        ]
    details.insert(0, ("Upstream", "MyoSuite 2.12.2 (Apache-2.0) on MuJoCo 3.6.0, the models that ship in its wheel"))
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
Generated by `scripts/myosuite/generate.py` from `scripts/myosuite/instances/{fam}.npz` and `{fam}.json`
(`make_facts.py`){f" and `scripts/myosuite/oracles/{fam}.npy`" if oracle == "full" else ""}; see `docs/benchmarks/myosuite.md`.
"""


def make(fam: str, out: Path) -> tuple[Path, Path]:
    f = json.loads((HERE / "instances" / f"{fam}.json").read_text())
    inst = HERE / "instances" / f"{fam}.npz"
    oracle = HERE / "oracles" / f"{fam}.npy"
    full = "reference_rows" in f

    p = out / f"myosuite-{dash(fam)}-i00-privileged"
    reset_dir(p)
    put(p / "task.toml", task_toml(fam, f, False))
    put(p / "instruction.md", priv_instruction(fam, f))
    put(p / "README.md", readme(fam, f, False))
    put(p / "environment/Dockerfile", PRIV_ENV_DOCKERFILE)
    put(p / "environment/instance.npz", src=inst)
    put(p / "environment/rcb_myosuite.py", src=SHARED / "rcb_myosuite.py")
    put(p / "tests/Dockerfile", PRIV_TESTS_DOCKERFILE)
    put(p / "tests/test.sh", src=SHARED / "test.sh", mode=0o755)
    put(p / "tests/grade.py", src=SHARED / "grade.py")
    put(p / "tests/rcb_myosuite.py", src=SHARED / "rcb_myosuite.py")
    put(p / "tests/instance.npz", src=inst)
    if full:
        put(p / "solution/solve.sh", src=SHARED / "solve.sh", mode=0o755)
        put(p / "solution/oracle_replay.py", src=SHARED / "oracle_replay.py")
        put(p / "solution/oracle.npy", src=oracle)

    s = out / f"myosuite-{dash(fam)}-i00-standard"
    reset_dir(s)
    put(s / "task.toml", task_toml(fam, f, True))
    put(s / "instruction.md", std_instruction(fam, f))
    put(s / "README.md", readme(fam, f, True))
    put(s / "environment/Dockerfile", STD_ENV_DOCKERFILE)
    put(s / "environment/docker-compose.yaml", STD_COMPOSE)
    put(
        s / "environment/client-requirements.txt",
        src=LAYER / _ENV.get("CLIENT_REQUIREMENTS", "client-requirements.txt").strip(),
    )
    put(s / "environment/rcb_client.py", src=LAYER / "rcb_client.py")
    put(s / "environment/rcb1.py", src=LAYER / "rcb1.py")
    for name in ("rcb_limited.py", "rcb1.py"):
        put(s / "environment/sim" / name, src=LAYER / name)
    put(s / "environment/sim/run.sh", src=LAYER / "run.sh", mode=0o755)
    put(s / "environment/sim/server.py", src=SHARED / "standard/server.py")
    put(s / "environment/sim/finalize.sh", src=SHARED / "standard/finalize.sh", mode=0o755)
    put(s / "environment/sim/rcb_myosuite.py", src=SHARED / "rcb_myosuite.py")
    put(s / "environment/sim/instance.npz", src=inst)
    put(s / "environment/sim/task_text.txt", f["goal"] + "\n")
    put(s / "tests/Dockerfile", STD_TESTS_DOCKERFILE)
    put(s / "tests/test.sh", src=SHARED / "standard/test.sh", mode=0o755)
    put(s / "tests/grade.py", src=SHARED / "standard/grade.py")
    if full:
        put(s / "solution/solve.sh", src=SHARED / "standard/solve.sh", mode=0o755)
        put(s / "solution/oracle_stream.py", src=SHARED / "standard/oracle_stream.py")
        put(s / "solution/oracle.npy", src=oracle)
    normalize(p)
    normalize(s)
    return p, s


def render_all(out: Path) -> list[str]:
    done = []
    for inst in sorted((HERE / "instances").glob("*.json")):
        done += [d.name for d in make(inst.stem, out)]
    return done


def ours(d: Path) -> bool:
    return d.is_dir() and d.name.startswith("myosuite-")


def check() -> int:
    """tasks/ must be exactly what render_all writes (contents and modes), with no other MyoSuite task directory."""
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
        print(f"FAIL tasks/{name}: differs from scripts/myosuite/generate.py (re-run it)")
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
