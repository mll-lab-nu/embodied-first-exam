#!/usr/bin/env python3
"""Generate the MyoSuite tasks: tasks/myosuite-<family>-i00-privileged and ...-standard (every family), and
...-standard-realtime for the families whose scene is dynamic (REALTIME; PROTOCOL §4b, §2.14).

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
import re
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
# The agent's time cutoff per mode (PROTOCOL §2.12): this benchmark's own number, written into every task's `[agent]
# timeout_sec`, the one source; normalize renders from it the instruction's closing `## Time limit`, the README row and
# the sim service's wall clock. To change it (an owner decision; the pull request states old -> new), edit it here and
# regenerate.
CUTOFF = {"privileged": 3600, "standard": 3600, "standard-realtime": 3600}
# The standard service's bound on the images of one call, quoted from the source: the texts state the enforced value.
MAX_FRAMES = int(re.search(r"^MAX_FRAMES = (\d+)", (SHARED / "standard" / "server.py").read_text(), re.M).group(1))
# The standard collect hook (finalize.sh): it ends the service (at most 900 s, RCB_COLLECT_END_TIMEOUT_S), writes the live
# episode's verdict and then renders the video, one pass over the graded episode's physics; nothing is replayed to grade
# (owner, 2026-10-17, board 0151). The render gets the rest of this budget: more than the two verdict replays and the
# third, filming one that the hook ran in it until then.
COLLECT_TIMEOUT = 1800
RESET_BUDGET = 10  # standard mode's default reset budget (owner, 2026-10-09; PROTOCOL §4.5, docs/benchmarks/myosuite.md)
REVIEW_PR = "65"  # the number of the pull request that adds the benchmark (human review, PROTOCOL §2.7)
HOSTS = [
    "chatgpt.com", "*.chatgpt.com", "auth.openai.com", "api.openai.com", "*.openai.com", "api.anthropic.com",
    "*.anthropic.com", "openrouter.ai", "*.openai.azure.com", "*.cognitiveservices.azure.com", "pypi.org", "files.pythonhosted.org", "deb.debian.org", "security.debian.org", "archive.ubuntu.com", "security.ubuntu.com", "snapshot.ubuntu.com",
]  # fmt: skip
BODY = {
    "hand": ("MyoHand", "myohand", "a musculoskeletal model of a human forearm and hand"),
    "arm": ("MyoArm", "myoarm", "a musculoskeletal model of a human shoulder, arm and hand"),
    "body": ("MyoArm with torso", "myoarm-torso",
             "a musculoskeletal model of a human torso, right arm and hand on a pelvis that slides on the floor"),
    "bimanual": ("MyoArm + MPL", "myoarm-mpl",
                 "a musculoskeletal right arm and hand next to a motorized prosthetic left arm (the Modular Prosthetic Limb)"),
    "legs": ("MyoLegs", "myolegs", "a free-standing musculoskeletal model of a human torso and both legs"),
    "osl": ("MyoLeg + OSL", "myoleg-osl",
            "a free-standing musculoskeletal model of a human whose right leg is an Open-Source Leg knee-ankle prosthesis"),
}
DEFAULT_CAMERA = {"table_tennis": "default", "bimanual": "front_view", "soccer": "agent_view", "chase_tag": "topview",
                  "osl_run": "side_view", **{f"dex_{k}": "center_cam" for k in ("apple_lift", "cylinder_pass", "bunny_inspect",
                  "hammer_use", "cup_pour", "airplane_fly")}}  # fmt: skip
RULE_DIFF = {
    "hold": "MyoSuite's goal has to hold for {hold_s} s, so passing through the goal does not count.",
    "event": "Success is the challenge's own event; nothing short of it counts, and the challenge's failure conditions "
             "and time limit apply.",
    "track": "The whole recorded motion has to be followed with the object in hand, within a few centimetres, for "
             "{track_steps} control steps.",
}
CAMERAS_STD = (
    "`hand_top` and `hand_side_inter` are close-ups of the hand, **mounted on the forearm** (the radius): they "
    "move with it (pronation turns them), so use the pose returned with each frame"
)


def default_camera(fam: str, f: dict) -> str:
    return DEFAULT_CAMERA.get(fam, "hand_top" if "hand_top" in f["cameras"] else f["cameras"][0])


def cameras_text(fam: str, f: dict) -> str:
    cams = ", ".join(f"`{c}`" for c in f["cameras"])
    hand = CAMERAS_STD + "; " if "hand_top" in f["cameras"] else ""
    scene = f.get("scene_cameras") or []   # cameras that ride on a body of the scene (make_facts.py): images only
    names = " and ".join(f"`{c}`" for c in scene)
    no_pose = (f" (except {names}, which ride{'s' if len(scene) == 1 else ''} on a body of the scene that is not yours: "
               "images and depth only, no mount and no pose -- `extrinsic_cv` / `cam2world_gl` are null in "
               "`meta[\"cameras\"]` and NaN per frame -- because the pose would be that body's position)" if scene else "")
    return (f"{cams} (640x480; default `{default_camera(fam, f)}`). {hand}`spec[\"cameras\"]` gives each camera's "
            "mounting (static, fixed to a body, or a MuJoCo tracking camera that follows one) and intrinsics, and every "
            f"response carries each frame's pose{no_pose}")


def actuation(f: dict) -> str:
    """The action, in words: muscles plus the non-muscle actuators some families have."""
    n_mus = f["n_muscles"]
    text = (f"{f['nu']} real numbers per control step, one per actuator in order: {n_mus} muscles"
            + (f" and {len(f['actuators'])} non-muscle actuators" if f["actuators"] else "") + ". A muscle's command a "
            "maps to its excitation u = 1 / (1 + exp(-5 (a - 0.5))) and is not clipped (a = -1: u ~ 0.0006, a = 0.5: 0.5, "
            "a = 1: 0.92, a = 2: 0.9994); activation follows excitation with a first-order delay (~10 ms up, ~40 ms down); "
            "muscles only pull; one muscle can cross several joints; its force also depends on its length and velocity.")
    if f["actuators"]:
        text += " The non-muscle actuators: " + "; ".join(f"`{a['name']}` (index {a['index']}): {a['command']}"
                                                           for a in f["actuators"]) + "."
    return text


def rule_text(f: dict) -> str:
    if f["rule"] == "hold":
        return (f"Robot Coding Bench counts the goal only when `solved` holds for {f['hold_steps']} consecutive control "
                f"steps ({f['hold_s']} s); `done` ends the episode as a failure. MyoSuite's step budget is lifted.")
    if f["rule"] == "event":
        return ("`solved` is the challenge's own success event: the episode ends in success at the first control step "
                "where it holds; `done` without it (its failure conditions, its own time limit) ends it as a failure. "
                "The gym step budget (`max_episode_steps`) is lifted; the challenge's own time limit is not.")
    return (f"MyoDex's `solved` is always 0, so Robot Coding Bench judges the tracking itself: the episode lasts "
            f"{f['track_steps']} control steps (the reference) and succeeds as stated above; `done` (MyoDex's "
            "termination) ends it early as a failure. `s.status()['info']` reports the current errors "
            "(`track_pos_err`, `track_rot_err`) and the count of on-track steps (`track_ok`).")
# Solvability evidence for the families without a reference solution (PROTOCOL §2.7): a successful model trial on the
# privileged task (the same frozen instance), re-graded by today's verifiers: docs/benchmarks/myosuite.md, Evidence.
# Run ids as in TAXONOMY; trials are Harbor trial names. `standard`: the same rows sent through the client.
OPUS = "Claude Code + Claude Opus 5.5 (run `claude_code-claude_opus_5_5-default`, 2026-09-28)"
LUNA = "Codex + GPT-6 Luna (run `codex-gpt6_luna-high`, via an OpenRouter adapter before protocol v1.0, 2026-09-29)"
OPUS3 = "Claude Code + Claude Opus 5.5 (run `claude_code-claude_opus_5_5-default`, 2026-10-06)"
F32_BAODING = "a ball drops after 206 control steps; 400 random float32 roundings of its rows fail too"
EVIDENCE = {
    "baoding": (OPUS, "myosuite-baoding-i00__J6BJVtG", 215, F32_BAODING),
    "sarc_key_turn": (OPUS3, "myosuite-sarc-key-turn-i00-privi__iVBaqTS", 230, True),
    "table_tennis": (OPUS3, "myosuite-table-tennis-i00-privil__kdQdy89", 111, True),
    "soccer": (OPUS3, "myosuite-soccer-i00-privileged__DuXNvn4", 308, True),
    "dex_apple_lift": (OPUS3, "myosuite-dex-apple-lift-i00-priv__j5qaRCZ", 57, True),
    "chase_tag": (OPUS3, "myosuite-chase-tag-i00-privilege__6GUXvYA", 329, "the walk no longer reaches the opponent within its 329 rows"),
    "osl_run": (OPUS3, "myosuite-osl-run-i00-privileged__cWgLuKv", 6714, "the runner falls after 629 control steps"),
    "die_reorient": (OPUS, "myosuite-die-reorient-i00__EtyJ3X7", 225, True),
    "pen_twirl": (OPUS, "myosuite-pen-twirl-i00__UtTYzQE", 513, True),
    "hand_pose": (LUNA, "myosuite-hand-pose-i00__fC7US9G", 360, True),
    "hand_reach": (LUNA, "myosuite-hand-reach-i00__w2ryUU7", 70, True),
    "obj_reorient": (LUNA, "myosuite-obj-reorient-i00__5dLP3ah", 305, True),
    "relocate": (LUNA, "myosuite-relocate-i00__PjqTvZ2", 231, True),
}
# set 3: families whose model attempts all failed (PROTOCOL §2.7: listed, never faked); filled from the runs
LUNA3 = "Codex + GPT-6 Luna, effort high, run `codex-gpt6_luna-high`"
NO_POSITIVE: dict[str, str] = {
    "bimanual": f"two model attempts failed: {LUNA3} and {OPUS3}",
    "dex_cylinder_pass": f"two model attempts failed: {LUNA3} and {OPUS3}",
    "dex_bunny_inspect": f"two model attempts failed: {OPUS3} and {LUNA3}",
    "dex_hammer_use": f"two model attempts failed: {LUNA3} and {OPUS3}",
    "dex_cup_pour": f"two model attempts failed: {OPUS3} and {LUNA3}",
    "dex_airplane_fly": f"two model attempts failed: {OPUS3} and {LUNA3}",
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
# Crash recovery (docs/protocol/standard_mode.md §13): run.sh exits non-zero when the service crashes, compose restarts the
# container (same container, same /data) and the service replays its journal into the same episode, never a reset.
# Knobs: ${{NAME:-default}} takes NAME from the shell that runs harbor; the defaults are the standard configuration and
# results under other settings are reported separately.
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
      RCB_WALL_CLOCK_S: "{CUTOFF["standard"]}"
      RCB_STARTUP_TIMEOUT_S: "300"   # the scene builds in a few seconds
      PYTHONPATH: /srv
      RCB_SESSION_LOG: ""           # the sidecar's own Session must not write the agent-side interaction log
      RCB_RESET_BUDGET: "${{RCB_RESET_BUDGET:-{RESET_BUDGET}}}"   # MyoSuite standard: {RESET_BUDGET} resets (PROTOCOL §4.5); 0: one episode
      RCB_COLLECT_BUDGET_S: "{COLLECT_TIMEOUT}"   # the collect hook's timeout_sec (task.toml): finalize.sh fits the video's render pass in
"""


