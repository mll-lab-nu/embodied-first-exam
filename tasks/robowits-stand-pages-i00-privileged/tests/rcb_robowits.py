"""
rcb_robowits.py — task-local tooling for RoboWits (Genesis 0.4.7 / gs_gym, UMass-Embodied-AGI/RoboWits @ 9cc30ae):
frozen evaluation-scene instance / privileged primitives / action recording / fresh-process deterministic replay.
Same shape as the robosuite example's rcb_traj.py and the BEHAVIOR tasks' rcb_behavior.py, so agents and verifiers
share one mental model.

Concepts
--------
instance   : one RoboWits evaluation scene = a registered task (e.g. robowits/14-stack-cubes-v0) + the object poses of one
             entry of the benchmark's dataset/robowits/eval_dataset_50/<id>.json. `make-instance` copies that entry into
             instance.json ("scene"), so a task directory is self-contained: Session(instance=...) rebuilds the scene from
             the task's own copy, never from the image's dataset. The env's reset puts the robot in its reset pose, the
             objects at those poses and settles 10 physics steps. In a FRESH process the canonical build sequence
             (gs.init -> env -> set_eval_dataset_idx -> reset) reproduces that state bit-exactly on one host (measured
             across processes); its sha1 over the Genesis SimState is stored in instance.json. On load, `instance_exact`
             = sha equality and `instance_matches` = sha equality or every object / joint pose within tolerance (another
             CPU or compiler may change the last bits; a wrong asset or simulator version moves objects by millimetres).
trajectory : the (T, 16) JOINT_ABS actions handed to the env, one row per control step (30 Hz control, 4 physics substeps):
             right arm 7 joint targets (rad), right gripper width (m, 0..0.1), left arm 7 joint targets, left gripper width.
             The physics runs on Genesis' single-threaded CPU backend, which is bit-deterministic: fresh processes and
             repeated in-process replays reproduce the frozen state and the final state exactly (measured with the oracle
             trajectory, contacts included), provided every episode starts from the restored snapshot (Session does that).
             The GPU backend is NOT (its contact solver settles the cubes differently from run to run), so it is never used
             for physics; the GPU only renders camera images through EGL.
budget     : there is no step budget: the agent's wall clock is the limit. MAX_STEPS only stops runaway trajectories.

CLI
---
  python rcb_robowits.py make-instance --task stack_cubes --eval-index 0 --out instance.json
  python rcb_robowits.py run-oracle    --task stack_cubes --instance instance.json --code oracle.py --out traj.npz
  python rcb_robowits.py replay        --task stack_cubes --instance instance.json --traj traj.npz [--repeat 2] [--video replay.mp4]
  python rcb_robowits.py render        --task stack_cubes --instance instance.json --traj traj.npz --out replay.mp4 [--every 2]
  python rcb_robowits.py selftest      --task stack_cubes --eval-index 0 --code oracle.py --out-dir /tmp/selftest   # 3 fresh processes

Python (what the agent gets)
----------------------------
  from rcb_robowits import Session
  s = Session("stack_cubes", instance="/app/instance.json")   # ~60 s: builds the Genesis scene and compiles kernels
  s.reset()                          # back to the frozen instance state (unlimited)
  p = s.primitives()                 # thin wrappers of the low-level action: move_ee, move_joints, set_gripper, hold, ...
  s.objects()                        # task objects: name -> position, orientation_wxyz, bounds, size, ...
  s.render_frame("ego")              # RGB (H, W, 3) uint8; s.render_grid(), s.render_video(actions, path); s.VIDEO_CAMERAS
  s.record_start(); ...; actions = s.record_stop()   # (T, 16) low-level actions, one row per control step
  s.status()                         # {'success': bool, 'progress': float, 'sim_steps': int, 'resets': int, 'state_sha': str}
  s.replay(actions)                  # resets, replays open-loop, returns status (exact on the CPU backend) -> self-check
  s.save_trajectory(actions, "/app/output/trajectory.npz")
"""
from __future__ import annotations

import os
os.environ.setdefault("PYOPENGL_PLATFORM", "egl")
os.environ.setdefault("QD_OFFLINE_CACHE", "0")  # every process compiles its kernels the same way (no cache-state dependence)

import argparse
import base64
import hashlib
import json
import math
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np

ROBOWITS_ROOT = Path(os.environ.get("ROBOWITS_ROOT", "/opt/robowits"))
# Interaction log: every Session (any process) appends one line per session start/reset/record/replay/exit, with the
# control steps consumed, to RCB_SESSION_LOG (default /app/output/rcb_session_log.jsonl, collected with the artifacts).
# It records the agent's whole debugging history, not just the trajectory it hands in (the verifier reports it as
# cost: agent_sessions / agent_resets / agent_sim_steps). Set RCB_SESSION_LOG="" to disable (the verifier does).
# The same line also goes to RCB_SESSION_LOG_KEEP (default /logs/agent/rcb_session_log.jsonl, where that directory
# exists: the agent's log directory). The host's rcb-log-mirror keeps an append-only copy of it, so the record
# survives even if the agent deletes or edits the /app/output copy (user 2026-09-26).
SESSION_LOG = os.environ.get("RCB_SESSION_LOG", "/app/output/rcb_session_log.jsonl")
SESSION_LOG_KEEP = os.environ.get("RCB_SESSION_LOG_KEEP", "/logs/agent/rcb_session_log.jsonl")


def _slog(ev: str, **kw) -> None:
    if not SESSION_LOG:
        return
    line = json.dumps({"ts": time.time(), "pid": os.getpid(), "ev": ev, **kw}) + "\n"
    try:
        os.makedirs(os.path.dirname(SESSION_LOG), exist_ok=True)
        with open(SESSION_LOG, "a") as f:
            f.write(line)
    except OSError:
        pass
    if SESSION_LOG_KEEP and os.path.isdir(os.path.dirname(SESSION_LOG_KEEP)):
        try:
            with open(SESSION_LOG_KEEP, "a") as f:
                f.write(line)
        except OSError:
            pass

DEFAULT_BACKEND = os.environ.get("RCB_ROBOWITS_BACKEND", "cpu")  # physics backend; "cpu" is the bit-deterministic one

