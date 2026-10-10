"""
rcb_dexjoco.py — task-local tooling for DexJoCo (brave-eai/dexjoco @ 8d23b0f, MuJoCo 3.4.0; Franka Panda + 16-DoF
Allegro hand, one or two arms): frozen scene instance / privileged state / thin primitives / action recording /
fresh-process deterministic replay. Same shape as rcb_robowits.py and rcb_traj.py (LIBERO), so agents and verifiers
share one mental model.

Concepts
--------
instance   : one DexJoCo scene = the task's env after reset with the initial object poses and table height of one
             recorded human demonstration restored (DexJoCo's own state restorer, demo state[0]). DexJoCo's reset
             samples object poses from the global RNG, so the scene is not rebuilt from a seed: instance.npz stores the
             full MuJoCo physics state, the mocap targets, the actuator controls and the env's Python-side task state
             (success counters, trigger flags, ...). Session(instance=...) builds the env, resets it once and loads that
             snapshot; every episode (reset, replay) starts from it. `state_sha` = sha1 over the physics state.
trajectory : the (T, A) actions handed to the env, one row per control step (50 Hz control, 10 physics substeps of
             2 ms): single-arm A = 23 = [tcp target xyz (m, world), tcp target quat wxyz, 16 Allegro joint targets
             (rad)]; bimanual A = 46 = [right 23, left 23]. The arm follows the target through DexJoCo's operational-
             space controller; the hand joints are position-controlled. MuJoCo on the CPU is deterministic: the same
             rows from the same snapshot give the same final state bit for bit (in-process and across processes).
episode    : as in DexJoCo's own evaluation, an episode ends at the first step where the task reports success, or where
             it reports a task failure (e.g. water_plant: trigger pulled away from the plant; bimanual_hanoi: an
             illegal tower). `success` = the episode ended in success. Replay stops at that step.
budget     : there is no step budget: the agent's wall clock is the limit. DexJoCo's 1000-1500-step episode caps and its
             real-time pacing (a sleep to 30 Hz in every step) are lifted; MAX_STEPS only stops runaway episodes.
             A trajectory handed in (privileged mode) has at most MAX_TRAJECTORY_ROWS rows: what the verifier can
             replay twice inside its timeout on the slowest family. `save_trajectory` refuses a longer one.

CLI
---
  python rcb_dexjoco.py make-instance --task water_plant --demo <demo>/replay.zarr --out instance.npz [--oracle-out oracle.npz]
  python rcb_dexjoco.py replay        --task water_plant --instance instance.npz --traj traj.npz [--repeat 2] [--video replay.mp4] [--out r.json]
  python rcb_dexjoco.py render        --task water_plant --instance instance.npz --traj traj.npz --out replay.mp4

Python (what the agent gets)
----------------------------
  from rcb_dexjoco import Session
  s = Session("water_plant", instance="/app/instance.npz")   # ~1 s
  s.reset()                          # back to the frozen instance state (unlimited)
  s.state()                          # privileged state: tcp_pose, gripper_pose (hand joints), object poses, table height
  p = s.primitives()                 # move_ee, set_hand, hold, get_ee_pose, get_hand, get_state, get_body_pose, ...
  s.render_frame("front")            # RGB (H, W, 3) uint8; s.cameras(), s.render_grid(), s.render_video(actions, path)
  s.record_start(); ...; actions = s.record_stop()   # (T, A) actions, one row per control step
  s.status()                         # {'success', 'done', 'reason', 'steps', 'resets', 'state_sha', 'info'}
  s.replay(actions)                  # resets, replays open-loop, returns status -> self-check before you hand in
  s.save_trajectory(actions, "/app/output/trajectory.npz")
"""
from __future__ import annotations

import os
os.environ.setdefault("MUJOCO_GL", "osmesa")
os.environ.setdefault("PYOPENGL_PLATFORM", "osmesa")

import argparse
import copy
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np

MAX_STEPS = 10_000_000          # runaway guard only; the wall clock is the budget
# Privileged hand-in cap: rows of /app/output/trajectory.npz (1000 s of robot time at 50 Hz; the longest reference has
# 1085 rows). The verifier replays a trajectory twice inside its timeout; the slowest family runs ~140 control steps/s.
# The verifier scores a longer file 0 (bad_trajectory). The standard service's recorded episode has no such cap.
MAX_TRAJECTORY_ROWS = 50_000
# Threads (docs/benchmarks/dexjoco.md, "Threads"): DexJoCo's operational-space controller does its linear algebra in numpy,
# and OpenBLAS gives one result on 4 or more threads (the references' and every published result's numerics), others on
# 1 and on 2-3. Every container sets OPENBLAS_NUM_THREADS=4, but OpenBLAS never runs more threads than the CPUs the
# process may run on (its affinity: a cpuset, taskset, a Slurm allocation; a docker `cpus:` quota does not change it).
# So a grading process checks the count it really runs with: below MIN_BLAS_THREADS it gives no verdict.
MIN_BLAS_THREADS = 4


