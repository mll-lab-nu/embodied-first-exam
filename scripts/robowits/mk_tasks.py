#!/usr/bin/env python3
"""Render the RoboWits tasks: per family the privileged task tasks/robowits-<family>-i00 and its standard twin
tasks/robowits-<family>-i00-standard (eai-standard/2.2), on the same frozen instance (docs/benchmarks/robowits.md).

usage: python3 scripts/robowits/mk_tasks.py [--check] [--list] [--instance PATH] [family ...]
  no family     every family whose status is "pr" in families.py
  --check       write nothing; exit 1 if a task would change (re-running the generator must give no diff)
  --list        print the family table (status, oracle, why a family was dropped)
  --instance    the frozen instance of a family that has no task directory yet (one family only), e.g.
                tasks/robowits-<family>-i00/environment/instance.json from dev/qineng 9eb18edf. A new family's
                instance is made in the image:
                  docker run --rm --gpus all -v $PWD:/w <IMAGE> bash -c "cd /tmp && python /w/scripts/robowits/shared/rcb_robowits.py \\
                    make-instance --task <family> --eval-index <i> --out /w/<dir>/instance.json"
                (register the family in shared/rcb_robowits.py TASKS first). Then add the family to families.py, vendor its
                predicate (--extract-predicate), write its criterion, render, and run oracle / nop and `harbor add --scan`.
  --extract-predicate FAMILY --src DIR
                copy `_check_success` of the family's RoboWits file (DIR = gs_gym/envs/robowits of RoboWits @ 9cc30ae, e.g.
                copied out of the image) to predicates/<NN>_<family>.py and print its sha for families.py

Inputs, all in the repository: shared/ (the RoboWits tooling rcb_robowits.py, the sim adapter server.py, the graders, the
standard oracle player: copied unchanged into every task, D9), scripts/eai_standard/ (the 2.2 layer, copied unchanged),
families.py (texts, flags, criteria), predicates/ (RoboWits' `_check_success`, verbatim, for the privileged
instruction), oracles/<family>/ (reference solutions: the privileged oracle script, the standard oracle's joint
rows). The frozen instance is the one input kept in the task itself: environment/instance.json of the privileged task
(the generator copies it to tests/ and to the standard twin's environment/sim/). A task has no results/ (PROTOCOL D3:
results are published on the results site), and every rendered task passes through scripts/task_conventions.normalize().
Needs only the Python standard library."""
from __future__ import annotations
import argparse, ast, hashlib, json, os, pathlib, re, stat, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import families as FM  # noqa: E402
sys.path.insert(0, str(ROOT / "scripts"))
import task_conventions as TC  # noqa: E402  the protocol's conventions: every generator ends with normalize(task_dir)

TASKS = ROOT / "tasks"
SHARED = HERE / "shared"
LAYER = ROOT / "scripts" / "eai_standard"
IMAGE = f"ghcr.io/mll-lab-nu/eai-robowits:{(ROOT / 'images/robowits/VERSION').read_text().strip()}"
# the one client base of every standard agent container and verifier, pinned by digest, and its pip pins (PROTOCOL §2.4):
# scripts/eai_standard/client.env and the file it names (checked by ci_checks/check-standard-client.sh)
CLIENT_ENV = dict(l.split("=", 1) for l in (LAYER / "client.env").read_text().splitlines() if "=" in l and not l.startswith("#"))
CLIENT_IMAGE = CLIENT_ENV["CLIENT_IMAGE"].strip()
CLIENT_REQUIREMENTS = CLIENT_ENV.get("CLIENT_REQUIREMENTS", "client-requirements.txt").strip()
PROTOCOL = "eai-standard/2.2"
BUDGET_S = 5400          # docs/benchmarks/robowits.md, Time budget (D8)
REVIEW = "PR #3"         # where the human review of the no-oracle families is recorded (PROTOCOL §2.7)
BK_VOLUME = ("${RCB_ROBOWITS_BLENDERKIT:?set RCB_ROBOWITS_BLENDERKIT to your BlenderKit model folder (images/robowits/NOTICE)}"
             ":/opt/robowits/assets/blender_kit:ro")
BK_NOTE = ("# The BlenderKit models this task loads may not be redistributed, so they are not in the image: they come read-only\n"
           "# from the host's folder $RCB_ROBOWITS_BLENDERKIT (images/robowits/NOTICE).\n")
EXEC = 0o755
FILE = 0o644
# The tooling's technical cap of one episode / trajectory (rcb_robowits.MAX_STEPS: Session's runaway guard, the standard
# service's `step_guard` end and /spec max_control_steps, the longest trajectory the privileged grader accepts). Read from
# the source, which this generator cannot import (numpy), so that the instructions always state the value that is enforced.
MAX_STEPS = int(re.search(r"^MAX_STEPS = ([\d_]+)", (SHARED / "rcb_robowits.py").read_text(), re.M).group(1).replace("_", ""))
MAX_STEPS_H = f"{MAX_STEPS / 30 / 3600:.2f}"       # hours of simulated time at the 30 Hz control rate
# Fixes to the published tasks (PROTOCOL §2.8): one README Change Log entry per mode, newest last.
CHANGE_LOG = {
    "priv": [
        "2026-10-10 (review of board 0067; findings RW-1, RW-5, RW-6, RW-7): the verifier reports an infrastructure error "
        "(`infra_error = 1`) instead of the agent's 0 when it cannot build the frozen scene or the scene it rebuilt does not match "
        "the frozen instance on its host (`instance_ok = 0`: another CPU vendor, docs/benchmarks/robowits.md, Hosts); a "
        "`trajectory.npz` that cannot be read or lacks `task` / `actions` is `bad_trajectory`, no longer `grader_error`; "
        "`reward.json` always carries `infra_error`; the verifier runs without network (`network_mode = \"no-network\"`); the "
        f"instruction states the tooling's cap of {MAX_STEPS} control steps per trajectory instead of leaving it unsaid. The "
        "pass rule, the frozen instance, the tooling and the predicate are unchanged; validated with synthetic tests of the "
        "grader, not re-run in the simulator.",
        "2026-10-10 (review round 2, board 0067; minor 2): `tests/grade.py` time-boxes the replay video, which it renders after "
        "the verdict is on disk: it is skipped or stopped (`video_timed_out = 1`) 180 s before the verifier's `timeout_sec` "
        "(`tests/test.sh` passes it as `--budget`). Before, the video replay of a very long trajectory could run into "
        "Harbor's verifier timeout, which discards the verdict already written. The verdict, the pass rule, the frozen "
        "instance and the tooling are unchanged; validated with a synthetic test of the grader, not re-run in the simulator.",
    ],
    "std": [
        "2026-10-10 (review of board 0067; findings RW-1, RW-2, RW-3, RW-4, RW-7, RW-8): the service checks every request "
        "field before it executes anything and answers 400 (before: a null or mistyped `dt` / `seconds` / `video_fps`, a "
        "`video_fps` outside 1..30 or a non-string `note` ended the episode with a 500, some of them after the chunk had run); "
        "a `joint_position` `dt` that is not a whole number of 1/30 s periods is answered 400 (before: rounded silently); `ee_pose` "
        "gripper widths outside the limits are listed in `meta[\"clipped\"]`; a frozen instance that the host cannot rebuild "
        "(reason `instance_mismatch`) and a grading replay that fails after a normal episode end as `infra_error = 1` with a "
        "complete record, at once and without waiting out the collect hook; a service that died while rendering the video keeps "
        f"its verdict; `/spec` (`max_control_steps`) and the instruction state the cap of {MAX_STEPS} control steps per "
        "episode; `reward.json` adds `sim_error`, `instance_mismatch`, `instance_exact`. The pass rule, the frozen instance, "
        "the tooling and the predicate are unchanged; validated with synthetic tests of the service and the grader, not "
        "re-run in the simulator.",
        '2026-10-10 (review round 2, board 0067): the client only (`environment/rcb_client.py`). `Robot()` waits up to '
        '3600 s for the service (was 600 s) and prints its progress to stderr once a minute, so the first `Robot()` '
        "outlasts the simulator's start (no effect on a scene that builds in about a minute); "
        '`cameras="name"` (a string) is one camera, no longer its characters. The '
        'service, the collect hook, the grader, the scene and the pass rule are unchanged.',
    ],
}


