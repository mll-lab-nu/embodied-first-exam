"""eai-standard/2.2 sim service for MolmoSpaces (docs/STANDARD_MODE.md, docs/benchmarks/molmospaces.md): the adapter
of the shared layer rcb_limited.py; the simulator is rcb_molmospaces.Episode (upstream MolmoSpaces, MuJoCo on the CPU).
HTTP surface: GET /spec, GET /status, POST /observe, POST /submit, POST /kinematics. Every call is logged to
/data/episode.jsonl; nothing about objects ever leaves this process.

The episode follows upstream's evaluation: one control step = one upstream Task.step; it ends when upstream's
is_done() says so (the benchmark's horizon), when the agent submits `done`, or when the agent's time is over (the
collect hook); success = upstream judge_success() on the final state, also when the task was met earlier and undone.

Crash recovery (rcb_limited.Episode, resume class `exact`: MuJoCo on the CPU repeats bit for bit in a fresh process):
every executed row is journaled; after a crash the service rebuilds the episode and replays the journal. When the
episode ends the service writes /data/trajectory.npz + /data/episode.json; the collect hook (finalize.sh) makes it exit
and writes final.json from episode.json.

The verdict is the live episode's (owner 2026-10-17, board 0150/0151): upstream's judge_success() on the state at the
episode's end, as upstream's evaluation and the privileged verifier's replay judge it; nothing replays it. The frozen
start is checked when the scene is built, before the agent is served: a start state whose hash is not the instance's
recorded t = 0 hash gives up as `instance_mismatch` (infra_error)."""

import math, os, sys, threading, time, traceback
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rcb_limited as L  # noqa: E402