# --------------------------------------------------------------------------- task family registry
TASKS: dict[str, dict] = {
    "stack_cubes": dict(
        robowits_task="robowits/14-stack-cubes-v0",
        eval_json="dataset/robowits/eval_dataset_50/14.json",
        text="Build a stable two-layer stack so the red cube's center is above the green colored dot.",
        objects=["base cube 1", "base cube 2", "apex cube", "apex target"],
        simulator="robowits", robot="marvin-bimanual", image="robowits",
    ),
    "dominos": dict(
        robowits_task="robowits/06-dominos-v0",
        eval_json="dataset/robowits/eval_dataset_50/06.json",
        text="Push the red block onto the green target area.",
        objects=["white block 4", "white block 3", "white block 2", "white block 1", "red block", "target area"],
        simulator="robowits", robot="marvin-bimanual", image="robowits",
    ),
    'stand_pages': dict(
        robowits_task="robowits/07-stand-pages-v0",
        eval_json="dataset/robowits/eval_dataset_50/07.json",
        text='Assemble the two pages using the stabilizing bar to create a standing hinge structure.',
        objects=['page A with eyelets', 'page B with eyelets', 'stabilizing bar'],
        simulator="robowits", robot="marvin-bimanual", image="robowits",
    ),
    'align_blocks': dict(
        robowits_task="robowits/01-align-blocks-v0",
        eval_json="dataset/robowits/eval_dataset_50/01.json",
        text='Align the three cubes perfectly in a straight line.',
        objects=['long rigid ruler'],
        simulator="robowits", robot="marvin-bimanual", image="robowits",
    ),
    'align_chopsticks': dict(
        robowits_task="robowits/26-align-chopsticks-v0",
        eval_json="dataset/robowits/eval_dataset_50/26.json",
        text='Make all six chopsticks point in the same direction, with their small thin ends all facing the same way.',
        objects=['board', 'ruler'],
        simulator="robowits", robot="marvin-bimanual", image="robowits",
    ),
    'balance_board': dict(
        robowits_task="robowits/29-balance-board-v0",
        eval_json="dataset/robowits/eval_dataset_50/29.json",
        text='Place the board onto the wall and keep it balanced.',
        objects=['board', 'small wall', 'support cube'],
        simulator="robowits", robot="marvin-bimanual", image="robowits",
    ),
    'ball_into_bottle': dict(
        robowits_task="robowits/12-ball-into-bottle-v0",
        eval_json="dataset/robowits/eval_dataset_50/12.json",
        text='Transfer the ball from the blue container into the red bottle.',
        objects=['ball container', 'funnel', 'red bottle', 'small ball'],
        simulator="robowits", robot="marvin-bimanual", image="robowits",
    ),
    'ball_into_jar': dict(
        robowits_task="robowits/20-ball-into-jar-v0",
        eval_json="dataset/robowits/eval_dataset_50/20.json",
        text='Put the foam ball fully into the jar.',
        objects=['foam ball', 'glass jar'],
        simulator="robowits", robot="marvin-bimanual", image="robowits",
    ),
    'ball_onto_tower': dict(
        robowits_task="robowits/17-ball-onto-tower-v0",
        eval_json="dataset/robowits/eval_dataset_50/17.json",
        text='Place the ball stably on top of the tower.',
        objects=['ball', 'large ring', 'medium ring', 'small ring', 'tower base'],
        simulator="robowits", robot="marvin-bimanual", image="robowits",
    ),
    'collect_screws': dict(
        robowits_task="robowits/10-collect-screws-v0",
        eval_json="dataset/robowits/eval_dataset_50/10.json",
        text='Collect the screw into the container',
        objects=['container', 'dustpan', 'screw'],
        simulator="robowits", robot="marvin-bimanual", image="robowits",
    ),
    'cover_with_lid': dict(
        robowits_task="robowits/13-cover-with-lid-v0",
        eval_json="dataset/robowits/eval_dataset_50/13.json",
        text='Cover the pot precisely using one lid.',
        objects=['lid large', 'lid medium', 'pot without lid', 'small lid'],
        simulator="robowits", robot="marvin-bimanual", image="robowits",
    ),
    'cylinder_through_hole': dict(
        robowits_task="robowits/18-cylinder-through-hole-v0",
        eval_json="dataset/robowits/eval_dataset_50/18.json",
        text='Insert the long rod through the opening so it rests over the green colored patch.',
        objects=['collection_zone', 'cylindrical_peg', 'hole_plate'],
        simulator="robowits", robot="marvin-bimanual", image="robowits",
    ),
    'differentiate_cubes': dict(
        robowits_task="robowits/30-differentiate-cubes-v0",
        eval_json="dataset/robowits/eval_dataset_50/30.json",
        text='Place the wooden cube to the green target area. Keep the metal cube inside the mug.',
        objects=['metal cube', 'mug', 'target area', 'water', 'water pitcher', 'wooden cube'],
        simulator="robowits", robot="marvin-bimanual", image="robowits",
    ),
    'gap_retrieve': dict(
        robowits_task="robowits/03-gap-retrieve-v0",
        eval_json="dataset/robowits/eval_dataset_50/03.json",
        text='Place the lemon on the green target area.',
        objects=['left boundary block', 'lemon', 'right boundary block', 'target area'],
        simulator="robowits", robot="marvin-bimanual", image="robowits",
    ),
    'hold_cup': dict(
        robowits_task="robowits/09-hold-cup-v0",
        eval_json="dataset/robowits/eval_dataset_50/09.json",
        text='Put the cup on the green target area on the slope without sliding down.',
        objects=['coaster', 'cup', 'slope', 'target area'],
        simulator="robowits", robot="marvin-bimanual", image="robowits",
    ),
    'move_cube': dict(
        robowits_task="robowits/28-move-cube-v0",
        eval_json="dataset/robowits/eval_dataset_50/28.json",
        text='Move any of the three cubes to the left of the goal line.',
        objects=['cube 1', 'cube 2', 'cube 3', 'goal line', 'rough slope', 'smooth slope'],
        simulator="robowits", robot="marvin-bimanual", image="robowits",
    ),
    'pinch_card': dict(
        robowits_task="robowits/04-pinch-card-v0",
        eval_json="dataset/robowits/eval_dataset_50/04.json",
        text="Pick the bank card up from the 'small table' surface.",
        objects=['bank card', 'eraser', 'small table', 'target area', 'target cube'],
        simulator="robowits", robot="marvin-bimanual", image="robowits",
    ),
    'place_book': dict(
        robowits_task="robowits/23-place-book-v0",
        eval_json="dataset/robowits/eval_dataset_50/23.json",
        text="Move the 'thin book' onto the 'blue target mat' without moving the heavy block from its place.",
        objects=['blue target mat', 'heavy block', 'pry board', 'thin book'],
        simulator="robowits", robot="marvin-bimanual", image="robowits",
    ),
    'place_tall_box': dict(
        robowits_task="robowits/11-place-tall-box-v0",
        eval_json="dataset/robowits/eval_dataset_50/11.json",
        text='Move the rectangular box onto the green target area.',
        objects=['beam plank', 'support block left', 'support block right', 'tall cardboard box', 'target area'],
        simulator="robowits", robot="marvin-bimanual", image="robowits",
    ),
    'raise_platform': dict(
        robowits_task="robowits/24-raise-platform-v0",
        eval_json="dataset/robowits/eval_dataset_50/24.json",
        text='Place the book on the cup supports.',
        objects=['cup support 1', 'cup support 2', 'heavy book', 'support cube 1', 'support cube 2'],
        simulator="robowits", robot="marvin-bimanual", image="robowits",
    ),
    'retrieve_cube': dict(
        robowits_task="robowits/02-retrieve-cube-v0",
        eval_json="dataset/robowits/eval_dataset_50/02.json",
        text='Retrieve the cube from the container and place it on the green target area.',
        objects=['cube', 'deep narrow container', 'target area'],
        simulator="robowits", robot="marvin-bimanual", image="robowits",
    ),
    'retrieve_roll': dict(
        robowits_task="robowits/27-retrieve-roll-v0",
        eval_json="dataset/robowits/eval_dataset_50/27.json",
        text='Use the long rod to retrieve the out-of-reach roll and move it to the green target area.',
        objects=['green target area', 'hollow roll', 'long rod'],
        simulator="robowits", robot="marvin-bimanual", image="robowits",
    ),
    'roll_up_ball': dict(
        robowits_task="robowits/05-roll-up-ball-v0",
        eval_json="dataset/robowits/eval_dataset_50/05.json",
        text='Move the box into the basket.',
        objects=['box', 'high basket', 'long board'],
        simulator="robowits", robot="marvin-bimanual", image="robowits",
    ),
    'round_dough_sheet': dict(
        robowits_task="robowits/08-round-dough-sheet-v0",
        eval_json="dataset/robowits/eval_dataset_50/08.json",
        text='Flattern the dough ball and make a perfect round sheet',
        objects=['dough ball', 'large flat board', 'round cutter'],
        simulator="robowits", robot="marvin-bimanual", image="robowits",
    ),
    'seal_colander': dict(
        robowits_task="robowits/21-seal-colander-v0",
        eval_json="dataset/robowits/eval_dataset_50/21.json",
        text='Make the container hold water for a short time.',
        objects=['curved holder', 'perforated container', 'pitcher', 'water'],
        simulator="robowits", robot="marvin-bimanual", image="robowits",
    ),
    'separate_marbles_and_sand': dict(
        robowits_task="robowits/15-separate-marbles-and-sand-v0",
        eval_json="dataset/robowits/eval_dataset_50/15.json",
        text='Remove sand from the jar and keep the marbles in the jar.',
        objects=['bowl', 'colander', 'jar', 'sand'],
        simulator="robowits", robot="marvin-bimanual", image="robowits",
    ),
    'stabilize_bottle': dict(
        robowits_task="robowits/22-stabilize-bottle-v0",
        eval_json="dataset/robowits/eval_dataset_50/22.json",
        text='Make the tube stand upright in the bowl without falling for a short time.',
        objects=['bowl', 'dry_sand', 'sand_container', 'tube'],
        simulator="robowits", robot="marvin-bimanual", image="robowits",
    ),
    'stand_bulb': dict(
        robowits_task="robowits/16-stand-bulb-v0",
        eval_json="dataset/robowits/eval_dataset_50/16.json",
        text='Stand the tall object with curved bottom stably within the green target area.',
        objects=['stabilizing ring', 'tall object with curved bottom', 'target patch'],
        simulator="robowits", robot="marvin-bimanual", image="robowits",
    ),
    'water_into_mug': dict(
        robowits_task="robowits/25-water-into-mug-v0",
        eval_json="dataset/robowits/eval_dataset_50/25.json",
        text='Collect water in the mug without moving the pitcher.',
        objects=['heavy_large_object', 'mug', 'pitcher', 'water'],
        simulator="robowits", robot="marvin-bimanual", image="robowits",
    ),
    'stack_bowls': dict(
        robowits_task="robowits/19-stack-bowls-v0",
        eval_json="dataset/robowits/eval_dataset_50/19.json",
        text='Nest the smaller bowl concentrically inside the larger one.',
        objects=['large bowl', 'medium bowl'],
        simulator="robowits", robot="marvin-bimanual", image="robowits",
    ),
}

ACTION_DIM = 16
CONTROL_HZ = 30
# Videos are fragmented MP4 (index up front, a fragment per keyframe): a file whose writer never closed (a replay killed
# at a timeout or crashing) still plays up to its last fragment; a plain MP4 is unplayable without its trailing index
# (board 0051, 10-09).
MP4_FRAGMENTED = "frag_keyframe+empty_moov+default_base_moof"
MAX_STEPS = 200_000        # no step budget (the wall clock is); this only stops a runaway trajectory (~1.9 h of sim time)
TABLE_Z = 0.76
ACTION_LAYOUT = ("16 absolute joint-position targets (RoboWits JOINT_ABS): right arm Joint1-7_R (rad), right gripper width "
                 "(m, 0=closed .. 0.1=open), left arm Joint1-7_L (rad), left gripper width (m). One row per control step "
                 "(30 Hz, dt=1/30 s, 4 physics substeps). Poses are in the Genesis world frame (robot base at (0, 0, 1.08), "
                 "table top at z=0.76), quaternions are WXYZ.")

ARM_SLICE = {"right": slice(0, 7), "left": slice(8, 15)}
GRIP_INDEX = {"right": 7, "left": 15}
GRIPPER_OPEN = 0.1


def _log(*a: Any) -> None:
    print("[rcb]", *a, file=sys.stderr, flush=True)


class PrimitiveError(RuntimeError):
    """A primitive could not be planned or executed (the episode is still alive unless said otherwise)."""