def slug(fam: str) -> str:
    """The family's base name; the task directories are <base>-privileged and <base>-standard (PROTOCOL §2.2)."""
    return f"robowits-{fam.replace('_', '-')}-i00"


def priv_dir(fam: str) -> str:
    return slug(fam) + "-privileged"


def std_dir(fam: str) -> str:
    return slug(fam) + "-standard"


def num(f: dict) -> str:
    return f["rid"].split("-", 1)[0]


def predicate_file(fam: str, f: dict) -> pathlib.Path:
    return HERE / "predicates" / f"{num(f)}_{fam}.py"


def startup_timeout(f: dict) -> int:
    """RCB_STARTUP_TIMEOUT_S: at least twice the slowest measured scene build, never below the 900 s default."""
    return int(f.get("startup_timeout_s") or max(900, 2 * max(f.get("build_s") or [0])))


def wrap(text: str, width: int = 118, first: str = "", rest: str = "") -> str:
    """Greedy word wrap at `width` columns (the instructions' style); explicit line breaks are kept. `first` prefixes the
    first line, `rest` every continuation line."""
    NB = "\u00a0"                     # numbers keep their unit, and "z = 0.76" stays on one line
    text = re.sub(r"(\d) (m|cm|mm|m/s|cm/s|mm/s|%|deg|degrees)(?=[\s.,;:)]|$)", rf"\1{NB}\2", text)
    text = re.sub(r"\b([xyz]) = (-?\d)", rf"\1{NB}={NB}\2", text)
    out, prefix = [], first
    for para in text.split("\n"):
        line, empty = prefix, True
        for w in para.split(" "):
            if not empty and len(line) + 1 + len(w) > width:
                out.append(line); line = rest + w
            else:
                line = line + w if empty else line + " " + w
            empty = False
        out.append(line); prefix = rest
    return "\n".join(out).replace(NB, " ")


def bullets(items: list[str], width: int = 118) -> str:
    """'- ' bullets; an item that starts with two spaces is a sub-bullet of the previous one."""
    return "\n".join(wrap(it.strip(), width, first="  - ", rest="    ") if it.startswith("  ") else wrap(it, width, first="- ", rest="  ")
                     for it in items)


def per_mode(v, mode: str) -> str:
    return v[mode] if isinstance(v, dict) else v


# ---------------------------------------------------------------------------------------------------------- texts
CRITERION_TERMS = {
    "priv": ("Terms: a *footprint* is an object's outline seen from above (the 2D convex hull of its collision mesh in the x-y "
             "plane); *not held* means that neither gripper tip (`Gripper_Tip_R` / `Gripper_Tip_L`, the frames of `s.ee_pose`) is "
             "inside the object's axis-aligned bounding box grown by 3 cm on every side; the *table bounds* are the rectangle "
             "x 0.21-1.00 m, |y| <= 0.69 m on the table top (z = 0.76 m)."),
    "std": ("Terms: a *footprint* is an object's outline seen from above; *not held* means that neither gripper tip (the "
            "`tcp_pose` points of your proprioception) is inside the object's bounding box grown by 3 cm on every side; the "
            "*table bounds* are a fixed rectangle slightly inside the edges of the table top (its corners are world positions, "
            "which this mode does not give: keeping clear of the table's edges satisfies it)."),
}
CRITERION_LEAD = {
    "priv": ("This is exactly what the grader checks, written from the predicate above (RoboWits' `_check_success`, which the "
             "grader runs). Where the task text says something else, this section and the predicate are what count. It is "
             "evaluated once per replay, on the state right after the last action of your trajectory (no settle steps are "
             "added: let things come to rest inside the trajectory), and must hold after both replays."),
    "std": ("This is exactly what the grader checks (RoboWits' success predicate, stated in words). Where the task text says "
            "something else, this section is what counts. The service evaluates it after every `submit` and after every "
            "`get_obs` that watches (`seconds` > 0), and once more when the episode ends; the first time it holds, the episode "
            "ends as a success. The service then replays your recorded episode, which must end in the same state and satisfy "
            "it again."),
}


def criterion_section(fam: str, f: dict, mode: str) -> str:
    c = f["criterion"]
    text = f["std_goal"] if mode == "std" and f.get("std_goal") else f_text(fam)
    first = re.match(r"(.+?[.!?])(\s|$)", text)                  # the task text's first sentence (dominos adds a scene description)
    quoted = json.dumps(first.group(1) if first else text, ensure_ascii=False)
    return (f"## Success criterion (as graded)\n{wrap(CRITERION_LEAD[mode])}\n\n"
            f"{bullets(c[mode])}\n\n"
            f"{wrap('Not checked: ' + per_mode(c['unchecked'], mode) + '.')}\n\n"
            f"{wrap('Task text vs grader (' + quoted + '): ' + per_mode(c['text_vs_code'], mode))}\n\n"
            f"{wrap(CRITERION_TERMS[mode])}\n")


def f_text(fam: str) -> str:
    return INSTANCES[fam]["text"]