def blas_threads() -> dict[str, Any]:
    """The thread count numpy's OpenBLAS runs with in this process, and what bounds it (all numeric, for reward.json):
    visible_cpus (the process's CPU affinity), openblas_num_threads_env (OPENBLAS_NUM_THREADS, 0 = not set),
    blas_threads (asked of the loaded OpenBLAS itself; if that fails, min(visible_cpus, the environment's setting)),
    threads_ok (1 iff blas_threads >= MIN_BLAS_THREADS)."""
    try:
        visible = len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        visible = int(os.cpu_count() or 1)
    env = 0
    for k in ("OPENBLAS_NUM_THREADS", "GOTO_NUM_THREADS", "OMP_NUM_THREADS"):   # OpenBLAS's own order
        try:
            env = int(os.environ.get(k, "") or 0)
        except ValueError:
            env = 0
        if env > 0:
            break
    n = 0
    try:
        import ctypes
        np.linalg.inv(np.eye(2))                                             # numpy's BLAS is loaded and initialised
        with open("/proc/self/maps") as f:
            libs = sorted({line.split()[-1] for line in f if "openblas" in line.rsplit("/", 1)[-1].lower()})
        for lib in libs:
            h = ctypes.CDLL(lib)
            for sym in ("openblas_get_num_threads64_", "openblas_get_num_threads", "scipy_openblas_get_num_threads64_",
                        "scipy_openblas_get_num_threads"):
                fn = getattr(h, sym, None)
                if fn is not None:
                    fn.restype = ctypes.c_int
                    n = max(n, int(fn()))
                    break
    except Exception:  # noqa: BLE001 -- no /proc, another BLAS, a stripped library: fall back to what bounds the count
        n = 0
    if n <= 0:
        n = min(visible, env) if env > 0 else visible
    return {"visible_cpus": int(visible), "openblas_num_threads_env": int(max(env, 0)), "blas_threads": int(n),
            "threads_ok": int(n >= MIN_BLAS_THREADS)}


def threads_message(t: dict) -> str:
    return (f"OpenBLAS runs {t['blas_threads']} thread(s) here ({t['visible_cpus']} CPU(s) visible to this process, "
            f"OPENBLAS_NUM_THREADS={t['openblas_num_threads_env'] or 'unset'}); DexJoCo's simulation gives the references' "
            f"numerics only on {MIN_BLAS_THREADS} or more (docs/benchmarks/dexjoco.md, Threads)")


# Order of the 16 hand values in an action row (and in the measured joints) per arm. DexJoCo's bimanual envs list the
# LEFT hand's fingers mirrored: ring, middle, index, thumb.
HAND_ORDER = {"right": ["index_0", "index_1", "index_2", "index_3", "middle_0", "middle_1", "middle_2", "middle_3",
                        "ring_0", "ring_1", "ring_2", "ring_3", "thumb_0", "thumb_1", "thumb_2", "thumb_3"],
              "left": ["ring_0", "ring_1", "ring_2", "ring_3", "middle_0", "middle_1", "middle_2", "middle_3",
                       "index_0", "index_1", "index_2", "index_3", "thumb_0", "thumb_1", "thumb_2", "thumb_3"]}
ACTION_LAYOUT = {23: "[tcp_xyz(3), tcp_quat_wxyz(4), allegro_joints(16)]",
                 46: "[right: tcp_xyz(3), tcp_quat_wxyz(4), allegro_joints(16), left: same 23]"}
_SIMPLE = (bool, int, float, str, type(None), np.integer, np.floating, np.bool_, np.ndarray)
# MjModel arrays that never change at run time and are large (assets, names): not part of the instance snapshot.
_MODEL_SKIP = ("mesh_", "tex_", "hfield_", "skin_", "name_", "names", "paths", "text_", "flex_", "bvh_", "oct_")


def _model_arrays(model) -> dict[str, np.ndarray]:
    """Every numeric MjModel array a task can change (DexJoCo's reset and state restorers move fixed bodies, the table
    and its legs by editing the model, which the physics state does not hold)."""
    out = {}
    for k in dir(model):
        if k.startswith("_") or k.startswith(_MODEL_SKIP):
            continue
        try:
            v = getattr(model, k)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(v, np.ndarray) and v.dtype.kind in "fiub" and v.size:
            out[k] = v
    return out


# Interaction log: every Session (any process) appends one line per session start/reset/record/replay/exit, with the
# control steps consumed, to RCB_SESSION_LOG (default /app/output/rcb_session_log.jsonl, collected with the artifacts),
# and to RCB_SESSION_LOG_KEEP (default /logs/agent/rcb_session_log.jsonl when that directory exists; the host's
# rcb-log-mirror keeps an append-only copy). The verifier reports it as cost and sets RCB_SESSION_LOG="".
SESSION_LOG = os.environ.get("RCB_SESSION_LOG", "/app/output/rcb_session_log.jsonl")
SESSION_LOG_KEEP = os.environ.get("RCB_SESSION_LOG_KEEP", "/logs/agent/rcb_session_log.jsonl")


def _slog(ev: str, **kw) -> None:
    if not SESSION_LOG:
        return
    line = json.dumps({"ts": time.time(), "pid": os.getpid(), "ev": ev, **kw}) + "\n"
    for path, must_exist in ((SESSION_LOG, False), (SESSION_LOG_KEEP, True)):
        if not path or (must_exist and not os.path.isdir(os.path.dirname(path))):
            continue
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a") as f:
                f.write(line)
        except OSError:
            pass