DATA = os.environ.get("RCB_DATA", "/data")
INSTANCE = os.environ.get("RCB_INSTANCE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "instance.json"))
WALL_CLOCK_S = float(os.environ.get("RCB_WALL_CLOCK_S", "3600"))
MAX_CHUNK_S = float(os.environ.get("RCB_MAX_CHUNK_S", "10"))
MAX_WATCH_S = float(os.environ.get("RCB_MAX_WATCH_S", "30"))
UNITS = os.environ["RCB_ACTION_UNITS"]  # the row's units, as the instruction words them (compose, from families.json)
LOCK = threading.Lock()
PID_FILE = os.path.join(DATA, "server.pid")
E = {
    "ready": False,
    "step": 0,
    "calls": 0,
    "done": False,
    "reason": None,
    "success": False,
    "t0": time.time(),
    "error": None,
}

import rcb_molmospaces as M  # noqa: E402

INST = M.load_instance(INSTANCE)
EP = L.Episode(DATA, dim=INST["t0"]["action_dim"], resume="exact")
EP.startup()  # start count, back-off after failed starts, the startup watchdog until scene_built()
S = M.Episode(INST)
START_SHA = S.state_sha()  # before anything else touches the scene: the frozen start, checked here (not in a replay)
if START_SHA != INST["t0"].get("state_sha"):
    EP.give_up(
        f"instance_mismatch: the frozen start state did not rebuild here (start {START_SHA}, frozen {INST['t0'].get('state_sha')})",
        infra=True,
    )
ROWS: list = []  # every executed row (a resume replays them first): trajectory.npz
CTRL_HZ = 1.0 / S.dt
SUBSTEPS = int(round(S.dt / float(S.env.current_model.opt.timestep)))
CAMS = S.agent_cameras
CAM0 = {c: S.camera_info(c) for c in CAMS}
LIMITS = S.command_limits()
GROUPS = [
    ("joint_pos", S.joint_names, "measured joint positions of the controlled joints (rad; base x, y in m)"),
    ("joint_vel", [f"{j}_vel" for j in S.joint_names], "measured joint velocities (rad/s, m/s)"),
    (
        "joint_effort",
        [f"{j}_effort" for j in S.joint_names],
        "actuator forces of those joints (N m, N): what each drive demands; a joint with an effort_limit in robot_spec "
        "applies at most that",
    ),
    ("gripper_opening", [f"{g}_opening_m" for g in S.grippers], "distance between the fingertips (m)"),
    (
        "tcp_pose",
        [f"{g}_{k}" for g in S.grippers for k in ("x", "y", "z", "qw", "qx", "qy", "qz")],
        "tool centre point of each gripper: x y z (m) + quaternion wxyz, world frame",
    ),
]
PROPRIO_LAYOUT = [n for _, names, _ in GROUPS for n in names]
PROPRIO_GROUPS, _i = {}, 0
for _g, _names, _meaning in GROUPS:
    PROPRIO_GROUPS[_g] = [_i, len(_names), _meaning]
    _i += len(_names)

SPEC = {
    "protocol": L.PROTOCOL,
    "protocol_compat": list(L.COMPAT),
    "simulator": "molmospaces (molmo-spaces 0.2.9, MuJoCo 3.5.0)",
    "robot": INST["episode"]["robot"]["robot_name"],
    "task_text": INST["facts"]["goal"],
    "control_hz": CTRL_HZ,
    "physics_substeps": SUBSTEPS,
    "max_chunk_s": MAX_CHUNK_S,
    "max_watch_s": MAX_WATCH_S,
    "cameras": {
        c: {
            "rgb": True,
            "depth": True,
            "mounted": CAM0[c]["mount"]["type"],
            "resolution": CAM0[c]["image_size"],
            "intrinsic_cv": CAM0[c]["intrinsic_cv"],
            "mount": CAM0[c]["mount"],
        }
        for c in CAMS
    },
    "default_cameras": list(CAMS),
    "action_types": {
        "joint_position": {
            "dim": S.action_dim,
            "layout": S.layout,
            "limits": dict(zip(S.layout, LIMITS.tolist())),
            "units": UNITS,
            "semantics": "absolute targets of upstream's joint-position controllers, one per control step; rows `dt` "
            "apart (a multiple of the control period, at most 0.5 s), `hold` or `linear` between rows; "
            "values outside the limits are clipped and reported",
        },
        "done": {
            "dim": 0,
            "layout": [],
            "semantics": 'ends the episode now, in the current state (no physics); r.submit("done", [])',
        },
        "not_yet": ["ee_pose", "joint_delta", "joint_velocity", "ee_delta", "joint_torque"],
    },
    "proprio_layout": PROPRIO_LAYOUT,
    "proprio_groups": PROPRIO_GROUPS,
    "static": {},
    "world": {
        "frame": "the simulator's world frame of this house: z up; the robot's base pose is its own (proprio joint_pos "
        "for RB-Y1; robot_spec for the fixed Franka)",
        "up": "+z",
        "units": {"length": "m", "angle": "rad", "time": "s"},
        "quaternion_order": "wxyz",
        "camera_axes": "intrinsic_cv / extrinsic_cv: OpenCV camera axes (x right, y down, z forward); cam2world_gl: OpenGL axes",
    },
    "budget": {"reset": 0, "steps": None, "wall_clock_s": WALL_CLOCK_S},
    "max_control_steps": S.horizon,
    "episode": f"one episode, no reset (upstream's evaluation): it ends after {S.horizon} control steps (the benchmark's "
    f"{INST['facts']['horizon_s']} s horizon), when you submit `done`, or when your time is over; success is judged "
    "on the state at that moment, also when the task was met earlier and undone",
    "robot_spec": S.robot_spec(),
    "kinematics": S.kinematics_spec(),
    "depth": {
        "modes": list(L.DEPTH_MODES),
        "default": "none",
        "kind": "z-depth",
        "unit": "m",
        "invalid": 0,
        "max_m": L.DEPTH_MAX_M,
        "frames_encoding": "uint16 mm, zlib",
        "noise": L.DEPTH_NOISE,
    },
}
L.check_spec(SPEC)  # a spec that misses a 2.2 field or names a forbidden one never starts the episode
EP.scene_built()


def ctrl_steps() -> int:
    return S.steps


def proprio_row() -> np.ndarray:
    p = S.proprio()
    return np.concatenate([p[g] for g, _, _ in GROUPS]).astype(np.float32)


def grab(cams, want_depth: bool):
    return {c: S.render(c) for c in cams}, ({c: S.render_depth(c) for c in cams} if want_depth else {})


def extrinsics(cams) -> dict:
    return {c: np.asarray(S.camera_info(c)["extrinsic_cv"], dtype=np.float64) for c in cams}


def write_final() -> None:
    if L.final_verdict(DATA):  # finalize.sh's verdict, or a give-up after crashes: never overwritten
        return
    L._write_json(os.path.join(DATA, "final.json"), {**summary(), "finalized": False, "live_sha": E.get("live_sha")})


def summary() -> dict:
    n = int(E.get("episode_control_steps") or ctrl_steps())
    return {
        "success": bool(E["success"]),
        "steps": E["step"],
        "calls": E["calls"],
        "control_steps": n,
        "physics_steps": n * SUBSTEPS,
        "elapsed_s": round((E.get("t_end") or time.time()) - E["t0"], 1),
        "reason": E["reason"],
        "done": E["done"],
        "family": INST["family"],
        "protocol": L.PROTOCOL,
        "n_actions": len(ROWS),
        "start_sha": START_SHA,
        "graded_by": "live",
        "replays": 0,
        **EP.final_fields(),
    }


def finish(reason: str) -> None:
    """The episode is over: upstream's verdict on the final state, then the record for the collect hook."""
    if E["done"]:
        return
    E["done"] = True
    E["reason"] = reason
    E["t_end"] = time.time()
    E["episode_control_steps"] = ctrl_steps()
    try:
        # a simulator error raised by the agent's actions (reason "error") leaves a post-exception state: never judged
        E["success"] = False if reason == "error" else S.success()
    except Exception:  # noqa: BLE001
        traceback.print_exc()
    EP.log(
        {"ev": "end", "reason": reason, "step": E["step"], "control_steps": ctrl_steps(), "success": bool(E["success"])}
    )
    dump()


def dump() -> None:
    if E.get("dumped"):
        return
    E["dumped"] = True
    E["live_sha"] = S.state_sha()
    np.savez(
        os.path.join(DATA, "trajectory.npz"),
        actions=np.asarray(ROWS, dtype=np.float64).reshape(-1, S.action_dim),
        layout=np.array(S.layout),
        family=INST["family"],
    )
    L._write_json(os.path.join(DATA, "episode.json"), {**summary(), "live_sha": E["live_sha"]})
    write_final()


def ctrl_step(a, rec) -> bool:
    """One executed control step, journaled. True when the call must stop here."""
    S.step(a)
    ROWS.append(np.asarray(a, dtype=np.float64))
    stop = EP.journal(a)
    rec.tick()
    if S.done:
        finish("horizon")
    return E["done"] or stop


def recorder(cams, fps: int, meta: dict) -> L.Recorder:
    return L.Recorder(
        cams,
        max(1, int(round(CTRL_HZ / max(1, fps)))),
        grab,
        proprio_row,
        extrinsics,
        ctrl_steps,
        depth=L.depth_mode(meta),
        clock_hz=CTRL_HZ,
    )


def video_fps(meta: dict) -> int:
    fps = meta.get("video_fps")
    if fps is None:
        return 5
    if isinstance(fps, bool) or not isinstance(fps, (int, float)) or not (1 <= fps <= 30):
        raise ValueError("video_fps must be in [1, 30]")
    return int(fps)


def cameras_of(meta: dict) -> list:
    cams = meta.get("cameras") or CAMS
    if not isinstance(cams, (list, tuple)) or not all(isinstance(c, str) for c in cams):
        raise ValueError(f"cameras must be a list of camera names; cameras: {CAMS}")
    bad = [c for c in cams if c not in CAMS]
    if bad:
        raise ValueError(f"unknown cameras {bad}; cameras: {CAMS}")
    return list(cams)


def number(meta: dict, key: str, default: float) -> float:
    """A numeric request field: `default` when the request has no such field; a finite number otherwise, else a 400 (a
    null, a string, a list, NaN/inf). Every field is checked before anything moves (PROTOCOL §4.6): a malformed request
    never becomes an exception past the checks, which would end the episode."""
    if key not in meta:
        return float(default)
    v = meta[key]
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ValueError(f"{key} must be a finite number, got {v!r:.80}")
    return float(v)


def note_of(meta: dict) -> str:
    note = meta.get("note")
    if note is not None and not isinstance(note, str):
        raise ValueError("note must be a string")
    return (note or "")[:500]


def meta_common(cams) -> dict:
    n = ctrl_steps()
    ci = {c: S.camera_info(c) for c in cams}
    return {
        "step": E["step"],
        "calls": E["calls"],
        "control_steps": n,
        "physics_steps": n * SUBSTEPS,
        "sim_time_s": round(n * S.dt, 3),
        "time_s": round(L.agent_time(E), 2),
        "time_left_s": max(0.0, round(WALL_CLOCK_S - L.agent_time(E), 1)),
        "proprio": {"layout": PROPRIO_LAYOUT, "now": proprio_row().tolist()},
        "done": E["done"],
        "reason": E["reason"],
        "cameras": {
            c: {k: ci[c][k] for k in ("intrinsic_cv", "extrinsic_cv", "cam2world_gl", "image_size")} for c in cams
        },
    }


def do_submit(meta: dict, A: np.ndarray):
    typ = meta.get("type")
    if not isinstance(typ, str):
        raise ValueError(f"type must be joint_position or done (not yet: {SPEC['action_types']['not_yet']})")
    if typ == "done":
        rec = recorder(cameras_of(meta), 5, meta)
        rec.tick(force=True, last=True)  # every response carries the last frames
        E["calls"] += 1
        finish("done")
        return {
            **meta_common(cameras_of(meta)),
            "chunk_id": E["calls"],
            "type": typ,
            "executed_rows": 0,
            "ok": True,
        }, rec.parts("none", 5)
    if typ != "joint_position":
        raise ValueError(f"type must be joint_position or done (not yet: {SPEC['action_types']['not_yet']})")
    dt = number(meta, "dt", S.dt)
    interp = meta.get("interpolate", "linear")
    video = meta.get("video", "mp4")
    cams, fps, note = cameras_of(meta), video_fps(meta), note_of(meta)
    k = dt / S.dt
    if A.ndim != 2 or A.shape[1] != S.action_dim:
        raise ValueError(f"joint_position actions must be (T, {S.action_dim}), got {list(A.shape)}")
    if not np.all(np.isfinite(A)):
        raise ValueError("actions contain NaN/inf")
    if not (dt <= 0.5 + 1e-9 and round(k) >= 1 and abs(k - round(k)) < 1e-6):
        raise ValueError(f"dt must be a whole multiple of the {S.dt:g} s control period and at most 0.5 s; got {dt}")
    if A.shape[0] * dt > MAX_CHUNK_S + 1e-9:
        raise ValueError(f"chunk longer than max_chunk_s={MAX_CHUNK_S}: {A.shape[0]} rows x {dt} s")
    if not isinstance(interp, str) or interp not in ("hold", "linear"):
        raise ValueError("interpolate must be hold|linear")
    if not isinstance(video, str) or video not in ("mp4", "frames", "both", "none"):
        raise ValueError("video must be mp4|frames|both|none")
    rec, clipped = recorder(cams, fps, meta), []
    E["calls"] += 1
    step0, before = E["step"], ctrl_steps()
    rec.tick(force=True)
    prev = S.hold_row()
    for ri, row in enumerate(A):
        E["step"] += 1
        target = np.clip(row, LIMITS[:, 0], LIMITS[:, 1])
        for j in np.flatnonzero(target != row)[:20]:
            clipped.append(
                {"row": ri, "index": int(j), "reason": f"{S.layout[j]} limit [{LIMITS[j, 0]:g}, {LIMITS[j, 1]:g}]"}
            )
        n = int(round(k))
        stop = False
        for s in range(1, n + 1):
            a = target if interp == "hold" else prev + (target - prev) * (s / n)
            if ctrl_step(a, rec):
                stop = True
                break
        prev = target
        if stop:
            break
    rec.tick(force=True, last=True)
    out = {
        **meta_common(cams),
        "chunk_id": E["calls"],
        "type": typ,
        "executed_rows": E["step"] - step0,
        "control_steps_chunk": ctrl_steps() - before,
        "physics_steps_chunk": (ctrl_steps() - before) * SUBSTEPS,
        "clipped": clipped[:200],
        "n_clipped": len(clipped),
        "plan": [],
        "ok": True,
    }
    EP.log(
        {
            "ev": "submit",
            "call": E["calls"],
            "rows": E["step"] - step0,
            "dt": dt,
            "interpolate": interp,
            "cameras": cams,
            "control_steps": ctrl_steps() - before,
            "n_clipped": len(clipped),
            "note": note,
            **({"stopped": EP.stop_reason} if EP.stopping else {}),
        }
    )
    return out, rec.parts(video, fps)


def do_observe(meta: dict):
    cams, fps = cameras_of(meta), video_fps(meta)
    seconds = number(meta, "seconds", 0.0)
    video = meta.get("video", "frames")
    if seconds < 0 or seconds > MAX_WATCH_S:
        raise ValueError(f"seconds must be in [0, {MAX_WATCH_S}]")
    if not isinstance(video, str) or video not in ("mp4", "frames", "both", "none"):
        raise ValueError("video must be mp4|frames|both|none")
    rec, before = recorder(cams, fps, meta), ctrl_steps()
    if seconds > 0 and not E["done"]:
        rec.tick(force=True)
        hold = S.hold_row()
        for _ in range(int(round(seconds / S.dt))):
            if ctrl_step(hold, rec):
                break
    rec.tick(force=True, last=True)
    E["calls"] += 1
    # what was watched: whole control steps (the request rounded to the control period), fewer if the episode ended
    ran = round((ctrl_steps() - before) * S.dt, 6)
    out = {
        **meta_common(cams),
        "obs_id": E["calls"],
        "seconds": ran,
        "control_steps_watch": ctrl_steps() - before,
        "physics_steps_watch": (ctrl_steps() - before) * SUBSTEPS,
        "ok": True,
    }
    EP.log(
        {
            "ev": "observe",
            "call": E["calls"],
            "seconds": ran,
            "seconds_requested": seconds,
            "cameras": cams,
            "control_steps": ctrl_steps() - before,
            **({"stopped": EP.stop_reason} if EP.stopping else {}),
        }
    )
    return out, rec.parts(video if seconds > 0 else ("frames" if video == "mp4" else video), fps)


def status() -> dict:
    return {
        "step": E["step"],
        "calls": E["calls"],
        "control_steps": ctrl_steps(),
        "done": E["done"],
        "reason": E["reason"],
        "elapsed_s": round(time.time() - E["t0"], 1),
    }


def end_from_signal() -> None:
    """The collect hook's SIGUSR1: end the episode (the agent's time is over), dump it, exit (the hook then writes final.json)."""
    with LOCK:
        E["exiting"] = True
        if not E["done"]:
            finish("timeout")
        EP.log({"ev": "exit", "reason": "collect hook: episode dumped"})
        if not os.path.exists(PID_FILE):
            open(PID_FILE, "w").write(str(os.getpid()))
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


def replay_row(row) -> None:
    """A journaled row during a resume."""
    S.step(row)
    ROWS.append(np.asarray(row, dtype=np.float64))


EP.begin(
    state=E,
    step=replay_row,
    state_sha=S.state_sha,
    proprio=proprio_row,
    spec=SPEC,
    on_end=end_from_signal,
    start_event={"family": INST["family"], "instance": INST["instance"], "cameras": CAMS},
)
if E["done"]:
    dump()  # resumed after the episode had ended: the record is rewritten from the replay
E["ready"] = True
write_final()
open(PID_FILE, "w").write(str(os.getpid()))
print(f"{L.PROTOCOL} MolmoSpaces sim ready (startup {EP.n_startups}, resumes {EP.resumes})", flush=True)
L.serve(
    L.Service(
        spec=SPEC,
        lock=LOCK,
        state=E,
        submit=do_submit,
        observe=do_observe,
        kinematics=S.kinematics,
        status=status,
        on_submit_error=lambda exc: finish("error"),
        log=EP.log,
        episode=EP,
        state_sha=S.state_sha,
        proprio=proprio_row,
    ),
    port=int(os.environ.get("RCB_PORT", "8000")),
)