PRIV_INSTRUCTION = """# RoboWits · @FAM@ — frozen instance

@INTRO@

@NOTE@The scene objects are the env's entities (`s.objects()`: @OBJECTS@; see
`/opt/robowits/gs_gym/envs/robowits/@FILE@`). RoboWits' success predicate is `_check_success` in that file:
```python
@PREDICATE@```

This is a *fixed scene instance*: object poses and the robot's start pose never change between resets. You may reset
and retry as many times as you want. Your deliverable is **one replayable trajectory**, not a general policy.

@CRITERION@
## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below).
It is replayed open-loop from the same initial state in a fresh process and scored 1 if the task is
completed at the end of the replay, else 0. Also leave the script that produced it at `/app/output/gen.py`.
Your wall-clock budget is 90 min (5400 s): save a trajectory as soon as one replays successfully (you can overwrite
it later), and do not stop before you have one.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_robowits import Session
s = Session("@FAM@", instance="/app/instance.json")   # @BUILD@: builds the frozen scene (object poses in instance.json)
s.reset()                          # back to the frozen initial state (unlimited; an exact snapshot restore)
p = s.primitives()                 # thin wrappers of the low-level action; each has a docstring: help(p["move_ee"])
s.objects()                        # objects: name -> position, orientation_wxyz, euler_xyz, bounds, size, velocity
p["move_ee"]("left", pos, quat_wxyz, linear=3)   # IK (RoboWits' own) to a gripper-tip pose, then joint interpolation
p["move_joints"]("left", q7); p["set_gripper"]("left", 0.0); p["open_gripper"]("left"); p["hold"](10)
s.ee_pose("left"); s.joint_positions(); s.ik("left", pos, quat_wxyz)    # kinematics helpers
s.render_frame("ego")              # RGB uint8 (480, 848, 3) from one camera (s.VIDEO_CAMERAS); s.render_grid()
s.render_depth("ego")              # float32 (480, 848) z-depth in metres (0 = no reading), pixel-aligned with render_frame("ego")
s.camera_info()                    # per camera: intrinsic_cv, extrinsic_cv (world -> camera, OpenCV axes), cam2world_gl, mount
s.robot_spec()                     # joints (position / velocity / effort limits), grippers, PD gains, tool frames Gripper_Tip_R/L
s.kinematics({"op": "fk", "q": q14})   # stateless FK / IK on the robot's model; {"op": "ik", "targets": {"Gripper_Tip_R": pose7}, "seed": q14}
s.joint_velocities(); s.joint_efforts(); s.gripper_width("left")   # measured state: 16-vectors in action layout (efforts: the PD drives')
s.object_pose(name); s.object_bounds(name); s.state_sha()          # one object's pose / AABB; the state hash that replays compare
p["set_joint_targets"](q16, steps=1); p["close_gripper"]("left"); p["gripper_quat"](yaw, approach)   # more thin wrappers: help(p[...])
s.step(action)                     # one low-level action (16 joint targets, below) = one control step (1/30 s)
s.record_start(); ...; actions = s.record_stop()   # (T, 16) actions, one row per control step
s.status()                         # {'success': bool, 'progress': float, 'sim_steps': int, 'resets': int, 'state_sha': str}
s.replay(actions)                  # resets, replays open-loop, returns status  -> use this to self-check
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_video(actions, "/app/output/check.mp4")   # replays from the frozen state and writes a tiled camera video
```
The primitives are deliberately thin (IK moves, joint moves, gripper, hold): grasping, placing and every other skill
are yours to build from them.

CLI equivalent of the grader:
`python /opt/tools/rcb_robowits.py replay --task @FAM@ --instance /app/instance.json --traj /app/output/trajectory.npz`

## Conventions
- World frame: robot base at (0, 0, 1.08), table top at z = 0.76, x points away from the robot, y to its left (the left
  arm works at y > 0). Quaternions are **WXYZ**.
- Action (16): right arm 7 joint targets (rad), right gripper width (m, 0 closed .. 0.1 open), left arm 7 joint targets,
  left gripper width; absolute position targets tracked by PD controllers. `s.hold_action()` is the no-op.
- Control runs at 30 Hz (@SUBSTEPS@). There is no step budget; your wall-clock budget is 90 min (5400 s).
  One technical cap: a trajectory, and a `Session` between two resets, has at most @MAXSTEPS@ control steps (about
  @MAXHOURS@ h of simulated time). `s.step` returns `True` on the step that reaches it and raises after it until
  `s.reset()`; the grader scores a trajectory with more rows 0 (`bad_trajectory`).
@GRIPPER@- One `Session` per process (Genesis initialises once). The physics runs on Genesis' bit-deterministic CPU backend at
  ~700 control steps/s; the GPU only renders camera images. Do not call `s.close()` before writing every output.
"""

GRIPPER_DEFAULT = ("- Grippers open to 10 cm. The gripper tip frame's +z axis is the approach direction and +x the finger-closing\n"
                   "  direction; `p[\"top_down_quat\"](yaw)` builds a vertical-approach orientation whose fingers close along `yaw`.\n")

STD_INSTRUCTION = """# RoboWits · @FAM@ — STANDARD MODE (robot as a service, eai-standard/2.2)

@INTRO@

@NOTE@@CRITERION@
## Rules (real-robot rules)
- **No reset.** The episode starts when the service comes up and ends on success, when your time is up, on a
  simulator error, or at the technical step cap below. Knocked-over objects stay knocked over.
- **No privileged state.** You see what the cameras see (RGB, and depth when you ask for it) plus the robot's own state:
  joint positions, velocities and drive efforts, gripper openings, end-effector poses. Nothing tells you where the
  objects are (no object poses or positions), and no endpoint tests the success criterion: the episode simply ends
  (`meta["done"]`, `reason` "success") the first time it holds.
- **Your wall-clock budget is 90 min (5400 s)** (`meta["time_left_s"]` counts it down). There is no step budget; actions
  and simulated time are reported as cost. One technical cap: the episode has at most @MAXSTEPS@ control steps (about
  @MAXHOURS@ h of simulated time at 30 Hz; `spec["max_control_steps"]`, counted by `meta["control_steps"]`; a `get_obs`
  that watches counts too). The call that reaches it stops there, the episode ends (`reason` "step_guard") and is graded
  as it stands. Use the time: ending your session before the task is done ends the episode as a failure.
- There is nothing to hand in: the service records your episode as the trajectory and grades it. Leave your script
  at `/app/output/gen.py` for the record.
- **Nothing is put into your context automatically.** Images and videos come back as arrays/bytes in a Python object;
  what you look at and where you store it is your code's decision.
- **If the service crashes** (a connection error or a 5xx instead of an answer), it restarts and resumes the SAME
  episode, never a reset, in the state after the last call it completed. `r.wait_ready()` waits until it answers again
  (resuming replays the episode so far: about a second per 700 control steps); then check `r.status()` (`calls`,
  `control_steps`) before you continue. A call that runs longer than `spec["max_call_wall_s"]` stops at the next control
  step and returns what it executed (`res.stopped`, `meta["executed_rows"]`).

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`)
```python
from rcb_client import Robot
@ROBOT@
spec = r.spec()                               # actions, cameras (intrinsics, mounting), robot_spec, world, kinematics, budget

obs = r.get_obs()                             # current frames from 3 cameras: obs.last[cam] -> uint8 (480,848,3)
obs.meta["proprio"]                           # {"layout": [80 names], "now": [...]}: groups in spec["proprio_groups"]
obs.meta["cameras"]                           # per camera: intrinsic_cv, extrinsic_cv, cam2world_gl of the LAST frame
obs = r.get_obs(depth=True)                   # + obs.last_depth[cam]: float32 (480,848) z-depth in metres, 0 = no reading
obs = r.get_obs(seconds=2.0, video="mp4")     # hold the last command and watch for 2 s (max 30): obs.video[cam] = mp4 bytes

res = r.submit("joint_position", A, dt=0.1)   # A: (T, 16) rows dt seconds apart; streamed at 30 Hz with linear interpolation
res = r.submit("ee_pose", P)                  # P: (T, 16) gripper-tip targets; inverse kinematics per row
res.meta["done"], res.meta["reason"], res.meta["plan"], res.meta["clipped"], res.meta["control_steps_chunk"]
res.video["ego"]                              # mp4 bytes of the execution (video="mp4" | "frames" | "both" | "none")
res.frames["ego"]                             # uint8 (N,480,848,3) at video_fps if requested
res.last["wrist_left"]; res.proprio           # last frame per camera; float32 (N, 80) proprio, one row per frame
res.frame_step, res.frame_time_s              # per frame: control steps since the episode start, simulated time (s)
res.extrinsic_cv["wrist_left"]                # (N,3,4) world -> camera at every frame (the wrist cameras move)
res = r.submit("joint_position", A, dt=0.1, depth="frames")   # + res.depth[cam]: (N,480,848) z-depth per frame (1 mm steps)
res.group("tcp_pose"); res.group("joint_effort", now=True)   # proprio columns by group name
r.fk(q14)["poses"]["Gripper_Tip_R"]           # forward kinematics of the 14 arm joints (spec["kinematics"]); moves nothing
r.ik({"Gripper_Tip_R": pose}, seed=q14)       # inverse kinematics -> {"ok", "q", "error"}; moves nothing
r.status(); r.wait_ready()                    # calls, control steps, done, reason; after a connection error: wait, then status
res.save("/app/runs/003")                     # meta.json, <cam>.mp4, last/, frames/, proprio.npy, depth, frame_meta.npz
```
Cameras: `ego` (static, above and behind the robot, looking at the table), `wrist_right` / `wrist_left` (on the wrists;
they move, so use the pose that comes with each frame). Resolution 848×480. `spec["cameras"][cam]` gives the intrinsics
and the mounting: a static pose, or the parent link and the fixed offset (world_T_cam = FK(link) · `link_T_cam_cv`). A
point (X, Y, Z) in a camera's OpenCV frame (x right, y down, z forward) appears at u = fx·X/Z + cx, v = fy·Y/Z + cy; depth
is that Z. `spec["robot_spec"]` lists the joints with their position, velocity and effort limits, the grippers, the PD
gains and the tool frames; `spec["world"]` the frame conventions.

### Action types
- `joint_position` (16): `Joint1_R..Joint7_R, right_gripper, Joint1_L..Joint7_L, left_gripper`; radians, gripper =
  opening width in metres, 0 = closed .. 0.1 = open. Absolute targets tracked by PD controllers. Rows are `dt` apart
  (`1/30 ≤ dt ≤ 0.5` s, a whole number of 1/30 s control periods: `2/30`, not `0.067`; any other `dt` is refused, never
  rounded); a chunk may cover at most 10 s; out-of-limit values are clipped and listed in `meta["clipped"]` (limits in
  the spec). Use `obs.meta["proprio"]["now"][:16]` as the starting row to move smoothly.
- `ee_pose` (16): right `x y z qw qx qy qz gripper`, left same; world frame (robot base at (0, 0, 1.08), x away from the
  robot, y to its left, +z up); quaternions wxyz. Each row is solved by inverse kinematics (no collision checking) and
  driven to in joint space; an arm whose IK fails holds and is reported in `meta["plan"]`. The pose is the **gripper tip**
  frame: +z is the approach direction, +x the direction the fingers close along (same convention as the `proprio`
  end-effector poses, so an observed pose is a valid target). At most 50 rows per submit; `dt` is ignored; a gripper
  width outside 0 .. 0.1 is clipped and listed in `meta["clipped"]`.
- A request with a field of the wrong type or out of range (`dt`, `seconds` outside 0 .. 30, `video_fps` not a whole
  number in 1 .. 30, `video`, `interpolate`, `cameras` not a list of names, `note` not a string, actions that are not
  finite (T, 16) numbers) is answered 400 before anything is executed: the client raises `ValueError`, nothing has
  moved and the episode goes on.

@OBJECTS@

The wrist joints are limited to ±60°, so a vertical approach only works for finger-closing directions within about ±60°
of the world y axis.
"""