# Task objects by readable name -> (kind, MuJoCo name). Live poses come from mjData (DexJoCo's state dict carries the
# objects' INITIAL poses only). kind: body (pos + quat wxyz), site / geom (pos), joint (qpos).
OBJECTS: dict[str, dict[str, tuple[str, str]]] = {
    "water_plant": {"spray_bottle": ("body", "link_2"), "spray_trigger": ("joint", "joint_0"),
                    "spray_nozzle": ("site", "ref_point"), "plant": ("body", "plant"), "table_top": ("site", "table_top")},
    "click_mouse": {"mouse": ("body", "link_3"), "mouse_button": ("joint", "mouse_joint_0"),
                    "mousepad": ("geom", "@_mousepad_geom_id"), "monitor": ("body", "display_link_1"),
                    "table_top": ("site", "table_top")},
    "hammer_nail": {"hammer": ("body", "hammer_body"), "nail": ("body", "nail"), "nail_top": ("site", "nail_top_site"),
                    "wood_top": ("site", "wood_top"), "table_top": ("site", "table_top")},
    "pick_bucket": {"bucket": ("body", "bucket"), "bucket_handle": ("joint", "bucket_joint_0"), "boxed_food": ("body", "boxed_food_0"),
                    "table_top": ("site", "table_top")},
    "pinch_tongs": {"tongs": ("body", "link_1"), "tongs_hinge": ("joint", "joint_0"), "table_top": ("site", "table_top")},
    "fold_glasses": {"glasses": ("body", "glass"), "temple_0": ("joint", "glass_joint_0"), "temple_1": ("joint", "glass_joint_1"),
                     "case": ("body", "open_box"), "table_top": ("site", "table_top")},
    "bimanual_microwave_cook": {"hot_dog": ("body", "hot_dog"), "microwave": ("body", "microwave_object"),
                                "door_hinge": ("joint", "microjoint"), "door_handle": ("geom", "door_handle"),
                                "start_button": ("geom", "start_button"), "stop_button": ("geom", "stop_button"),
                                "table_top": ("site", "table_top")},
    "bimanual_unlock_ipad": {"ipad": ("body", "ipad_body"), "ipad_screen": ("geom", "ipad_screen"), "stand": ("body", "ipad_stand"),
                             "table_top": ("site", "table_top")},
    "bimanual_assembly": {"peg": ("body", "industreal_round_peg_8mm"), "peg_tip": ("site", "industreal_round_peg_8mm_tip_site"),
                          "tray": ("body", "industreal_tray_insert_round_peg_8mm"),
                          "socket": ("site", "industreal_tray_insert_round_peg_8mm_socket_site"), "table_top": ("site", "table_top")},
    "bimanual_photograph": {"camera": ("body", "link_19"), "view_point": ("site", "view_direction_site"),
                            "shutter": ("geom", "camera_body_top_cap"), "logo": ("geom", "photograph_logo_disk"),
                            "target_region": ("geom", "photograph_target_region_visual"), "table_top": ("site", "table_top")},
    "bimanual_hanoi": {"disk_small": ("body", "hanoi_disk_small"), "disk_medium": ("body", "hanoi_disk_medium"),
                       "disk_large": ("body", "hanoi_disk_large"), "post_a": ("site", "hanoi_post_a_site"),
                       "post_b": ("site", "hanoi_post_b_site"), "post_c": ("site", "hanoi_post_c_site")},
}


# Success checks robot_coding_bench tightens on top of DexJoCo's own (DexJoCo's check still has to pass; its task
# failures still end the episode). water_plant: upstream only asks for the nozzle near the plant while the trigger is
# pulled, which a bottle lying on the table and spraying away from the plant satisfies (two Opus 5.5 runs did exactly
# that, spraying 84 and 114 degrees away). We also require the spray to point at the plant.
WATER_AIM_MAX_DEG = 45.0          # the human demonstration sprays 33 degrees off the nozzle -> plant direction


def water_aim_deg(model, data) -> float:
    """Angle (deg) between the spray direction and the direction from the nozzle reference point to the plant. The spray
    direction is the bottle body's +z axis, along which DexJoCo draws its spray cone: perpendicular to the bottle's long
    axis (+y, bottom to spray head), out of the front of the head on the side the trigger faces."""
    spray = data.body("link_2").xmat.reshape(3, 3)[:, 2]
    to_plant = data.body("plant").xpos - data.site("ref_point").xpos
    c = float(np.dot(spray, to_plant) / max(1e-9, np.linalg.norm(to_plant)))
    return float(np.degrees(np.arccos(np.clip(c, -1.0, 1.0))))


def _log(*a: Any) -> None:
    print("[rcb_dexjoco]", *a, file=sys.stderr, flush=True)


class PrimitiveError(RuntimeError):
    pass


def _task_config(task: str):
    from dexjoco.tasks.mappings import CONFIG_MAPPING
    if task not in CONFIG_MAPPING:
        raise KeyError(f"unknown task {task!r}; known: {sorted(CONFIG_MAPPING)}")
    return CONFIG_MAPPING[task]()


def _plain(v: Any) -> bool:
    if isinstance(v, _SIMPLE):
        return True
    if isinstance(v, (list, tuple)):
        return all(_plain(x) for x in v)
    if isinstance(v, dict):
        return all(isinstance(k, (str, int)) and _plain(x) for k, x in v.items())
    return False


def quat_mul(a, b) -> np.ndarray:
    w1, x1, y1, z1 = a; w2, x2, y2, z2 = b
    return np.array([w1*w2 - x1*x2 - y1*y2 - z1*z2, w1*x2 + x1*w2 + y1*z2 - z1*y2,
                     w1*y2 - x1*z2 + y1*w2 + z1*x2, w1*z2 + x1*y2 - y1*x2 + z1*w2])


def quat_slerp(a, b, t: float) -> np.ndarray:
    a = np.asarray(a, float) / np.linalg.norm(a); b = np.asarray(b, float) / np.linalg.norm(b)
    d = float(np.dot(a, b))
    if d < 0:
        b, d = -b, -d
    if d > 0.9995:
        q = a + t * (b - a); return q / np.linalg.norm(q)
    th = np.arccos(d); s = np.sin(th)
    return (np.sin((1 - t) * th) * a + np.sin(t * th) * b) / s


