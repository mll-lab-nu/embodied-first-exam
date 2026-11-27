"""eai-standard/2.1 sim service: the simulator-agnostic half of a standard-mode sidecar (docs/protocol/README.md §4,
docs/protocol/standard_mode.md).

The robot as a service: the agent reaches a simulator it cannot open over HTTP. GET /spec, GET /status, POST /observe
and POST /submit; POST /reset exists only when the run grants resets (budget.reset > 0); everything else is 404.
Responses that carry data are RCB1 frames (rcb1.py), never base64. Everything simulator-specific comes in through an
adapter (the `Sim` contract below), so this file imports no simulator: a sidecar is its benchmark's adapter plus this.

One thread does all of it -- the HTTP requests, the SIGUSR1 wrap-up, the finalize -- because a simulator's GL context
belongs to the thread that made it (MuJoCo renders black frames from any other).

The episode starts when the service is ready. It ends on success, by the task's own rule ("failed": the robot fell,
the episode's control steps ran out), on a simulator error ("error"), or at SIGUSR1 ("timeout": the collect hook, once
the agent's container is gone). With a reset budget, POST /reset abandons the running episode and starts another from
the frozen instance; only the last episode is graded, and (without agent-ended episodes, below) a success ends the
trial.

A request is checked in full before anything runs: whatever is wrong with it is a 400 and nothing ran. Once it runs,
any failure is the simulator's: a 500, and the episode ends ("error").

eai-standard/3.0 (docs/protocol/standard_mode.md): standard mode is Gym's env.step. Time passes only inside /submit,
which blocks until its rows have run and answers with their video, `duration_s` (robot seconds it ran) and
`planned_duration_s` (rows x dt as sent). A hold chunk -- /submit {"type": <type>, "interpolate": "hold", "seconds": n}
with no rows -- holds the current target (sim.hold()) for n seconds. /observe is a pure read: it never moves time;
`seconds` > 0 is refused (400); `last_s` = 0 (default) is the current frame, `last_s` = n the frames the recorder took
in the last n robot seconds. The recorder (FrameRing): during every /submit, every 1 / RCB_CAMERA_FPS robot seconds,
the RGB image of every camera with the proprio row and the control step, in a ring of RCB_LOOKBACK_S robot seconds
(/spec.timing.recorder); an image the call rendered for its own answer is reused, never rendered twice.

Evidence under DATA, never visible to the agent:
  episode.jsonl        one line per event; every state the service may resume from is a checkpoint (it carries
                       state_sha and journal_rows)
  trajectory_live.f64  the journal: every executed control step in the simulator's own action space, float64
  calls/NNNNNN/        each call's response meta and the actions as sent
  startups.jsonl       one line per process start
  final.json           kept current (written atomically); "finalized": true once the verdict is in -- before the
                       video is rendered ("video_pending": true while it is), so the video never decides anything
  trajectory.npz       the graded episode (the deliverable: every control step since the last reset, as executed)
  replay.mp4, replay.last.png   the episode's video, rendered from trajectory.npz after the verdict (for people only)
  trajectory.first.npz, replay.first.mp4, replay.first.last.png   with resets, the trial's first episode too (its
                       rows from the journal, its video rendered after the graded one's): the no-reset view, for people;
                       final.json's first_success / first_reason say how it ended (evidence only). Without
                       agent-ended episodes a success ends the trial, so first_success is the graded success when no
                       reset was made, else 0; with them (a success ends nothing, and a step-limit or failure end may be
                       followed by a reset) it is the first episode's own end judgement, as the "end" event recorded it
                       (no end window, no live_verdict), or null when that is not on record

The verdict is the live episode's (docs/protocol/README.md H.4; owner, 2026-10-17): success = the episode this
service ran ended in success under the task's rule (the adapter's step()), judged here, after the agent's container is
gone; nothing is replayed to grade it. An adapter may add its benchmark's own record of the live episode with
live_verdict(rows, success) -> dict, e.g. a settle window run on the live simulator: its "success" can only take a
success away, never give one: only a real True keeps it; a live_verdict() that raises, returns what JSON cannot hold, or
whose process died in it (a restart finds the live_verdict_begin marker and does not run it again) takes it away too
(live_verdict_error) -- the episode's 0, never infrastructure. An adapter that still defines verify() is refused at
build (a TypeError), unless it sets replay_free = True: nothing calls it, and its rule must not vanish silently.

The frozen initial state is checked on the live simulator, as no replay checks it later: an adapter that records the
instance's starting-state hash sets `start_sha`; a fresh trial whose scene does not start there gives up before the agent
is served (instance_mismatch, infra_error = 1), and so does an adapter whose build() raises InstanceMismatch (its own
loader refused the instance). A reset that does not bring the scene back to start_sha ends the trial at once the same
way (the reset is answered 409 with gave_up, and every call after it too).

Crash recovery: compose restarts a crashed service (restart: on-failure). It replays the journal up to the last
checkpoint, checks the state hash, and continues the SAME episode -- never a reset. A call in flight is lost as a
whole (its caller got an error, not a result, so nothing was learned). More than RCB_MAX_RESUMES restarts since the
episode began (every process start counts, also one that died building the scene or replaying the journal) end the
trial: sim_crashed_on_call if every crash was the agent's (here: it happened while serving one of its calls -- not a
/reset, whose rebuild is the simulator's -- while the episode was running), else sim_crashed (infrastructure,
infra_error = 1). Once the outcome is decided (the graded episode ended in success, or failed with no reset left),
crashes cannot take it away: the restart past the limit resumes the episode and finalizes it as it ended. Each process writes a fatal signal's record (SIGSEGV, SIGBUS, SIGFPE, SIGILL,
SIGABRT: faulthandler) to crash.log, and startups.jsonl notes crash.log's size at every start, so the death before a
start is known to be a simulator crash or not (a kill -- SIGKILL, SIGTERM, the OOM killer -- leaves no record);
"resuming" logs it (fatal_signal), and whether the crashing thread was inside a control step (in_step). This service
keeps the in-call rule; the realtime layer counts a simulator crash inside a control step after the agent's first
command as the agent's (rcb_realtime.py). A reset whose scene does not rebuild ends the episode "error" as
infrastructure in both (infra_error = 1: the agent's reset was legitimate); an error raised by the agent's own call
is its 0. A verdict already on disk is never overwritten; a crash, a hang or a slow render
of the video loses only the video.
"""
from __future__ import annotations

import collections
import contextlib
import errno
import faulthandler
import json
import os
import signal
import tempfile
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable
from urllib.parse import urlparse

import numpy as np

import rcb1

PROTOCOL = "eai-standard/2.1"
MAX_BODY = 64 * 1024 * 1024           # request bodies above this are refused (413)
MAX_RESPONSE = 256 * 1024 * 1024      # responses above this drop frames/ and depth/ (meta.degraded says so)
MAX_VIDEO_FPS = 30
MAX_FRAMES_PER_CALL = 3000            # images in one response (cameras x frames, depth counted again): bounds memory
VIDEOS = ("mp4", "frames", "both", "none")
ON_SERVICE_ERROR = ("if a call fails with a connection error or a 5xx, the service may have crashed and resumed the "
                    "same episode (never a reset): the state is the one after the last call that completed on the "
                    "service, which you may not have received; check GET /status before continuing")
# Agent-ended episodes (docs/protocol/README.md §3 "Agent-ended episodes", standard_mode.md "Agent-ended episodes";
# required for every standard and realtime task from eai-standard/3.0). RCB_AGENT_END=1: the service never shows the task's
# success and a success never ends the episode; POST /finish (JSON {}) ends it (reason "finished"), and so do the step
# cap (reason "step_limit": the adapter's max_control_steps, or RCB_STEP_LIMIT=N when set, which may only lower it) and
# the end of the agent's session ("timeout"); those three ends are judged on the state they leave. A done that step()
# returns without a success is the task's failure rule ("failed"): 0 on a goal judged on the end state, after a success
# too; on a goal of events it ends the episode with the events reached so far. The adapter may declare:
#   end_judgement = "state"   (default) the task's success as things stand at the end;
#                 = "events"  a goal made of moments (a scored goal, a referee's call, a sequence of strikes): any
#                             success the episode reached counts, also when a failure rule ends it afterwards (an
#                             event that happened stands); a simulator error or a reset still gives 0;
#   end_window_steps = K      a settle or hold window: K control steps of sim.hold() run from the end state after an
#                             end-state end (in finalize, after the agent is gone), the success judged at its last step;
#                             a hold counter in step() counts the steps already held;
#   hidden_keys = {...}       step() info keys that tell the agent about its success or progress (dropped from every
#                             answer; HIDDEN_KEYS always are);
#   step() info["step_cap"]   a done that is the task's episode length, not a failure: judged as it stands.
AGENT_END = os.environ.get("RCB_AGENT_END") == "1"
STEP_LIMIT = int(os.environ.get("RCB_STEP_LIMIT") or 0) or None
if STEP_LIMIT is not None and (not AGENT_END or STEP_LIMIT < 1):
    raise RuntimeError("RCB_STEP_LIMIT needs RCB_AGENT_END=1 and a positive number of steps")
END_STATE_REASONS = ("finished", "timeout", "step_limit")     # ends judged on the state they leave
# final.json "ended_by": "session_end" is the end of the agent's session (its time limit, its token budget or its own
# exit: the runner's record says which); an infrastructure end (the reason's word before any ":") is "error"; any end
# not listed is "failed" (the task's own failure rule)
ENDED_BY = {"finished": "finish", "step_limit": "step_limit", "timeout": "session_end", "error": "error",
            "sim_crashed_on_call": "error", "sim_crashed": "error", "resume_failed": "error", "instance_mismatch": "error"}
HIDDEN_KEYS = frozenset({"success", "live_success", "is_success", "reward", "score", "progress", "stage", "stages",
                         "stages_reached", "subtask", "subtasks_done", "hold_steps", "settled"})
SUCCESS_SIGNAL_NOTE = ("hidden: the service never tells you whether you have succeeded and a success does not end the "
                       "episode; POST /finish (JSON {}) ends it (if you never call it, the end of your session does) and "
                       "the episode is judged then, as the instruction's Goal says: on how things stand at that moment, "
                       "and on any steps the Goal says count as they happen; after /finish every call is refused (409)")