def priv_instruction(fam: str, f: dict) -> str:
    pred = predicate_file(fam, f).read_text()
    intro = ("You control a simulated **bimanual Marvin** robot (two 7-DoF arms with Pika parallel grippers; RoboWits on Genesis "
             f"0.4.7 physics) via Python. **Task:** {f_text(fam)}")
    subs = {"@FAM@": fam, "@INTRO@": wrap(intro), "@NOTE@": (f["priv_note"] + "\n\n") if f.get("priv_note") else "",
            "@OBJECTS@": ", ".join(f"`{o}`" for o in f["objects"]), "@FILE@": f"{num(f)}_{fam}.py", "@PREDICATE@": pred,
            "@CRITERION@": criterion_section(fam, f, "priv"), "@BUILD@": f.get("build_note") or "~60 s",
            "@SUBSTEPS@": f"{f['substeps']} physics substeps per control step in this scene" if f.get("substeps") else "4 physics substeps",
            "@GRIPPER@": f.get("priv_gripper_note") or GRIPPER_DEFAULT, "@MAXSTEPS@": str(MAX_STEPS), "@MAXHOURS@": MAX_STEPS_H}
    s = PRIV_INSTRUCTION
    for k, v in subs.items():
        s = s.replace(k, v)
    return s


def std_instruction(fam: str, f: dict) -> str:
    rt = f.get("robot_timeout")
    robot = (f"r = Robot(timeout={rt})                      # connects (waits while the service builds the scene, {f['build_note'].split(' (')[0]})"
             if rt else
             f"r = Robot()                                   # connects (waits while the service builds the scene, {(f.get('build_note') or '~1 min').split(' (')[0]})")
    intro = ("You control a bimanual **Marvin** robot (two 7-DoF arms with Pika parallel grippers) **as if it were real hardware**: "
             f"the simulator runs in a service you cannot open. You get one client and one episode. **Task:** {f.get('std_goal') or f_text(fam)}")
    subs = {"@FAM@": fam, "@INTRO@": wrap(intro), "@NOTE@": (f["std_note"] + "\n\n") if f.get("std_note") else "",
            "@CRITERION@": criterion_section(fam, f, "std"), "@ROBOT@": robot, "@OBJECTS@": f["std_objects"],
            "@MAXSTEPS@": str(MAX_STEPS), "@MAXHOURS@": MAX_STEPS_H}
    s = STD_INSTRUCTION
    for k, v in subs.items():
        s = s.replace(k, v)
    return s


def bk_row(f: dict, where: str) -> str:
    return (f"| BlenderKit models | not redistributable, so not in the image: mounted read-only{' ' + where if where else ''} from "
            f"`$RCB_ROBOWITS_BLENDERKIT` (how to obtain them: `images/robowits/NOTICE`) |\n") if f["blenderkit"] else ""


def has_solution(f: dict) -> bool:
    return f["oracle"] in ("full", "partial")


def oracle_row(f: dict, mode: str) -> str:
    if has_solution(f):
        what = ("`solution/solve.sh` records the reference solution (`solution/oracle_*.py`)" if mode == "priv" else
                "`solution/solve.sh` streams the privileged oracle's joint targets (one row per control step, `hold`) as `joint_position` chunks")
        if f["oracle"] == "full":
            return f"| Oracle | full: {what} |"
        return f"| Oracle | partial: {what}; it scored 1 on an earlier version of this task, not re-run on this one (`oracle_evidence`); human review in {REVIEW} |"
    return f"| Oracle | none (RoboWits ships no expert): `oracle_evidence` in `task.toml`; human review in {REVIEW} |"


def reference_text(fam: str, f: dict, mode: str) -> str:
    if has_solution(f):
        if mode == "priv":
            return wrap(f["reference"])
        return wrap(f"`solution/oracle_replay.py` replays the privileged oracle's recorded joint targets (`solution/oracle_qpos.npy`, one row "
                    f"per control step, `hold`) through the client, with no privileged information at run time; `solution/solve.sh` runs it. "
                    f"The rows are the trajectory of the privileged reference solution (`{priv_dir(fam)}`, `solution/`).")
    return wrap("None: RoboWits ships no expert or planner, and none is written for this family (`oracle = \"none\"`). Evidence that it "
                f"is solvable: `oracle_evidence` in `task.toml` and the positive example cited in the review table of {REVIEW} (the trial is "
                "published on the results site).")