# --------------------------------------------------------------------------- small geometry helpers (numpy, wxyz)
def quat_to_mat(q) -> np.ndarray:
    w, x, y, z = [float(v) for v in q]
    n = math.sqrt(w * w + x * x + y * y + z * z) or 1.0
    w, x, y, z = w / n, x / n, y / n, z / n
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def mat_to_quat(R) -> np.ndarray:
    R = np.asarray(R, dtype=np.float64)
    t = np.trace(R)
    if t > 0:
        s = math.sqrt(t + 1.0) * 2; w = 0.25 * s; x = (R[2, 1] - R[1, 2]) / s; y = (R[0, 2] - R[2, 0]) / s; z = (R[1, 0] - R[0, 1]) / s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2; w = (R[2, 1] - R[1, 2]) / s; x = 0.25 * s; y = (R[0, 1] + R[1, 0]) / s; z = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2; w = (R[0, 2] - R[2, 0]) / s; x = (R[0, 1] + R[1, 0]) / s; y = 0.25 * s; z = (R[1, 2] + R[2, 1]) / s
    else:
        s = math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2; w = (R[1, 0] - R[0, 1]) / s; x = (R[0, 2] + R[2, 0]) / s; y = (R[1, 2] + R[2, 1]) / s; z = 0.25 * s
    q = np.array([w, x, y, z]); return q / np.linalg.norm(q)


def rot_angle(Ra, Rb) -> float:
    c = (np.trace(np.asarray(Ra).T @ np.asarray(Rb)) - 1.0) / 2.0
    return float(math.acos(max(-1.0, min(1.0, c))))