class Session:
    """One DexJoCo env on a frozen instance. Every episode starts from the instance snapshot."""

    def __init__(self, task: str, instance: str | Path | None = None, *, max_steps: int = MAX_STEPS,
                 image_size: tuple[int, int] = (480, 640)):
        import mujoco
        self._mj = mujoco
        self.task = task
        self.max_steps = int(max_steps)
        self.cfg = _task_config(task)
        # render_mode "none" keeps DexJoCo from rendering its cameras on every step (CPU rendering is ~100x the
        # physics cost); frames are rendered on demand by render_frame().
        self.env = self.cfg.get_environment(policy_mode=True, render_mode="none", randomize=False)
        self.base = self.env.unwrapped
        self.base.hz = float("inf")                      # no real-time pacing
        self.model, self.data = self.base._model, self.base._data
        if hasattr(self.base, "image_obs"):
            self.base.image_obs = False                  # bimanual envs take image_obs=True by default, read per step
        # Several envs render all their cameras inside every observation regardless of image_obs / render_mode
        # (click_mouse, hammer_nail, pinch_tongs; pick_bucket has its image_obs test commented out). Rendering only
        # reads mjData, so it is replaced by blank frames of the same count; render_frame() renders on demand.
        try:
            n = len(self.base.render())
        except RuntimeError:                              # water_plant: render_mode "none" already stops its rendering
            n = 0
        if n:
            blank = np.zeros((1, 1, 3), np.uint8)
            self.base.render = lambda: tuple(blank for _ in range(n))
        self.bimanual = task.startswith("bimanual_")
        self.action_dim = 46 if self.bimanual else 23
        self.base.reset()
        self._renderer = None
        self._image_size = image_size
        self._rec: list[np.ndarray] | None = None
        self.resets = 0
        self._snapshot = None
        self.instance_meta: dict[str, Any] = {}
        if instance is not None:
            self.load_instance(instance)
        else:
            self._snapshot = self.snapshot()
        self._episode_reset()
        self._total_steps = 0
        self.threads = blas_threads()
        if not self.threads["threads_ok"]:     # the agent's own runs go on; a grading process gives no verdict like this
            _log("WARNING: " + threads_message(self.threads) + ". Results here can differ from the verifier's replay, "
                 "which runs on 4 threads: give this container at least 4 CPUs and OPENBLAS_NUM_THREADS=4.")
        _slog("session_start", task=task)
        import atexit
        atexit.register(lambda: _slog("session_end", task=task, resets=self.resets, sim_steps=self._total_steps + self.steps))

    # ------------------------------------------------------------------ state snapshots
    def snapshot(self) -> dict[str, Any]:
        mj = self._mj
        sz = mj.mj_stateSize(self.model, mj.mjtState.mjSTATE_INTEGRATION)
        phys = np.empty(sz); mj.mj_getState(self.model, self.data, phys, mj.mjtState.mjSTATE_INTEGRATION)
        attrs = {k: copy.deepcopy(v) for k, v in vars(self.base).items()
                 if not k.startswith("__") and _plain(v) and k not in ("hz", "render_mode")}
        return {"physics": phys, "mocap_pos": self.data.mocap_pos.copy(), "mocap_quat": self.data.mocap_quat.copy(),
                "ctrl": self.data.ctrl.copy(), "act": self.data.act.copy() if self.model.na else np.zeros(0),
                "attrs": attrs, "model": {k: v.copy() for k, v in _model_arrays(self.model).items()}}

    def restore(self, snap: dict[str, Any]) -> None:
        mj = self._mj
        live = _model_arrays(self.model)
        for k, v in snap.get("model", {}).items():
            if k in live and live[k].shape == v.shape:
                live[k][...] = v
        mj.mj_setState(self.model, self.data, np.asarray(snap["physics"]), mj.mjtState.mjSTATE_INTEGRATION)
        self.data.mocap_pos[:] = snap["mocap_pos"]; self.data.mocap_quat[:] = snap["mocap_quat"]
        self.data.ctrl[:] = snap["ctrl"]
        for k, v in snap["attrs"].items():
            setattr(self.base, k, copy.deepcopy(v))
        mj.mj_forward(self.model, self.data)

    def state_sha(self) -> str:
        mj = self._mj
        sz = mj.mj_stateSize(self.model, mj.mjtState.mjSTATE_INTEGRATION)
        phys = np.empty(sz); mj.mj_getState(self.model, self.data, phys, mj.mjtState.mjSTATE_INTEGRATION)
        h = hashlib.sha1(phys.tobytes())
        for k, v in sorted(_model_arrays(self.model).items()):
            h.update(k.encode()); h.update(np.ascontiguousarray(v).tobytes())
        return h.hexdigest()[:16]

    def save_instance(self, path: str | Path, meta: dict | None = None) -> None:
        snap = self.snapshot()
        np.savez_compressed(path, task=self.task, physics=snap["physics"], mocap_pos=snap["mocap_pos"],
                 **{"model__" + k: v for k, v in snap["model"].items()},
                 mocap_quat=snap["mocap_quat"], ctrl=snap["ctrl"], act=snap["act"],
                 attrs=json.dumps(_to_json(snap["attrs"])), attr_types=json.dumps(_types(snap["attrs"])),
                 sha=self.state_sha(), meta=json.dumps(meta or {}))

    def load_instance(self, path: str | Path) -> None:
        d = np.load(path, allow_pickle=False)
        if str(d["task"]) != self.task:
            raise ValueError(f"instance is for task {str(d['task'])!r}, not {self.task!r}")
        attrs = _from_json(json.loads(str(d["attrs"])), json.loads(str(d["attr_types"])))
        model = {k[len("model__"):]: d[k] for k in d.files if k.startswith("model__")}
        self._snapshot = {"physics": d["physics"], "mocap_pos": d["mocap_pos"], "mocap_quat": d["mocap_quat"],
                          "ctrl": d["ctrl"], "act": d["act"], "attrs": attrs, "model": model}
        self.instance_meta = json.loads(str(d["meta"]))
        self.restore(self._snapshot)
        self.instance_sha = str(d["sha"])
        self.instance_exact = self.state_sha() == self.instance_sha
        if not self.instance_exact:
            _log(f"WARNING: restored state sha {self.state_sha()} != instance sha {self.instance_sha}")

    # ------------------------------------------------------------------ episode
    def _episode_reset(self) -> None:
        self.restore(self._snapshot)
        self.steps = 0
        self.done = False
        self.success = False
        self.reason: str | None = None
        self.last_info: dict[str, Any] = {}
        self._rcb_count = 0                           # robot_coding_bench's own hold counter (tightened checks)

    def reset(self) -> None:
        """Back to the frozen instance state (unlimited). Starts a new episode."""
        _slog("reset", task=self.task, n=self.resets + 1, sim_steps_before=self.steps)
        self._total_steps += self.steps
        self._episode_reset()
        self.resets += 1

    def step(self, action) -> bool:
        """One control step with a (A,) action row. Returns True while the episode is running."""
        a = np.asarray(action, dtype=np.float64).reshape(-1)
        if a.shape != (self.action_dim,):
            raise ValueError(f"action must have {self.action_dim} values {ACTION_LAYOUT[self.action_dim]}, got {a.shape}")
        if not np.all(np.isfinite(a)):
            raise ValueError("action contains NaN or inf")
        if self.done:
            raise PrimitiveError(f"episode is over ({self.reason}); call reset()")
        if self.steps >= self.max_steps:
            raise PrimitiveError(f"runaway guard: {self.max_steps} steps")
        for q in ((a[3:7],) if not self.bimanual else (a[3:7], a[26:30])):
            n = np.linalg.norm(q)
            if n < 1e-6:
                raise ValueError("tcp quaternion has zero norm")
        raw = {"right": a[:23], "left": a[23:46]} if self.bimanual else a
        self.base.env_step = 0                       # DexJoCo's episode cap is lifted (wall clock is the budget)
        _, _, terminated, _, info = self.base.step(raw)
        if getattr(self.base, "_pending_illegal_reset", False):
            self.base._pending_illegal_deadline = float("inf")   # hanoi: never auto-reset on a wall-clock timer
        self.steps += 1
        if self._rec is not None:
            self._rec.append(a.astype(np.float64))
        self.last_info = {k: _jsonable(v) for k, v in dict(info).items()}
        succeed = bool(info.get("succeed", False))
        if self.task == "water_plant":
            # upstream's zone + trigger condition, held 30 steps, AND the spray aimed at the plant (WATER_AIM_MAX_DEG)
            aim = water_aim_deg(self.model, self.data)
            zone_and_trigger = int(self.base._success_counter) > 0
            self._rcb_count = self._rcb_count + 1 if (zone_and_trigger and aim <= WATER_AIM_MAX_DEG) else 0
            self.last_info.update({"aim_deg": round(aim, 2), "rcb_success_count": self._rcb_count, "upstream_succeed": succeed})
            succeed = self._rcb_count >= 30
            failed = bool(terminated) and not bool(info.get("succeed", False)) and bool(self.base._trigger_pulled)
            terminated = failed                        # upstream's own success no longer ends the episode
        if succeed:
            self.done, self.success, self.reason = True, True, "success"
        elif terminated:
            self.done, self.reason = True, _failure_reason(self.task, info)
        return not self.done

    def hold_action(self) -> np.ndarray:
        """The action that keeps the current tcp targets and hand joint targets."""
        return np.concatenate([self._arm_target(arm) for arm in self.arms()])

    def status(self) -> dict[str, Any]:
        return {"success": bool(self.success), "done": bool(self.done), "reason": self.reason, "steps": int(self.steps),
                "resets": int(self.resets), "state_sha": self.state_sha(), "info": self.last_info}

    # ------------------------------------------------------------------ recording / replay
    def record_start(self) -> None:
        self._rec = []

    def record_stop(self) -> np.ndarray:
        rec, self._rec = self._rec or [], None
        _slog("record", task=self.task, n_actions=len(rec), success=bool(self.success))
        return np.asarray(rec, dtype=np.float64).reshape(-1, self.action_dim)

    def save_trajectory(self, actions, path: str | Path, meta: dict | None = None, *,
                        max_rows: int | None = MAX_TRAJECTORY_ROWS) -> None:
        """Write the trajectory file. More than `max_rows` rows are refused (the privileged verifier's hand-in cap,
        MAX_TRAJECTORY_ROWS); the standard service records its own episode with max_rows=None."""
        A = np.asarray(actions, dtype=np.float64)
        if A.ndim != 2 or A.shape[1] != self.action_dim:
            raise ValueError(f"trajectory must be (T, {self.action_dim}), got {A.shape}")
        if max_rows is not None and len(A) > max_rows:
            raise ValueError(f"trajectory has {len(A)} rows, more than the hand-in cap of {max_rows} "
                             "(the verifier scores a longer file 0)")
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        np.savez(path, actions=A, task=self.task, instance_sha=getattr(self, "instance_sha", ""),
                 action_layout=ACTION_LAYOUT[self.action_dim], meta=json.dumps(meta or {}))

    def replay(self, actions) -> dict[str, Any]:
        """Reset to the instance and replay open-loop until the episode ends or the rows run out."""
        A = np.asarray(actions, dtype=np.float64)
        self.reset()
        n = 0
        for row in A:
            n += 1
            if not self.step(row):
                break
        st = self.status(); st["replayed_rows"] = n; st["rows"] = int(len(A))
        _slog("replay", task=self.task, n_actions=int(len(A)), success=st["success"])
        return st

    # ------------------------------------------------------------------ privileged state
    def arms(self) -> tuple[str, ...]:
        return ("right", "left") if self.bimanual else ("right",)

    def state(self) -> dict[str, list]:
        """DexJoCo's state dict (privileged): tcp_pose [xyz, quat wxyz] (per arm), gripper_pose (16 hand joints per arm),
        each task object's pose [xyz, quat wxyz], table_delta_height."""
        obs = self.base._compute_observation()
        return {k: np.asarray(v, float).reshape(-1).round(6).tolist() for k, v in obs["state"].items()}

    def objects(self) -> dict[str, dict[str, Any]]:
        """Live privileged state of the task's objects: name -> {kind, pos, quat_wxyz} (bodies), {pos} (sites, geoms),
        {qpos} (joints)."""
        out: dict[str, dict[str, Any]] = {}
        for name, (kind, ref) in OBJECTS.get(self.task, {}).items():
            if kind == "body":
                p, q = self.body_pose(ref); out[name] = {"kind": kind, "pos": p.round(5).tolist(), "quat_wxyz": q.round(5).tolist()}
            elif kind == "site":
                out[name] = {"kind": kind, "pos": self.data.site(ref).xpos.round(5).tolist()}
            elif kind == "geom":
                gid = int(getattr(self.base, ref[1:])) if ref.startswith("@") else self.model.geom(ref).id
                out[name] = {"kind": kind, "pos": self.data.geom_xpos[gid].round(5).tolist()}
            elif kind == "joint":
                out[name] = {"kind": kind, "qpos": float(np.asarray(self.data.joint(ref).qpos).reshape(-1)[0])}
        return out

    def bodies(self) -> list[str]:
        mj = self._mj
        return [mj.mj_id2name(self.model, mj.mjtObj.mjOBJ_BODY, i) or f"body{i}" for i in range(self.model.nbody)]

    def body_pose(self, name: str) -> tuple[np.ndarray, np.ndarray]:
        b = self.data.body(name)
        return b.xpos.copy(), b.xquat.copy()

    def _mocap_id(self, arm: str) -> int:
        if not self.bimanual:
            return 0
        attr = getattr(self.base, f"_mocap_{arm}_id", None)
        if attr is not None:
            return int(attr)
        try:
            return int(self.model.body(f"target_{arm}").mocapid)
        except KeyError:
            return 0 if arm == "right" else 1           # bimanual_unlock_ipad indexes mocap 0 / 1 directly

    def _hand_ctrl_ids(self, arm: str) -> np.ndarray:
        ids = np.asarray(self.base._allegro_ctrl_ids)
        if not self.bimanual:
            return ids
        return ids[:16] if arm == "right" else ids[16:32]

    def _arm_target(self, arm: str) -> np.ndarray:
        i = self._mocap_id(arm)
        return np.concatenate([self.data.mocap_pos[i], self.data.mocap_quat[i], self.data.ctrl[self._hand_ctrl_ids(arm)]])

    def ee_pose(self, arm: str = "right") -> tuple[np.ndarray, np.ndarray]:
        """Actual tcp pose (xyz, quat wxyz) of an arm (the controller tracks the mocap target with some lag)."""
        st = self.base._compute_observation()["state"]
        key = "tcp_pose" if not self.bimanual else "tcp_pose"
        v = np.asarray(st[key], float).reshape(-1)
        if self.bimanual:
            v = v[:7] if arm == "right" else v[7:14]
        return v[:3].copy(), v[3:7].copy()

    def hand_joints(self, arm: str = "right") -> np.ndarray:
        v = np.asarray(self.base._compute_observation()["state"]["gripper_pose"], float).reshape(-1)
        return (v[:16] if arm == "right" else v[16:32]).copy() if self.bimanual else v[:16].copy()

    def hand_limits(self, arm: str = "right") -> np.ndarray:
        """(16, 2) joint-target ranges (rad) of an arm's Allegro hand, in the action's order (see HAND_ORDER)."""
        return self.model.actuator_ctrlrange[self._hand_ctrl_ids(arm)].copy()

    # ------------------------------------------------------------------ rendering (on demand)
    def cameras(self) -> list[str]:
        mj = self._mj
        return [mj.mj_id2name(self.model, mj.mjtObj.mjOBJ_CAMERA, i) for i in range(self.model.ncam)]

    def render_frame(self, camera: str | None = None, size: tuple[int, int] | None = None) -> np.ndarray:
        mj = self._mj
        h, w = size or self._image_size
        if self._renderer is None or (self._renderer.height, self._renderer.width) != (h, w):
            if self._renderer is not None:
                # a second OSMesa context next to a live one reads back garbage: close the old one first
                self._renderer.close(); self._renderer = None
            self.model.vis.global_.offheight = max(self.model.vis.global_.offheight, h)
            self.model.vis.global_.offwidth = max(self.model.vis.global_.offwidth, w)
            self._renderer = mj.Renderer(self.model, height=h, width=w)
        cam = camera if camera is not None else self.default_camera()
        self._renderer.update_scene(self.data, camera=cam)
        return self._renderer.render().copy()

    def video_cameras(self) -> list[str]:
        """The cameras of a replay video: the default static camera and the (right) hand camera."""
        cams = [c for c in (self.default_camera(), "handcam_rgb", "handcam_rgb_right") if c in self.cameras()]
        return list(dict.fromkeys(cams))[:2]

    def default_camera(self) -> str:
        cams = self.cameras()
        for c in ("front", "agentview", "overview"):
            if c in cams:
                return c
        return cams[0]

    def render_grid(self, cameras: list[str] | None = None, size: tuple[int, int] = (240, 320), cols: int = 3) -> np.ndarray:
        cams = cameras or self.cameras()
        frames = [self.render_frame(c, size) for c in cams]
        while len(frames) % cols:
            frames.append(np.zeros_like(frames[0]))
        rows = [np.concatenate(frames[i:i + cols], axis=1) for i in range(0, len(frames), cols)]
        return np.concatenate(rows, axis=0)

    def render_video(self, actions, path: str | Path, *, cameras: list[str] | None = None, every: int = 2, fps: int = 25,
                     size: tuple[int, int] = (240, 320), deadline: float | None = None) -> dict[str, Any]:
        """Replay `actions` from the frozen state into an mp4. `deadline` (a time.time() value): stop there and keep
        the frames written so far (the verifier's time box; a video never decides a verdict)."""
        import imageio.v2 as imageio
        A = np.asarray(actions, dtype=np.float64)
        self.reset()
        cams = cameras or [self.default_camera()]
        w = imageio.get_writer(str(path), fps=fps, codec="libx264", quality=7, macro_block_size=8)
        try:
            w.append_data(np.concatenate([self.render_frame(c, size) for c in cams], axis=1))
            for i, row in enumerate(A):
                running = self.step(row)
                if i % every == 0 or not running:
                    w.append_data(np.concatenate([self.render_frame(c, size) for c in cams], axis=1))
                if not running or (deadline is not None and time.time() > deadline):
                    break
        finally:
            w.close()
        return self.status()

    # ------------------------------------------------------------------ primitives
    def primitives(self) -> dict[str, Callable]:
        s = self

        def _run(targets: dict[str, np.ndarray], steps: int) -> dict:
            for _ in range(max(1, int(steps))):
                row = s.hold_action()
                for arm, t in targets.items():
                    k = s.arms().index(arm) * 23
                    row[k:k + len(t)] = t if len(t) == 23 else np.concatenate([t, row[k + len(t):k + 23]])
                if not s.step(row):
                    break
            return s.status()

        def get_objects():
            """Live poses of the task objects (see Session.objects())."""
            return s.objects()

        def get_state():
            """Privileged state dict: tcp_pose, gripper_pose (hand joints), object poses, table_delta_height."""
            return s.state()

        def get_ee_pose(arm: str = "right"):
            return s.ee_pose(arm)

        def get_ee_target(arm: str = "right"):
            t = s._arm_target(arm); return t[:3].copy(), t[3:7].copy()

        def get_hand(arm: str = "right"):
            """Measured hand joint angles (16,)."""
            return s.hand_joints(arm)

        def get_hand_target(arm: str = "right"):
            return s._arm_target(arm)[7:23].copy()

        def get_body_pose(name: str):
            """World pose (xyz, quat wxyz) of any MuJoCo body (see s.bodies())."""
            return s.body_pose(name)

        def hold(steps: int = 10):
            """Keep every target for `steps` control steps."""
            return _run({}, steps)

        def move_ee(arm: str, pos, quat_wxyz=None, *, steps: int | None = None, max_speed: float = 0.25,
                    max_rot_speed: float = 1.5, settle: int = 10, hand=None):
            """Move an arm's tcp target to (pos, quat) along a straight line + slerp, then hold `settle` steps.
            steps defaults to what max_speed (m/s) and max_rot_speed (rad/s) allow at 50 Hz. `hand` (16,) optionally
            interpolates the hand joint targets along the same path."""
            p0, q0 = get_ee_target(arm)
            p1 = np.asarray(pos, float); q1 = q0 if quat_wxyz is None else np.asarray(quat_wxyz, float)
            q1 = q1 / np.linalg.norm(q1)
            h0 = get_hand_target(arm); h1 = h0 if hand is None else np.asarray(hand, float)
            if steps is None:
                ang = 2 * np.arccos(min(1.0, abs(float(np.dot(q0 / np.linalg.norm(q0), q1)))))
                steps = int(np.ceil(max(np.linalg.norm(p1 - p0) / (max_speed / 50), ang / (max_rot_speed / 50), 1)))
            for i in range(1, steps + 1):
                t = i / steps
                tgt = np.concatenate([p0 + t * (p1 - p0), quat_slerp(q0, q1, t), h0 + t * (h1 - h0)])
                st = _run({arm: tgt}, 1)
                if st["done"]:
                    return st
            return _run({}, settle) if settle else s.status()

        def set_hand(arm: str, q16, *, steps: int = 25, settle: int = 10):
            """Interpolate an arm's 16 Allegro joint targets to q16 (rad) over `steps`, then hold `settle` steps."""
            h0 = get_hand_target(arm); h1 = np.asarray(q16, float).reshape(16)
            p, q = get_ee_target(arm)
            for i in range(1, steps + 1):
                st = _run({arm: np.concatenate([p, q, h0 + i / steps * (h1 - h0)])}, 1)
                if st["done"]:
                    return st
            return _run({}, settle) if settle else s.status()

        def set_targets(row, steps: int = 1):
            """Send one raw (A,) action row for `steps` control steps."""
            r = np.asarray(row, float)
            for _ in range(max(1, int(steps))):
                if not s.step(r):
                    break
            return s.status()

        return {"get_objects": get_objects, "get_state": get_state, "get_ee_pose": get_ee_pose, "get_ee_target": get_ee_target, "get_hand": get_hand,
                "get_hand_target": get_hand_target, "get_body_pose": get_body_pose, "hold": hold, "move_ee": move_ee,
                "set_hand": set_hand, "set_targets": set_targets}

    def close(self) -> None:
        try:
            self.env.close()
        except Exception:
            pass