def readme(title: str, rows: list[tuple[str, str]], task: str, difficulty: str, reference: str, verification: str, mode: str) -> str:
    """README content in the standard layout (PROTOCOL §2.1). normalize() (scripts/task_conventions.py) then writes the key
    table (benchmark, mode, twin, simulator / robot, family / instance, oracle, budget, base image) from task.toml and the
    Dockerfiles, and moves these extra rows and the Change Log (PROTOCOL §2.8) into ## Details."""
    table = "\n".join(["| | |", "|---|---|"] + [f"| {k} | {v} |" for k, v in rows])
    log = "\n".join(f"- {e}" for e in CHANGE_LOG[mode])
    return (f"# {title}\n\n{table}\n\n## Task\n{task}\n\n## Difficulty\n{difficulty}\n\n## Reference solution\n{reference}\n\n"
            f"## Verification\n{verification}\n\n## Change Log\n{log}\n")


def host_detail(f: dict) -> list[tuple[str, str]]:
    """The host constraint of a family whose frozen instance only one CPU vendor rebuilds (families.py `host_cpu_vendor`)."""
    v = f.get("host_cpu_vendor")
    return [("Host CPU", f"`{v}` only (`[metadata].host_cpu_vendor` in `task.toml`: the `vendor_id` of `/proc/cpuinfo`). On another "
                         "vendor's CPU the frozen instance rebuilt by Genesis' CPU backend is out of tolerance, and the trial ends as "
                         "an infrastructure error (`infra_error = 1`), never as a result (docs/benchmarks/robowits.md, Hosts)")] if v else []


def host_toml(f: dict) -> str:
    """The machine-readable host constraint ([metadata], a benchmark-specific field: docs/TAXONOMY.md), or nothing."""
    v = f.get("host_cpu_vendor")
    return (f"host_cpu_vendor = {toml_str(v)}   # run on hosts whose /proc/cpuinfo vendor_id is this: elsewhere the frozen instance "
            "is out of tolerance (infra_error)\n") if v else ""


def bk_detail(f: dict, where: str) -> list[tuple[str, str]]:
    return [("BlenderKit models", f"not redistributable, so not in the image: mounted read-only{' ' + where if where else ''} from "
                                  "`$RCB_ROBOWITS_BLENDERKIT` (how to obtain them: `images/robowits/NOTICE`)")] if f["blenderkit"] else []


def review_line(f: dict, twin: str = "") -> str:
    if f["oracle"] == "full":
        return ""
    if f["oracle"] == "partial":
        return (f"\n\nOracle partial: the reference solution scored 1 on an earlier version of this task and was not re-run on this one\n"
                f"(`oracle_evidence` in `task.toml`); human review in {REVIEW} (PROTOCOL §2.7){twin}.")
    return f"\n\nNo oracle; human review in {REVIEW} (PROTOCOL §2.7){twin}: the positive example, the `nop` result and the predicate\nsummary are in the PR's review table."


def priv_readme(fam: str, f: dict) -> str:
    ver = (f"Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in a fresh process, twice; pass iff\n"
           f"RoboWits' `_check_success` holds after every replay, the final-state hashes agree and the rebuilt frozen scene matches\n"
           f"the recorded one (`tests/grade.py`; a scene that does not match is the host's failure, `infra_error = 1`, never the\n"
           f"agent's 0), plus `/logs/verifier/replay.mp4`. What the predicate checks, in words:\n"
           f"`instruction.md`, \"Success criterion (as graded)\". The trajectory is the per-control-step JOINT_ABS record (T, 16);\n"
           f"Genesis' CPU backend restores the frozen snapshot exactly, so in-process repeats and fresh processes agree bit for bit\n"
           f"on one CPU vendor (docs/benchmarks/robowits.md).")
    if f["oracle"] == "full":
        ver += " The oracle scores 1 and `nop` scores 0."
    ver += review_line(f)
    rows = [("RoboWits task", f"`{f['rid']}-v0` (RoboWits @ 9cc30ae, Genesis 0.4.7: CPU physics backend, EGL rendering on the GPU)"),
            ("Instance", f"entry {f['eval_index']} of RoboWits' `eval_dataset_50/{num(f)}.json`; object poses and the expected state hash in "
                         "`environment/instance.json` (the verifier's copy in `tests/`)"),
            ("Robot", "Marvin bimanual: 2 × 7-DoF arms with Pika parallel grippers; JOINT_ABS actions (T, 16) at 30 Hz"),
            ("GPU", "EGL camera rendering only (`environment/docker-compose.yaml`, `tests/docker-compose.yaml`)")] + bk_detail(f, "") + host_detail(f)
    task = wrap(f"{f_text(fam)} One replayable trajectory from the frozen instance (evaluation scene {f['eval_index']} of RoboWits task "
                f"{int(num(f))}), with the privileged tooling (`rcb_robowits.py`: the scene's state, resets, thin primitives, replay); the "
                "success criterion as graded is in `instruction.md`.")
    return readme(priv_dir(fam), rows, task, wrap(f["difficulty"]), reference_text(fam, f, "priv"), ver, "priv")


def std_readme(fam: str, f: dict) -> str:
    det = ("the in-process replay is bit-exact on Genesis' CPU backend" if f["backend"] == "cpu" else
           "Genesis' GPU backend is not bit-exact here: determinism is reported, not required")
    ver = wrap(f"`success` = live success ∧ replay success ∧ deterministic ({det}), computed inside the sidecar, and no "
               f"infrastructure failure (`tests/grade.py` reads the sidecar's `final.json`); `/logs/verifier/replay.mp4`. What is "
               f"checked, in words: `instruction.md`, \"Success criterion (as graded)\"."
               + (" The oracle scores 1 and `nop` scores 0." if f["oracle"] == "full" else ""))
    ver += review_line(f, ", with its privileged twin")
    cls = "exact" if f["backend"] == "cpu" else "approx"
    rows = [("Protocol", f"`{PROTOCOL}` (docs/STANDARD_MODE.md): `submit` chunks of `joint_position` (16, streamed at the 30 Hz control "
                         "rate with the agent's `dt`) or `ee_pose` (16, IK per row); `observe` frames or a watch window; stateless "
                         "`kinematics`; binary RCB1 responses"),
            ("Crash recovery", f"`restart: on-failure:6`; the service replays its journal and resumes the same episode (resume class "
                               f"`{cls}`, docs/STANDARD_MODE.md §13)"),
            ("Agent and verifier image", f"`{CLIENT_IMAGE}` with the shared pins (`environment/{CLIENT_REQUIREMENTS}`)"),
            ("Instance", f"the privileged twin's frozen instance (`environment/sim/instance.json`): entry {f['eval_index']} of RoboWits' "
                         f"`eval_dataset_50/{num(f)}.json`")] + bk_detail(f, "into the `sim` sidecar") + host_detail(f)
    task = wrap(f"{f_text(fam)} The same frozen instance as `{priv_dir(fam)}`, as a robot service (`{PROTOCOL}`): the simulator runs "
                "in the `sim` sidecar, which the agent cannot open; the agent gets one episode, no reset and no privileged state, only the "
                "client (calibrated RGB-D cameras, proprioception, `joint_position` / `ee_pose` chunks, stateless kinematics). The sidecar "
                "records the episode as the trajectory, replays it and renders the video; the success criterion as graded is in "
                "`instruction.md`.")
    diff = wrap(f"That of `{priv_dir(fam)}` (its Difficulty), without resets, privileged state or the tooling's primitives: the agent "
                "perceives the scene through calibrated RGB-D cameras and its own proprioception, and every action it sends is part of "
                "the one graded episode.")
    return readme(std_dir(fam), rows, task, diff, reference_text(fam, f, "std"), ver, "std")