# ------------------------------------------------------------------------------------------- standard-realtime twins
# The dynamic families (each task's `[metadata] dynamics`; PROTOCOL §2) get a `-standard-realtime` twin (owner, 2026-10-14,
# board 0112): the same frozen instance and success rule, served by shared/realtime/server.py (the rcb_service.Sim
# adapter on rcb_myosuite.Session) behind the shared eai-standard/2.3 layer (rcb_realtime.py + rcb_service.py, copied
# unchanged from scripts/humanoidbench/shared/; check-tooling-identity.sh). Per family: the slowdown S its service runs
# at, from the real-time factor RTF measured on the reference workstation (PROTOCOL §4b: S = 1 when RTF >= 3, else
# ~1.5 / RTF rounded up), and how it was measured (docs/benchmarks/myosuite.md, "Standard-realtime").
REALTIME = {
    "table_tennis": {
        "slowdown": 1,
        "rtf": "2.1-2.7",
        "measured": "2026-10-14, board 0112, ws-1 (32 cores, load 30-60), the service capped at 4 CPUs: 2.08 with "
                    "the realtime service's clock flat out (RCB_SLOWDOWN = 0.01, 11 episodes, 13.3 s of robot time), 2.6-2.7 "
                    "for the bare physics; S = ceil(1.5 / 2.08) = 1. At S = 1 a controller at the control rate with a "
                    "camera image every 0.25 s ran 11 episodes with no stall (largest lag 0.23 s), and an EGL frame takes "
                    "5 ms (an OSMesa one 1.3 s)",
        "evidence": "a successful episode of the privileged twin (GPT-6 Luna xhigh, trial "
                    "`myosuite-table-tennis-i00-privil__SMNgbHk`, 82 rows) planned from step 0 in one "
                    "`submit(..., at=0)` at S = 1 succeeds live and in the fresh replay, with no stall (board 0112, "
                    "2026-10-14); the standard twin's evidence holds for the same instance and rule",
        "rally": "the serve reaches you and the rally is decided within about 1.2 s of robot time after the clock starts "
                 "(an episode that does nothing ends after 121 control steps)",
    },
}
RT_REVIEW_PR = "201"  # the pull request that adds the standard-realtime twins (human review, PROTOCOL §2.7)
RT_RESET_BUDGET = 10   # PROTOCOL §4b: every standard-realtime task allows resets, 10 by default (owner, 2026-10-14)
RT = SHARED / "realtime"
RT_ENV_DOCKERFILE = f"""# Standard-realtime mode: the agent container has NO simulator and no MyoSuite code, only Python and the realtime client
# (eai-standard/2.3), on the shared pinned client base with the shared pins (scripts/eai_standard/client.env).
FROM {CLIENT_IMAGE}
COPY client-requirements.txt /tmp/client-requirements.txt
RUN pip install --no-cache-dir -r /tmp/client-requirements.txt
COPY rcb_client.py rcb1.py /opt/tools/
ENV PYTHONPATH=/opt/tools
RUN mkdir -p /app/output
WORKDIR /app
"""


def rt_compose(fam: str) -> str:
    S = REALTIME[fam]["slowdown"]
    return f"""# Standard-realtime mode (PROTOCOL §4b): the simulator runs in the `sim` sidecar (the agent cannot open it), on its own clock
# once an episode starts (sim/rcb_realtime.py, the shared eai-standard/2.3 layer, with sim/server.py, MyoSuite's adapter);
# the agent only reaches port 8000. No `expose`/`ports` on sim: under Harbor's egress control it shares main's network
# namespace (localhost:8000).
# GPU on sim: the physics is MuJoCo on the CPU, but every image the agent asks for is rendered here, and on a clock that
# does not stop a render is time the simulator cannot step: EGL on the GPU takes ~5 ms a frame, OSMesa ~1.3 s
# (table_tennis, 640x480). `graphics` is the capability that mounts the EGL driver (server.py writes its ICD manifest).
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
    restart: on-failure:6          # N >= 3 (PROTOCOL §4.1); a resume continues the episode, paused
    environment:
      RCB_INSTANCE: /srv/instance.npz
      RCB_TASK_INFO: /srv/task.json
      RCB_DATA: /data
      RCB_WALL_CLOCK_S: "{CUTOFF["standard-realtime"]}"
      RCB_STARTUP_TIMEOUT_S: "300"   # the scene builds in a few seconds
      PYTHONPATH: /srv
      RCB_SESSION_LOG: ""           # the sidecar's own Session must not write the agent-side interaction log
      RCB_SLOWDOWN: "${{RCB_SLOWDOWN:-{S}}}"                # S = {S}: the world runs at 1/S of real speed (this family's measured RTF; PROTOCOL §4b)
      RCB_RESET_BUDGET: "${{RCB_RESET_BUDGET:-{RT_RESET_BUDGET}}}"        # {RT_RESET_BUDGET} resets (PROTOCOL §4b default); 0: one episode
      RCB_GL: "${{RCB_GL:-auto}}"                     # auto: EGL on the GPU when it works, else OSMesa
      NVIDIA_DRIVER_CAPABILITIES: compute,graphics,utility
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
"""