# eai-standard/3.0 (module docstring): the rules on top of every 2.x layer, the standard recorder's rate and length
EAI_STANDARD = "eai-standard/3.0"
CAMERA_FPS = float(os.environ.get("RCB_CAMERA_FPS") or 10.0)    # the recorder: frames per robot second (all cameras)
LOOKBACK_S = float(os.environ.get("RCB_LOOKBACK_S") or 3.0)     # robot seconds the recorder's ring keeps
DEPTH_PAST = ("depth with last_s > 0: the recorder keeps no depth for these cameras (spec timing.recorder.depth lists "
              "the cameras it keeps depth for): ask for depth with last_s = 0")
SECONDS_GONE = ('observe never lets time pass (eai-standard/3.0): to let n seconds pass, submit a hold chunk '
                '{"type": <type>, "interpolate": "hold", "seconds": n} with no rows; last_s = n returns the frames '
                'recorded in the last n seconds')
AE_FIELDS = ("success_signal", "ended_by", "hidden_success_seen", "hidden_success_first_step",
             "trial_hidden_success_seen", "finish_time_s", "step_limit", "steps_used", "end_judgement",
             "end_window_steps", "end_window_success")


class Sim:
    """The adapter contract, duck-typed (this class only documents it). One object = one frozen scene.

    Rows come in three forms: what the agent sends (an action of one of spec()["action_types"]), the same after
    clip(), and a "sim row" (to_sim()), the action in the simulator's own space, which step() executes and the
    journal and the graded trajectory record (raw_dim floats)."""
    control_dt: float                       # seconds per control step; a chunk's dt is a whole multiple of it
    max_control_steps: int                  # the task's episode length: the episode ends there
    cameras: tuple[str, ...]                # every camera the agent may ask for
    depth_cameras: tuple[str, ...]          # the ones that also give depth
    proprio_layout: list[str]               # the proprio row's columns
    raw_dim: int                            # a sim row's width

    def spec(self) -> dict: ...                       # simulator, robot, task_text, episode, action_types, cameras, robot facts
    def interpolable(self, type: str) -> bool: ...    # may a row of this type span several control steps?
    def images(self, cameras: list[str], depth: bool) -> tuple[dict, dict]: ...   # ({cam: uint8 HxWx3}, {cam: float32 HxW m})
    def proprio(self) -> np.ndarray: ...              # float32, one value per proprio_layout column
    def clip(self, type: str, rows: np.ndarray) -> tuple[np.ndarray, list]: ...   # into the limits; [{row, index, reason}]
    def to_sim(self, type: str, row: np.ndarray) -> np.ndarray: ...               # an agent row -> a sim row
    def command(self, type: str) -> np.ndarray: ...   # the last row executed, exactly as clip() returned it: a chunk
                                                      # interpolates from it, so a chunk equals its rows sent one by one
    def hold(self) -> tuple[str, np.ndarray]: ...      # the row that holds the last command (a hold chunk: /submit
                                                       # with no rows, "interpolate": "hold", "seconds": n)
    def step(self, row: np.ndarray) -> tuple[bool, bool, dict]: ...   # one control step -> (done, success, info)
    def reset(self) -> None: ...                       # back to the frozen instance
    def state_sha(self) -> str: ...
    # optional: start_sha: str   the frozen instance's starting-state hash, as state_sha() gives it: a fresh trial that
    #           does not start there is refused before the agent is served, and a reset that does not return there
    #           ends the trial at once (both instance_mismatch, an infrastructure failure)
    # optional: live_verdict(rows, success) -> dict   the benchmark's own record of the live episode, judged on the live
    #           simulator after the episode ended and before the video (e.g. a settle window); "success": False takes the
    #           success away (live_rule; only True keeps it), an exception, a value JSON cannot hold or a crash in
    #           it does too (live_verdict_error); other keys (numpy scalars as numbers) go into final.json, except
    #           the service's own (RESERVED)
    # optional: replay_free = True   the adapter has a verify() but knows nothing calls it (else refused at build)
    # optional: record_frames = True (default: the recorder renders every camera at its rate during a /submit) |
    #           "delivered" (it keeps only the images a call rendered for its own answer: no extra render, for an
    #           adapter whose rendering has effects of its own) | False (no recorder: last_s answers the current frame)
    # build() may raise InstanceMismatch: the adapter's own loader found the frozen instance does not build (infra)
    def save_trajectory(self, rows: np.ndarray, path: str, meta: dict) -> None: ...
    def render_video(self, rows: np.ndarray, path: str) -> None: ...   # path and path.last.png: the episode's video, after
                                                                        # the verdict; it never decides anything


class GiveUp(Exception):
    """The service will not run this trial's episode again; final.json says why."""


class InstanceMismatch(Exception):
    """Raised by an adapter's build(): this image does not build the frozen instance's starting state (infrastructure)."""


# final.json keys the service writes itself: a live_verdict() may not set them
RESERVED = frozenset({"protocol", "success", "live_success", "done", "reason", "calls", "rows", "control_steps",
                      "control_steps_total", "episodes", "resets", "reset_budget", "elapsed_s", "sim_startups",
                      "finalized", "n_actions", "graded_by", "replays", "state_sha", "video", "video_pending",
                      "video_source", "live_rule", "live_verdict_error", "finalize_error", "infra_error",
                      "instance_mismatch", "ev", "ts", "deterministic", "replay_success", "live_sha", "first_success",
                      "first_reason", "first_n_actions", "first_video"} | set(AE_FIELDS))


def json_safe(d: dict) -> dict:
    """An adapter's dict as final.json can hold it: numpy scalars and arrays as Python values; raises if anything else
    is not JSON (so the caller can record that instead of dying writing final.json)."""
    out = {}
    for k, v in d.items():
        if isinstance(v, np.generic):
            v = v.item()
        elif isinstance(v, np.ndarray):
            v = v.tolist()
        out[str(k)] = v
    json.dumps(out, allow_nan=False)
    return out


class Refused(Exception):
    """A request the service turns down with `code` and the JSON `body`; nothing was executed."""

    def __init__(self, code: int, body: dict):
        super().__init__(body.get("error"))
        self.code, self.body = code, body


def real(meta: dict, key: str, default=None):
    """meta[key] as a float: a JSON number (not a boolean, not a string), finite; absent or null -> `default`.
    ValueError (a 400 inside bad_request) otherwise."""
    v = meta.get(key)
    if v is None:
        return default
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not np.isfinite(float(v)):
        raise ValueError(f"{key} must be a finite number (got {v!r:.60})")
    return float(v)


@contextlib.contextmanager
def bad_request():
    """Checking a request, before anything runs: whatever goes wrong here is the request's fault (400)."""
    try:
        yield
    except Refused:
        raise
    except Exception as exc:  # noqa: BLE001 -- a wrong type, value or shape of any field
        raise Refused(400, {"error": str(exc)[:300] or type(exc).__name__}) from None


CRASH_LOG = "crash.log"
FATAL = b"Fatal Python error"                 # how faulthandler begins a fatal signal's record
_crash_log = None                             # this process's crash.log, open for faulthandler


def count_start(data: str) -> int:
    """Record one process start in startups.jsonl (with crash.log's size: what the deaths before it wrote there);
    returns how many there have been."""
    path = os.path.join(data, "startups.jsonl")
    crash = os.path.join(data, CRASH_LOG)
    size = os.path.getsize(crash) if os.path.exists(crash) else 0
    with open(path, "a") as f:
        f.write(json.dumps({"ts": time.time(), "pid": os.getpid(), "crash_log_bytes": size}) + "\n")
    with open(path) as f:
        return sum(1 for _ in f)


def enable_crash_log(data: str) -> None:
    """A fatal signal (SIGSEGV, SIGBUS, SIGFPE, SIGILL, SIGABRT) leaves a record in DATA/crash.log (faulthandler, which
    writes to the file descriptor directly, nothing buffered); a kill (SIGKILL, SIGTERM, the OOM killer) leaves none."""
    global _crash_log
    _crash_log = open(os.path.join(data, CRASH_LOG), "a", buffering=1)
    faulthandler.enable(file=_crash_log, all_threads=True)


STEP_FRAMES = (" in _step",)                  # the service's control step (Service._step, which runs sim.step)


def crashed_in_step(record: bytes) -> bool:
    """Does a fatal signal's record (faulthandler: every thread's stack, the crashing one under "Current thread", most
    recent call first) show the crashing thread inside a control step? Not when it died building the scene, replaying
    the journal to resume, resetting, rendering for a request, finalizing or in live_verdict()."""
    text = record.decode("utf-8", "replace")
    i = text.find("Current thread")
    if i < 0:
        return False
    block = text[i:].split("\n\n", 1)[0]
    return any(line.rstrip().endswith(STEP_FRAMES) for line in block.splitlines()[1:])


def deaths(data: str) -> list[dict]:
    """The process deaths startups.jsonl implies, in order: the k-th (0-based) ended process k + 1 (1-based, as a start
    event's `startup` counts) and came before start k + 2. Each: {"process", "restart_ts", "fatal_signal", "in_step"};
    fatal_signal = crash.log grew between the two starts with a fatal signal's record (None: a start without the size,
    before 2026-10-17); in_step = that record shows the crashing thread inside a control step (crashed_in_step)."""
    try:
        with open(os.path.join(data, "startups.jsonl")) as f:
            starts = [json.loads(line) for line in f if line.strip()]
    except (OSError, ValueError):
        return []
    try:
        with open(os.path.join(data, CRASH_LOG), "rb") as f:
            log = f.read()
    except OSError:
        log = b""
    out = []
    for k in range(len(starts) - 1):
        a, b = starts[k].get("crash_log_bytes"), starts[k + 1].get("crash_log_bytes")
        chunk = b"" if a is None or b is None else log[int(a):int(b)]
        fatal = None if a is None or b is None else FATAL in chunk
        out.append({"process": k + 1, "restart_ts": float(starts[k + 1].get("ts") or 0.0), "fatal_signal": fatal,
                    "in_step": bool(fatal) and crashed_in_step(chunk)})
    return out


def write_json_atomic(path: str, obj: dict) -> None:
    """Write then rename: the collect hook polling the file never reads half of it."""
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(obj, f)
    os.replace(tmp, path)