def toml_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def priv_toml(fam: str, f: dict) -> str:
    s = priv_dir(fam)
    oracle = f'oracle = "{f["oracle"]}"' + (f"\noracle_evidence = {toml_str(per_mode(f['oracle_evidence'], 'priv'))}" if f["oracle"] != "full" else "")
    desc = (f"RoboWits {fam} (bimanual Marvin, Genesis): produce one replayable trajectory. {f_text(fam)} Frozen scene instance "
            f"(RoboWits evaluation scene {f['eval_index']} of task {int(num(f))}).")
    vt = f.get("verifier_timeout_s") or 1800
    mem = f.get("memory_mb") or 16384
    return f"""schema_version = "1.3"
artifacts = ["/app/output/"]

[task]
name = "robot-coding-bench/{s}"
description = {toml_str(desc)}
authors = [{{ name = "qineng" }}]
keywords = ["robotics", "robowits", "genesis", "marvin-bimanual", "dual-arm", "code-as-policy", "trajectory", "{fam}"]

[metadata]
author_name = "qineng"
task_type = "trajectory"          # trajectory | policy   (see docs/PROTOCOL.md)
simulator = "robowits"            # RoboWits @ 9cc30ae on Genesis 0.4.7 (CPU physics backend, EGL rendering)
robot = "marvin-bimanual"
family = "{fam}"
mode = "privileged"
{oracle}
instance_seed = {f['eval_index']}                 # scene = environment/instance.json (entry {f['eval_index']} of RoboWits' eval_dataset_50/{num(f)}.json + expected state hash); identity = dataset.toml digest
{host_toml(f)}expert_time_estimate_hours = 1.0

[verifier]
timeout_sec = {float(vt)}
environment_mode = "separate"     # verifier runs in its own sandbox (tests/Dockerfile); the agent container is gone by then
network_mode = "no-network"       # the replay needs no download: assets in the image, Genesis' caches seeded from instance.json

[agent]
timeout_sec = {float(BUDGET_S)}             # RoboWits budget: 1.5 h of wall clock (docs/benchmarks/robowits.md)
# egress: Harbor default (public). `scripts/set_agent_egress.py allowlist` closes it to the model APIs.

[environment]
build_timeout_sec = 3600.0
cpus = 4
memory_mb = {mem}

[verifier.environment]
build_timeout_sec = 1800.0
"""


def std_toml(fam: str, f: dict) -> str:
    s = slug(fam)   # the standard directory is s + "-standard"
    oracle = f'oracle = "{f["oracle"]}"' + (f"\noracle_evidence = {toml_str(per_mode(f['oracle_evidence'], 'std'))}" if f["oracle"] != "full" else "")
    desc = (f"STANDARD MODE (robot as a service, {PROTOCOL}): RoboWits {fam} on the same frozen instance as the privileged task "
            f"(evaluation scene {f['eval_index']} of task {int(num(f))}). {f_text(fam)} The agent only gets a client: get_obs (RGB, optional "
            f"depth, proprioception, calibrated cameras), submit (joint_position or ee_pose chunks), stateless kinematics. No reset, "
            f"no privileged state; the sim service records the episode as a trajectory and grades it.")
    ct = f.get("collect_timeout_s") or 2400
    return f"""schema_version = "1.3"
artifacts = [
  {{ source = "/data/final.json", service = "sim" }},
  {{ source = "/data/episode.jsonl", service = "sim" }},
  {{ source = "/data/trajectory.npz", service = "sim" }},
  {{ source = "/data/replay.mp4", service = "sim" }},
  {{ source = "/data/replay.last.png", service = "sim" }},
  {{ source = "/data/journal.f64", service = "sim" }},
  {{ source = "/data/startups.jsonl", service = "sim" }},
  {{ source = "/data/server.log", service = "sim" }},
  "/app/output/",
]

[task]
name = "robot-coding-bench/{s}-standard"
description = {toml_str(desc)}
authors = [{{ name = "qineng" }}]
keywords = ["robotics", "robowits", "genesis", "marvin-bimanual", "dual-arm", "standard-mode", "trajectory", "{fam}"]

[metadata]
author_name = "qineng"
task_type = "trajectory"
simulator = "robowits"
robot = "marvin-bimanual"
family = "{fam}"
mode = "standard"                  # RGB + proprioception only; no object poses, no reset
protocol = "{PROTOCOL}"
{oracle}
instance_seed = {f['eval_index']}
{host_toml(f)}expert_time_estimate_hours = 2.0

[verifier]
timeout_sec = 1200.0
environment_mode = "separate"
network_mode = "no-network"

[[verifier.collect]]
service = "sim"
# end the episode (SIGUSR1 to the live service, through a crash resume if one is under way), wait for the in-process
# grade and the video (final.json video_done), then hand over the record (docs/STANDARD_MODE.md §13.3)
command = "python3 /srv/rcb_limited.py end /data --wait-key video_done --timeout {ct - 120}; cat /data/final.json"
timeout_sec = {ct}                # service up (a resume replays the journal first), the grading replay, then the video

[agent]
timeout_sec = {float(BUDGET_S)}             # RoboWits budget: 1.5 h of wall clock (docs/benchmarks/robowits.md)
# egress: Harbor default (public). `scripts/set_agent_egress.py allowlist` closes it to the model APIs.

[environment]
build_timeout_sec = 1800.0
cpus = 4
memory_mb = {f.get('memory_mb') or 16384}
"""


def gpu_service(indent: str = "    ") -> str:
    return (f"{indent}deploy:\n{indent}  resources:\n{indent}    reservations:\n{indent}      devices:\n"
            f"{indent}        - driver: nvidia\n{indent}          count: 1\n{indent}          capabilities: [gpu]\n")


def priv_compose(f: dict, tests: bool) -> str:
    head = ("# The verifier replays in the simulator, which needs the GPU for Genesis' EGL cameras (the replay video).\n" if tests else
            "# Genesis renders camera images through EGL on the GPU (the physics runs on its bit-deterministic CPU backend). Harbor's\n"
            "# local docker sandbox rejects [environment].gpus, but merging this onto the main service passes the device through.\n")
    vol = f"    volumes:\n      - {BK_VOLUME}\n" if f["blenderkit"] else ""
    return head + (BK_NOTE if f["blenderkit"] else "") + "services:\n  main:\n    shm_size: \"2gb\"\n" + vol + gpu_service()


def std_compose(fam: str, f: dict) -> str:
    gpu = f["backend"] == "gpu"
    lines = ["# Standard mode: the simulator runs in the `sim` sidecar (agent cannot open it); the agent only reaches port 8000.",
             "# No `expose`/`ports` on sim: under Harbor's egress control it shares main's network namespace (localhost:8000).",
             ("# Genesis runs physics on the GPU here (particle-heavy scene, not bit-exact) and renders the cameras through EGL." if gpu else
              "# Genesis runs physics on the CPU (bit-deterministic) and needs the GPU only for EGL camera rendering."),
             "# Crash recovery (docs/STANDARD_MODE.md §13): run.sh exits non-zero when the service crashes, compose restarts the",
             "# container (same container, same /data) and the service replays its journal into the same episode, never a reset."]
    out = "\n".join(lines) + "\n" + (BK_NOTE if f["blenderkit"] else "")
    out += "services:\n  main:\n    depends_on: [sim]\n  sim:\n"
    out += f"    image: {IMAGE}\n    volumes:\n      - ./sim:/srv:ro\n" + (f"      - {BK_VOLUME}\n" if f["blenderkit"] else "")
    out += "    working_dir: /tmp\n    command: sh /srv/run.sh\n    restart: on-failure:6          # N >= 3 (PROTOCOL §4.1); a resume continues the episode\n"
    out += "    environment:\n"
    if gpu:
        out += "      RCB_ROBOWITS_BACKEND: gpu     # particle-heavy scene: GPU physics (not bit-exact; resume class approx)\n"
    out += (f"      RCB_TASK: {fam}\n      RCB_INSTANCE: /srv/instance.json\n      RCB_DATA: /data\n      RCB_WALL_CLOCK_S: \"{BUDGET_S}\"\n"
            f"      RCB_STARTUP_TIMEOUT_S: \"{startup_timeout(f)}\"   # >= 2 x the slowest measured scene build (docs/benchmarks/robowits.md)\n"
            "      PYTHONPATH: /srv\n      QD_OFFLINE_CACHE: \"0\"\n"
            "      RCB_SESSION_LOG: \"\"           # the sidecar's own Session must not write the agent-side interaction log\n")
    out += "    shm_size: \"2gb\"\n" + gpu_service()
    return out