def rt_instruction(fam: str, f: dict) -> str:
    b, rt = BODY[f["body"]], REALTIME[fam]
    S = rt["slowdown"]
    hz = round(1 / f["dt"])
    ms = round(f["dt"] * 1000, 1)
    ms = int(ms) if ms == int(ms) else ms
    atype = "muscle" if not f["actuators"] else "actuators"
    root = (", the pose and velocity of your free-standing root (the pelvis: `root_*`)" if f["free_root"] else "")
    return f"""# MyoSuite · {fam} — STANDARD-REALTIME MODE (robot as a service; time does not stop)

You control the **{b[0]}**, {b[2]}, **as if it were real**: the simulator (MyoSuite 2.12.2 on MuJoCo) runs in a service
you cannot open, you reach it only through a client, and like the real world it does not wait for you: once an episode
is running, the body and the ball move while you think. You act only through its actuators ({f["n_muscles"]} muscles{
f" and {len(f['actuators'])} other actuators" if f["actuators"] else ""}).
**Task:** {f["goal"]}

{f["scene"]} Here the rally is fast: {rt["rally"]}.

**Slowdown: S = {S}.** The world runs at 1/S of real speed: one control step ({ms} ms of robot time) every S x {ms} ms of
wall-clock time{" (real time)" if S == 1 else ""}. `spec()["timing"]["slowdown"]` states it.

## Rules (real-world rules)
- **Time does not stop.** An episode starts paused, on the frozen starting state, with every command at -1 (muscles
  relaxed). Its clock starts at your first `submit` (or `get_obs(seconds=s)`) and from then on the simulator runs at
  {hz} Hz of robot time (S = {S}), one control step every {ms * S:g} ms of wall-clock time, whether or not you send anything, until
  the episode ends. Between your commands it executes what you planned, then holds the last commands you sent; nothing
  pauses for you, not your thinking, not your tool calls.
- **You are far too slow to steer it turn by turn.** One turn of yours (a model response, a tool call) takes seconds;
  the whole rally takes about a second. Drive the body with a program: a controller of your own (Python in your
  container, with numpy and the client) that plans or streams the commands, started in the background
  (`nohup python /app/output/gen.py > /app/output/run.log 2>&1 &`) or in the foreground if it ends with the episode. Use
  your turns to start episodes, read what happened, and improve the program.
- **Episodes and resets.** An episode ends at the task's own success event, at its failure conditions (see the task),
  when your time is up, or on a simulator error. You have **{RT_RESET_BUDGET} resets** (`spec()["budget"]["reset"]`,
  which is authoritative: if it says 0, there is no reset and the one episode is the run). `r.reset()` puts the body,
  the ball and the scene back on the same frozen starting state and starts a new episode, paused until your next
  `submit`, either abandoning the running episode or after one has ended. Once an episode has ended, `submit` raises
  `EpisodeOver` (its message gives `resets_left`) until you reset. **Only the last episode is graded**: an episode you
  reset away is never graded, a success ends the run at once (no reset after it), and when your time is up the episode
  then running is the one graded. The wall clock is the run's and never restarts; `meta["episode"]` and
  `meta["resets_left"]` count the episodes.
- **No privileged state, no score.** You see what the cameras see (RGB, and depth on request) and the body's own
  proprioception: joint positions and velocities, muscle activations and lengths, the actuators' generalized force on
  each joint{root}. No ball, paddle, table or goal poses, no success check: the service judges the episode and only
  tells you that it ended and why (`meta["done"]`, `meta["reason"]`: `"success"`, `"error"` after a simulator error,
  else `"failed"`). `spec()` gives the body's own facts: the actuators, the joints and their limits, each camera's
  intrinsics and mounting.
- There is nothing to hand in: the service records every control step it ran and grades the last episode as it ran
  (nothing is replayed). Keep the controller that drives the body at `/app/output/gen.py` for the record:
  save it early and keep it current.
- Do not stop early: while the episode runs, or a reset is left, the run can still pass.

## Time and streaming
- `submit` answers at once, with the body as it is now: the rows you sent have not run yet. They become the plan from
  control step `at` (an episode step number; by default the next step), replacing whatever was planned from `at` on and
  keeping what is planned before it. When the plan runs out, the last commands are held. `res.meta["control_steps"]`
  is the number of steps run so far in this episode (so the next step has that number), `res.meta["proprio"]["now"]`
  the proprioception now, `res.meta["plan_end_step"]` where the plan now ends.
- Open loop: plan a whole movement at once (`dt` a multiple of {f["dt"]:g} s; a chunk covers at most 10 s), from step
  `at = 0` for the episode's start: `r.submit("{atype}", rows, dt={f["dt"]:g}, interpolate="hold", at=0, cameras=[])`
  starts the clock and runs exactly those rows from the first step; `at` may be up to
  `spec()["timing"]["max_ahead_steps"]` steps ahead.
- Closed loop: send one row per control step, `r.submit("{atype}", a[None], cameras=[])`, computed from the
  proprioception the previous call returned. `cameras=[]` skips the images (the fastest call).
- Latency: a reading is a few milliseconds old when it reaches you, and a row takes effect at the next control step at
  the earliest. A row whose step has already run when the request arrives is dropped (`res.meta["late_steps"]` counts
  them); the rest of its chunk applies from the next step.
- `get_obs()` reads the body now; `get_obs(seconds=s)` (at most 30) waits while s seconds of robot time run and returns
  what the cameras saw meanwhile (the body keeps executing its plan). `spec()["timing"]` states all this; `r.status()`
  shows `running` and `lag_s`.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.3`, standard-realtime mode)
Your whole interface to the body. Its docstring is the full reference (`python -c "import rcb_client;
help(rcb_client)"`); the calls and the endpoints they use:

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the scene is ready |
| `r.spec()` | `GET /spec` | the body's facts: the actuators' order (`action_types["{atype}"]["layout"]`), `control_dt` ({f["dt"]:g} s), `timing`, the cameras, `proprio_layout`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s`, `running`, `planned_steps`, `lag_s`, and `episode`, `resets_left`, `control_steps_total` (all episodes) |
| `r.submit("{atype}", A, dt={f["dt"]:g}, interpolate="linear", at=None, cameras=None)` | `POST /submit` | plans `A`, rows of {f["nu"]} commands `dt` seconds apart (a chunk covers at most 10 s), from step `at`; answers at once; the first one starts the episode's clock |
| `r.get_obs(cameras=None, seconds=0, include_depth=False, video="frames")` | `POST /observe` | the body now, or what the cameras saw over the next `seconds` |
| `r.reset(cameras=None, include_depth=False)` | `POST /reset` | a new episode from the frozen starting state, paused (at most {RT_RESET_BUDGET} in all); returns the start's frames |

The answers are binary (RCB1) and come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`),
`res.last[camera]` (the last frame), `res.frames` or `res.video` (what the cameras saw during a watch), `res.proprio`
(proprioception rows). A malformed request raises `ValueError` and changes nothing.
```python
from rcb_client import Robot
import numpy as np
r = Robot()
rows = -np.ones((80, {f["nu"]}))                  # 0.8 s of commands, one row per control step
res = r.submit("{atype}", rows, dt={f["dt"]:g}, interpolate="hold", at=0, cameras=[])   # starts the clock
while not r.status()["done"]:
    ...                                          # or stream: r.submit("{atype}", a[None], cameras=[]) each step
```
Cameras: {", ".join(f"`{c}`" for c in f["cameras"])} (640x480, default `{default_camera(fam, f)}`), rendered on the
service's GPU in a few milliseconds each; `cameras=None` means every camera, so name the ones you need.

Each proprioception row (`meta["proprio"]["now"]`, `res.proprio`) has, in `spec()["proprio_layout"]` order: `q_<joint>`,
`qd_<joint>`, `act_<muscle>`, `len_<muscle>` (m), `effort_<joint>` (the actuators' generalized force on the joint){
", `root_*`" if f["free_root"] else ""}.

### Action type `{atype}` ({f["nu"]})
{actuation(f)} Columns in `spec()["action_types"]["{atype}"]["layout"]` order; rows `dt` apart, `interpolate="linear"`
(default: a straight line from the commands in force) or `"hold"`; the realtime client sends them as float64. The control rate
is {hz} Hz ({f["frame_skip"]} physics substeps).
"""