def give_up(data: str, reason: str, infra: bool) -> None:
    """Record that this trial's episode will not run (again): final.json failed and finalized with the reason (a
    finalized final.json is kept as it is), and the PID file for the collect hook."""
    with open(os.path.join(data, "episode.jsonl"), "a") as f:
        f.write(json.dumps({"ts": time.time(), "ev": "restart_refused", "reason": reason}) + "\n")
    path = os.path.join(data, "final.json")
    try:
        with open(path) as f:
            fin = json.load(f)
    except (OSError, ValueError):
        fin = {}
    if not fin.get("finalized"):
        if "ended_by" in fin:                        # an agent-ended episode's record of an earlier end: the trial
            fin["ended_by"] = "error"                # ends on this give-up, no end the agent or the task chose
        fin.update({"protocol": PROTOCOL, "success": False, "done": True, "reason": reason, "finalized": True,
                    **({"infra_error": 1} if infra else {})})
        write_json_atomic(path, fin)
    elif fin.get("video_pending"):                   # the verdict stands; no video is coming from this trial any more
        write_json_atomic(path, {**fin, "video": False, "video_pending": False})
    with open(os.path.join(data, "server.pid"), "w") as f:
        f.write(str(os.getpid()))


def encode_mp4(frames, fps: float) -> bytes:
    """H.264 mp4 of (N,H,W,3) frames: an array, or a list (or any iterable) of (H,W,3) frames."""
    import imageio.v2 as imageio
    fd, path = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    try:
        with imageio.get_writer(path, format="FFMPEG", mode="I", fps=fps, codec="libx264", macro_block_size=1,
                                output_params=["-movflags", "+faststart", "-pix_fmt", "yuv420p"]) as w:
            for f in frames:
                w.append_data(np.ascontiguousarray(f))
        with open(path, "rb") as f:
            return f.read()
    finally:
        os.unlink(path)