def priv_dockerfile(f: dict) -> str:
    gpu = " RCB_ROBOWITS_BACKEND=gpu" if f["backend"] == "gpu" else ""
    return (f"# Base image = RoboWits + Genesis 0.4.7 (see images/robowits/). Everything task-specific is copied here.\nFROM {IMAGE}\n"
            "COPY instance.json /app/instance.json\nCOPY rcb_robowits.py /opt/tools/rcb_robowits.py\n"
            f"ENV PYTHONPATH=/opt/tools QD_OFFLINE_CACHE=0{gpu}\nRUN mkdir -p /app/output\nWORKDIR /app\n")


def priv_tests_dockerfile(f: dict) -> str:
    gpu = " RCB_ROBOWITS_BACKEND=gpu" if f["backend"] == "gpu" else ""
    return ("# Separate verifier sandbox (PROTOCOL §4): the same simulator image with the verifier's own copies of the\n"
            "# tooling and the frozen instance baked in. Nothing the agent did in its container reaches this one — Harbor\n"
            "# uploads only the declared artifacts (/app/output/), so a patched success check or a swapped interpreter in\n"
            "# the agent container cannot influence the verdict.\n"
            f"FROM {IMAGE}\nCOPY grade.py instance.json rcb_robowits.py test.sh /tests/\n"
            "RUN chmod +x /tests/test.sh && mkdir -p /app/output /logs/verifier\n"
            f"ENV PYTHONPATH=/tests QD_OFFLINE_CACHE=0{gpu}\nWORKDIR /tests\n")


CLEAR_LOGS = ("rm -rf /logs/verifier/*   # verdicts from an earlier run never survive (docs/PROTOCOL.md §2.6)\n"
              "mkdir -p /logs/verifier\n")


def priv_test_sh(fam: str) -> str:
    return ("#!/bin/bash\n# Verifier: replay /app/output/trajectory.npz from the frozen instance (the tests/ copy) in a fresh process.\n"
            "# Writes /logs/verifier/reward.txt (1/0) and reward.json (numeric fields, see docs/PROTOCOL.md).\n" + CLEAR_LOGS +
            f"python /tests/grade.py --family {fam} --instance /tests/instance.json --traj /app/output/trajectory.npz --repeat 2 \\\n"
            f"  --budget {FM.FAMILIES[fam].get('verifier_timeout_s') or 1800} 2> /logs/verifier/grade.log\n")


def std_test_sh() -> str:
    return ("#!/bin/bash\n# Verifier (separate sandbox): the sim sidecar's artifacts were uploaded to /data by Harbor.\n" + CLEAR_LOGS +
            "python /tests/grade.py 2> /logs/verifier/grade.log\n")


def std_dockerfile() -> str:
    return ("# Standard mode: the agent container has NO simulator and no RoboWits code — only Python and the client, on the shared\n"
            "# pinned client base with the shared pins (scripts/eai_standard/client.env, client-requirements.txt).\n"
            f"FROM {CLIENT_IMAGE}\nCOPY {CLIENT_REQUIREMENTS} /tmp/{CLIENT_REQUIREMENTS}\n"
            f"RUN pip install --no-cache-dir -r /tmp/{CLIENT_REQUIREMENTS}\nCOPY rcb_client.py rcb1.py /opt/tools/\n"
            "ENV PYTHONPATH=/opt/tools\nRUN mkdir -p /app/output\nWORKDIR /app\n")


def std_tests_dockerfile(f: dict) -> str:
    gpu = "ENV RCB_ROBOWITS_BACKEND=gpu\n" if f["backend"] == "gpu" else ""
    return ("# Separate verifier sandbox: grades the sim service's own artifacts; needs nothing but python.\n"
            f"FROM {CLIENT_IMAGE}\nCOPY test.sh /tests/test.sh\nCOPY grade.py /tests/grade.py\nRUN chmod +x /tests/test.sh\n" + gpu)


def priv_solve_sh(fam: str) -> str:
    return ("#!/bin/bash\n# Oracle: run the human-written reference solution (kept in solution/, never in the agent image) and record it.\n"
            "set -e\nmkdir -p /app/output\n"
            f"python /opt/tools/rcb_robowits.py run-oracle --task {fam} --instance /app/instance.json --code /solution/oracle_{fam}.py --out /app/output/trajectory.npz\n"
            f"cp /solution/oracle_{fam}.py /app/output/gen.py\n")


STD_SOLVE_SH = ("#!/bin/bash\n# Oracle (standard mode): replays the privileged oracle's joint targets, one row per control step, as `joint_position`\n"
                "# chunks through the client. Uses no privileged information at run time (only the pre-recorded targets).\n"
                "set -e\nmkdir -p /app/output\ncp /solution/oracle_replay.py /app/output/gen.py\npython /solution/oracle_replay.py\n")


# ---------------------------------------------------------------------------------------------------------- rendering
INSTANCES: dict[str, dict] = {}


def load_instance(fam: str, f: dict, given: str | None) -> bytes:
    p = TASKS / priv_dir(fam) / "environment/instance.json"
    if given:                    # a new family: the instance as make-instance wrote it, normalised once
        inst = json.load(open(given)); inst.pop("max_steps", None)
        raw = json.dumps(inst, indent=1).encode()
    elif p.exists():             # the committed frozen instance, byte for byte
        raw = p.read_bytes()
    else:
        sys.exit(f"{fam}: no frozen instance ({p.relative_to(ROOT)} missing): pass --instance")
    inst = json.loads(raw)
    assert inst["task"] == fam and inst["robowits_task"] == f"robowits/{f['rid']}-v0" and int(inst["eval_index"]) == f["eval_index"], fam
    INSTANCES[fam] = inst
    return raw


def copied(p: pathlib.Path) -> tuple[bytes, int]:
    """A shared source, copied unchanged (content and executable bit)."""
    return p.read_bytes(), EXEC if p.stat().st_mode & 0o100 else FILE