def rt_task_toml(fam: str, f: dict) -> str:
    b, rt = BODY[f["body"]], REALTIME[fam]
    oracle, ev = "none", rt["evidence"] + f"; human review in PR #{RT_REVIEW_PR}"
    first = f["goal"].split(". ")[0]
    keywords = ["robotics", "myosuite", "mujoco", "musculoskeletal", b[1], "trajectory", fam, "standard-realtime-mode"]
    desc = (f"STANDARD-REALTIME MODE (robot as a service on a clock that does not stop, eai-standard/2.3, slowdown S = "
            f"{rt['slowdown']}): MyoSuite {fam} ({b[0]}, {f['n_muscles']} muscles) on the same frozen instance as "
            f"myosuite-{dash(fam)}-i00-privileged: {first}. Once an episode starts the body and the ball move whatever the "
            "agent does, so the agent plans or streams actuator commands from a program of its own through the client "
            f"(cameras, the body's joints and muscles); {RT_RESET_BUDGET} resets, only the last episode graded; no object "
            "state; the sim service records every executed control step and grades the last episode as it ran (nothing is replayed).")
    oracle_lines = f'oracle = "{oracle}"\n' + (f"oracle_evidence = {toml_str(ev)}\n" if ev else "")
    return f"""# Generated by scripts/myosuite/generate.py -- edit the generator, the shared sources or the instance facts, not this.
schema_version = "1.3"
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
  {{ source = "/data/crash.log", service = "sim" }},
  "/app/output/",
]

[task]
name = "robot-coding-bench/myosuite-{dash(fam)}-i00-standard-realtime"
description = {toml_str(desc)}
authors = [{{ name = "{AUTHOR}" }}]
keywords = [{", ".join(toml_str(k) for k in keywords)}]

[metadata]
author_name = "{AUTHOR}"
task_type = "trajectory"
simulator = "myosuite"            # MyoSuite 2.12.2 on MuJoCo 3.6.0 (CPU physics; EGL rendering on the GPU)
robot = "{b[1]}"
family = "{fam}"
mode = "standard-realtime"
protocol = "eai-standard/2.3"
{oracle_lines}instance_seed = 0                 # {f['env_id']}: seed(0), then reset(seed=0)
expert_time_estimate_hours = {f['hours'] + 2.0}

[verifier]
timeout_sec = 900.0
environment_mode = "separate"
network_mode = "no-network"

# The agent's time is up: stop whatever it left running in its container. Harbor stops that container only after
# collecting from it (~12 s), and a script still running there would keep driving the body past the deadline.
[[verifier.collect]]
service = "main"
command = "kill -9 -1 2>/dev/null; exit 0"
timeout_sec = 30

# Then the episode ends: SIGUSR1 to the service (re-sent every 30 s, in case it was restarting), which writes the live
# episode's verdict (nothing is replayed to grade it). The verdict ("finalized": true, set before any video is rendered)
# is waited for until 300 s (a restart and a resume included); then the hook waits for the video, rendered from the
# trajectory ("video_pending"), until 870 s -- a video that is not ready by then is lost, the verdict is not.
[[verifier.collect]]
service = "sim"
command = "t0=$(date +%s); while [ ! -f /data/server.pid ] && [ $(( $(date +%s) - t0 )) -lt 120 ]; do sleep 2; done; i=0; while [ $(( $(date +%s) - t0 )) -lt 300 ] && ! grep -q '\\"finalized\\": true' /data/final.json 2>/dev/null; do [ $((i % 15)) -eq 0 ] && kill -USR1 $(cat /data/server.pid 2>/dev/null) 2>/dev/null; i=$((i + 1)); sleep 2; done; while [ $(( $(date +%s) - t0 )) -lt 870 ] && grep -q '\\"video_pending\\": true' /data/final.json 2>/dev/null; do sleep 2; done; cat /data/final.json"
timeout_sec = 900

[agent]
timeout_sec = {CUTOFF["standard-realtime"]}.0
# The agent reaches the model APIs and the package registries, nothing else (scripts/set_agent_egress.py HOSTS), as in
# every MyoSuite task (PROTOCOL §2.11).
network_mode = "allowlist"
allowed_hosts = [{", ".join(toml_str(h) for h in HOSTS)}]

[environment]
build_timeout_sec = 1800.0
cpus = 4
memory_mb = 8192
"""


def rt_readme(fam: str, f: dict) -> str:
    b, rt = BODY[f["body"]], REALTIME[fam]
    name = f"myosuite-{dash(fam)}-i00-standard-realtime"
    S = rt["slowdown"]
    task = (f"MyoSuite `{f['env_id']}` ({b[0]}, {f['n_muscles']} muscles) on the same frozen instance as "
            f"`myosuite-{dash(fam)}-i00-privileged`: {f['goal']}\n{f['scene']} Standard-realtime mode (eai-standard/2.3, "
            f"slowdown S = {S}): once an episode's clock starts the body and the ball move whatever the agent does; it "
            f"drives the body through the realtime client from a program of its own, with only its own proprioception "
            f"and the scene's cameras, and {RT_RESET_BUDGET} resets (only the last episode is graded).")
    diff = (f"Same instance and success rule as the standard twin (first-pass rating: {f['difficulty']}, harder here). "
            f"The scene is dynamic (scripts/task_dynamics.toml: the ball is served with an initial velocity): "
            f"{rt['rally']}, so nothing can be steered call by call; the agent has to plan or stream the muscle "
            f"commands from a program, and learn the body and the serve from {RT_RESET_BUDGET + 1} real attempts.")
    ref = ("None in the repository. Solvability evidence: a successful episode of the privileged twin (82 rows, GPT-6 Luna "
           "xhigh) planned from step 0 through this service at S = 1 succeeded live and in the fresh replay, with no "
           "stall (board 0112, 2026-10-14)." if fam == "table_tennis" else f"None. Solvability evidence: {rt['evidence']}.")
    ver = ("The sim service (`environment/sim/rcb_realtime.py` + `rcb_service.py`, the shared eai-standard/2.3 layer, with "
           "`environment/sim/server.py`, MyoSuite's adapter) judges the episode live and records every control step it "
           "ran (`trajectory_live.f64`), after checking at the episode's start that the scene is the frozen instance "
           "(its recorded state hash; else `instance_mismatch`, an infrastructure failure); after the agent's time the "
           "collect hook stops the agent's programs and signals the service, which writes the live episode's verdict to "
           "`final.json` (`graded_by` = `live`; nothing is replayed to grade it) and then renders `replay.mp4` from the "
           "trajectory, which decides nothing; `tests/grade.py` (separate sandbox, no network) passes iff the live "
           "episode succeeded. The clock's record (`stalls`, `max_lag_s`, ...) is copied into `reward.json` "
           "and decides nothing. `nop`: the episode never starts (its clock starts at the first submit), reward 0.")
    details = [
        ("Upstream", "MyoSuite 2.12.2 (Apache-2.0) on MuJoCo 3.6.0, the models that ship in its wheel"),
        ("Slowdown", f"S = {S} (`RCB_SLOWDOWN`'s default): measured RTF {rt['rtf']} ({rt['measured']})"),
        ("Service", "the realtime layer of HumanoidBench, BiGym 2.0 and RoboOlympics (`rcb_realtime.py`, `rcb_service.py`, "
                    "unchanged) with `server.py`, which implements `rcb_service.Sim` on `rcb_myosuite.Session` (the "
                    "standard twin's scene, action and success rule); cameras " + ", ".join(f"`{c}`" for c in f["cameras"])
                    + " (640 x 480, EGL on the GPU)"),
        ("Resources", "4 CPUs and a GPU for rendering (the physics is on the CPU)"),
        ("Reset budget", f"{RT_RESET_BUDGET} (`RCB_RESET_BUDGET`, compose default; PROTOCOL §4b): `POST /reset` starts a new "
                         "episode from the frozen instance, paused; only the last episode is graded, a success ends the "
                         "trial; results under another budget or slowdown are reported separately"),
    ]
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
(`make_facts.py`) and `scripts/myosuite/shared/realtime/`; see `docs/benchmarks/myosuite.md`, "Standard-realtime".