class Recorder:
    """What one call returns: a proprio row at its start, every `every` control steps (the requested video_fps, rounded to
    whole control steps) and at its end; with them the cameras' frames when a video or the frames are asked for, else
    only the last frame (rendering is most of a call's cost)."""

    def __init__(self, sim, cameras: list[str], fps: int, depth: bool, video: str):
        self.sim, self.cams, self.depth, self.video = sim, cameras, depth, video
        self.every = max(1, round(1.0 / (sim.control_dt * fps)))
        self.fps = 1.0 / (self.every * sim.control_dt)
        self.images = video != "none"
        self.frames = {c: [] for c in cameras}
        self.dep = {c: [] for c in cameras}
        self.prop: list[np.ndarray] = []
        self.k, self.grabbed_at = 0, None

    def images_per_call(self, steps: int) -> int:
        per_frame = len(self.cams) + (len(set(self.cams) & set(self.sim.depth_cameras)) if self.depth else 0)
        return (steps // self.every + 2 if self.images else 1) * per_frame

    def start(self) -> None:
        self._grab(self.images)

    def step(self) -> None:
        self.k += 1
        if self.k % self.every == 0:
            self._grab(self.images)

    def finish(self) -> None:
        if self.grabbed_at != self.k:
            self._grab(self.images)
        if not self.images:
            self._grab(True, proprio=False)          # the one frame a call without video returns: the last

    def _grab(self, images: bool, proprio: bool = True) -> None:
        if images:
            rgb, dep = self.sim.images(self.cams, self.depth)
            for c in self.cams:
                self.frames[c].append(rgb[c])
                if c in dep:                         # kept as it is sent: float16 (2 bytes a pixel; RGB has 3)
                    self.dep[c].append(np.asarray(dep[c]).astype(np.float16))
        if proprio:
            self.prop.append(np.asarray(self.sim.proprio(), np.float32))
            self.grabbed_at = self.k

    def parts(self) -> list:
        """The response's RCB1 parts; the Recorder hands its frames over (call it once). One copy of the frames: no
        np.stack; frames/ and depth/ are written into the body from the lists (rcb1.Frames, which empties them), the
        mp4 is encoded from the list, and a list nothing sends is let go of here."""
        out = []
        for c in self.cams:
            fp = rcb1.frames_part(f"frames/{c}", self.frames[c])   # np.stack's dtype and shape (and its error if empty)
            fr, self.frames[c] = fp[2], []
            if self.video in ("mp4", "both"):
                out.append((f"video/{c}", "mp4", encode_mp4((np.asarray(f, fr.dtype) for f in fr.arrays), self.fps),
                            {"fps": round(self.fps, 3), "n": int(len(fr.arrays))}))
            last = rcb1.array_part(f"last/{c}", np.asarray(fr.arrays[-1], fr.dtype))
            if self.video in ("frames", "both"):
                out.append(fp)
            else:
                fr.arrays.clear()
            out.append(last)
            if self.dep[c]:
                out.append(rcb1.frames_part(f"depth/{c}", self.dep[c]))
            self.dep[c] = []
        out.append(rcb1.array_part("proprio", np.stack(self.prop)))
        return out


class FrameRing:
    """The standard recorder (eai-standard/3.0; module docstring): during every /submit, every `every` control steps, the
    RGB image of each camera, the proprio row and the control step, kept for the last `buffer_s` robot seconds; /observe
    last_s reads it. Cleared at a reset (a process start begins with it empty)."""

    def __init__(self, cameras, control_dt: float, mode=True, fps: float = CAMERA_FPS, buffer_s: float = LOOKBACK_S):
        self.mode = mode if mode in ("delivered", False) else True
        self.cams, self.cdt = list(cameras), float(control_dt)
        self.every = max(1, int(round(1.0 / (self.cdt * max(float(fps), 1e-9)))))   # at most the control rate
        self.fps, self.buffer_s = 1.0 / (self.every * self.cdt), float(buffer_s)
        self.keep = max(1, int(round(self.buffer_s / self.cdt)))                   # control steps kept
        self.frames: collections.deque = collections.deque()                       # {step, rgb: {cam: img}, proprio}

    def spec(self) -> dict:
        how = {True: "during /submit", "delivered": "during /submit: the images the submit's own answer carries",
               False: "nothing: last_s returns the current frame"}[self.mode]
        return {"cameras": self.cams if self.mode else [], "fps": round(self.fps, 3), "buffer_s": self.buffer_s,
                "records": how, "depth": []}           # RGB only: depth comes with the current frame (last_s = 0)

    def clear(self) -> None:
        self.frames.clear()

    def has(self, step: int) -> bool:
        return bool(self.frames) and self.frames[-1]["step"] == step

    def add(self, step: int, rgb: dict, proprio) -> None:
        while self.frames and self.frames[-1]["step"] >= step:
            self.frames.pop()
        self.frames.append({"step": int(step), "rgb": rgb, "proprio": proprio})
        while self.frames and self.frames[0]["step"] < step - self.keep:
            self.frames.popleft()

    def window(self, now: int, last_s: float, fps: float, cameras=None) -> list[dict]:
        """The frames of the last `last_s` robot seconds before control step `now` (at most buffer_s), at least
        1 / fps apart, newest last; [] when none was recorded in it. Only frames that hold an image of every camera in
        `cameras` count ("delivered" keeps the cameras each submit asked for, so a frame may lack one): the answer's
        frames/<cam>, proprio and frame_step then share one frame axis."""
        n = int(round(min(float(last_s), self.buffer_s) / self.cdt))
        every = max(self.every, int(round(1.0 / (self.cdt * max(float(fps), 1e-9)))))
        need = list(cameras or ())
        sel: list[dict] = []
        for f in reversed(self.frames):
            if f["step"] < now - n or f["step"] > now:
                break
            if any(c not in f["rgb"] for c in need):
                continue
            if not sel or sel[-1]["step"] - f["step"] >= every:
                sel.append(f)
        return sel[::-1]


class Service:
    """Episode bookkeeping, evidence and the HTTP endpoints around one `Sim`."""

    def __init__(self, sim, *, data: str = "/data", reset_budget: int = 0, wall_clock_s: float = 3600.0,
                 max_chunk_s: float = 10.0, max_frames_per_call: int = MAX_FRAMES_PER_CALL,
                 max_resumes: int = 2, agent_end: bool | None = None, step_limit: int | None = None):
        # agent-ended episodes (AGENT_END above; the arguments override the environment, for tests)
        self.agent_end = AGENT_END if agent_end is None else bool(agent_end)
        self.step_limit = (STEP_LIMIT if step_limit is None else (int(step_limit) or None)) if self.agent_end else None
        self.end_judgement = str(getattr(sim, "end_judgement", "state") or "state")
        if self.end_judgement not in ("state", "events"):
            raise ValueError(f"end_judgement must be 'state' or 'events', not {self.end_judgement!r}")
        self.cap = min(int(sim.max_control_steps), self.step_limit or int(sim.max_control_steps))
        self.hidden = (HIDDEN_KEYS | frozenset(getattr(sim, "hidden_keys", ()) or ())) if self.agent_end else frozenset()
        self.now_success, self.seen_step, self.trial_seen, self.finish_t = False, None, False, None
        if callable(getattr(sim, "verify", None)) and not getattr(sim, "replay_free", False):
            # A grading replay of its own is no longer called: an adapter that still has one would lose
            # whatever its replay applied, silently. It moves that rule to step() / live_verdict(), or says it has done
            # so (replay_free = True).
            raise TypeError(f"{type(sim).__name__} defines verify(), which this service never calls: move its rule "
                            "to step() or live_verdict(), or set replay_free = True")
        self.sim, self.data = sim, data
        self.reset_budget, self.wall_clock_s = int(reset_budget), float(wall_clock_s)
        self.max_chunk_s = float(max_chunk_s)
        self.max_frames, self.max_resumes = int(max_frames_per_call), int(max_resumes)
        os.makedirs(os.path.join(data, "calls"), exist_ok=True)
        self.journal_path = os.path.join(data, "trajectory_live.f64")
        self.ring = FrameRing(sim.cameras, sim.control_dt, getattr(sim, "record_frames", True))   # eai-standard/3.0
        self.spec = self._spec()
        self.types = {k: v for k, v in self.spec["action_types"].items() if isinstance(v, dict)}
        self.calls = self.rows = self.resets = 0
        self.journal_rows = 0          # control steps executed over the whole trial (the journal's length)
        self.ep_start = 0              # where the current episode begins in the journal
        self.episode: list[np.ndarray] = []   # the current episode's sim rows: what finalize grades
        self.done, self.reason, self.success = False, None, False
        self.stopping = False          # SIGUSR1 seen: the agent is gone
        self.finalized, self.verdict = False, {}
        self.t0 = self.t_end = None    # the clock starts at the agent's first request
        self.starts = 1
        self.ep_start_ok = True        # the current episode began at the frozen instance's start_sha (or none is known)
        self.judged_before = False     # a process of this trial died inside live_verdict()
        self.error_infra = False       # the episode's "error" is the simulator's, not the agent's (a reset's rebuild)
        self._unwritten: list[np.ndarray] = []   # sim rows executed since the last checkpoint

    # ------------------------------------------------------------------ spec and status
    def _spec(self) -> dict:
        own = self.sim.spec()
        core = {"protocol": PROTOCOL, "standard": EAI_STANDARD, "control_dt": self.sim.control_dt, "max_control_steps": self.cap,
                "max_chunk_s": self.max_chunk_s, "max_video_fps": MAX_VIDEO_FPS,
                "max_frames_per_call": self.max_frames, "proprio_layout": list(self.sim.proprio_layout),
                "budget": {"reset": self.reset_budget, "wall_clock_s": self.wall_clock_s},
                "clock": "time_s and elapsed_s count from your first request to the service; time_left_s is "
                         "budget.wall_clock_s minus time_s",
                "on_service_error": ON_SERVICE_ERROR}
        if clash := sorted(set(core) & set(own)):
            raise ValueError(f"the adapter's spec() must not set {clash}")
        cams = {c: {"rgb": True, "depth": c in self.sim.depth_cameras, **own["cameras"].get(c, {})}
                for c in self.sim.cameras}
        spec = {**core, **own, "cameras": cams}
        spec["timing"] = {**(own["timing"] if isinstance(own.get("timing"), dict) else {}),
                          "submit": "blocks until its rows have run and answers with their video and duration_s; "
                                    'a hold chunk {"type": <type>, "interpolate": "hold", "seconds": n} with no rows '
                                    "holds the current target for n seconds (at most max_chunk_s)",
                          "observe": "a pure read, at once; no time passes: last_s = 0 (default) the current frame, "
                                     "last_s = n the frames recorded in the last n seconds (at most recorder.buffer_s)",
                          "recorder": self.ring.spec()}
        if self.reset_budget:
            spec["reset"] = ("POST /reset abandons the running episode and starts a new one from the same starting "
                             "state, budget.reset times in all; only the last episode is graded, and a success ends "
                             "the trial")
        if self.agent_end:
            if "success_signal" in own:
                raise ValueError("the adapter's spec() must not set ['success_signal']")
            spec["success_signal"] = SUCCESS_SIGNAL_NOTE
            if self.step_limit:
                spec["budget"]["steps"] = self.cap
            if self.reset_budget:
                spec["reset"] = ("POST /reset abandons the running episode and starts a new one from the same starting "
                                 "state, budget.reset times in all; only the last episode is graded (after /finish "
                                 "no reset is possible)")
        return spec

    def clock(self) -> float:
        return 0.0 if self.t0 is None else time.time() - self.t0

    def _counters(self) -> dict:
        out = {"calls": self.calls, "rows": self.rows, "control_steps": len(self.episode), "done": self.done,
               "reason": self.reason}
        if self.step_limit:
            out.update(step_limit=self.cap, steps_left=max(0, self.cap - len(self.episode)))
        if self.reset_budget:
            out.update(episode=self.resets + 1, control_steps_total=self.journal_rows, resets_left=self._resets_left())
        return out

    def _resets_left(self) -> int:
        """The resets /reset would still grant: 0 whenever it is a 409 whatever the budget (a success shown, the
        agent's time up, /finish or the session's end, a service that gave up)."""
        if (self._success_shown() or self.stopping or self.finalized
                or (self.agent_end and self.done and self.reason in ("finished", "timeout"))):
            return 0
        return max(0, self.reset_budget - self.resets)

    def status(self) -> dict:
        return {**self._counters(), "elapsed_s": round(self.clock(), 1)}

    def meta(self) -> dict:
        t = self.clock()
        return {**self._counters(), "sim_time_s": round(len(self.episode) * self.sim.control_dt, 4),
                "time_s": round(t, 2), "time_left_s": max(0.0, round(self.wall_clock_s - t, 1)),
                "proprio": {"layout": list(self.sim.proprio_layout),
                            "now": np.asarray(self.sim.proprio(), np.float32).tolist()}}

    # ------------------------------------------------------------------ evidence
    def log(self, ev: str, **kw) -> None:
        with open(os.path.join(self.data, "episode.jsonl"), "a") as f:
            f.write(json.dumps({"ts": time.time(), "ev": ev, **kw}) + "\n")

    def _events(self) -> list[dict]:
        try:
            with open(os.path.join(self.data, "episode.jsonl")) as f:
                return [json.loads(line) for line in f if line.strip()]
        except OSError:
            return []

    def _checkpoint(self, ev: str, **kw) -> None:
        """Log a state this service may resume from, after appending everything executed since the last one to the
        journal. Rows of a call that never reaches its checkpoint are lost with it, as the call is."""
        if self._unwritten:
            with open(self.journal_path, "ab") as f:
                f.write(np.asarray(self._unwritten, dtype=np.float64).tobytes())
            self._unwritten = []
        self.log(ev, **kw, calls=self.calls, rows=self.rows, resets=self.resets, ep_start=self.ep_start,
                 journal_rows=self.journal_rows, done=self.done, reason=self.reason, success=self.success,
                 error_infra=self.error_infra, state_sha=self.sim.state_sha(),
                 **({"now_success": self.now_success, "seen_step": self.seen_step, "trial_seen": self.trial_seen,
                     "finish_t": self.finish_t} if self.agent_end else {}))
        self._write_final()

    def _write_final(self) -> None:
        end = self.t_end or time.time()
        d = {"protocol": PROTOCOL, "success": False, "live_success": self.success, "done": self.done,
             "reason": self.reason, "calls": self.calls, "rows": self.rows, "control_steps": len(self.episode),
             "control_steps_total": self.journal_rows, "episodes": self.resets + 1, "resets": self.resets,
             "reset_budget": self.reset_budget, "elapsed_s": round(end - self.t0, 1) if self.t0 else 0.0,
             "sim_startups": self.starts, "finalized": self.finalized, **self.verdict, **self._ae_fields()}
        if self.verdict.get("graded_by") == "live":     # the verdict is in: the live episode's, nothing replayed
            d["success"] = bool(self.success and self.verdict.get("live_rule", True))
        if self.reason == "error" and self.error_infra:  # the simulator failed, not the agent's commands
            d["infra_error"] = 1
        if not self.ep_start_ok:                        # the graded episode began off the frozen instance (a reset)
            d.update(success=False, instance_mismatch=True, infra_error=1)
        # The first attempt (evidence only). No reset: it is the graded episode. Without agent-ended episodes a success
        # ends the trial, so a first episode a reset followed did not succeed; with them a success ends nothing and a
        # step-limit or failure end may be followed by a reset: the first episode's own end judgement (_first_episode,
        # in finalize; null until then or when it is not on record).
        if self.resets == 0:
            d["first_success"] = bool(d["success"])
        elif not self.agent_end:
            d["first_success"] = False
        else:
            d.setdefault("first_success", None)
        d.setdefault("first_reason", self.reason if self.resets == 0 else None)
        write_json_atomic(os.path.join(self.data, "final.json"), d)

    def _ae_fields(self) -> dict:
        """final.json's record of an agent-ended episode (evidence only; nothing without the feature)."""
        if not self.agent_end:
            return {}
        r = self.reason
        out = {"success_signal": "hidden", "ended_by": ENDED_BY.get(str(r).split(":")[0], "failed") if r else None,
               "end_judgement": self.end_judgement, "hidden_success_seen": self.seen_step is not None,
               "hidden_success_first_step": self.seen_step, "trial_hidden_success_seen": bool(self.trial_seen),
               "finish_time_s": round(self.finish_t - self.t0, 1) if self.finish_t and self.t0 else None}
        if self.step_limit:
            out.update(step_limit=self.cap, steps_used=len(self.episode))
        return out

    def _success_shown(self) -> bool:
        """The success as an answer may let it show (the trial over, no reset after it): never with the feature on (an
        episode the step cap ended keeps its resets as before a success)."""
        return self.success and not self.agent_end

    def _hidden_success(self, success) -> None:
        """The task's success as the state now is (after a control step): kept, never latched and never shown; the
        episode's first one is logged."""
        self.now_success = bool(success)
        if success and self.seen_step is None:
            self.seen_step, self.trial_seen = len(self.episode), True
            self.log("hidden_success", control_steps=self.seen_step, episode=self.resets + 1)

    def _judged(self) -> bool:
        """An end-state end's verdict before the settle window: the state's success, or for a goal of moments whether
        the episode reached one."""
        return self.seen_step is not None if self.end_judgement == "events" else self.now_success

    def _shown(self, info: dict) -> dict:
        """step()'s info as an answer may carry it: without the keys that would tell the agent about its success."""
        return {k: v for k, v in info.items() if k not in self.hidden} if self.hidden else info

    def _save_call(self, meta: dict, actions: np.ndarray | None) -> None:
        d = os.path.join(self.data, "calls", f"{self.calls:06d}")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "meta.json"), "w") as f:
            json.dump(meta, f)
        if actions is not None:
            np.save(os.path.join(d, "actions.npy"), actions)

    # ------------------------------------------------------------------ start, resume, give up
    def start(self) -> None:
        """A fresh episode, or -- after a crash -- the same one again. Raises GiveUp when it must not run again."""
        try:
            with open(os.path.join(self.data, "startups.jsonl")) as f:
                self.starts = max(1, sum(1 for _ in f))
        except OSError:
            self.starts = 1
        ev = self._events()
        if not any(e["ev"] == "start" for e in ev):
            # The frozen initial state is checked when the episode begins (the verdict is the live episode's, so no later
            # replay checks it): a scene that did not build to the instance's recorded state is no trial of this task.
            want = getattr(self.sim, "start_sha", None)
            if want and (got := self.sim.state_sha()) != want:
                self._give_up(f"instance_mismatch: the scene started at {got}, the frozen instance records {want}",
                              infra=True)
            open(self.journal_path, "wb").close()
            self._checkpoint("start", protocol=PROTOCOL, spec=self.spec, startup=self.starts)
        else:
            self._resume(ev)
        with open(os.path.join(self.data, "server.pid"), "w") as f:
            f.write(str(os.getpid()))

    def _resume(self, ev: list[dict]) -> None:
        path = os.path.join(self.data, "final.json")
        try:
            with open(path) as f:
                fin = json.load(f)
        except (OSError, ValueError):
            fin = {}
        if fin.get("finalized") or "deterministic" in fin or "graded_by" in fin:
            # Graded already. The process died rendering the video (video_pending; before 2026-10, a verdict not yet
            # finalized): all it lost is the video.
            if not fin.get("finalized") or fin.get("video_pending"):
                write_json_atomic(path, {**fin, "finalized": True, "video": False, "video_pending": False})
            self._give_up("restarted after finalize", infra=False)
        first = int(next(e for e in ev if e["ev"] == "start")["startup"])
        restarts = self.starts - first
        last = max(i for i, e in enumerate(ev) if e["ev"] in ("start", "resuming"))
        in_call = self._died_in_call(ev[last:])     # did the process that died do so serving one of the agent's calls?
        in_calls = sum(bool(e["crashed_in_call"]) for e in ev if e["ev"] == "resuming") + int(in_call)
        died = [d for d in deaths(self.data) if d["process"] >= first]      # the deaths since the episode began
        fatal = bool(died and died[-1]["fatal_signal"])                      # the one just before this start
        ci = max(i for i, e in enumerate(ev) if "state_sha" in e and "journal_rows" in e)
        cp = ev[ci]
        # An end logged after it without a checkpoint (_end's fallback: the state could not be hashed) still ended the
        # episode: it resumes from that checkpoint ended, as the end event says
        end = next((e for e in reversed(ev[ci + 1:]) if e["ev"] == "end" and e.get("done")), None)
        if end is not None:
            cp = {**cp, "done": True, "reason": end["reason"], "success": bool(end.get("success")),
                  "error_infra": bool(end.get("error_infra")),
                  **({"finish_t": end["finish_t"]} if end.get("finish_t") is not None else {})}
        # The live outcome is decided when the graded episode has ended and nothing can follow it: a success, or a
        # failure with no reset left. Then crashes after it cannot take that outcome away: past the restarts, the
        # episode is resumed and finalized as it ended (its own verdict, live_verdict() included), not given up.
        decided = bool(cp["done"]) and cp["reason"] != "reset" and (
            bool(cp["success"]) or int(cp["resets"]) >= self.reset_budget
            or (self.agent_end and cp["reason"] in ("finished", "timeout")))
        finalize_now = restarts > self.max_resumes and decided
        if restarts > self.max_resumes and not decided:
            agent = self._agent_crashes(ev, died, in_calls) >= restarts   # every crash was the agent's
            self._give_up("sim_crashed_on_call" if agent else "sim_crashed", infra=not agent)
        self.log("resuming", crashed_in_call=in_call, fatal_signal=fatal, restart=restarts,
                 **({"finalize_decided": True} if finalize_now else {}))
        n, dim = int(cp["journal_rows"]), int(self.sim.raw_dim)
        rows = np.fromfile(self.journal_path, dtype=np.float64) if os.path.exists(self.journal_path) else np.zeros(0)
        if rows.size < n * dim:
            self._give_up("resume_failed: journal shorter than the log", infra=True)
        rows = rows[: n * dim].reshape(n, dim)
        for row in rows[cp["ep_start"]:]:
            self.sim.step(row)
        if self.sim.state_sha() != cp["state_sha"]:
            self._give_up("resume_failed: replayed state differs from the logged one", infra=True)
        rows.tofile(self.journal_path)                # drop the steps of the call that was in flight
        self.calls, self.rows, self.resets = int(cp["calls"]), int(cp["rows"]), int(cp["resets"])
        self.ep_start, self.journal_rows = int(cp["ep_start"]), n
        self.episode = [r.copy() for r in rows[self.ep_start:]]
        self.done, self.reason, self.success = bool(cp["done"]), cp["reason"], bool(cp["success"])
        if self.agent_end:
            self.now_success, self.seen_step = bool(cp.get("now_success")), cp.get("seen_step")
            self.trial_seen, self.finish_t = bool(cp.get("trial_seen")), cp.get("finish_t")
        self.judged_before = any(e["ev"] == "live_verdict_begin" for e in ev)   # a process died in live_verdict()
        self.error_infra = bool(cp.get("error_infra", self.error_infra))
        if cp["ev"] == "end" and cp["reason"] == "reset":
            # The process died inside a reset, after the abandoned episode's end and before the new episode began: a
            # reset lost with its call never happened (as in server_mj.py), so that episode runs on and the reset is
            # not charged; the agent may reset again (before, every call was a 409 until it did).
            self.done, self.reason, self.success = False, None, False
        self.t0 = next((e["t0"] for e in ev if e["ev"] == "first_request"), None)
        if self.done:
            self.t_end = next((e["ts"] for e in reversed(ev) if e["ev"] == "end"), cp["ts"])
        self._checkpoint("resumed", downtime_s=round(time.time() - float(ev[-1]["ts"]), 1))
        if finalize_now:
            # Past the restarts with the outcome decided: grade it now (the agent may still be calling, but nothing it
            # does can change a decided episode) and serve nothing more -- the crashes it suffered came after its end.
            self.stopping = True
            self._finalize()
            self._give_up("restarted after finalize: crashes after the episode had ended", infra=False)

    @staticmethod
    def _died_in_call(evs: list[dict]) -> bool:
        """Did the process whose events these are die serving one of the agent's calls while its episode was still
        running? A /reset is not counted (its rebuild is the simulator's, infrastructure), nor a call that came after
        the episode had ended (only deaths before the episode's end count toward the agent's crashes)."""
        open_call, over = None, False
        for e in evs:
            if "journal_rows" in e and "done" in e:
                over = bool(e["done"]) and e.get("reason") != "reset"
            if e["ev"] == "call_begin":
                open_call = (e.get("path"), over)
            elif e["ev"] == "call_end":
                open_call = None
        return bool(open_call) and open_call[0] != "/reset" and not open_call[1]

    def _agent_crashes(self, ev: list[dict], died: list[dict], in_calls: int) -> int:
        """How many of the deaths since the episode began were the agent's: here, those while serving a call (its
        commands were running); rcb_realtime.py counts simulator crashes after the first command instead."""
        return in_calls

    def _give_up(self, reason: str, infra: bool) -> None:
        """End the trial without running its episode again (give_up()) and stop."""
        give_up(self.data, reason, infra)
        raise GiveUp(reason)

    # ------------------------------------------------------------------ requests
    def first_request(self) -> None:
        if self.t0 is None:
            self.t0 = time.time()
            self.log("first_request", t0=self.t0)

    def handle(self, method: str, path: str, body: bytes = b"", content_length: int | None = None) -> tuple[int, str, bytes]:
        """One request -> (status, content type, body): the whole HTTP surface, without the HTTP."""
        self.first_request()
        path = urlparse(path).path
        if method == "GET" and path in ("/spec", "/status"):
            return self._reply_json(200, self.spec if path == "/spec" else self.status())
        if self.agent_end and method == "POST" and path == "/finish":
            if (len(body) if content_length is None else content_length) > MAX_BODY:   # as every POST (its body unread)
                return self._reply_json(413, {"error": f"request body over {MAX_BODY} bytes"})
            self.log("call_begin", path=path, call=self.calls + 1)
            try:
                return self._reply_json(200, self._agent_finish())
            except Refused as exc:
                return self._reply_json(exc.code, exc.body)
            finally:
                self.log("call_end", path=path)
        routes = {"/submit": self._submit, "/observe": self._observe}
        if self.reset_budget:
            routes["/reset"] = self._reset
        if method != "POST" or path not in routes:
            return self._reply_json(404, {"error": "no such endpoint"})
        if (len(body) if content_length is None else content_length) > MAX_BODY:
            return self._reply_json(413, {"error": f"request body over {MAX_BODY} bytes"})
        try:
            meta, parts = self._decode(body)
        except Exception as exc:  # noqa: BLE001 -- any malformed body is the caller's error
            return self._reply_json(400, {"error": f"malformed body: {exc}"[:300]})
        self.log("call_begin", path=path, call=self.calls + 1)
        try:
            out, blobs = routes[path](meta, parts)
        except Refused as exc:                       # 400 (bad_request), 409: nothing ran
            return self._reply_json(exc.code, exc.body)
        except Exception as exc:  # noqa: BLE001 -- it ran and failed: the episode ends, as on hardware
            traceback.print_exc()
            self.log("error", path=path, error=repr(exc)[:500])
            self._end("error")
            return self._reply_json(500, {"error": "simulator error", "detail": repr(exc)[:200]})
        finally:
            self.log("call_end", path=path)
        return self._reply_rcb1(out, blobs)

    @staticmethod
    def _decode(body: bytes) -> tuple[dict, dict]:
        if body[:4] == rcb1.MAGIC:
            meta, parts = rcb1.decode(body)
        else:
            meta, parts = json.loads(body or b"{}"), {}
        if not isinstance(meta, dict):
            raise ValueError("the body must be a JSON object or an RCB1 frame")
        return meta, parts

    @staticmethod
    def _reply_json(code: int, obj: dict) -> tuple[int, str, bytes]:
        return code, "application/json", json.dumps(obj).encode()

    @staticmethod
    def _reply_rcb1(meta: dict, parts: list) -> tuple[int, str, bytes]:
        if rcb1.size(meta, parts) > MAX_RESPONSE:    # known before anything is built: the body is built once
            for p in parts:
                if p[0].startswith(("frames/", "depth/")) and isinstance(p[2], rcb1.Frames):
                    p[2].arrays.clear()
            parts = [p for p in parts if not p[0].startswith(("frames/", "depth/"))]
            meta = {**meta, "degraded": f"response over {MAX_RESPONSE} bytes: frames/ and depth/ dropped"}
        return 200, "application/x-rcb1", rcb1.encode(meta, parts)

    def _view(self, meta: dict, default_video: str) -> tuple[list[str], int, str, bool]:
        cams = meta.get("cameras") or list(self.sim.cameras)
        if isinstance(cams, str):
            cams = [c for c in cams.split(",") if c]
        if not isinstance(cams, list) or (unknown := sorted(set(map(str, cams)) - set(self.sim.cameras))):
            raise ValueError(f"unknown camera(s) {unknown if isinstance(cams, list) else cams}; "
                             f"the cameras are {list(self.sim.cameras)}")
        # Each camera once, in the order asked for. A name repeated N times would be rendered into one list N times and
        # returned N times (N * N images), which the frame budget counted as N: a small request could exhaust the memory.
        cams = list(dict.fromkeys(map(str, cams)))
        fps = real(meta, "video_fps", 10.0)
        if not 1 <= fps <= MAX_VIDEO_FPS:
            raise ValueError(f"video_fps must be in [1, {MAX_VIDEO_FPS}]")
        fps = int(fps)
        video = meta.get("video", default_video)
        if video not in VIDEOS:
            raise ValueError(f"video must be one of {list(VIDEOS)}")
        depth = bool(meta.get("include_depth", False))
        if depth and not set(cams) & set(self.sim.depth_cameras):
            raise ValueError(f"include_depth: none of {cams} has depth; spec()['cameras'][name]['depth'] says which do")
        return cams, fps, video, depth

    def _frame_budget(self, rec: Recorder, steps: int) -> None:
        n = rec.images_per_call(steps)
        if n > self.max_frames:
            raise ValueError(f"this call would return {n} images (cameras x frames, depth counted again); the limit is "
                             f"{self.max_frames}: ask for fewer cameras, a lower video_fps or a shorter chunk")

    def _conflict(self) -> Refused:
        if self.stopping:
            return Refused(409, {"error": "trial finished: your time is up", "reason": self.reason})
        body = {"error": "episode finished", "reason": self.reason}
        if self.reset_budget:
            body["resets_left"] = self._resets_left()
        return Refused(409, body)

    def _observe_refusal(self) -> Refused | None:
        """An /observe's 409, whatever it asks: after /finish, after the session's end (SIGUSR1) and after a give-up
        every call but GET /spec and /status is refused; after any other end of the episode it may still look."""
        if self.stopping or (self.agent_end and self.done and self.reason == "finished"):
            return self._conflict()
        if self.finalized:
            return Refused(409, {"error": "the sim service gave up on this trial", "reason": self.reason, "gave_up": True})
        return None

    def _step(self, typ: str, row: np.ndarray) -> dict:
        """One control step: execute, journal, and end the episode if it is over."""
        sim_row = np.asarray(self.sim.to_sim(typ, row), dtype=np.float64)
        done, success, info = self.sim.step(sim_row)
        self._unwritten.append(sim_row)
        self.journal_rows += 1
        self.episode.append(sim_row)
        if self.agent_end:     # the success is only recorded; a failure rule ends the episode, the step cap judges it
            self._hidden_success(success)
            if done and not success and not info.get("step_cap"):
                self._end("failed")
            elif len(self.episode) >= self.cap or (done and info.get("step_cap")):
                self._end("step_limit")
            return info
        if success:
            self._end("success")
        elif done or len(self.episode) >= self.sim.max_control_steps:
            self._end("failed")
        return info

    def _end(self, reason: str) -> None:
        if self.done:
            return
        self.done, self.reason, self.success = True, reason, reason == "success"
        if self.agent_end:     # an end-state end is judged on the state it leaves; on a goal of events a failure end
            # keeps the events that happened (decision 1); any other end (a simulator error, a reset) is 0
            self.success = (reason in END_STATE_REASONS
                            or (self.end_judgement == "events" and reason == "failed")) and self._judged()
            if reason == "finished":
                self.finish_t = time.time()
        self.t_end = time.time()
        try:
            self._checkpoint("end")
        except Exception as exc:  # noqa: BLE001 -- a broken simulator may not even hash: the end is still logged
            # (with how it ended: a resume from the checkpoint before it keeps the episode ended, _resume)
            self.log("end", reason=reason, done=True, success=bool(self.success), error_infra=bool(self.error_infra),
                     **({"finish_t": self.finish_t} if self.agent_end else {}), checkpoint_error=repr(exc)[:300])
            self._write_final()

    def _agent_finish(self) -> dict:
        """POST /finish: the agent ends the episode; the state it leaves is graded. After it, or after any end, a 409."""
        if self.done or self.stopping:
            raise self._conflict()
        self._end("finished")
        return {"ok": True, **self.status()}

    def _record(self, rec: Recorder | None, fresh: bool, force: bool = False) -> None:
        """The recorder (FrameRing), after a /submit's start, each of its control steps and its end: every ring.every
        control steps (and, forced, at the call's start and end) the images of every camera, the proprio row and the
        step. `fresh`: rec's newest images show this step (reused, not rendered again)."""
        ring = self.ring
        step = len(self.episode)
        if not ring.mode:
            return
        if ring.has(step):                           # recorded already: the same state (nothing ran since), so the
            if fresh and rec is not None:            # images this call rendered fill the cameras the frame lacks
                have = ring.frames[-1]["rgb"]        # ("delivered" keeps what each call asked for)
                for c in rec.cams:
                    if c in ring.cams and c not in have and rec.frames.get(c):
                        have[c] = rec.frames[c][-1]
            return
        if not (force or step % ring.every == 0):
            return
        rgb = {}
        if fresh and rec is not None:
            for c in rec.cams:
                if c in ring.cams and rec.frames.get(c):
                    rgb[c] = rec.frames[c][-1]
        missing = [c for c in ring.cams if c not in rgb]
        if missing and ring.mode is True:
            got, _ = self.sim.images(missing, False)
            rgb.update({c: got[c] for c in missing if c in got})
        if rgb:
            ring.add(step, rgb, np.asarray(self.sim.proprio(), np.float32))

    def _hold_seconds(self, meta: dict, parts: dict) -> float | None:
        """A hold chunk's seconds (a /submit with no rows, "interpolate": "hold", "seconds": n), or None for a chunk
        with rows. ValueError (400) for a mix of the two."""
        if "actions" in parts:
            data = parts["actions"].get("data") if isinstance(parts["actions"], dict) else parts["actions"]
            rows = data is not None and np.size(data) > 0
        else:
            src = meta.get("actions", meta.get("rows"))
            rows = src is not None and not (isinstance(src, (list, tuple)) and not src)
        if meta.get("seconds") is None:
            return None
        if rows:
            raise ValueError("a chunk with rows takes no `seconds` (its rows and dt say how long it runs); a hold chunk "
                             '{"type": <type>, "interpolate": "hold", "seconds": n} has no rows')
        if meta.get("interpolate") != "hold":
            raise ValueError('a chunk without rows is a hold chunk: {"type": <type>, "interpolate": "hold", '
                             '"seconds": n}')
        sec = real(meta, "seconds")
        if not 0.0 < sec <= self.max_chunk_s + 1e-9:
            raise ValueError(f"a hold chunk's seconds must be in (0, {self.max_chunk_s:g}] (max_chunk_s)")
        return sec

    def _submit(self, meta: dict, parts: dict) -> tuple[dict, list]:
        if self.done or self.stopping:
            raise self._conflict()
        with bad_request():
            typ = meta.get("type")
            if not isinstance(typ, str) or typ not in self.types:
                raise ValueError(f"type must be one of {sorted(self.types)}")
            hold = self._hold_seconds(meta, parts)
        if hold is not None:
            return self._hold_chunk(typ, hold, meta)
        with bad_request():
            try:
                A = np.asarray(parts["actions"]["data"] if "actions" in parts else meta.get("actions"), dtype=np.float64)
            except (TypeError, ValueError, KeyError):
                raise ValueError("send the actions as an RCB1 array part `actions` or a JSON list of rows") from None
            dim = int(self.types[typ]["dim"])
            if A.ndim != 2 or A.shape[0] < 1 or A.shape[1] != dim:
                raise ValueError(f"{typ} actions must be (T, {dim}) with T >= 1, got {list(A.shape)}")
            if not np.all(np.isfinite(A)):
                raise ValueError("actions contain NaN or inf")
            cdt = self.sim.control_dt
            dt = real(meta, "dt", cdt)
            k = round(dt / cdt) if np.isfinite(dt / cdt) else 0
            if k < 1 or abs(k * cdt - dt) > 1e-9:
                raise ValueError(f"dt must be a positive whole multiple of control_dt = {cdt} s (never rounded)")
            if k > 1 and not self.sim.interpolable(typ):
                raise ValueError(f"{typ}: one row is one control step, so dt must be control_dt = {cdt} s")
            if len(A) * k * cdt > self.max_chunk_s + 1e-9:
                raise ValueError(f"the chunk covers {len(A) * k * cdt:g} s: more than max_chunk_s = {self.max_chunk_s:g}")
            interp = meta.get("interpolate", "linear")
            if interp not in ("linear", "hold"):
                raise ValueError("interpolate must be linear or hold")
            cams, fps, video, depth = self._view(meta, "mp4")
            rec = Recorder(self.sim, cams, fps, depth, video)
            self._frame_budget(rec, len(A) * k)
        rows, clipped = self.sim.clip(typ, A)
        before, info, executed, stop = len(self.episode), {}, 0, False
        prev = np.asarray(self.sim.command(typ), dtype=np.float64)
        rec.start()
        self._record(rec, rec.images, force=True)
        for i, row in enumerate(rows):
            for j in range(1, k + 1):
                info = self._step(typ, row if interp == "hold" else prev + (row - prev) * (j / k))
                rec.step()
                self._record(rec, rec.images and rec.grabbed_at == rec.k)
                if self.done or self.stopping or info.get("blocked"):
                    stop = True
                    break
            executed, prev = i + 1, row
            if stop:
                break
        rec.finish()
        self._record(rec, True, force=True)
        self.calls += 1
        self.rows += executed
        ran = len(self.episode) - before
        out = {**self.meta(), "chunk_id": self.calls, "type": typ, "executed_rows": executed,
               "control_steps_chunk": ran, "duration_s": round(ran * cdt, 4),
               "planned_duration_s": round(len(A) * k * cdt, 4), "clipped": clipped[:200], "n_clipped": len(clipped),
               **({"frame_step": len(self.episode)} if cams else {}), **self._shown(info), "ok": True}
        self._checkpoint("submit", type=typ, n_rows=len(A), dt=dt, interpolate=interp, cameras=cams,
                         note=str(meta.get("note") or "")[:500], executed_rows=executed, n_clipped=len(clipped), **info)
        self._save_call(out, A)
        return out, rec.parts()

    def _hold_chunk(self, typ: str, seconds: float, meta: dict) -> tuple[dict, list]:
        """A hold chunk: the current target (sim.hold(), what the 2.x watch held) for round(seconds / control_dt)
        control steps, answered as a /submit (the video of the hold, duration_s)."""
        cdt = self.sim.control_dt
        with bad_request():
            cams, fps, video, depth = self._view(meta, "mp4")
            n = max(1, int(round(seconds / cdt)))
            rec = Recorder(self.sim, cams, fps, depth, video)
            self._frame_budget(rec, n)
        before, info = len(self.episode), {}
        htyp, hrow = self.sim.hold()
        rec.start()
        self._record(rec, rec.images, force=True)
        for _ in range(n):
            info = self._step(htyp, hrow)
            rec.step()
            self._record(rec, rec.images and rec.grabbed_at == rec.k)
            if self.done or self.stopping or info.get("blocked"):     # as a chunk with rows stops
                break
        rec.finish()
        self._record(rec, True, force=True)
        self.calls += 1
        ran = len(self.episode) - before
        out = {**self.meta(), "chunk_id": self.calls, "type": typ, "hold": True, "executed_rows": 0,
               "control_steps_chunk": ran, "duration_s": round(ran * cdt, 4), "planned_duration_s": round(seconds, 4),
               "clipped": [], "n_clipped": 0, **({"frame_step": len(self.episode)} if cams else {}), **self._shown(info),
               "ok": True}
        self._checkpoint("submit", type=typ, n_rows=0, hold=True, seconds=round(seconds, 4), cameras=cams,
                         note=str(meta.get("note") or "")[:500], executed_rows=0, n_clipped=0, **info)
        self._save_call(out, None)
        return out, rec.parts()

    def _observe(self, meta: dict, parts: dict) -> tuple[dict, list]:
        """A pure read (eai-standard/3.0): no time passes. last_s = 0 the current frame; last_s = n the frames the
        recorder took in the last n robot seconds (none: the current frame, meta.last_s = 0)."""
        refused = self._observe_refusal()
        if refused:
            raise refused
        with bad_request():
            if real(meta, "seconds", 0.0) != 0.0:
                raise ValueError(SECONDS_GONE)
            last_s = real(meta, "last_s", 0.0)
            if not last_s >= 0.0:
                raise ValueError("last_s must be a number of seconds >= 0")
            cams, fps, video, depth = self._view(meta, "frames")
            if last_s > 0 and depth:
                raise ValueError(DEPTH_PAST)
            step = len(self.episode)
            window = self.ring.window(step, last_s, fps, cams) if last_s > 0 else []
            if window:
                n = len(cams) * len(window)
                if n > self.max_frames:
                    raise ValueError(f"this call would return {n} images (cameras x frames); the limit is "
                                     f"{self.max_frames}: ask for fewer cameras, a lower video_fps or a shorter last_s")
            else:
                rec = Recorder(self.sim, cams, fps, depth, video if video != "mp4" else "frames")   # no time: no video
                self._frame_budget(rec, 0)
        if window:
            parts_out = self._window_parts(window, cams, fps, video)
            covered = round((window[-1]["step"] - window[0]["step"]) * self.sim.control_dt, 4)
            shown = int(window[-1]["step"])
        else:
            rec.start()
            rec.finish()
            parts_out, covered, shown = rec.parts(), 0.0, step
        self.calls += 1
        out = {**self.meta(), "obs_id": self.calls, "last_s": covered, "frame_step": shown, "seconds": 0.0,
               "control_steps_watch": 0, "ok": True}
        self._checkpoint("observe", last_s=covered, cameras=cams)
        self._save_call(out, None)
        return out, parts_out

    def _window_parts(self, window: list[dict], cams: list[str], fps: int, video: str) -> list:
        """An /observe answer's RCB1 parts from recorded frames (FrameRing.window, which keeps only frames holding every
        requested camera): per camera its video / frames as asked and the newest image as last/, the frames' proprio
        rows and their control steps, one frame axis for all of them."""
        cdt = self.sim.control_dt
        gap = (window[-1]["step"] - window[0]["step"]) / max(1, len(window) - 1) if len(window) > 1 else 0
        rate = 1.0 / (cdt * gap) if gap else float(fps)
        out = []
        for c in cams:
            imgs = [f["rgb"][c] for f in window]
            stack = np.stack([np.asarray(i, np.uint8) for i in imgs])
            if video in ("mp4", "both"):
                out.append((f"video/{c}", "mp4", encode_mp4(stack, rate), {"fps": round(rate, 3), "n": int(len(stack))}))
            if video in ("frames", "both"):
                out.append(rcb1.array_part(f"frames/{c}", stack))
            out.append(rcb1.array_part(f"last/{c}", stack[-1]))
        out.append(rcb1.array_part("proprio", np.stack([f["proprio"] for f in window])))
        out.append(rcb1.array_part("frame_step", np.asarray([f["step"] for f in window], np.int64)))
        return out

    def _reset_view(self, meta: dict) -> tuple[list[str], int, str, bool]:
        """A reset's checks, all of them, before anything changes: Refused (409, 400) or the view it returns."""
        if self._success_shown() or self.stopping:
            raise Refused(409, {"error": "trial finished: " + ("an episode succeeded" if self.success else "your time is up"),
                                "reason": self.reason})
        if self.agent_end and self.done and self.reason in ("finished", "timeout"):
            raise self._conflict()                   # the agent ended the episode: nothing follows it
        if self.finalized:
            raise Refused(409, {"error": "the sim service gave up on this trial", "reason": self.reason, "gave_up": True})
        if self.resets >= self.reset_budget:
            raise Refused(409, {"error": "reset budget exhausted", "budget": self.reset_budget})
        with bad_request():
            return self._view(meta, "frames")

    def _reset(self, meta: dict, parts: dict) -> tuple[dict, list]:
        cams, fps, video, depth = self._reset_view(meta)
        if not self.done:
            self._end("reset")                       # the running episode is abandoned
        try:
            self.sim.reset()
        except Exception:
            # The simulator failed to start the new episode: the trial ends on a simulator error, not on the episode
            # the agent had every right to abandon (handle() answers 500; its _end("error") finds the episode ended).
            # The agent's reset was legitimate: this error is infrastructure (owner, 2026-10-17; both modes).
            self.done, self.reason, self.success, self.error_infra = True, "error", False, True
            try:
                self._checkpoint("end", reset_failed=True)
            except Exception as exc:  # noqa: BLE001 -- a broken simulator may not even hash
                self.log("end", reason="error", reset_failed=True, done=True, success=False, error_infra=True,
                         checkpoint_error=repr(exc)[:300])
                self._write_final()
            raise
        self.resets += 1
        self.ring.clear()                            # the recorder keeps this episode's frames only
        self.ep_start, self.episode = self.journal_rows, []
        self.done, self.reason, self.success, self.t_end = False, None, False, None
        self.now_success, self.seen_step = False, None
        self.error_infra = False
        want = getattr(self.sim, "start_sha", None)
        got = self.sim.state_sha() if want else None
        self.ep_start_ok = not want or got == want   # the episode starts at the frozen instance
        if not self.ep_start_ok:
            # No trial of this task can go on from here: the service gives up at once (instance_mismatch,
            # infrastructure), finalized, and refuses every call after this one.
            self.done, self.success, self.finalized = True, False, True
            self.reason = f"instance_mismatch: a reset brought the scene to {got}, the frozen instance records {want}"
            self.verdict = {"video": False, "video_pending": False}
            self._checkpoint("reset", cameras=cams, start_ok=False)
            give_up(self.data, self.reason, infra=True)
            raise Refused(409, {"error": "the sim service gave up on this trial", "reason": self.reason, "gave_up": True})
        rec = Recorder(self.sim, cams, fps, depth, "frames" if video == "mp4" else video)   # no time: no video
        rec.start()
        rec.finish()
        self.calls += 1
        out = {**self.meta(), **({"frame_step": len(self.episode)} if cams else {}), "ok": True}
        self._checkpoint("reset", cameras=cams, start_ok=self.ep_start_ok)
        self._save_call(out, None)
        return out, rec.parts()

    # ------------------------------------------------------------------ the end of the trial
    def on_sigusr1(self, *_) -> None:
        """The agent is gone (the [[verifier.collect]] hook). Only a flag: the handler may fire in the middle of a
        request; a chunk stops at its next control step and poll() wraps up between requests."""
        self.stopping = True

    def poll(self) -> None:
        """Between requests (the HTTP loop calls it every 0.5 s): after SIGUSR1, end the episode and finalize."""
        if self.stopping and not self.finalized:
            if not self.done:
                self._end("timeout")
            self._finalize()

    def _first_episode(self) -> tuple[dict, np.ndarray | None]:
        """With resets, the trial's first episode: how it ended (the last "end" of episode 1 in the log; a reset lost
        with its call did not end it) and its rows (the journal up to the first reset's ep_start). Without: nothing."""
        if self.resets == 0:
            return {}, None
        ev = self._events()
        end = [e for e in ev if e["ev"] == "end" and int(e.get("resets", 0)) == 0]
        cut = next((int(e["ep_start"]) for e in ev if e["ev"] == "reset" and int(e.get("resets", 0)) == 1
                    and "ep_start" in e), None)
        info = {"first_reason": end[-1].get("reason") if end else None}
        if self.agent_end:                           # the "end" event's own judgement (no end window, no live_verdict)
            info["first_success"] = bool(end[-1].get("success")) if end and "success" in end[-1] else None
        if not cut:
            return info, None
        rows = np.fromfile(self.journal_path, dtype=np.float64, count=cut * int(self.sim.raw_dim))
        if rows.size != cut * int(self.sim.raw_dim):
            return info, None
        return {**info, "first_n_actions": cut}, rows.reshape(cut, -1)

    def _finalize(self) -> None:
        """The verdict: the live episode's (docs/protocol/README.md H.4). The graded episode (every control step since the last
        reset) is saved as the trajectory, the deliverable that stays replayable, and the success is the one the live
        episode ended with (plus the adapter's live_verdict(), which can only take it away): final from the moment it is
        written ("finalized": true). Nothing is replayed to grade it. Then a video for humans, rendered from the
        trajectory, which can no longer change or void the verdict: while it renders final.json says
        "video_pending": true (the collect hook waits for it as long as its time allows)."""
        rows = first_rows = None
        try:
            rows = np.asarray(self.episode, dtype=np.float64).reshape(-1, self.sim.raw_dim)
            try:
                live_sha = self.sim.state_sha()
            except Exception:  # noqa: BLE001 -- a simulator broken by the episode's own error may not hash: no verdict lost
                traceback.print_exc()
                live_sha = None
            self.sim.save_trajectory(rows, os.path.join(self.data, "trajectory.npz"),
                                     {"source": "standard-mode episode", "protocol": PROTOCOL, "reason": self.reason,
                                      "episode": self.resets + 1})
            verdict = {"n_actions": int(len(rows)), "graded_by": "live", "replays": 0, "state_sha": live_sha,
                       "video": False, "video_source": "render"}
            first_rows = None
            try:                                     # the first episode is evidence only: it never decides anything
                first, first_rows = self._first_episode()
                verdict.update(first)
                if first_rows is not None:
                    self.sim.save_trajectory(first_rows, os.path.join(self.data, "trajectory.first.npz"),
                                             {"source": "standard-mode episode (the first; not graded)",
                                              "protocol": PROTOCOL, "reason": str(first.get("first_reason")),
                                              "episode": 1})
                    verdict["first_video"] = False
            except Exception as exc:  # noqa: BLE001
                traceback.print_exc()
                self.log("first_episode_error", error=repr(exc)[:500])
                first_rows = None
            window = int(getattr(self.sim, "end_window_steps", 0) or 0)
            if (self.agent_end and window > 0 and self.end_judgement == "state" and self.reason in END_STATE_REASONS
                    and self.ep_start_ok):
                # the task's settle or hold window, run from the state the episode ended in (the agent is gone); the
                # success is the one at its last step (a failure rule in it gives 0)
                typ, hold = self.sim.hold()
                ok = self.now_success
                for _ in range(window):
                    d, s, i = self.sim.step(np.asarray(self.sim.to_sim(typ, hold), dtype=np.float64))
                    ok = bool(s)
                    if d and not s and not (i or {}).get("step_cap"):
                        break
                self.success = ok
                verdict.update(end_window_steps=window, end_window_success=ok)
            judge = getattr(self.sim, "live_verdict", None)
            if callable(judge):
                # the benchmark's own record of the live episode, judged on the live simulator (e.g. a settle window):
                # recorded in final.json; its "success" can take a success away (live_rule), never give one. It runs
                # after the agent's container is gone; whatever goes wrong in it is the episode's: no success
                # A process that died in it (a native crash) would die again on every resume: the restart that finds the
                # marker judges the hook failed instead (live_verdict_error "crashed": the episode's 0, not infra).
                if self.judged_before:
                    verdict.update(live_rule=False, live_verdict_error="crashed: the process died in live_verdict()")
                else:
                    self.log("live_verdict_begin")
                    try:
                        extra = json_safe(dict(judge(rows, bool(self.success)) or {}))
                        if "success" in extra:
                            verdict["live_rule"] = extra.pop("success") is True   # only a real True keeps a success
                        verdict.update({k: v for k, v in extra.items() if k not in RESERVED})
                    except Exception as exc:  # noqa: BLE001
                        traceback.print_exc()
                        verdict.update(live_rule=False, live_verdict_error=repr(exc)[:300])
            self.verdict = verdict
            self.log("verdict", **{k: v for k, v in verdict.items() if isinstance(v, (bool, int, float, str))})
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self.log("finalize_error", error=repr(exc)[:500])
            self.verdict = {"finalize_error": repr(exc)[:300]}
        graded = "finalize_error" not in self.verdict
        self.verdict["video_pending"] = graded
        self.finalized = True
        self._write_final()                          # the verdict, finalized, on disk before any video is rendered
        if not graded:
            return
        try:
            self.sim.render_video(rows, os.path.join(self.data, "replay.mp4"))
            self.verdict["video"] = True
        except Exception as exc:  # noqa: BLE001 -- the video is for humans; it never decides the verdict
            traceback.print_exc()
            self.log("video_error", error=repr(exc)[:500])
        if first_rows is not None:
            try:
                self.sim.render_video(first_rows, os.path.join(self.data, "replay.first.mp4"))
                self.verdict["first_video"] = True
            except Exception as exc:  # noqa: BLE001
                traceback.print_exc()
                self.log("first_video_error", error=repr(exc)[:500])
        self.verdict["video_pending"] = False
        try:
            self._write_final()
        except Exception:  # noqa: BLE001 -- the finalized verdict is on disk already; only the video's flag is lost
            traceback.print_exc()

    # ------------------------------------------------------------------ HTTP
    def http_server(self, address: tuple[str, int]) -> HTTPServer:
        svc = self

        class Handler(BaseHTTPRequestHandler):
            timeout = 120   # a client that stalls mid-request is dropped: one thread serves everyone

            def log_message(self, *a):
                pass

            def _send(self, code: int, ctype: str, body: bytes) -> None:
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                self._send(*svc.handle("GET", self.path))

            def do_POST(self):
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    n = -1
                if n < 0:                            # (read(-1) would read to the end of the stream, without a limit)
                    self.close_connection = True
                    return self._send(*svc._reply_json(400, {"error": "bad Content-Length"}))
                if n > MAX_BODY:                     # refused unread: drop the connection with it
                    self.close_connection = True
                    return self._send(*svc.handle("POST", self.path, b"", content_length=n))
                self._send(*svc.handle("POST", self.path, self.rfile.read(n)))

        class Server(HTTPServer):
            def service_actions(self):
                svc.poll()

        return Server(address, Handler)

    def bind(self, port: int) -> HTTPServer:
        """The HTTP server on `port`. Something else may hold the port -- in the network namespace it shares with the
        agent's container, an agent's process can take it while this service (re)starts -- so wait, not die (a death
        here would count as a crash); the trial can still end meanwhile (SIGUSR1)."""
        busy = False
        while True:
            try:
                return self.http_server(("0.0.0.0", port))
            except OSError as exc:
                if exc.errno != errno.EADDRINUSE:
                    raise
            if not busy:
                busy = True
                self.log("port_busy", port=port)
            self.poll()
            time.sleep(1.0)

    def serve(self, port: int = 8000) -> None:
        signal.signal(signal.SIGUSR1, self.on_sigusr1)
        srv = self.bind(port)
        print(f"{PROTOCOL} sim service ready on :{port}", flush=True)
        srv.serve_forever()