def files_for(fam: str, f: dict, inst: bytes) -> dict[str, dict[str, tuple[bytes, int]]]:
    """{task dir name: {relative path: (bytes, mode)}} for the family's two tasks."""
    if f.get("criterion") is None:
        sys.exit(f"{fam}: no criterion in families.py: write the 'Success criterion (as graded)' texts before rendering")
    pred = predicate_file(fam, f)
    if not pred.is_file():
        sys.exit(f"{fam}: {pred.relative_to(ROOT)} missing (--extract-predicate)")
    sha = hashlib.sha256(pred.read_bytes()).hexdigest()[:16]
    if sha != f["predicate_sha"]:
        sys.exit(f"{fam}: predicate sha {sha} != families.py {f['predicate_sha']}: the predicate changed, re-check the criterion texts")
    sh = lambda p: copied(SHARED / p)                      # noqa: E731
    ly = lambda p: copied(LAYER / p)                       # noqa: E731
    t = lambda s, mode=FILE: (s.encode(), mode)            # noqa: E731
    priv = {
        "task.toml": t(priv_toml(fam, f)), "instruction.md": t(priv_instruction(fam, f)), "README.md": t(priv_readme(fam, f)),
        "environment/Dockerfile": t(priv_dockerfile(f)), "environment/docker-compose.yaml": t(priv_compose(f, tests=False)),
        "environment/instance.json": (inst, FILE), "environment/rcb_robowits.py": sh("rcb_robowits.py"),
        "tests/Dockerfile": t(priv_tests_dockerfile(f)), "tests/docker-compose.yaml": t(priv_compose(f, tests=True)),
        "tests/grade.py": sh("grade_privileged.py"), "tests/instance.json": (inst, FILE), "tests/rcb_robowits.py": sh("rcb_robowits.py"),
        "tests/test.sh": t(priv_test_sh(fam), EXEC),
    }
    std = {
        "task.toml": t(std_toml(fam, f)), "instruction.md": t(std_instruction(fam, f)), "README.md": t(std_readme(fam, f)),
        "environment/Dockerfile": t(std_dockerfile()), "environment/docker-compose.yaml": t(std_compose(fam, f)),
        "environment/rcb_client.py": ly("rcb_client.py"), "environment/rcb1.py": ly("rcb1.py"),
        f"environment/{CLIENT_REQUIREMENTS}": ly(CLIENT_REQUIREMENTS),
        "environment/sim/server.py": sh("server.py"), "environment/sim/rcb_robowits.py": sh("rcb_robowits.py"),
        "environment/sim/instance.json": (inst, FILE), "environment/sim/rcb_limited.py": ly("rcb_limited.py"),
        "environment/sim/rcb1.py": ly("rcb1.py"), "environment/sim/run.sh": ly("run.sh"),
        "tests/Dockerfile": t(std_tests_dockerfile(f)), "tests/grade.py": sh("grade_standard.py"), "tests/test.sh": t(std_test_sh(), EXEC),
    }
    if has_solution(f):
        od = HERE / "oracles" / fam
        for p in sorted(od.iterdir()):
            if p.name.startswith("oracle_qpos") or p.name == "oracle_meta.json":
                std[f"solution/{p.name}"] = (p.read_bytes(), FILE)
            else:
                priv[f"solution/{p.name}"] = (p.read_bytes(), FILE)
        assert f"solution/oracle_{fam}.py" in priv and "solution/oracle_qpos.npy" in std, fam
        priv["solution/solve.sh"] = t(priv_solve_sh(fam), EXEC)
        std["solution/solve.sh"] = t(STD_SOLVE_SH, EXEC)
        std["solution/oracle_replay.py"] = sh("oracle_replay.py")
    return {priv_dir(fam): priv, std_dir(fam): std}


def render_family(fam: str, f: dict, inst: bytes) -> dict[str, dict[str, tuple[bytes, int]]]:
    """Both tasks of the family as they are committed: rendered into a scratch directory (twins side by side, as normalize()
    reads the twin), passed through scripts/task_conventions.normalize(), read back. Re-running is idempotent because the
    normalized output is what sync() compares against."""
    out: dict[str, dict[str, tuple[bytes, int]]] = {}
    with tempfile.TemporaryDirectory(prefix="mk_robowits_") as td:
        files = files_for(fam, f, inst)
        for task, want in files.items():
            for rel, (data, mode) in want.items():
                q = pathlib.Path(td) / task / rel
                q.parent.mkdir(parents=True, exist_ok=True); q.write_bytes(data); os.chmod(q, mode)
        for task in files:
            TC.normalize(pathlib.Path(td) / task)
        for task in files:
            d = pathlib.Path(td) / task
            out[task] = {q.relative_to(d).as_posix(): (q.read_bytes(), EXEC if q.stat().st_mode & 0o100 else FILE)
                         for q in sorted(d.rglob("*")) if q.is_file()}
    return out


def sync(task: str, want: dict[str, tuple[bytes, int]], check: bool) -> list[str]:
    """Make tasks/<task> hold exactly `want` (__pycache__ untouched; anything else, results/ included, is removed). Returns the
    changes."""
    d = TASKS / task; changes = []
    have = set()
    if d.is_dir():
        for p in d.rglob("*"):
            rel = p.relative_to(d).as_posix()
            if p.is_file() and "__pycache__" not in rel:
                have.add(rel)
    for rel in sorted(have - set(want)):
        changes.append(f"delete {task}/{rel}")
        if not check:
            (d / rel).unlink()
    for rel, (data, mode) in sorted(want.items()):
        p = d / rel
        if not p.is_file() or p.read_bytes() != data:
            changes.append(f"write  {task}/{rel}")
            if not check:
                p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data)
        if p.is_file() and stat.S_IMODE(p.stat().st_mode) & 0o111 != mode & 0o111:
            changes.append(f"chmod  {task}/{rel}")
            if not check:
                os.chmod(p, mode)
    if not check and d.is_dir():
        for p in sorted(d.rglob("*"), key=lambda q: -len(q.parts)):
            if p.is_dir() and not any(p.iterdir()):
                p.rmdir()
    return changes


def extract_predicate(fam: str, src: str) -> None:
    f = FM.FAMILIES[fam]
    path = pathlib.Path(src) / f"{num(f)}_{fam}.py"
    code = path.read_text(); tree = ast.parse(code)
    cs = next(ast.get_source_segment(code, fn) for c in tree.body if isinstance(c, ast.ClassDef) for fn in c.body
              if isinstance(fn, ast.FunctionDef) and fn.name == "_check_success")
    out = predicate_file(fam, f); out.write_text(cs + "\n")
    print(f"{out.relative_to(ROOT)}: predicate_sha = {hashlib.sha256(out.read_bytes()).hexdigest()[:16]}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("families", nargs="*"); ap.add_argument("--check", action="store_true"); ap.add_argument("--list", action="store_true")
    ap.add_argument("--instance"); ap.add_argument("--extract-predicate", metavar="FAMILY"); ap.add_argument("--src")
    a = ap.parse_args()
    if a.list:
        for fam, f in FM.FAMILIES.items():
            print(f"{fam:24s} {f['status']:8s} oracle={f['oracle']:7s} {f.get('pending', '')}")
        for fam, why in FM.DROPPED.items():
            print(f"{fam:24s} dropped  {why}")
        return 0
    if a.extract_predicate:
        if not a.src:
            sys.exit("--extract-predicate needs --src <gs_gym/envs/robowits dir of RoboWits @ 9cc30ae>")
        extract_predicate(a.extract_predicate, a.src); return 0
    fams = a.families or [k for k, v in FM.FAMILIES.items() if v["status"] == "pr"]
    unknown = [x for x in fams if x not in FM.FAMILIES]
    if unknown:
        sys.exit(f"unknown families {unknown} (dropped: {sorted(FM.DROPPED)})")
    if a.instance and len(fams) != 1:
        sys.exit("--instance takes exactly one family")
    changes = []
    for fam in fams:
        f = FM.FAMILIES[fam]
        inst = load_instance(fam, f, a.instance)
        for task, want in render_family(fam, f, inst).items():
            changes += sync(task, want, a.check)
    for c in changes:
        print(c)
    print(f"{len(fams)} families, {2 * len(fams)} tasks: {len(changes)} change(s){' needed' if a.check else ''}")
    return 1 if (a.check and changes) else 0


if __name__ == "__main__":
    sys.exit(main())