# ---------------------------------------------------------------------- helpers
def _failure_reason(task: str, info: dict) -> str:
    if info.get("illegal_state"):
        return "failure: " + str(info.get("illegal_reason") or "illegal state")
    if task == "water_plant":
        return "failure: trigger pulled away from the plant"
    if task == "bimanual_unlock_ipad":
        return "failure: wrong passcode"
    return "failure: task terminated"


def _jsonable(v: Any) -> Any:
    if isinstance(v, np.ndarray):
        return v.round(6).tolist()
    if isinstance(v, (np.floating,)):
        return round(float(v), 6)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    return v


def _types(attrs: dict) -> dict:
    def t(v):
        if isinstance(v, np.ndarray):
            return {"nd": str(v.dtype), "shape": list(v.shape)}
        if isinstance(v, (np.bool_, np.integer, np.floating)):
            return {"np": str(np.asarray(v).dtype)}
        if isinstance(v, bool):
            return "bool"
        if isinstance(v, int):
            return "int"
        if isinstance(v, float):
            return "float"
        if isinstance(v, tuple):
            return {"tuple": [t(x) for x in v]}
        if isinstance(v, list):
            return {"list": [t(x) for x in v]}
        if isinstance(v, dict):
            return {"dict": {str(k): t(x) for k, x in v.items()}, "keys": [type(k).__name__ for k in v]}
        return type(v).__name__
    return {k: t(v) for k, v in attrs.items()}