### Change Log
- 2026-10-14 (owner, board 0112): added. The family's scene is dynamic (PROTOCOL §2.14), so it gets a standard-realtime
  twin with S = {S} and {RT_RESET_BUDGET} resets.
- 2026-10-17 (owner, boards 0150 and 0151): graded by the live episode; no grading replay. The service
  (`environment/sim/rcb_service.py`, the shared layer, and `environment/sim/server.py`, which no longer has a fresh-replay
  `verify()`) writes the live episode's verdict (`graded_by` = `live`, `replays` = 0) and renders `replay.mp4` from the
  trajectory after it; it checks at the episode's start that the scene hashes to the frozen instance's recorded state
  (`start_sha`; else `instance_mismatch`, an infrastructure failure). The collect hook waits 300 s for the verdict (was
  840 s, which a replay needed), the video until 870 s as before. `tests/grade.py`: success = the live success. The
  instruction says the episode is graded as it ran. The scene, the instance, the pass rule, the clock and the slowdown
  are unchanged, so the task keeps its name; a result graded before passed only if the live episode succeeded too.
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


def oracle_meta(fam: str, f: dict, std: bool) -> tuple[str, str]:
    """(oracle, oracle_evidence) for task.toml."""
    if "reference_rows" in f:
        return "full", ""
    if fam not in EVIDENCE:
        return "none", (f"no positive example yet ({NO_POSITIVE.get(fam, 'not attempted')}); the task is reported "
                        f"separately until one exists (PROTOCOL §7, Open 4); human review in PR #{REVIEW_PR}")
    who, trial, rows, through_client = EVIDENCE[fam]
    if not std:
        ev = (
            f"a successful model trial on this frozen instance: {who}, trial `{trial}` ({rows} rows); today's verifier "
            f"scores its trajectory 1 in two fresh trials (docs/benchmarks/myosuite.md); human review in PR #{REVIEW_PR}"
        )
    elif through_client is True:
        ev = (
            f"the privileged twin's positive example ({who}, trial `{trial}`, {rows} rows) rounded to float32, as the "
            f"client sends it, and streamed through the client: the service scores it 1 live and in both replays, in two "
            f"fresh trials (docs/benchmarks/myosuite.md); human review in PR #{REVIEW_PR}"
        )
    else:
        ev = (
            f"no positive example in standard mode yet: the privileged twin's ({who}, trial `{trial}`) fails once its "
            f"rows are rounded to the client's float32 ({through_client}); the family's solvability rests on the "
            f"privileged twin; human review in PR #{REVIEW_PR}"
        )
    return "none", ev


def priv_instruction(fam: str, f: dict) -> str:
    b = BODY[f["body"]]
    ms = round(f["dt"] * 1000, 1)
    ms = int(ms) if ms == int(ms) else ms
    cam = default_camera(fam, f)
    ref = ("\n\nThe reference motion (the goal) is MyoDex's `s.base.ref` and, per control step, the observation's "
           "`targ_obj_com` / `targ_obj_rot`; `curr_obj_com` / `curr_obj_rot` are the object's." if f["rule"] == "track" else "")
    return f"""# MyoSuite · {fam} — frozen instance

You control the **{b[0]}**, {b[2]} (MyoSuite 2.12.2 on MuJoCo), via Python, through its actuators — {f["n_muscles"]}
muscles{f" and {len(f['actuators'])} non-muscle actuators" if f["actuators"] else ""}: there is no joint-level controller.
**Task:** {f["goal"]}

{f["scene"]} `s.state()` gives the task's observation dict (privileged): {", ".join(f"`{k}`" for k in f["obs_keys"])}.
MyoSuite's reward code (from `/usr/local/lib/python3.11/site-packages/{f["reward_path"]}`; `solved` is the goal test,
`done` the failure test):
```python
{f["reward_src"]}
```
{rule_text(f)}{ref}

This is a *fixed scene instance*: the start pose, the objects and the goal never change between resets. You may reset and
retry as many times as you want. Your deliverable is **one replayable trajectory**, not a general policy.

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below). It is replayed
open-loop from the same initial state in two fresh processes and scored 1 if both episodes end in success in the same
state, else 0. Also leave the script that produced it at `/app/output/gen.py`.

Save a trajectory as soon as you have one that works, improve it while time remains, and do not stop early.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_myosuite import Session
s = Session("{fam}", instance="/app/instance.npz")   # a few seconds
s.reset()                          # back to the frozen initial state (unlimited; an exact snapshot restore)
s.state()                          # the task's observation dict (privileged; see above)
s.actuators(); s.muscles(); s.joints()   # {f["nu"]} actuators (kind, command); muscles; hinge/slide joints (qpos/dof address, range)
s.moment_arms()                    # ({f["nu"]}, nv) actuator moment arms at the current pose
s.model, s.data                    # MuJoCo model / data: read them freely; only the actions you record are replayed
s.excitation(a); s.command_for(u)  # muscle command a -> excitation u = 1/(1+exp(-5(a-0.5))) and its inverse
s.step(a)                          # one control step ({ms} ms): {f["nu"]} commands; False once the episode is over
s.rest_action()                    # every command at -1 (muscles relaxed)
s.status()                         # {{'success', 'done', 'reason', 'steps', 'resets', 'solved_run', 'rule', 'state_sha', 'info', ...}}
s.record_start(); ...; actions = s.record_stop()   # (T, {f["nu"]}) commands, one row per control step
s.replay(actions)                  # resets, replays open-loop until the episode ends, returns status -> self-check
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_frame("{cam}")            # RGB uint8 (480, 640, 3); cameras: {", ".join(f["cameras"])}
s.render_video(actions, "/app/output/check.mp4", cameras=["{cam}"])
```
There are no motion primitives: every skill is yours to build from actuator commands.

CLI equivalent of the grader:
`python /opt/tools/rcb_myosuite.py replay --instance /app/instance.npz --traj /app/output/trajectory.npz --repeat 2`

## Conventions
- Action: {actuation(f)}
- Control step {ms} ms ({f["frame_skip"]} physics substeps). There is no step budget: your wall-clock time is the limit
  (~{f["steps_per_s"]} control steps/s here). An episode ends at success or failure; `s.step` then refuses further
  actions until `s.reset()`.
"""