def refuse_forever(reason: str, port: int = 8000) -> None:
    """After a give-up: answer every request 409 with the reason until the container is removed. Before, nothing
    listened once the service had given up, and a client waited out its whole connection timeout for a simulator that
    would never answer. The verdict is on disk already: nothing here reads or changes it."""
    body = json.dumps({"error": "the sim service gave up on this episode and will not serve it", "reason": reason,
                       "gave_up": True}).encode()

    class Refusal(BaseHTTPRequestHandler):
        timeout = 30                                 # a client that stops sending must not hold the only thread

        def _refuse(self):
            try:
                n = int(self.headers.get("Content-Length") or 0)
                if 0 < n <= MAX_BODY:                # take the request first: a client still sending would see a reset
                    self.rfile.read(n)
                self.send_response(409)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (OSError, ValueError):
                pass
            self.close_connection = True

        do_GET = do_POST = _refuse

        def log_message(self, *args):
            pass

    def answer():
        while True:
            try:
                HTTPServer(("0.0.0.0", port), Refusal).serve_forever()
            except Exception:  # noqa: BLE001 -- a busy port, or anything else: the give-up stands without the answer
                time.sleep(5.0)

    threading.Thread(target=answer, daemon=True).start()
    while True:
        time.sleep(3600)


def main(build: Callable[[], Sim], port: int = 8000) -> None:
    """A sidecar's life: count the start, back off after a failed one, build the scene under a startup watchdog, resume
    or start the episode, serve. Settings: RCB_DATA (/data), RCB_RESET_BUDGET (0), RCB_WALL_CLOCK_S (3600),
    RCB_STARTUP_TIMEOUT_S (300), RCB_MAX_RESUMES (2)."""
    env = os.environ.get
    data = env("RCB_DATA", "/data")
    os.makedirs(data, exist_ok=True)
    starts = count_start(data)
    # Compose restarts a failed start at once; a scene that failed to build (e.g. the GPU full of other trials) would
    # meet the same conditions every time, so wait before rebuilding -- only before the episode exists.
    if starts > 1 and not os.path.exists(os.path.join(data, "episode.jsonl")):
        time.sleep(min(120, 20 * (starts - 1)))
    pending: list[int] = []
    signal.signal(signal.SIGUSR1, lambda *_: pending.append(1))   # its default action would kill the process
    # A scene build that hangs (no crash, so compose never restarts it) must end the process. Neither a Python thread
    # (a native hang may hold the GIL) nor SIGALRM's default action (PID 1 ignores it) can; faulthandler's C watchdog
    # dumps every thread's traceback and exits. Before the scene exists no episode exists: the retry is no reset.
    enable_crash_log(data)                           # a fatal signal leaves its record (deaths())
    faulthandler.dump_traceback_later(float(env("RCB_STARTUP_TIMEOUT_S", "300")), exit=True)   # (to stderr: a hang
    try:                                                                                       # is no crash record)
        sim = build()
    except InstanceMismatch as exc:                  # the adapter's own loader refused the frozen instance
        faulthandler.cancel_dump_traceback_later()
        reason = f"instance_mismatch: {exc}"[:500]
        give_up(data, reason, infra=True)
        print(f"restart refused: {reason}", flush=True)
        signal.signal(signal.SIGUSR1, lambda *_: None)
        refuse_forever(reason, port)
    faulthandler.cancel_dump_traceback_later()       # a resume replay may take minutes
    svc = Service(sim, data=data, reset_budget=int(env("RCB_RESET_BUDGET") or 0),
                  wall_clock_s=float(env("RCB_WALL_CLOCK_S") or 3600), max_resumes=int(env("RCB_MAX_RESUMES") or 2))
    try:
        svc.start()
    except GiveUp as exc:
        print(f"restart refused: {exc}", flush=True)
        signal.signal(signal.SIGUSR1, lambda *_: None)
        refuse_forever(str(exc), port)
    if pending:
        svc.on_sigusr1()
    svc.serve(port)