def _to_json(attrs: dict) -> dict:
    def j(v):
        if isinstance(v, np.ndarray):
            return v.tolist()
        if isinstance(v, (np.bool_,)):
            return bool(v)
        if isinstance(v, np.integer):
            return int(v)
        if isinstance(v, np.floating):
            return float(v)
        if isinstance(v, (list, tuple)):
            return [j(x) for x in v]
        if isinstance(v, dict):
            return {str(k): j(x) for k, x in v.items()}
        return v
    return {k: j(v) for k, v in attrs.items()}


def _from_json(vals: dict, types: dict) -> dict:
    def f(v, t):
        if isinstance(t, dict) and "np" in t:
            return np.asarray(v, dtype=t["np"])[()]
        if isinstance(t, dict) and "nd" in t:
            return np.asarray(v, dtype=t["nd"]).reshape(t["shape"])
        if isinstance(t, dict) and "tuple" in t:
            return tuple(f(x, tt) for x, tt in zip(v, t["tuple"]))
        if isinstance(t, dict) and "list" in t:
            return [f(x, tt) for x, tt in zip(v, t["list"])]
        if isinstance(t, dict) and "dict" in t:
            out = {}
            for (k, x), kt in zip(v.items(), t["keys"]):
                out[int(k) if kt == "int" else k] = f(x, t["dict"][k])
            return out
        if t == "bool":
            return bool(v)
        if t == "int":
            return int(v)
        if t == "float":
            return float(v)
        return v
    return {k: f(v, types[k]) for k, v in vals.items()}