def wrap_angle(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


GL2CV = np.diag([1.0, -1.0, -1.0, 1.0])   # OpenGL camera axes (x right, y up, z back) -> OpenCV (x right, y down, z forward)


def _r(a, nd: int = 7) -> list:
    """A matrix / vector as nested lists of floats rounded to `nd` decimals (JSON-ready)."""
    return np.round(np.asarray(a, dtype=np.float64), nd).tolist()


def gripper_quat(closing_yaw: float, approach=(0.0, 0.0, -1.0)) -> np.ndarray:
    """Tip orientation (wxyz) whose fingers close along the horizontal direction `closing_yaw` (rad, world x->y) and whose
    approach axis (gripper base -> fingertips) points along `approach` (default straight down). Measured tip-frame
    convention of the Pika grippers: local +z = approach axis, local +x = finger closing axis."""
    c = np.array([math.cos(closing_yaw), math.sin(closing_yaw), 0.0])
    a = np.asarray(approach, dtype=np.float64); a = a - a.dot(c) * c
    if np.linalg.norm(a) < 1e-6:
        raise ValueError("approach direction must not be parallel to the closing direction")
    a = a / np.linalg.norm(a)
    y = np.cross(a, c)
    return mat_to_quat(np.stack([c, y, a], axis=1))


def top_down_quat(closing_yaw: float, tilt: float = 0.0) -> np.ndarray:
    """gripper_quat() for a vertical approach; `tilt` (rad, >0) leans the approach direction away from the robot (+x),
    like the robot's reset pose (tilt ~1.1 rad) — useful when a fully vertical approach is out of reach."""
    a = np.array([math.sin(tilt), 0.0, -math.cos(tilt)])
    return gripper_quat(closing_yaw, a)


# --------------------------------------------------------------------------- BlenderKit models
# The BlenderKit models are never in the image (images/robowits/NOTICE). A task mounts the host's folder read-only at
# /opt/robowits/assets/blender_kit: either plaintext (<uuid>/obj.glb, fetched with your own BlenderKit key), which
# RoboWits reads directly, or our encrypted bundle (<uuid>/obj.glb.enc Fernet tokens + robowits_blenderkit.key). For the
# bundle, only the models this family loads are decrypted, into a private tmpfs dir that RoboWits finds through
# GS_GYM_ASSET_PATHS; it is deleted as soon as the scene is built. An unlimited agent is root in the same container and
# can read the key: the encryption keeps the models from being copied around, not from the agent (NOTICE).
BLENDERKIT_DIR = ROBOWITS_ROOT / "assets" / "blender_kit"
BLENDERKIT_KEY = BLENDERKIT_DIR / "robowits_blenderkit.key"


def _fernet_decrypt(token: bytes, key: bytes) -> bytes:
    """A Fernet token (github.com/fernet/spec) decrypted with the standard library (HMAC-SHA256) and the image's openssl
    (AES-128-CBC): the image has no `cryptography` package."""
    import hmac
    k = base64.urlsafe_b64decode(key.strip())
    data = base64.urlsafe_b64decode(token.strip())
    body, mac = data[:-32], data[-32:]
    if data[:1] != b"\x80" or not hmac.compare_digest(hmac.new(k[:16], body, hashlib.sha256).digest(), mac):
        raise ValueError("BlenderKit bundle: wrong key or a corrupted model file")
    return subprocess.run(["openssl", "enc", "-d", "-aes-128-cbc", "-K", k[16:].hex(), "-iv", body[9:25].hex()],
                          input=body[25:], capture_output=True, check=True).stdout


def _blenderkit_prepare(cls) -> str | None:
    """Encrypted bundle mounted: decrypt the models the RoboWits task class can load (every UUID in its source files) into
    a fresh 0700 dir under /dev/shm and put it on GS_GYM_ASSET_PATHS. Returns the dir (None for a plaintext folder)."""
    if not BLENDERKIT_KEY.is_file():
        return None
    import inspect, re, tempfile
    src = "".join(Path(inspect.getsourcefile(c)).read_text() for c in cls.__mro__ if c.__module__.startswith("gs_gym"))
    tmp = tempfile.mkdtemp(prefix="rcb_bk_", dir="/dev/shm" if os.path.isdir("/dev/shm") else None)
    key = BLENDERKIT_KEY.read_bytes()
    for uid in sorted(set(re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", src))):
        enc = BLENDERKIT_DIR / uid / "obj.glb.enc"
        if enc.is_file():
            out = Path(tmp) / "blender_kit" / uid / "obj.glb"
            out.parent.mkdir(parents=True)
            out.write_bytes(_fernet_decrypt(enc.read_bytes(), key))
    os.environ["GS_GYM_ASSET_PATHS"] = ":".join(p for p in (tmp, os.environ.get("GS_GYM_ASSET_PATHS", "")) if p)
    return tmp


def _blenderkit_cleanup(tmp: str | None) -> None:
    """Delete the decrypted models (the built scene no longer reads them) and drop the dir from GS_GYM_ASSET_PATHS."""
    if tmp:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
        os.environ["GS_GYM_ASSET_PATHS"] = ":".join(p for p in os.environ.get("GS_GYM_ASSET_PATHS", "").split(":") if p and p != tmp)

# --------------------------------------------------------------------------- session
class Session:
    def __init__(self, task: str, instance: str | Path | None = None, *, eval_index: int | None = None,
                 strict: bool = False, max_steps: int | None = None, backend: str = DEFAULT_BACKEND):
        if task not in TASKS:
            raise KeyError(f"unknown task {task!r}; known: {list(TASKS)}")
        self.task, self.spec = task, TASKS[task]
        inst, scene_entry = None, None
        if instance is not None:
            inst = json.load(open(instance))
            if inst.get("task") != task:
                raise ValueError(f"instance task {inst.get('task')} != session task {task}")
            eval_index = int(inst["eval_index"])
            scene_entry = inst.get("scene")  # the frozen scene's object poses: the task directory's own copy
        if eval_index is None:
            raise ValueError("need instance=path or eval_index=<entry of the RoboWits eval dataset>")
        self.eval_index, self.max_steps, self.backend = int(eval_index), int(max_steps or MAX_STEPS), backend

        import torch
        import genesis as gs
        import gs_gym
        self.th, self.gs = torch, gs
        for kind in ("cvx", "ptc"):
            if inst and inst.get(f"genesis_{kind}"):
                self._seed_cache(inst[f"genesis_{kind}"], kind)
        if not getattr(gs, "_initialized", False):
            kw = {"backend": gs.gpu if backend == "gpu" else gs.cpu}
            try:
                gs.init(seed=0, logging_level="warning", **kw)
            except TypeError:
                gs.init(**kw)
        # Scene source: the instance file's embedded entry (self-contained task, what the verifier uses) or, when exploring
        # other scenes by index, the benchmark's own dataset shipped in the base image.
        if scene_entry is not None:
            import tempfile
            self._scene_dir = tempfile.mkdtemp(prefix="rcb_scene_")
            dataset_json = str(Path(self._scene_dir) / "scene.json")
            Path(dataset_json).write_text(json.dumps([scene_entry]))
            dataset_idx, self.scene_source = 0, "instance"
        else:
            dataset_json, dataset_idx, self.scene_source = str(ROBOWITS_ROOT / self.spec["eval_json"]), self.eval_index, "dataset"
        t0 = time.time()
        _log(f"building {self.spec['robowits_task']} (eval index {self.eval_index}, scene from {self.scene_source}, backend={backend}); ~60 s ...")
        cls = gs_gym.get_task_class(self.spec["robowits_task"])
        bk_tmp = _blenderkit_prepare(cls)   # encrypted BlenderKit bundle: this family's models, decrypted for the build only
        import atexit
        atexit.register(_blenderkit_cleanup, bk_tmp)
        self.env = cls(genesis_backend=backend, device="cuda" if backend == "gpu" else "cpu", show_viewer=False,
                       eval_dataset_json=dataset_json, control_mode="JOINT_ABS", max_episode_steps=10 ** 9)
        self.scene = self.env._scene.scene
        self.robot = self.env._robot
        self.device = self.env._device
        self.base_pos = np.asarray(self.robot.args.position, dtype=np.float64)
        self._recording: list[np.ndarray] | None = None
        self._video: dict | None = None
        self.episode_done = False
        self.n_steps = 0
        self._resets = 0
        self._total_steps = 0
        _slog("session_start", task=task, eval_index=self.eval_index)
        import atexit
        atexit.register(lambda: _slog("session_end", task=task, resets=self._resets, sim_steps=self._total_steps + self.n_steps))

        # canonical instance build (the verifier does exactly this in its fresh process). RoboWits draws some placements
        # from an unseeded generator (ball_into_jar's foam ball XY): a fixed seed makes the build the same in every process
        self.env.seed(0)
        self.env.set_eval_dataset_idx(dataset_idx)
        self.env.reset()
        _blenderkit_cleanup(bk_tmp)          # the scene is built: the decrypted models are deleted
        self.scene_entry = scene_entry if scene_entry is not None else self._dataset_entry(dataset_idx)
        self.S0 = self.scene.get_state()
        self._targets = self.joint_positions()
        self.instance_sha = self.state_sha()
        # Frozen-state check: exact sha (bit-reproducible on one host), else every object / joint pose within tolerance
        # (a different CPU or compiler may change the last bits; a wrong dataset or simulator version moves objects by mm).
        expected = inst.get("state_sha") if inst else None
        self.instance_exact = expected is None or expected == self.instance_sha
        self.instance_matches = self.instance_exact or (inst is not None and self._poses_match(inst))
        if not self.instance_exact:
            if self.instance_matches:
                _log(f"WARNING: state sha {self.instance_sha} != {expected} but every object/joint pose matches within tolerance (different host?)")
            else:
                msg = f"instance state sha {self.instance_sha} != expected {expected} and poses differ (asset / simulator / dataset drift?)"
                if strict:
                    raise RuntimeError(msg)
                _log("WARNING:", msg)
        # Genesis keeps solver internals (warm starts) outside SimState: a rollout that continues straight from the build
        # differs in the last bits from one that starts after scene.reset(S0). Every episode -- live or replayed, in this
        # process or a fresh one -- therefore starts from the restored snapshot, so all of them integrate identically.
        self._restore()
        if self.state_sha() != self.instance_sha:
            raise RuntimeError("snapshot restore changed the frozen state (Genesis version drift?)")
        _log(f"instance ready in {time.time() - t0:.0f}s; state_sha={self.instance_sha}; max_steps={self.max_steps}")

    @staticmethod
    def _seed_cache(entries: dict, kind: str) -> None:
        """Put the frozen instance's Genesis cache files (base64 in instance.json) into Genesis' cache before the scene is
        built: convex decompositions (kind "cvx") and physics-based particle samples (kind "ptc"). Genesis runs CoACD on
        meshes loaded with coacd_options and samples "pbs" particle bodies (MPM, SPH) with SPlisHSPlasH's volume sampler;
        neither is reproducible in another process (other hulls or other particles, hence another frozen state). With the
        cache seeded every process (agent, verifier, limited service) builds the same scene, without recomputing either."""
        from genesis.utils import misc
        d = Path(getattr(misc, f"get_{kind}_cache_dir")()); d.mkdir(parents=True, exist_ok=True)
        for name, b64 in entries.items():
            data = base64.b64decode(b64)
            p = d / Path(name).name
            if not p.exists() or p.read_bytes() != data:
                p.write_bytes(data)

    def _dataset_entry(self, idx: int) -> dict:
        """The placement entry (object -> pos / euler / quat) of dataset entry `idx`, as the env consumes it."""
        ds = self.env._eval_dataset or {}
        key = self.env._eval_dataset_keys[idx] if self.env._eval_dataset_keys else str(idx)
        raw = ds.get(key, {}).get("objs_info", {})
        return {n: {k: v for k, v in o.items() if k in ("pos", "quat", "euler")} for n, o in raw.items() if n in self.env._entities}

    def _poses_match(self, inst: dict, pos_tol: float = 2e-3, quat_tol: float = 2e-2, joint_tol: float = 2e-3) -> bool:
        try:
            objs = self.objects()
            for name, ref in (inst.get("objects") or {}).items():
                cur = objs.get(name)
                if cur is None:
                    return False
                if np.max(np.abs(np.asarray(cur["position"]) - np.asarray(ref["position"]))) > pos_tol:
                    return False
                if "orientation_wxyz" not in cur or "orientation_wxyz" not in ref:  # particle bodies: centroid only
                    continue
                q0, q1 = np.asarray(cur["orientation_wxyz"]), np.asarray(ref["orientation_wxyz"])
                if min(np.max(np.abs(q0 - q1)), np.max(np.abs(q0 + q1))) > quat_tol:
                    return False
            ref_q = inst.get("reset_joint_targets")
            if ref_q is not None and np.max(np.abs(self.joint_positions() - np.asarray(ref_q))) > joint_tol:
                return False
            return bool(inst.get("objects"))
        except Exception as exc:  # noqa: BLE001
            _log("pose comparison failed:", repr(exc)[:120])
            return False

    # ---- state helpers
    def _flat_state(self) -> np.ndarray:
        st = self.scene.get_state()
        parts = []
        for sol in st.solvers_state:
            for name in sorted(n for n in dir(sol) if not n.startswith("_")):
                v = getattr(sol, name, None)
                if hasattr(v, "detach"):
                    parts.append(v.detach().cpu().double().numpy().ravel())
                elif hasattr(v, "to_numpy"):
                    parts.append(np.asarray(v.to_numpy(), dtype=np.float64).ravel())
        return np.concatenate(parts) if parts else np.zeros(0)

    def state_sha(self) -> str:
        return hashlib.sha1(np.ascontiguousarray(self._flat_state()).tobytes()).hexdigest()[:16]

    # ---- episode control
    def reset(self) -> None:
        """Return to the frozen instance state (exact state restore; controller targets back to the reset pose). On the CPU
        backend a replay after reset() reproduces the fresh-process result bit-exactly."""
        _slog("reset", task=self.task, n=self._resets + 1, sim_steps_before=self.n_steps)
        self._resets += 1
        self._total_steps += self.n_steps
        self._restore()

    def _restore(self) -> None:
        self._recording = None
        self.episode_done = False
        self.n_steps = 0
        self.scene.reset(self.S0)
        self.robot.hold_reset_position()
        self.env._step_count = 0
        self._targets = self.joint_positions()

    def step(self, action) -> bool:
        """Apply one low-level action (16 joint targets, see ACTION_LAYOUT) for one control step (1/30 s).
        Returns True once MAX_STEPS control steps have run (a runaway guard, not a budget); further steps raise."""
        a = np.asarray(action, dtype=np.float32).reshape(-1)
        if a.size != ACTION_DIM:
            raise ValueError(f"action must have {ACTION_DIM} entries, got {a.size}")
        if not np.all(np.isfinite(a)):
            raise ValueError("action contains nan/inf")
        if self.episode_done:
            raise PrimitiveError(f"{self.max_steps} control steps reached (runaway guard); call reset() before stepping again")
        if self._recording is not None:
            self._recording.append(a.copy())
        self.env.apply_action(self.th.as_tensor(a, device=self.device))
        self._targets = a.astype(np.float64)
        self.n_steps += 1
        if self._video is not None and self.n_steps % self._video["every"] == 0:
            self._video_add()
        if self.n_steps >= self.max_steps:
            self.episode_done = True
        return self.episode_done

    def hold_action(self) -> np.ndarray:
        """The action that keeps the current joint targets (what the robot does when a primitive is idle)."""
        return self._targets.copy()

    def status(self) -> dict[str, Any]:
        return {"success": bool(self.env._check_success().item()), "progress": round(float(self.env.get_reward()[0].item()), 4),
                "sim_steps": int(self.n_steps), "resets": self._resets, "state_sha": self.state_sha()}

    # ---- recording / trajectories
    def record_start(self) -> None:
        self._recording = []

    def record_stop(self) -> np.ndarray:
        acts = np.stack(self._recording) if self._recording else np.zeros((0, ACTION_DIM), np.float32)
        self._recording = None
        _slog("record", task=self.task, n_actions=int(len(acts)), success=bool(self.env._check_success().item()))
        return acts.astype(np.float32)

    def save_trajectory(self, actions: np.ndarray, path: str | Path, meta: dict | None = None) -> None:
        np.savez(path, actions=np.asarray(actions, dtype=np.float32), task=self.task, robowits_task=self.spec["robowits_task"],
                 eval_index=self.eval_index, instance_sha=self.instance_sha, action_dim=ACTION_DIM, action_layout=ACTION_LAYOUT,
                 meta=json.dumps(meta or {}))

    def replay(self, actions: np.ndarray) -> dict[str, Any]:
        """Open-loop replay after reset() (exact on the CPU backend): what the verifier does, twice, in its own process."""
        self.reset()
        for a in np.asarray(actions, dtype=np.float32):
            if self.step(a):
                break
        st = self.status()
        _slog("replay", task=self.task, n_actions=int(len(actions)), success=st["success"])
        return st

    # ---- rendering (same API as the RoboTwin tasks' Session: render_frame / render_grid / render_video)
    VIDEO_CAMERAS: tuple[str, ...] = ("ego", "wrist_right", "wrist_left")   # ego: static, above and behind the robot

    def render_frame(self, camera: str = "ego", size: tuple[int, int] | None = None) -> np.ndarray:
        """RGB (H, W, 3) uint8 from one camera (848x480; see VIDEO_CAMERAS); `size=(w, h)` resizes. Rendering does not
        touch the physics state."""
        img = np.ascontiguousarray(np.asarray(self.env.render_frame(0, camera))[..., :3]).astype(np.uint8)
        if size is not None and (img.shape[1], img.shape[0]) != tuple(size):
            from PIL import Image
            img = np.asarray(Image.fromarray(img).resize(tuple(size), Image.BILINEAR))
        return img

    def render_grid(self, cameras: tuple[str, ...] = VIDEO_CAMERAS, cols: int = 3, size: tuple[int, int] = (424, 240)) -> np.ndarray:
        """One image tiling `cameras` (row-major, `cols` per row; each resized to `size`)."""
        tiles = [self.render_frame(c, size=size) for c in cameras]
        while len(tiles) % cols:
            tiles.append(np.zeros_like(tiles[0]))
        return np.concatenate([np.concatenate(tiles[i:i + cols], axis=1) for i in range(0, len(tiles), cols)], axis=0)

    def render_video(self, actions: np.ndarray, path: str | Path, *, every: int = 2, fps: int = 15,
                     cameras: tuple[str, ...] = VIDEO_CAMERAS, cols: int = 3, size: tuple[int, int] = (424, 240)) -> dict[str, Any]:
        """Replay `actions` from the frozen instance (reset() first) and write an MP4 of `cameras` tiled, one frame every
        `every` control steps (+ `<path>.last.png`). Returns the final status plus n_frames and the video path."""
        import imageio.v2 as imageio
        self.reset()
        path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
        n = 0
        # frames go straight to the encoder: a long episode's frames would not fit in memory
        with imageio.get_writer(str(path), fps=fps, format="FFMPEG", codec="libx264", macro_block_size=1,
                                output_params=["-movflags", MP4_FRAGMENTED]) as w:
            def grab() -> np.ndarray:
                nonlocal n
                f = self.render_grid(cameras, cols=cols, size=size); w.append_data(f); n += 1
                return f
            grab()
            for i, a in enumerate(np.asarray(actions, dtype=np.float32)):
                if self.step(a):
                    break
                if (i + 1) % every == 0:
                    grab()
            last = grab()
        imageio.imwrite(str(path.with_suffix(".last.png")), last)
        return {**self.status(), "n_frames": n, "video": str(path)}

    # ---- video while stepping (ego camera + both wrist cameras; the verifier's replay.mp4)
    def start_video(self, path: str | Path, fps: int = 15, every: int | None = None) -> None:
        import imageio.v2 as imageio
        every = every or max(1, CONTROL_HZ // fps)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        # frames go straight to the encoder: a long episode's frames would not fit in memory
        w = imageio.get_writer(str(path), fps=fps, format="FFMPEG", codec="libx264", macro_block_size=1,
                               output_params=["-movflags", MP4_FRAGMENTED])
        self._video = {"path": str(path), "every": every, "writer": w, "last": None}
        self._video_add()

    def _video_add(self) -> None:
        f = self._video_frame(); self._video["writer"].append_data(f); self._video["last"] = f

    def _video_frame(self) -> np.ndarray:
        ego = self.env.render_frame(0, "ego")
        wr = self.env.render_frame(0, "wrist_right")[::2, ::2]
        wl = self.env.render_frame(0, "wrist_left")[::2, ::2]
        side = np.concatenate([wr, wl], axis=0)
        if side.shape[0] != ego.shape[0]:
            pad = np.zeros((ego.shape[0] - side.shape[0], side.shape[1], 3), np.uint8) if side.shape[0] < ego.shape[0] else None
            side = np.concatenate([side, pad], axis=0) if pad is not None else side[: ego.shape[0]]
        return np.ascontiguousarray(np.concatenate([ego, side], axis=1))

    def stop_video(self) -> str | None:
        if self._video is None:
            return None
        import imageio.v2 as imageio
        v, self._video = self._video, None
        v["writer"].close()
        imageio.imwrite(str(Path(v["path"]).with_suffix(".last.png")), v["last"])
        return v["path"]

    # ---- objects / robot state
    def objects(self) -> dict[str, dict]:
        """Task objects by name -> position (world), orientation_wxyz, euler_xyz, bounds (AABB [[min],[max]]), size, velocity, fixed.
        Particle objects (MPM/SPH/PBD: dough, sand, water) have no orientation: they report material "particle", the particle
        centroid as position, the mean particle velocity, the particle AABB and n_particles."""
        from gs_gym.envs.robowits.placement import _is_fixed_entity
        names = [n for n in self.env._entities if n != "table"]
        info = self.env.collect_objs_info(names)
        out = {}
        for n in names:
            ent = self.env.get_entity(n)
            o = info.get(n)
            if o is None:
                continue
            if o.get("material") == "particle":
                c, v = (o["pos"].mean(axis=0), o["vel"].mean(axis=0)) if len(o["pos"]) else (np.zeros(3), np.zeros(3))
                out[n] = {"material": "particle", "position": [round(float(x), 5) for x in c],
                          "bounds": [[round(float(x), 5) for x in row] for row in o["bounds"]],
                          "velocity": [round(float(x), 5) for x in v], "n_particles": int(len(o["pos"]))}
                continue
            quat = ent.get_quat()[0].detach().cpu().numpy()
            out[n] = {"position": [round(float(x), 5) for x in o["pos"]], "orientation_wxyz": [round(float(x), 6) for x in quat],
                      "euler_xyz": [round(float(x), 5) for x in o["euler"]], "bounds": [[round(float(x), 5) for x in row] for row in o["bounds"]],
                      "size": [round(float(x), 5) for x in self.env._entities[n].get("size", (0, 0, 0))],
                      "velocity": [round(float(x), 5) for x in o["vel"]], "fixed": bool(_is_fixed_entity(ent))}
        return out

    def object_pose(self, name: str) -> tuple[np.ndarray, np.ndarray]:
        """(position(3), quaternion wxyz(4)) of an object in the world frame; for a particle object, (particle centroid, identity)."""
        ent = self.env.get_entity(name)
        if ent is None:
            raise KeyError(f"unknown object {name!r}; known: {[n for n in self.env._entities if n != 'table']}")
        if not hasattr(ent, "get_quat"):
            return self._particles(ent).mean(axis=0), np.array([1.0, 0.0, 0.0, 0.0])
        return ent.get_pos()[0].detach().cpu().numpy().astype(np.float64), ent.get_quat()[0].detach().cpu().numpy().astype(np.float64)

    def _particles(self, ent) -> np.ndarray:
        return ent.get_particles_pos()[0].detach().cpu().numpy().astype(np.float64)

    def object_bounds(self, name: str) -> np.ndarray:
        """Axis-aligned bounding box [[xmin,ymin,zmin],[xmax,ymax,zmax]] of an object (world frame)."""
        from gs_gym.envs.robowits import utils as _u
        ent = self.env.get_entity(name)
        if ent is not None and not hasattr(ent, "get_quat"):
            p = self._particles(ent)
            return np.array([p.min(axis=0), p.max(axis=0)])
        return _u.get_AABB(ent, self.device).cpu().numpy()[0].astype(np.float64)

    def joint_positions(self) -> np.ndarray:
        """Current joint positions as a 16-vector in action layout (gripper entries = finger1 + finger2 = width)."""
        q = self.robot.joint_positions[0].detach().cpu().numpy().astype(np.float64)
        return np.concatenate([q[0:7], [q[7] + q[8]], q[9:16], [q[16] + q[17]]])

    def ee_pose(self, arm: str) -> tuple[np.ndarray, np.ndarray]:
        """(position(3), quaternion wxyz(4)) of the gripper tip frame (Gripper_Tip_R/L) in the world frame."""
        pose = (self.robot.right_ee_pose if arm == "right" else self.robot.left_ee_pose)[0].detach().cpu().numpy().astype(np.float64)
        return pose[:3], pose[3:7]

    def gripper_width(self, arm: str) -> float:
        return float(self.joint_positions()[GRIP_INDEX[arm]])

    def joint_velocities(self) -> np.ndarray:
        """Measured joint velocities as a 16-vector in action layout (rad/s; gripper entries = opening rate, m/s)."""
        v = self.robot._dof_to_sequential(self.robot.robot_entity.get_dofs_velocity())[0].detach().cpu().numpy().astype(np.float64)
        return np.concatenate([v[0:7], [v[7] + v[8]], v[9:16], [v[16] + v[17]]])

    def joint_efforts(self) -> np.ndarray:
        """The force each PD drive applied at the last physics step, as a 16-vector in action layout (N m; gripper entries
        = the two fingers' sum, N): a motor-current analogue that rises when the arm pushes against something."""
        f = self.robot._dof_to_sequential(self.robot.robot_entity.get_dofs_control_force())[0].detach().cpu().numpy().astype(np.float64)
        return np.concatenate([f[0:7], [f[7] + f[8]], f[9:16], [f[16] + f[17]]])

    # ---- inverse kinematics (RoboWits' own pink/pinocchio solver; targets in the robot base frame internally)
    def ik(self, arm: str, pos, quat_wxyz) -> tuple[np.ndarray, float, float]:
        """Solve the 7 joint targets of `arm` ('left'|'right') that put its gripper tip at world pose (pos, quat_wxyz).
        Returns (q7, position_error_m, rotation_error_rad) of the (joint-limit-clamped) solution; no exception on failure."""
        if arm not in ARM_SLICE:
            raise ValueError("arm must be 'left' or 'right'")
        r = self.robot
        solver = r._get_ik_solver()
        allq = r.robot_entity.get_dofs_position()[0].detach().cpu().numpy()
        cur = np.concatenate([allq[r.left_arm_dofs], allq[r.left_gripper_dofs], allq[r.right_arm_dofs], allq[r.right_gripper_dofs]])
        solver.update_configuration(cur)
        frame = r._ee_link_right_name if arm == "right" else r._ee_link_left_name
        target = np.asarray(pos, dtype=np.float64) - self.base_pos
        rot = quat_to_mat(quat_wxyz)
        q = solver.inverse_kinematics(frame_name=frame, target_position=target, target_rotation=rot, max_solver_iters=200)
        sl = slice(9, 16) if arm == "right" else slice(0, 7)
        lo = (r.right_arm_lower if arm == "right" else r.left_arm_lower).cpu().numpy()
        hi = (r.right_arm_upper if arm == "right" else r.left_arm_upper).cpu().numpy()
        q_arm = np.clip(q[sl], lo, hi)
        q_full = np.array(q, dtype=np.float64); q_full[sl] = q_arm
        solver.update_configuration(q_full)
        p, R = solver.forward_kinematics(frame)
        return q_arm.astype(np.float64), float(np.linalg.norm(p - target)), rot_angle(R, rot)

    # ---- cameras, depth, robot spec, stateless kinematics (the same data the limited service's /spec and /kinematics
    # serve, docs/STANDARD_MODE.md rcb-limited/2.2). Nothing here steps physics or changes the simulator state.
    def _link_T(self, link) -> np.ndarray:
        p = link.get_pos(); q = link.get_quat()
        T = np.eye(4)
        T[:3, :3] = quat_to_mat(np.asarray(q.cpu() if hasattr(q, "cpu") else q, dtype=np.float64).reshape(-1)[:4])
        T[:3, 3] = np.asarray(p.cpu() if hasattr(p, "cpu") else p, dtype=np.float64).reshape(-1)[:3]
        return T

    def camera_info(self, cameras=None) -> dict[str, dict]:
        """Per camera, for the current state: intrinsic_cv (3x3), extrinsic_cv (3x4 world -> camera, OpenCV axes: x right, y
        down, z forward), cam2world_gl (4x4 camera -> world, OpenGL axes: x right, y up, z backward), image_size [W, H],
        mount ({"type": "static", ...} or {"type": "link", "parent_link", "link_T_cam_cv"}: world_T_cam = link pose @
        link_T_cam_cv) and moves. A pixel (u, v) of render_frame / render_depth sees u = fx X/Z + cx, v = fy Y/Z + cy."""
        out = {}
        for name in (cameras or self.VIDEO_CAMERAS):
            cam = self.env._cameras[name]; o = cam._options
            W, H = int(o.res[0]), int(o.res[1]); f = (H / 2.0) / math.tan(math.radians(float(o.fov)) / 2.0)   # vertical fov
            if cam._link is not None:
                off = np.asarray(o.offset_T, dtype=np.float64)
                T_gl = self._link_T(cam._link) @ off
                mount = {"type": "link", "parent_link": cam._link.name, "link_T_cam_cv": _r(off @ GL2CV)}
            else:
                T_gl = np.asarray(cam._camera_wrapper.transform, dtype=np.float64).reshape(4, 4)
                mount = {"type": "static", "extrinsic_cv": _r(np.linalg.inv(T_gl @ GL2CV)[:3]), "cam2world_gl": _r(T_gl)}
            out[name] = {"intrinsic_cv": _r([[f, 0.0, W / 2.0], [0.0, f, H / 2.0], [0.0, 0.0, 1.0]]),
                         "extrinsic_cv": _r(np.linalg.inv(T_gl @ GL2CV)[:3]), "cam2world_gl": _r(T_gl), "image_size": [W, H],
                         "mount": mount, "moves": cam._link is not None}
        return out

    def render_depth(self, camera: str = "ego", size: tuple[int, int] | None = None) -> np.ndarray:
        """z-depth (H, W) float32 in metres (distance along the camera's optical axis), pixel-aligned with
        render_frame(camera) (same size); 0 = no reading. `size=(w, h)` resizes (nearest neighbour). Rendering does not
        touch the physics state."""
        cam = self.env._cameras[camera]
        cam.read()                                   # the current state's render: camera pose and scene up to date
        res = cam._shared_metadata.renderer.render_camera(cam._camera_wrapper, rgb=False, depth=True, segmentation=False, normal=False)
        d = np.array(res[1], dtype=np.float32).reshape(int(cam._options.res[1]), int(cam._options.res[0]))
        d[~np.isfinite(d) | (d <= 0) | (d >= float(cam._options.far) * 0.999)] = 0.0
        if size is not None and (d.shape[1], d.shape[0]) != tuple(size):
            from PIL import Image
            d = np.asarray(Image.fromarray(d).resize(tuple(size), Image.NEAREST), dtype=np.float32)
        return d

    def _kin(self):
        """Our own pinocchio model of the robot's URDF (the one RoboWits' IK uses), separate from the live controller's:
        FK and IK depend only on their arguments."""
        if getattr(self, "_kin_state", None) is None:
            import pinocchio as pin
            from gs_gym.solvers.kinematics import KinematicsSolver
            r = self.robot
            home = r.reset_joint_positions[0].detach().cpu().numpy().astype(np.float64)       # R arm, R fingers, L arm, L fingers
            ks = KinematicsSolver(r._urdf_path, initial_q=np.concatenate([home[9:16], home[16:18], home[0:7], home[7:9]]))
            model = ks.robot.model
            finger = {model.getJointId(n) for n in r.RIGHT_GRIPPER_JOINTS + r.LEFT_GRIPPER_JOINTS}
            links = [fr.name for fr in model.frames if fr.type == pin.FrameType.BODY and fr.parentJoint not in finger and fr.name != "universe"]
            idx = {n: model.joints[model.getJointId(n)].idx_q for n in r.RIGHT_ARM_JOINTS + r.LEFT_ARM_JOINTS + r.RIGHT_GRIPPER_JOINTS + r.LEFT_GRIPPER_JOINTS}
            self._kin_state = {"pin": pin, "ks": ks, "model": model, "data": model.createData(), "links": links, "idx": idx,
                               "home": home, "names": list(r.RIGHT_ARM_JOINTS) + list(r.LEFT_ARM_JOINTS)}
        return self._kin_state

    def _kin_q(self, q14) -> np.ndarray:
        k = self._kin(); q = np.zeros(k["model"].nq)
        for n, v in zip(k["names"], np.asarray(q14, dtype=np.float64).reshape(-1)):
            q[k["idx"][n]] = v
        return q

    def _kin_fk(self, q14, links) -> dict[str, np.ndarray]:
        k = self._kin(); pin = k["pin"]
        pin.framesForwardKinematics(k["model"], k["data"], self._kin_q(q14))
        out = {}
        for n in links:
            M = k["data"].oMf[k["model"].getFrameId(n)]
            out[n] = np.concatenate([np.asarray(M.translation) + self.base_pos, mat_to_quat(np.asarray(M.rotation))])
        return out

    def kinematics_spec(self) -> dict:
        """What kinematics() answers: joint layout, frames, conventions (the limited service's spec["kinematics"])."""
        k = self._kin()
        tips = [self.robot._ee_link_right_name, self.robot._ee_link_left_name]
        return {"endpoint": "/kinematics", "stateless": True, "joint_names": list(k["names"]), "frame": "world", "quaternion_order": "wxyz",
                "links": list(k["links"]), "tcp_frames": tips, "ee_frames": tips, "ik_targets": tips,
                "ik": {"solver": "pink (pinocchio differential IK, quadprog QP) on the robot's URDF, started from the seed (default: the "
                                 "reset pose), with a small pull towards the seed and the reset pose", "joints": "the 7 joints of each arm whose tip "
                                 "is a target; the other arm keeps its seed", "collision": "none", "tol_pos_m": 0.002, "tol_rot_rad": 0.02,
                       "max_iters": 200},
                "note": "q = the 14 arm joints (right first, as proprio); the finger joints do not move any listed frame"}

    def kinematics(self, req: dict) -> dict:
        """Stateless FK / IK on the robot's kinematic model (never the simulator): the limited service's /kinematics.
        {"op": "fk", "q": 14 arm joints, "links": [...]} -> {"ok", "op", "frame", "poses": {link: [x,y,z, qw,qx,qy,qz]}} (world);
        {"op": "ik", "targets": {"Gripper_Tip_R": [x,y,z, qw,qx,qy,qz], ...}, "seed": q14, "tol_pos_m", "tol_rot_rad",
        "max_iters"} -> {"ok", "op", "frame", "q": q14 | None, "error": {frame: {"pos_m", "rot_rad"}}}."""
        k = self._kin(); spec = self.kinematics_spec(); n = len(k["names"])
        op = req.get("op")
        if req.get("base_pose") is not None:
            raise ValueError("base_pose: this robot's base is fixed (kinematics frame = world)")
        if op == "fk":
            q = np.asarray(req.get("q"), dtype=np.float64).reshape(-1)
            links = req.get("links") or spec["links"]
            if q.size != n or not np.all(np.isfinite(q)) or any(l not in spec["links"] for l in links):
                raise ValueError(f"fk needs q ({n} finite values) and links from {spec['links']}")
            return {"ok": True, "op": "fk", "frame": "world", "poses": {l: [float(v) for v in p] for l, p in self._kin_fk(q, links).items()}}
        if op != "ik":
            raise ValueError("op must be 'fk' or 'ik'")
        tg = req.get("targets") or {}
        if not tg or any(f not in spec["ik_targets"] for f in tg):
            raise ValueError(f"ik targets must be frames from {spec['ik_targets']}")
        ik = spec["ik"]
        tol_p, tol_r = float(req.get("tol_pos_m", ik["tol_pos_m"])), float(req.get("tol_rot_rad", ik["tol_rot_rad"]))
        it = int(req.get("max_iters", ik["max_iters"]))
        home = k["home"]
        seed = np.asarray(req["seed"], dtype=np.float64).reshape(-1) if req.get("seed") is not None else np.concatenate([home[0:7], home[9:16]])
        if seed.size != n or not np.all(np.isfinite(seed)):
            raise ValueError(f"seed must be {n} finite values")
        frames = list(tg); P = [np.asarray(tg[f][:3], dtype=np.float64) - self.base_pos for f in frames]
        R = [quat_to_mat(np.asarray(tg[f][3:7], dtype=np.float64)) for f in frames]
        q_seed = self._kin_q(seed); q_seed[[k["idx"][j] for j in self.robot.RIGHT_GRIPPER_JOINTS + self.robot.LEFT_GRIPPER_JOINTS]] = 0.025
        k["ks"].update_configuration(q_seed)
        qs = np.asarray(k["ks"].inverse_kinematics(frame_name=frames, target_position=P, target_rotation=R, max_solver_iters=it), dtype=np.float64)
        sol = np.array([qs[k["idx"][j]] for j in k["names"]])
        for arm, sl, tip in (("right", slice(0, 7), self.robot._ee_link_right_name), ("left", slice(7, 14), self.robot._ee_link_left_name)):
            if tip not in tg:
                sol[sl] = seed[sl]                   # an arm without a target keeps its seed
        got = self._kin_fk(sol, frames)
        err = {f: (float(np.linalg.norm(got[f][:3] - np.asarray(tg[f][:3], dtype=np.float64))), rot_angle(quat_to_mat(got[f][3:]), R[i]))
               for i, f in enumerate(frames)}
        ok = all(e[0] <= tol_p and e[1] <= tol_r for e in err.values())
        return {"ok": bool(ok), "op": "ik", "frame": "world", "q": [float(v) for v in sol],
                "error": {f: {"pos_m": e[0], "rot_rad": e[1]} for f, e in err.items()}}

    def robot_spec(self) -> dict:
        """The robot's spec sheet (the limited service's spec["robot_spec"]): joints in order with their limits, grippers,
        controller and gains, tool frames. Only the robot: nothing about the scene."""
        r = self.robot; ent = r.robot_entity; k = self._kin(); model = k["model"]
        lo, hi = [np.asarray(x.cpu() if hasattr(x, "cpu") else x, dtype=np.float64).reshape(-1) for x in ent.get_dofs_limit()]
        kp = np.asarray(ent.get_dofs_kp().cpu(), dtype=np.float64).reshape(-1); kv = np.asarray(ent.get_dofs_kv().cpu(), dtype=np.float64).reshape(-1)
        frng = np.asarray(ent.get_dofs_force_range()[1].cpu(), dtype=np.float64).reshape(-1)
        joints, gains = [], {}
        for side, arm_dofs, grip_dofs, arm_names, grip_names in (
                ("right", r.right_arm_dofs, r.right_gripper_dofs, r.RIGHT_ARM_JOINTS, r.RIGHT_GRIPPER_JOINTS),
                ("left", r.left_arm_dofs, r.left_gripper_dofs, r.LEFT_ARM_JOINTS, r.LEFT_GRIPPER_JOINTS)):
            for d, nme, typ, unit, grp in [(d, nme, "revolute", "rad", f"arm_{side}") for d, nme in zip(arm_dofs, arm_names)] + \
                                          [(d, nme, "prismatic", "m", f"gripper_{side}") for d, nme in zip(grip_dofs, grip_names)]:
                jid = model.getJointId(nme); vi = model.joints[jid].idx_v
                joints.append({"name": nme, "type": typ, "unit": unit, "position_limits": [round(float(lo[d]), 6), round(float(hi[d]), 6)],
                               "velocity_limit": None, "effort_limit": round(float(frng[d]), 6), "group": grp,
                               "rated_velocity": round(float(model.velocityLimit[vi]), 6), "rated_effort": round(float(model.effortLimit[vi]), 6),
                               "rated_source": "the limits declared in the robot's URDF (RoboWits' marvin_bimanual model)",
                               "note": "velocity_limit: the simulation enforces none (the PD tracking sets the speed); effort_limit: the "
                                       "simulator's drive force clamp; rated_*: the URDF's values"})
                gains[nme] = {"stiffness": float(kp[d]), "damping": float(kv[d])}
        tcp = {}
        for side, tip, gbase in (("right", r._ee_link_right_name, r.GRIPPER_BASE_LINK_RIGHT), ("left", r._ee_link_left_name, r.GRIPPER_BASE_LINK_LEFT)):
            f = self._kin_fk(np.concatenate([k["home"][0:7], k["home"][9:16]]), [gbase, tip])
            Tb, Tt = np.eye(4), np.eye(4)
            Tb[:3, :3], Tb[:3, 3] = quat_to_mat(f[gbase][3:]), f[gbase][:3]; Tt[:3, :3], Tt[:3, 3] = quat_to_mat(f[tip][3:]), f[tip][:3]
            tcp[tip] = {"parent_link": gbase, "link_T_frame": _r(np.linalg.inv(Tb) @ Tt),
                        "definition": f"the {side} Pika gripper's tip frame (URDF link {tip}): the point between the fingertips (TCP); "
                                      "+z = approach direction (gripper base -> fingertips), +x = the direction the fingers close along. "
                                      "The ee_pose action, the proprio end-effector pose and the IK use this frame."}
        grip = {side: {"joints": list(g), "opening_m": [0.0, float(GRIPPER_OPEN)], "tcp_frame": tip,
                       "command": f"joint_position entry {side}_gripper (index {GRIP_INDEX[side]}) and the ee_pose {side}_gripper entry: the "
                                  f"target opening in metres, 0 = closed .. {GRIPPER_OPEN} = open, split equally between the two fingers "
                                  "(each prismatic 0..0.05 m, PD position control); interpolated with the arm joints between rows; closing on "
                                  "an object squeezes it with the PD force (no assisted grasping)"}
                for side, g, tip in (("right", r.RIGHT_GRIPPER_JOINTS, r._ee_link_right_name), ("left", r.LEFT_GRIPPER_JOINTS, r._ee_link_left_name))}
        return {"name": "marvin-bimanual", "description": "two 7-DoF Marvin arms on a fixed base, each with a Pika parallel gripper and a "
                                                            "wrist camera (RoboWits on Genesis 0.4.7, CPU physics)",
                "base": {"type": "fixed", "pose": [float(v) for v in self.base_pos] + [1.0, 0.0, 0.0, 0.0],
                         "note": "world pose of the kinematic root (x y z qw qx qy qz): the arms' URDF frame, axes aligned with the world"},
                "joints": joints, "grippers": grip,
                "controller": {"type": "joint position PD per DoF (Genesis control_dofs_position), gravity included in the simulation",
                               "control_hz": CONTROL_HZ, "physics_hz": CONTROL_HZ * 4, "gains": gains,
                               "note": "targets are applied at the 30 Hz control rate and held over the 4 physics substeps"},
                "tcp": tcp}

    # ---- primitives for the agent: deliberately thin wrappers of the low-level action (joint targets, gripper width, IK
    # moves). Grasping, placing and every other skill are the agent's to build.
    def primitives(self) -> dict[str, Callable]:
        s = self

        def get_object_pose(name: str):
            """-> (position(3), quaternion wxyz(4)) of `name` in the world frame."""
            return s.object_pose(name)

        def get_object_bounds(name: str):
            """-> AABB [[xmin,ymin,zmin],[xmax,ymax,zmax]] of `name` (world frame)."""
            return s.object_bounds(name)

        def get_ee_pose(arm: str):
            """-> (position(3), quaternion wxyz(4)) of the gripper tip of `arm` ('left'|'right')."""
            return s.ee_pose(arm)

        def get_joint_targets():
            """-> the 16-vector of the currently commanded joint targets (action layout)."""
            return s.hold_action()

        def hold(steps: int = 10):
            """Keep the current targets for `steps` control steps (lets objects settle)."""
            for _ in range(int(steps)):
                s.step(s.hold_action())

        def set_joint_targets(targets, steps: int = 1):
            """Command a full 16-vector of joint targets for `steps` control steps (no interpolation)."""
            for _ in range(int(steps)):
                s.step(targets)

        def set_gripper(arm: str, width: float, steps: int = 15):
            """Command the gripper width of `arm` (0 = closed .. 0.1 = open) and hold for `steps` control steps."""
            t = s.hold_action(); t[GRIP_INDEX[arm]] = float(np.clip(width, 0.0, GRIPPER_OPEN))
            for _ in range(int(steps)):
                s.step(t)

        def open_gripper(arm: str, steps: int = 15):
            """Open the gripper of `arm` fully (width 0.1 m)."""
            set_gripper(arm, GRIPPER_OPEN, steps)

        def close_gripper(arm: str, steps: int = 15):
            """Close the gripper of `arm` (width target 0; the PD controller squeezes whatever is between the fingers)."""
            set_gripper(arm, 0.0, steps)

        def move_joints(arm: str, q7, *, max_dq: float = 0.04, steps: int | None = None, settle: int = 0):
            """Interpolate the 7 joint targets of `arm` linearly from the current targets to `q7` (rad), at most `max_dq`
            rad per control step (or exactly `steps` steps), then hold `settle` steps."""
            cur = s.hold_action(); goal = cur.copy(); goal[ARM_SLICE[arm]] = np.asarray(q7, dtype=np.float64)
            n = int(steps) if steps else max(4, int(math.ceil(float(np.max(np.abs(goal - cur))) / max_dq)))
            for i in range(1, n + 1):
                s.step(cur + (goal - cur) * (i / n))
            for _ in range(int(settle)):
                s.step(goal)

        def move_ee(arm: str, pos, quat_wxyz=None, *, max_dq: float = 0.04, steps: int | None = None, settle: int = 0,
                    tol: float = 0.008, linear: int = 0):
            """Move the gripper tip of `arm` to world pose (pos, quat_wxyz; default: keep the current orientation).
            IK (pink/pinocchio) then joint interpolation (`max_dq` rad/step). `linear=k` splits the motion into k straight-line
            Cartesian waypoints (use for descents/lifts). Raises PrimitiveError if the IK residual exceeds `tol` metres.
            Returns the final tip position error (m)."""
            p1 = np.asarray(pos, dtype=np.float64)
            p0, q0 = s.ee_pose(arm)
            quat = np.asarray(quat_wxyz if quat_wxyz is not None else q0, dtype=np.float64)
            k = max(1, int(linear))
            for j in range(1, k + 1):
                pj = p0 + (p1 - p0) * (j / k) if k > 1 else p1
                q7, ep, er = s.ik(arm, pj, quat)
                if ep > tol or er > 0.2:
                    raise PrimitiveError(f"IK for {arm} arm at {np.round(pj, 3).tolist()} failed: residual {ep * 1000:.1f} mm / {math.degrees(er):.1f} deg")
                move_joints(arm, q7, max_dq=max_dq, steps=(steps if k == 1 else None), settle=(settle if j == k else 0))
            pe, _ = s.ee_pose(arm)
            return float(np.linalg.norm(pe - p1))

        return {"get_object_pose": get_object_pose, "get_object_bounds": get_object_bounds, "get_ee_pose": get_ee_pose,
                "get_joint_targets": get_joint_targets, "hold": hold, "set_joint_targets": set_joint_targets,
                "set_gripper": set_gripper, "open_gripper": open_gripper, "close_gripper": close_gripper, "move_joints": move_joints,
                "move_ee": move_ee, "ik": s.ik, "top_down_quat": top_down_quat, "gripper_quat": gripper_quat}

    def exec_code(self, code: str, extra: dict | None = None) -> dict[str, Any]:
        """Run agent/oracle code with the primitives in scope (also: session, objects, TASK, np, math, PrimitiveError)."""
        g: dict[str, Any] = {"__name__": "__main__", "np": np, "math": math, "session": self, "objects": self.objects,
                             "TASK": dict(self.spec, table_z=TABLE_Z), "PrimitiveError": PrimitiveError, **self.primitives(), **(extra or {})}
        try:
            exec(code, g, g)
            return {"ok": True}
        except BaseException as exc:  # noqa: BLE001
            import traceback
            traceback.print_exc(file=sys.stderr)
            return {"ok": False, "error": repr(exc)[:300]}

    def close(self) -> None:
        try:
            self.env.close()
        except Exception as exc:  # noqa: BLE001
            _log("close:", repr(exc)[:120])


# --------------------------------------------------------------------------- CLI
def _load_traj(path: str) -> dict[str, Any]:
    d = np.load(path, allow_pickle=False)
    return {k: (d[k].item() if d[k].shape == () else d[k]) for k in d.files}


def _git_commit(path: Path) -> str:
    try:
        return subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10).stdout.strip()[:12]
    except Exception:  # noqa: BLE001
        return ""


def cmd_make_instance(a) -> None:
    t0 = time.time()
    s = Session(a.task, eval_index=a.eval_index)
    # Genesis caches written while building, not reproducible in another process (CoACD hulls .cvx, "pbs" particle
    # samples .ptc): frozen into the instance, see _seed_cache
    from genesis.utils import misc
    caches = {}
    for kind in ("cvx", "ptc"):
        d = Path(getattr(misc, f"get_{kind}_cache_dir")())
        caches[kind] = {p.name: base64.b64encode(p.read_bytes()).decode() for p in sorted(d.glob(f"*.{kind}")) if p.stat().st_mtime >= t0} if d.is_dir() else {}
    out = {"task": a.task, "robowits_task": s.spec["robowits_task"], "eval_json": s.spec["eval_json"], "eval_index": s.eval_index,
           "text": s.spec["text"], "scene": s.scene_entry, "state_sha": s.instance_sha, "action_dim": ACTION_DIM, "control_hz": CONTROL_HZ,
           "backend": s.backend, "reset_joint_targets": [round(float(x), 6) for x in s.joint_positions()], "objects": s.objects(),
           "genesis_version": s.gs.__version__, "robowits_commit": _git_commit(ROBOWITS_ROOT)}
    for kind, files in caches.items():
        if files:
            out[f"genesis_{kind}"] = files
    Path(a.out).write_text(json.dumps(out, indent=1))
    print(json.dumps({"instance": a.out, "state_sha": s.instance_sha}), flush=True)
    s.close()


def cmd_run_oracle(a) -> None:
    """Run the reference code on the frozen instance in this fresh process and record every low-level action."""
    s = Session(a.task, instance=a.instance, strict=True)
    code = open(a.code).read()
    t0 = time.time()
    s.record_start()
    r = s.exec_code(code)
    acts = s.record_stop()
    st = s.status()
    s.save_trajectory(acts, a.out, meta={"source": "oracle", "exec": r, "wall_s": round(time.time() - t0, 1)})
    print(json.dumps({"traj": a.out, "n_actions": int(len(acts)), "exec": r, **st, "wall_s": round(time.time() - t0, 1)}), flush=True)
    s.close()


def cmd_replay(a) -> None:
    traj = _load_traj(a.traj)
    if str(traj.get("task")) != a.task:
        print(json.dumps({"error": f"trajectory task {traj.get('task')} != {a.task}"}), flush=True); sys.exit(2)
    s = Session(a.task, instance=a.instance, strict=a.strict)
    acts = np.asarray(traj["actions"], dtype=np.float32)
    t0 = time.time()
    outs = [s.replay(acts) for _ in range(a.repeat)]
    out = {"n_actions": int(len(acts)), "instance_sha": s.instance_sha, "instance_matches": s.instance_matches,
           "instance_exact": s.instance_exact, "replays": outs, "all_success": all(o["success"] for o in outs),
           "deterministic": len({o["state_sha"] for o in outs}) == 1, "wall_s": round(time.time() - t0, 1)}
    if a.video:
        s.start_video(a.video, fps=a.fps); s.replay(acts); s.stop_video(); out["video"] = a.video
    print(json.dumps(out), flush=True)
    s.close()


def cmd_render(a) -> None:
    s = Session(a.task, instance=a.instance)
    cams = tuple(a.cameras.split(",")) if a.cameras else Session.VIDEO_CAMERAS
    print(json.dumps(s.render_video(_load_traj(a.traj)["actions"], a.out, every=a.every, fps=a.fps, cameras=cams, cols=a.cols)), flush=True)
    s.close()


def cmd_selftest(a) -> None:
    """Determinism evidence in 3 fresh processes: make-instance, run-oracle, replay --repeat 2 (fresh == live, repeats agree)."""
    here, out = Path(__file__).resolve(), Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)
    inst, traj = out / "instance.json", out / "trajectory.npz"

    def run(*args):
        cmd = [sys.executable, str(here), *map(str, args)]
        _log("selftest>", " ".join(cmd[2:]))
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=open(out / "selftest.stderr.log", "ab"), text=True)
        lines = [l for l in p.stdout.splitlines() if l.startswith("{")]
        return json.loads(lines[-1]) if lines else {"error": f"no json output (rc={p.returncode})"}

    r0 = run("make-instance", "--task", a.task, "--eval-index", a.eval_index, "--out", inst)
    r1 = run("run-oracle", "--task", a.task, "--instance", inst, "--code", a.code, "--out", traj)
    r2 = run("replay", "--task", a.task, "--instance", inst, "--traj", traj, "--repeat", 2, "--strict")
    reps = r2.get("replays") or [{}]
    ok = bool(r1.get("success")) and bool(r2.get("all_success")) and bool(r2.get("deterministic")) \
        and reps[0].get("state_sha") == r1.get("state_sha") and bool(r2.get("instance_matches"))
    print(json.dumps({"make_instance": r0, "oracle": r1, "replay": r2, "PASS": ok}, indent=1), flush=True)
    sys.exit(0 if ok else 1)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("make-instance"); q.add_argument("--task", required=True); q.add_argument("--eval-index", type=int, required=True)
    q.add_argument("--out", required=True); q.set_defaults(fn=cmd_make_instance)
    q = sub.add_parser("run-oracle"); q.add_argument("--task", required=True); q.add_argument("--instance", required=True)
    q.add_argument("--code", required=True); q.add_argument("--out", required=True); q.set_defaults(fn=cmd_run_oracle)
    q = sub.add_parser("replay"); q.add_argument("--task", required=True); q.add_argument("--instance", required=True); q.add_argument("--traj", required=True)
    q.add_argument("--repeat", type=int, default=2); q.add_argument("--video", default=None); q.add_argument("--fps", type=int, default=15)
    q.add_argument("--strict", action="store_true", help="fail if the rebuilt frozen scene does not match instance.json (poses within tolerance)"); q.set_defaults(fn=cmd_replay)
    q = sub.add_parser("render"); q.add_argument("--task", required=True); q.add_argument("--instance", required=True); q.add_argument("--traj", required=True)
    q.add_argument("--out", required=True); q.add_argument("--every", type=int, default=2); q.add_argument("--fps", type=int, default=15)
    q.add_argument("--cameras", default=None); q.add_argument("--cols", type=int, default=3); q.set_defaults(fn=cmd_render)
    q = sub.add_parser("selftest"); q.add_argument("--task", default="stack_cubes"); q.add_argument("--eval-index", type=int, default=0)
    q.add_argument("--code", required=True); q.add_argument("--out-dir", required=True); q.set_defaults(fn=cmd_selftest)
    a = p.parse_args(); a.fn(a)


if __name__ == "__main__":
    main()