def std_instruction(fam: str, f: dict) -> str:
    b = BODY[f["body"]]
    hz = round(1 / f["dt"])
    atype = "muscle" if not f["actuators"] else "actuators"
    end = {"hold": f"on success (the goal held {f['hold_steps']} control steps, {f['hold_s']} s), on the task's failure",
           "event": "on success (the challenge's own success event), on its failure conditions or its own time limit",
           "track": f"after {f['track_steps']} control steps (the reference motion; then it is judged), early at MyoDex's "
                    "termination"}[f["rule"]]
    root = (" and the pose and velocity of your free-standing root (the pelvis: `root_pose`, `root_vel`)"
            if f["free_root"] else "")
    kin = ("`/kinematics` gives the fingertip sites and the camera mounts for any joint positions."
           if any(c.startswith("hand_") for c in f["cameras"]) else "`/kinematics` gives the camera mounts for any joint positions.")
    refline = ("\n- The goal is a reference motion: `spec[\"reference_motion\"]` gives, per control step, the object's "
               "centre of mass relative to where it starts and its orientation." if f["rule"] == "track" else "")
    return f"""# MyoSuite · {fam} — STANDARD MODE (robot as a service, eai-standard/2.2)

You control the **{b[0]}**, {b[2]}, **as if it were real**: the simulator (MyoSuite 2.12.2 on MuJoCo) runs in a service
you cannot open. You get one client and up to {RESET_BUDGET + 1} episodes, and you act only through its actuators ({f["n_muscles"]} muscles{
f" and {len(f['actuators'])} other actuators" if f["actuators"] else ""}).
**Task:** {f["goal"]}

{f["scene"]}

## Rules
- **Episodes and resets.** The episode starts when the service comes up and ends {end}, when your time is up, or on
  a simulator error. You have **{RESET_BUDGET} resets** (`spec["budget"]["reset"]`, which is authoritative: if it says
  0, there is no reset and the one episode is the run). A reset (`POST /reset`, below) puts the body and the scene back
  on the same frozen starting state and starts a new episode, either abandoning the running one or after one has ended;
  it takes no simulated time and returns the start's images and proprioception. Once an episode has ended, `submit`
  raises `EpisodeOver` until you reset. **Only the last episode is graded**: an episode you reset away is never graded,
  a success ends the run at once (no reset after it), and when your time is up the episode then running is the one
  graded. The wall clock is the run's and never restarts; `meta["episode"]` and `meta["resets_left"]` count the
  episodes (`meta["control_steps"]` is the current episode's).
- **No privileged state.** You see what the cameras see (RGB, and depth on request, with each camera's calibration) and
  the body's own proprioception: joint positions, velocities and actuator torques, muscle activations and lengths{root}.
  No object, ball, opponent or goal poses, no success check: `meta["done"]` / `meta["reason"]` tell you when the episode
  is over and why.{refline}
- Steps are unlimited; your only budget is the time limit (`## Time limit`; `meta["time_left_s"]` is the service's count of it).
  Simulated time only advances with your commands (and `get_obs(seconds=...)`, which holds the last command). Do not stop early: while
  the episode runs, or a reset is left, the run can still pass.
- Nothing to hand in: the service records your episode and grades it. Leave your script at `/app/output/gen.py`.
- **If the service crashes**, a call fails with a connection error: it restarts and resumes the SAME episode (never a
  reset) in the state after the last call it completed. `r.wait_ready()` waits for it; then check `r.status()`.
- **Nothing is put into your context automatically.** Images and videos come back as arrays/bytes in a Python object.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`)
```python
from rcb_client import Robot
r = Robot()                                    # connects (waits while the service starts)
spec = r.spec()                                # actuators, joints, cameras (+ intrinsics, mounting), proprio layout, kinematics, budget
obs = r.get_obs()                              # obs.last[cam] -> uint8 (480, 640, 3) (default camera: {default_camera(fam, f)})
obs = r.get_obs(cameras=["{f["cameras"][0]}"], depth=True)   # + obs.last_depth[cam] -> float32 (480, 640), metres
obs.meta["proprio"]                            # {{"layout": [...], "now": [...]}}: q_*, qd_*, act_*, len_*, effort_*{", root_*" if f["free_root"] else ""}
obs.meta["cameras"]                            # per camera intrinsic_cv / extrinsic_cv / cam2world_gl at the last frame
res = r.submit("{atype}", rows, dt={f["dt"]:g})          # rows: (T, {f["nu"]}) commands, one row per control step
res.meta["done"], res.meta["reason"], res.meta["control_steps_chunk"]; res.video[cam]; res.last[cam]; res.proprio
obs = r.get_obs(seconds=1.0, video="mp4")      # hold the last command and watch for 1 s (max 30)
r.fk(q)                                        # forward kinematics of the listed links (no physics)
r.status()                                     # calls, control steps, done, reason, elapsed time, episode, resets_left
obs = r._post("/reset", {{"cameras": ["{f["cameras"][0]}"]}}, [], 900)   # POST /reset: a new episode (the 2.2 client has no reset())
```
Cameras: {cameras_text(fam, f)}. Rendering is on the CPU: ask only for the cameras you need; `video="none"` makes a
chunk fastest. One call returns at most {MAX_FRAMES} images (cameras x frames at `video_fps`, default 10, at most {hz}; depth
for every frame counts again; `spec["max_frames_per_call"]`): a larger request is refused with a 400 before anything
runs, so ask for fewer cameras, a lower `video_fps` or a shorter call. Proprioception (`spec["proprio_groups"]`): `joint_pos` (`q_<joint>`), `joint_vel` (`qd_<joint>`),
`muscle_activation` (`act_<muscle>`), `muscle_length` (`len_<muscle>`, m), `joint_effort` (`effort_<joint>`, the
actuators' generalized force on each joint){", `root_pose`, `root_vel`" if f["free_root"] else ""}. {kin}

### Action type `{atype}` ({f["nu"]})
{actuation(f)} Columns in `spec["action_types"]["{atype}"]["layout"]` order. Rows are `dt` apart (a whole multiple of the
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
  { source = "/data/video.log", service = "sim" },             # the collect hook's render pass, which draws replay.mp4
  "/app/output/",
]"""
        desc = (
            f"STANDARD MODE (robot as a service, eai-standard/2.2): MyoSuite {fam} ({b[0]}, {f['n_muscles']} muscles) on the "
            f"same frozen instance as myosuite-{dash(fam)}-i00-privileged: {first}. The agent only gets a client: "
            "cameras (RGB, optional depth, calibration), the body's joints and muscles, actuator command chunks, "
            f"fingertip kinematics; {RESET_BUDGET} resets, only the last episode graded; no object state; the sim service "
            "records the episode and grades it as it ran (the live episode; nothing is replayed)."
        )
    else:
        head = 'artifacts = ["/app/output/"]'
        desc = (
            f"MyoSuite {fam} ({b[0]}, {f['n_muscles']} muscles, MuJoCo): produce one replayable trajectory of actuator commands. "
            f"{first}. Frozen scene instance ({f['env_id']}, reset seed 0); graded by two fresh-process replays."
        )
    meta_extra = 'protocol = "eai-standard/2.2"\n' if std else ""
    oracle_lines = f'oracle = "{oracle}"\n' + (f"oracle_evidence = {toml_str(ev)}\n" if ev else "")
    verifier = (
        f"""[verifier]
timeout_sec = 600.0
environment_mode = "separate"
network_mode = "no-network"

# The agent's time is up: stop whatever it left running in its container. Harbor stops that container only after
# collecting from it (~12 s), and a script still running there would keep driving the robot past the deadline.
[[verifier.collect]]
service = "main"
command = "kill -9 -1 2>/dev/null; exit 0"
timeout_sec = 30

[[verifier.collect]]
service = "sim"
command = "sh /srv/finalize.sh"   # end + dump + exit the service, write the live verdict to final.json, then the video
timeout_sec = {COLLECT_TIMEOUT}                # the video's one render pass gets what is left (finalize.sh: RCB_COLLECT_BUDGET_S)
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
timeout_sec = {CUTOFF["standard" if std else "privileged"]}.0
# The agent reaches the model APIs and the package registries, nothing else (scripts/set_agent_egress.py HOSTS). MyoSuite's
# trained baselines ship in its PyPI wheel (and a standard-mode agent could rebuild the simulator from it): reachable
# since 2026-10-11, left to the instruction's honour rule (PROTOCOL §2.11).
network_mode = "allowlist"
allowed_hosts = [{", ".join(toml_str(h) for h in HOSTS)}]

[environment]
build_timeout_sec = 1800.0
cpus = 4
memory_mb = 8192
"""


CHANGE_LOG_HEAD = """
### Change Log
"""
CHASE_TAG_TEXT = (
    "- 2026-10-10 (board 0067, R2): the scene text said \"an opponent moves in it\"; in this frozen instance the opponent's\n"
    "  policy is `stationary` (MyoChallenge draws it once), so the text now says that it stands still. Only the text\n"
    "  changed: the instance, the tooling and the pass rule are the same.\n"
)


R3_STD = f"""\
- 2026-10-10 (review round 3, board 0067): the shared service layer and the client only
  (`environment/sim/rcb_limited.py`, `environment/rcb_client.py`). A camera named more than once in `cameras` is
  rendered and returned once (N copies of one name made the service build N x N images within the frame budget, which
  could exhaust its memory). A service that has given up on the episode (it could not start it, or could not resume it
  after its crashes) answers every request with 409 and the reason, and `Robot()` / `wait_ready()` raise `EpisodeOver`
  at once; before, nothing answered and they waited out their timeout (up to an hour). `environment/sim/server.py`
  waits for a port that is still held when it restarts (`rcb_limited.bind`) instead of exiting. The collect hook, the
  grader, the scene and the pass rule are unchanged.
- 2026-10-10 (review round 3, board 0067): `environment/sim/server.py` bounds the images of one call: at most
  {MAX_FRAMES} (cameras x frames, per-frame depth counted again; `/spec` `max_frames_per_call`, stated in the instruction);
  a larger request is a 400 and nothing runs. Before, a call had no bound, and one request within the documented
  ranges (a 30 s watch at the control rate, or several cameras with per-frame depth) could exhaust the sidecar's memory:
  the service was killed, and a trial that then failed was recorded as an infrastructure failure
  (`resource_service_oom`), not as a result. The default camera at the default 10 fps fits every chunk and watch
  (302 images at most). The scene, instance and pass rule are unchanged, so the task keeps its name.
- 2026-10-13 (owner, boards 0085 and 0087): the sim service's clock (`environment/sim/rcb_limited.py`,
  `environment/sim/server.py`, the docstring of `environment/rcb_client.py`). `meta["time_s"]` and
  `meta["time_left_s"]` count from the agent's first request to the service (any endpoint), and a restarted service
  keeps that moment; before, they counted from the service's own start of the episode (when its scene was ready).
  Where the service is ready before the agent's phase begins (the harness is installed in between: a median of 79 s
  over the recorded standard trials), that clock ran ahead of the agent's and `time_left_s` reached 0 while the agent
  still had that time. `/spec` says what the clock counts from (`budget.clock`), and the instruction's `## Time limit`
  tells the agent to plan by `time_left_s`. The service never ended an episode on this clock: the scene, the frozen
  instance, the pass rule and the grader are unchanged, so the task keeps its name and earlier results stand.
- 2026-10-17 (owner, boards 0150 and 0151): graded by the live episode; no grading replay. `environment/sim/finalize.sh`
  writes the live episode's verdict (the task's rule as the service applied it to the steps it ran, its hold or track
  window included; `graded_by` = `live`, `replays` = 0) and no longer replays the trajectory in two fresh processes;
  `replay.mp4` is rendered after the verdict by one pass over the trajectory (`environment/sim/video.py`), which
  decides nothing. `environment/sim/server.py` checks at the episode's start that the scene hashes to the frozen
  instance's recorded state (else `instance_mismatch`, an infrastructure failure, before the agent is served; before,
  the replays checked it). `tests/grade.py`: success = the live success; `reward.json` drops `replay_success`,
  `deterministic` and `live_matches_replay` and adds `graded_by_live`, `replays`. A collect hook on `main`
  (`kill -9 -1`) stops whatever the agent left running before the service ends the episode. The scene, the instance,
  the pass rule and everything the agent sees are unchanged, so the task keeps its name; a result graded before passed
  only if the live episode succeeded too.
"""
R3_PRIV = """\
- 2026-10-10 (review round 3, board 0067): `tests/grade.py` only. A byte that is not valid UTF-8 in the session log
  the agent's tools write (`/app/output/rcb_session_log.jsonl`, read only for the self-reported `agent_*` cost fields)
  stopped the grader before it wrote a reward, so the trial had no verdict; the log is now read tolerantly and can no
  longer decide anything. A trial whose log is valid is graded as before; the pass rule is unchanged.
- 2026-10-10 (review round 3, board 0067): `tests/grade.py`, whose failure a 0 is. The width of the rows is checked
  against the instance's actuators before any replay (a file that is no trajectory for this instance is
  `bad_trajectory`, as before). After that check a replay process that gives no result (out of time, killed for
  memory, not started) is `replay_failed` with `grader_error = 1` and `infra_error = 1`; it was booked as the agent's
  `bad_trajectory`. Every `reward.json` now carries `infra_error` (1 next to every `grader_error`, so also when the
  verifier's host does not rebuild the frozen instance). The pass rule is unchanged; a trial graded `bad_trajectory`
  before this date whose rows had the right shape was an infrastructure failure.
"""


OSL_SIDE_TEXT = (
    "- 2026-10-14 (board 0113, from board 0086): the texts said that the prosthesis is the left leg; MyoSuite's model\n"
    "  puts the Open-Source Leg on the right (its joints are `osl_knee_angle_r` and `osl_ankle_angle_r`, under `femur_r`),\n"
    "  and the texts now say so. Text only: the instance, the tooling and the pass rule are the same.\n"
)
BAODING_END_TEXT = (
    "- 2026-10-14 (board 0113, from board 0086): an episode that has not succeeded after 1000 control steps (25 s) ends\n"
    "  there as a failure, and the task text says so. MyoSuite's baoding targets are a precomputed trajectory of 1000\n"
    "  points; with MyoSuite's step budget lifted, the step after it raised an IndexError (the service answered 500 and\n"
    "  the episode ended as a simulator error; a privileged replay that long stopped with an error). Nothing before that\n"
    "  step changes: the instance, the tooling's physics and the pass rule are the same, and every verdict reached before\n"
    "  is the same now.\n"
)


def change_log(fam: str, f: dict, std: bool) -> str:
    """The README's Change Log: the standard service's history, plus what changed for this family alone."""
    out = CHANGE_LOG if std else ""
    scene = f.get("scene_cameras") or []
    if std:
        names = " and ".join(f"`{c}`" for c in scene)
        out += (
            "- 2026-10-10 (board 0067, R2): the service no longer publishes the pose of a camera that rides on a body of the\n"
            "  scene that is not the agent's own (decided from the model: the camera's body is a mocap body or sits behind a\n"
            "  joint that is not the body's). "
            + (f"Here that is {names}: it still gives images and depth, but no mount, no\n"
               "  `extrinsic_cv` / `cam2world_gl` (null in `meta[\"cameras\"]`, NaN per frame), and its body is no longer a\n"
               "  `/kinematics` link. Before, its pose was that body's position plus a constant, which standard mode must not\n"
               "  give (PROTOCOL §4.5); runs recorded before this date could read it and are reported with that note. The\n"
               "  scene, instance and pass rule are unchanged, so the task keeps its name.\n" if scene else
               "This family has no such camera: nothing a run sees changes.\n")
            + "  The client (`environment/rcb_client.py`): `Robot()` waits up to 3600 s for the service (was 600 s; no effect\n"
            "  here, the service is up in seconds) and prints its progress, and `cameras=\"name\"` (a string) is one camera,\n"
            "  no longer its characters.\n"
        )
    if fam == "chase_tag":
        out += CHASE_TAG_TEXT
    out += R3_STD if std else R3_PRIV
    out += {"osl_run": OSL_SIDE_TEXT, "baoding": BAODING_END_TEXT}.get(fam, "")
    if out and not std:
        out = CHANGE_LOG_HEAD + out
    return out


CHANGE_LOG = CHANGE_LOG_HEAD + f"""\
- 2026-10-09: the standard service's `effort_<joint>` proprioception (`joint_effort`) reads the force the physics
  applied (MyoSuite's robot data), not the mirror's zero-command force; and `RCB_RESET_BUDGET`'s default 0 ->
  {RESET_BUDGET} (owner decision; PROTOCOL §4.5, docs/benchmarks/myosuite.md), with `POST /reset` in the service. The
  scene, instance and pass rule are unchanged, so the task keeps its name; runs recorded before this date saw the wrong
  efforts and had no reset, and are reported separately.
- 2026-10-10: a malformed request field (a null or non-numeric `dt` / `seconds`, `cameras` that is not a list of names,
  a `note` that is not text) is answered with 400 before anything runs; before, it was a 500 that ended the episode
  (for `note`, after the chunk had run). `tests/grade.py` books a missing, unreadable or never-finalized `final.json`
  as `infra_error = 1` instead of the agent's 0, and `finalize.sh` writes `final.json` atomically. The scene, instance
  and pass rule are unchanged, so the task keeps its name; every verdict that was reached before is the same now.
"""


def readme(fam: str, f: dict, std: bool) -> str:
    b = BODY[f["body"]]
    name = f"myosuite-{dash(fam)}-i00-{'standard' if std else 'privileged'}"
    twin = f"myosuite-{dash(fam)}-i00-{'privileged' if std else 'standard'}"
    oracle, ev = oracle_meta(fam, f, std)
    if std:
        task = (
            f"MyoSuite `{f['env_id']}` ({b[0]}, {f['n_muscles']} muscles) on the same frozen instance as `{twin}`: "
            f"{f['goal']}\n{f['scene']} Standard mode (eai-standard/2.2): the agent drives the body through a client, with "
            f"only its own proprioception and the scene's cameras, and {RESET_BUDGET} resets (only the last episode is graded)."
        )
        diff = (
            f"Same instance and success rule as `{twin}` (first-pass rating: {f['difficulty']}). In standard mode the "
            "agent loses free resets, the simulator and the object state: it sees camera images and the limb's "
            f"proprioception, acts in actuator-command chunks, and gets {RESET_BUDGET} resets, so it has to close the loop on "
            "what it sees and learn the body from a few real attempts."
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
            "The sim service judges the episode live (the task's rule on the steps it ran: "
            + {"hold": f"the goal held {f['hold_steps']} control steps", "event": "the challenge's own success event",
               "track": f"on track over the {f['track_steps']}-step reference"}[f["rule"]]
            + ") and records every executed control step; it checks at the episode's start that the scene is the "
            "frozen instance (its recorded state hash; else `instance_mismatch`, an infrastructure failure). The "
            "collect hook (`environment/sim/finalize.sh`) ends the service and writes that live verdict to "
            "`final.json` (`graded_by` = `live`; nothing is replayed to grade it), then renders `replay.mp4` in one "
            "pass over the recorded trajectory, which decides nothing; `tests/grade.py` (separate sandbox, no network) "
            "passes iff the live episode succeeded. A missing or unreadable `final.json`, one without a verdict, or a "
            "give-up after crashes not all inside the agent's calls is an infrastructure failure (`infra_error = 1`), "
            "not the agent's 0. "
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
                "(`scripts/eai_standard/`); cameras " + ", ".join(f"`{c}`" for c in f["cameras"]) + " (640 x 480); "
                "forward kinematics of the body's links",
            ),
            ("Resources", "4 CPUs, no GPU (CPU physics, OSMesa rendering); after the agent's phase the collect hook "
             "only renders the video (one pass over the graded episode), it replays nothing to grade"),
            ("Reset budget", f"{RESET_BUDGET} (`RCB_RESET_BUDGET`, compose default; PROTOCOL §4.5): `POST /reset` starts a new "
             "episode from the frozen instance; only the last episode is graded, a success ends the trial; results under "
             "another budget are reported separately"),
        ]
    else:
        task = (
            f"MyoSuite `{f['env_id']}` ({b[0]}, {b[2]}, {f['n_muscles']} muscles"
            + (f" and {len(f['actuators'])} other actuators" if f["actuators"] else "") + f"): {f['goal']}\n{f['scene']} "
            f"The deliverable is one replayable trajectory of actuator commands (`/app/output/trajectory.npz`, "
            f"`(T, {f['nu']})`, one row per {round(f['dt'] * 1000, 1):g} ms control step)."
        )
        diff = (
            f"First-pass rating: {f['difficulty']}. The action is muscle-level ({f['n_muscles']} muscles, each only "
            "pulling, several crossing more than one joint, with activation delays): the agent has to build its own "
            "joint control from muscle excitations. " + RULE_DIFF[f["rule"]].format(**f)
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
            "is checked against its recorded hash); pass iff both episodes end in success ("
            + {"hold": f"the goal held {f['hold_steps']} control steps", "event": "the challenge's own success event",
               "track": f"on track over the {f['track_steps']}-step reference"}[f["rule"]]
            + ") in the same state (`deterministic`). "
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
                f"{f['nu']} actuator commands per control step ({round(f['dt'] * 1000, 1):g} ms, "
                f"{f['frame_skip']} physics substeps); success rule `{f['rule']}` (docs/benchmarks/myosuite.md)",
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
{change_log(fam, f, std)}"""


def make(fam: str, out: Path) -> tuple[Path, ...]:
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
    put(s / "environment/sim/video.py", src=SHARED / "standard/video.py")
    put(s / "environment/sim/rcb_myosuite.py", src=SHARED / "rcb_myosuite.py")
    put(s / "environment/sim/instance.npz", src=inst)
    put(s / "environment/sim/task.json", json.dumps({"task_text": f["goal"], "default_cameras": [default_camera(fam, f)],
                                                       "reference": f.get("reference")}, indent=1) + "\n")
    put(s / "tests/Dockerfile", STD_TESTS_DOCKERFILE)
    put(s / "tests/test.sh", src=SHARED / "standard/test.sh", mode=0o755)
    put(s / "tests/grade.py", src=SHARED / "standard/grade.py")
    if full:
        put(s / "solution/solve.sh", src=SHARED / "standard/solve.sh", mode=0o755)
        put(s / "solution/oracle_stream.py", src=SHARED / "standard/oracle_stream.py")
        put(s / "solution/oracle.npy", src=oracle)
    normalize(p)
    normalize(s)
    if fam not in REALTIME:
        return p, s

    r = out / f"myosuite-{dash(fam)}-i00-standard-realtime"
    reset_dir(r)
    put(r / "task.toml", rt_task_toml(fam, f))
    put(r / "instruction.md", rt_instruction(fam, f))
    put(r / "README.md", rt_readme(fam, f))
    put(r / "environment/Dockerfile", RT_ENV_DOCKERFILE)
    put(r / "environment/docker-compose.yaml", rt_compose(fam))
    put(
        r / "environment/client-requirements.txt",
        src=LAYER / _ENV.get("CLIENT_REQUIREMENTS", "client-requirements.txt").strip(),
    )
    put(r / "environment/rcb_client.py", src=RT / "rcb_client.py")
    put(r / "environment/rcb1.py", src=LAYER / "rcb1.py")
    for name in ("rcb_realtime.py", "rcb_service.py", "server.py"):
        put(r / "environment/sim" / name, src=RT / name)
    put(r / "environment/sim/rcb1.py", src=LAYER / "rcb1.py")
    put(r / "environment/sim/rcb_myosuite.py", src=SHARED / "rcb_myosuite.py")
    put(r / "environment/sim/instance.npz", src=inst)
    put(r / "environment/sim/task.json", json.dumps({"task_text": f["goal"], "default_cameras": [default_camera(fam, f)],
                                                       "reference": f.get("reference")}, indent=1) + "\n")
    put(r / "tests/Dockerfile", STD_TESTS_DOCKERFILE)
    put(r / "tests/test.sh", src=SHARED / "standard/test.sh", mode=0o755)
    put(r / "tests/grade.py", src=RT / "grade.py")
    normalize(r)
    return p, s, r


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