def _load_traj(path: str) -> np.ndarray:
    return np.asarray(np.load(path, allow_pickle=False)["actions"], dtype=np.float64)


# ---------------------------------------------------------------------- CLI
def cmd_make_instance(a) -> None:
    import zarr
    from dexjoco.tasks.state_restorers import restore_initial_state
    s = Session(a.task)
    root = zarr.open(a.demo, mode="r")
    state0 = np.asarray(root["data"]["state"][0]).ravel()
    s.base.reset()
    restore_initial_state(s.env, a.task, s.cfg, state0)
    s._snapshot = s.snapshot()
    s._episode_reset()
    meta = {"source": "DexJoCo-Datasets-Raw demo, initial state restored with dexjoco.tasks.state_restorers",
            "demo": a.demo_name or os.path.basename(os.path.dirname(os.path.abspath(a.demo))), "dexjoco": "8d23b0f"}
    s.save_instance(a.out, meta)
    _log("instance", a.out, "sha", s.state_sha())
    if a.oracle_out:
        A = np.asarray(root["data"]["action"], dtype=np.float64)
        s2 = Session(a.task, instance=a.out)
        st = s2.replay(A)
        s2.save_trajectory(A[:st["replayed_rows"]], a.oracle_out, {"source": "demo actions", "demo": meta["demo"]})
        print(json.dumps({"oracle": a.oracle_out, **{k: st[k] for k in ("success", "reason", "replayed_rows", "rows", "state_sha")}}))


def cmd_replay(a) -> None:
    """Replay a trajectory from the frozen instance, `--repeat` times (each in a new Session). `--out` writes the result
    as JSON (the standard-mode collect hook runs one replay per fresh process); `--video` renders the first replay
    (at most ~1500 frames, after the verdict fields are known; it never changes them) and stops
    `--video-deadline-s` seconds after this process started, keeping the frames written so far."""
    t_start = time.time()
    A = _load_traj(a.traj)
    runs, instance_ok, video = [], True, False
    for i in range(a.repeat):
        s = Session(a.task, instance=a.instance)
        instance_ok = instance_ok and bool(s.instance_exact)
        st = s.replay(A)
        runs.append({k: st[k] for k in ("success", "reason", "steps", "state_sha", "replayed_rows", "rows")})
        if a.video and i == 0:
            try:
                n = int(st["replayed_rows"])
                s.render_video(A[:n], a.video, cameras=s.video_cameras(), every=max(2, -(-n // 1500)),
                               deadline=(t_start + a.video_deadline_s) if a.video_deadline_s else None)
                video = os.path.isfile(a.video)
            except Exception:  # noqa: BLE001
                import traceback
                traceback.print_exc(file=sys.stderr)
        s.close()
    out = {"n_actions": int(len(A)), "replays": runs, "all_success": all(r["success"] for r in runs),
           "deterministic": len({r["state_sha"] for r in runs}) == 1, "success": bool(runs[0]["success"]),
           "state_sha": runs[0]["state_sha"], "reason": runs[0]["reason"], "steps": runs[0]["steps"],
           "instance_ok": instance_ok, "video": video, **blas_threads()}
    if not out["threads_ok"]:
        _log("WARNING: " + threads_message(out) + ": this replay is not the references' numerics")
    print(json.dumps(out))
    if a.out:
        with open(a.out, "w") as f:
            json.dump(out, f)


def cmd_render(a) -> None:
    s = Session(a.task, instance=a.instance)
    print(json.dumps(s.render_video(_load_traj(a.traj), a.out, every=a.every)))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make-instance"); m.add_argument("--task", required=True); m.add_argument("--demo", required=True)
    m.add_argument("--demo-name"); m.add_argument("--out", required=True); m.add_argument("--oracle-out")
    r = sub.add_parser("replay"); r.add_argument("--task", required=True); r.add_argument("--instance", required=True)
    r.add_argument("--traj", required=True); r.add_argument("--repeat", type=int, default=2); r.add_argument("--video")
    r.add_argument("--out", help="also write the result to this JSON file")
    r.add_argument("--video-deadline-s", type=float, default=0.0, help="stop the video this long after the start (0: never)")
    v = sub.add_parser("render"); v.add_argument("--task", required=True); v.add_argument("--instance", required=True)
    v.add_argument("--traj", required=True); v.add_argument("--out", required=True); v.add_argument("--every", type=int, default=2)
    a = ap.parse_args()
    {"make-instance": cmd_make_instance, "replay": cmd_replay, "render": cmd_render}[a.cmd](a)


if __name__ == "__main__":
    main()
