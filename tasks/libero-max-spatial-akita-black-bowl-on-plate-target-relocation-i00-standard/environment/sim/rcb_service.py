"""eai-standard/2.1 sim service: the simulator-agnostic half of a standard-mode sidecar (docs/PROTOCOL.md §4,
docs/LIMITED_MODE_PROTOCOL.md).

The robot as a service: the agent reaches a simulator it cannot open over HTTP. GET /spec, GET /status, POST /observe
and POST /submit; POST /reset exists only when the run grants resets (budget.reset > 0); everything else is 404.
Responses that carry data are RCB1 frames (rcb1.py), never base64. Everything simulator-specific comes in through an
adapter (the `Sim` contract below), so this file imports no simulator: a sidecar is its benchmark's adapter plus this.

One thread does all of it -- the HTTP requests, the SIGUSR1 wrap-up, the finalize -- because a simulator's GL context
belongs to the thread that made it (MuJoCo renders black frames from any other).

The episode starts when the service is ready. It ends on success, by the task's own rule ("failed": the robot fell,
the episode's control steps ran out), on a simulator error ("error"), or at SIGUSR1 ("timeout": the collect hook, once
the agent's container is gone). With a reset budget, POST /reset abandons the running episode and starts another from
the frozen instance; only the last episode is graded, and a success ends the trial.

A request is checked in full before anything runs: whatever is wrong with it is a 400 and nothing ran. Once it runs,
any failure is the simulator's: a 500, and the episode ends ("error").

Evidence under DATA, never visible to the agent:
  episode.jsonl        one line per event; every state the service may resume from is a checkpoint (it carries
                       state_sha and journal_rows)
  trajectory_live.f64  the journal: every executed control step in the simulator's own action space, float64
  calls/NNNNNN/        each call's response meta and the actions as sent
  startups.jsonl       one line per process start
  final.json           kept current (written atomically); "finalized": true once the verdict is in
  trajectory.npz, replay.mp4, replay.last.png   the graded episode and its fresh replay

Crash recovery: compose restarts a crashed service (restart: on-failure). It replays the journal up to the last
checkpoint, checks the state hash, and continues the SAME episode -- never a reset. A call in flight is lost as a
whole (its caller got an error, not a result, so nothing was learned). More than RCB_MAX_RESUMES restarts since the
episode began (every process start counts, also one that died building the scene or replaying the journal) end the
trial: sim_crashed_on_call if every crash happened while serving a call (the agent's failure), else sim_crashed
(infrastructure, infra_error = 1). A verdict already on disk is never overwritten; a crash while rendering the video
loses only the video.
"""
from __future__ import annotations

import contextlib
import errno
import faulthandler
import json
import os
import signal
import tempfile
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
    def hold(self) -> tuple[str, np.ndarray]: ...      # the row that holds the last command (/observe with seconds > 0)
    def step(self, row: np.ndarray) -> tuple[bool, bool, dict]: ...   # one control step -> (done, success, info)
    def reset(self) -> None: ...                       # back to the frozen instance
    def state_sha(self) -> str: ...
    def verify(self, rows: np.ndarray) -> dict: ...    # replay in a fresh simulator -> {"success", "state_sha"}
    def save_trajectory(self, rows: np.ndarray, path: str, meta: dict) -> None: ...
    def render_video(self, rows: np.ndarray, path: str) -> None: ...   # path and path.last.png


class GiveUp(Exception):
    """The service will not run this trial's episode again; final.json says why."""


class Refused(Exception):
    """A request the service turns down with `code` and the JSON `body`; nothing was executed."""

    def __init__(self, code: int, body: dict):
        super().__init__(body.get("error"))
        self.code, self.body = code, body


@contextlib.contextmanager
def bad_request():
    """Checking a request, before anything runs: whatever goes wrong here is the request's fault (400)."""
    try:
        yield
    except Refused:
        raise
    except Exception as exc:  # noqa: BLE001 -- a wrong type, value or shape of any field
        raise Refused(400, {"error": str(exc)[:300] or type(exc).__name__}) from None


def count_start(data: str) -> int:
    """Record one process start in startups.jsonl; returns how many there have been."""
    path = os.path.join(data, "startups.jsonl")
    with open(path, "a") as f:
        f.write(json.dumps({"ts": time.time(), "pid": os.getpid()}) + "\n")
    with open(path) as f:
        return sum(1 for _ in f)


def write_json_atomic(path: str, obj: dict) -> None:
    """Write then rename: the collect hook polling the file never reads half of it."""
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(obj, f)
    os.replace(tmp, path)


def encode_mp4(frames: np.ndarray, fps: float) -> bytes:
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
                if c in dep:
                    self.dep[c].append(dep[c])
        if proprio:
            self.prop.append(np.asarray(self.sim.proprio(), np.float32))
            self.grabbed_at = self.k

    def parts(self) -> list:
        out = []
        for c in self.cams:
            fr = np.stack(self.frames[c])
            if self.video in ("mp4", "both"):
                out.append((f"video/{c}", "mp4", encode_mp4(fr, self.fps), {"fps": round(self.fps, 3), "n": int(len(fr))}))
            if self.video in ("frames", "both"):
                out.append(rcb1.array_part(f"frames/{c}", fr))
            out.append(rcb1.array_part(f"last/{c}", fr[-1]))
            if self.dep[c]:
                out.append(rcb1.array_part(f"depth/{c}", np.stack(self.dep[c]).astype(np.float16)))
        out.append(rcb1.array_part("proprio", np.stack(self.prop)))
        return out


class Service:
    """Episode bookkeeping, evidence and the HTTP endpoints around one `Sim`."""

    def __init__(self, sim, *, data: str = "/data", reset_budget: int = 0, wall_clock_s: float = 3600.0,
                 max_chunk_s: float = 10.0, max_watch_s: float = 30.0, max_frames_per_call: int = MAX_FRAMES_PER_CALL,
                 max_resumes: int = 2):
        self.sim, self.data = sim, data
        self.reset_budget, self.wall_clock_s = int(reset_budget), float(wall_clock_s)
        self.max_chunk_s, self.max_watch_s = float(max_chunk_s), float(max_watch_s)
        self.max_frames, self.max_resumes = int(max_frames_per_call), int(max_resumes)
        os.makedirs(os.path.join(data, "calls"), exist_ok=True)
        self.journal_path = os.path.join(data, "trajectory_live.f64")
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
        self._unwritten: list[np.ndarray] = []   # sim rows executed since the last checkpoint

    # ------------------------------------------------------------------ spec and status
    def _spec(self) -> dict:
        own = self.sim.spec()
        core = {"protocol": PROTOCOL, "control_dt": self.sim.control_dt, "max_control_steps": self.sim.max_control_steps,
                "max_chunk_s": self.max_chunk_s, "max_watch_s": self.max_watch_s, "max_video_fps": MAX_VIDEO_FPS,
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
        if self.reset_budget:
            spec["reset"] = ("POST /reset abandons the running episode and starts a new one from the same starting "
                             "state, budget.reset times in all; only the last episode is graded, and a success ends "
                             "the trial")
        return spec

    def clock(self) -> float:
        return 0.0 if self.t0 is None else time.time() - self.t0

    def _counters(self) -> dict:
        out = {"calls": self.calls, "rows": self.rows, "control_steps": len(self.episode), "done": self.done,
               "reason": self.reason}
        if self.reset_budget:
            out.update(episode=self.resets + 1, control_steps_total=self.journal_rows,
                       resets_left=0 if self.success or self.stopping else self.reset_budget - self.resets)
        return out

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
                 state_sha=self.sim.state_sha())
        self._write_final()

    def _write_final(self) -> None:
        end = self.t_end or time.time()
        d = {"protocol": PROTOCOL, "success": False, "live_success": self.success, "done": self.done,
             "reason": self.reason, "calls": self.calls, "rows": self.rows, "control_steps": len(self.episode),
             "control_steps_total": self.journal_rows, "episodes": self.resets + 1, "resets": self.resets,
             "reset_budget": self.reset_budget, "elapsed_s": round(end - self.t0, 1) if self.t0 else 0.0,
             "sim_startups": self.starts, "finalized": self.finalized, **self.verdict}
        if "deterministic" in self.verdict:
            d["success"] = bool(self.success and self.verdict["replay_success"] and self.verdict["deterministic"])
        write_json_atomic(os.path.join(self.data, "final.json"), d)

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
        if fin.get("finalized") or "deterministic" in fin:
            # Graded already. A verdict that is not finalized: the process died rendering the video, all it lost.
            if not fin.get("finalized"):
                write_json_atomic(path, {**fin, "finalized": True, "video": False})
            self._give_up("restarted after finalize", infra=False)
        restarts = self.starts - int(next(e for e in ev if e["ev"] == "start")["startup"])
        last = max(i for i, e in enumerate(ev) if e["ev"] in ("start", "resuming"))
        in_call = False                              # did the process that died do so while serving a call?
        for e in ev[last:]:
            in_call = {"call_begin": True, "call_end": False}.get(e["ev"], in_call)
        in_calls = sum(bool(e["crashed_in_call"]) for e in ev if e["ev"] == "resuming") + int(in_call)
        if restarts > self.max_resumes:
            agent = in_calls == restarts             # every crash happened inside a call: the agent's commands did it
            self._give_up("sim_crashed_on_call" if agent else "sim_crashed", infra=not agent)
        self.log("resuming", crashed_in_call=in_call, restart=restarts)
        cp = [e for e in ev if "state_sha" in e and "journal_rows" in e][-1]
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
        self.t0 = next((e["t0"] for e in ev if e["ev"] == "first_request"), None)
        if self.done:
            self.t_end = next((e["ts"] for e in reversed(ev) if e["ev"] == "end"), cp["ts"])
        self._checkpoint("resumed", downtime_s=round(time.time() - float(ev[-1]["ts"]), 1))

    def _give_up(self, reason: str, infra: bool) -> None:
        """End the trial without running its episode again: mark it failed (a finalized final.json is kept as it is),
        leave the PID file for the collect hook, and stop."""
        self.log("restart_refused", reason=reason)
        path = os.path.join(self.data, "final.json")
        try:
            with open(path) as f:
                fin = json.load(f)
        except (OSError, ValueError):
            fin = {}
        if not fin.get("finalized"):
            fin.update({"protocol": PROTOCOL, "success": False, "done": True, "reason": reason, "finalized": True,
                        **({"infra_error": 1} if infra else {})})
            write_json_atomic(path, fin)
        with open(os.path.join(self.data, "server.pid"), "w") as f:
            f.write(str(os.getpid()))
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
        body = rcb1.encode(meta, parts)
        if len(body) > MAX_RESPONSE:
            parts = [p for p in parts if not p[0].startswith(("frames/", "depth/"))]
            meta = {**meta, "degraded": f"response over {MAX_RESPONSE} bytes: frames/ and depth/ dropped"}
            body = rcb1.encode(meta, parts)
        return 200, "application/x-rcb1", body

    def _view(self, meta: dict, default_video: str) -> tuple[list[str], int, str, bool]:
        cams = meta.get("cameras") or list(self.sim.cameras)
        if isinstance(cams, str):
            cams = [c for c in cams.split(",") if c]
        if not isinstance(cams, list) or (unknown := sorted(set(map(str, cams)) - set(self.sim.cameras))):
            raise ValueError(f"unknown camera(s) {unknown if isinstance(cams, list) else cams}; "
                             f"the cameras are {list(self.sim.cameras)}")
        try:
            fps = int(meta.get("video_fps", 10))
        except (TypeError, ValueError, OverflowError):
            raise ValueError("video_fps must be an integer") from None
        if not 1 <= fps <= MAX_VIDEO_FPS:
            raise ValueError(f"video_fps must be in [1, {MAX_VIDEO_FPS}]")
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
            body["resets_left"] = 0 if self.success else self.reset_budget - self.resets
        return Refused(409, body)

    def _step(self, typ: str, row: np.ndarray) -> dict:
        """One control step: execute, journal, and end the episode if it is over."""
        sim_row = np.asarray(self.sim.to_sim(typ, row), dtype=np.float64)
        done, success, info = self.sim.step(sim_row)
        self._unwritten.append(sim_row)
        self.journal_rows += 1
        self.episode.append(sim_row)
        if success:
            self._end("success")
        elif done or len(self.episode) >= self.sim.max_control_steps:
            self._end("failed")
        return info

    def _end(self, reason: str) -> None:
        if self.done:
            return
        self.done, self.reason, self.success = True, reason, reason == "success"
        self.t_end = time.time()
        try:
            self._checkpoint("end")
        except Exception as exc:  # noqa: BLE001 -- a broken simulator may not even hash: the end is still logged
            self.log("end", reason=reason, checkpoint_error=repr(exc)[:300])
            self._write_final()

    def _submit(self, meta: dict, parts: dict) -> tuple[dict, list]:
        if self.done or self.stopping:
            raise self._conflict()
        with bad_request():
            typ = meta.get("type")
            if not isinstance(typ, str) or typ not in self.types:
                raise ValueError(f"type must be one of {sorted(self.types)}")
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
            try:
                dt = cdt if meta.get("dt") is None else float(meta["dt"])
            except (TypeError, ValueError):
                raise ValueError("dt must be a number of seconds") from None
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
        for i, row in enumerate(rows):
            for j in range(1, k + 1):
                info = self._step(typ, row if interp == "hold" else prev + (row - prev) * (j / k))
                rec.step()
                if self.done or self.stopping or info.get("blocked"):
                    stop = True
                    break
            executed, prev = i + 1, row
            if stop:
                break
        rec.finish()
        self.calls += 1
        self.rows += executed
        out = {**self.meta(), "chunk_id": self.calls, "type": typ, "executed_rows": executed,
               "control_steps_chunk": len(self.episode) - before, "clipped": clipped[:200], "n_clipped": len(clipped),
               **info, "ok": True}
        self._checkpoint("submit", type=typ, n_rows=len(A), dt=dt, interpolate=interp, cameras=cams,
                         note=str(meta.get("note") or "")[:500], executed_rows=executed, n_clipped=len(clipped), **info)
        self._save_call(out, A)
        return out, rec.parts()

    def _observe(self, meta: dict, parts: dict) -> tuple[dict, list]:
        with bad_request():
            try:
                seconds = float(meta.get("seconds") or 0.0)
            except (TypeError, ValueError):
                raise ValueError("seconds must be a number") from None
            if not 0.0 <= seconds <= self.max_watch_s:
                raise ValueError(f"seconds must be in [0, {self.max_watch_s:g}]")
            cams, fps, video, depth = self._view(meta, "frames")
            n = int(round(seconds / self.sim.control_dt)) if not (self.done or self.stopping) else 0
            rec = Recorder(self.sim, cams, fps, depth, video if n or video != "mp4" else "frames")   # no time: no video
            self._frame_budget(rec, n)
        before = len(self.episode)
        rec.start()
        if n:
            typ, row = self.sim.hold()
            for _ in range(n):
                self._step(typ, row)
                rec.step()
                if self.done or self.stopping:
                    break
        rec.finish()
        self.calls += 1
        ran = len(self.episode) - before
        out = {**self.meta(), "obs_id": self.calls, "seconds": round(ran * self.sim.control_dt, 4),
               "control_steps_watch": ran, "ok": True}
        self._checkpoint("observe", seconds=out["seconds"], cameras=cams)
        self._save_call(out, None)
        return out, rec.parts()

    def _reset(self, meta: dict, parts: dict) -> tuple[dict, list]:
        if self.success or self.stopping:
            raise Refused(409, {"error": "trial finished: " + ("an episode succeeded" if self.success else "your time is up"),
                                "reason": self.reason})
        if self.resets >= self.reset_budget:
            raise Refused(409, {"error": "reset budget exhausted", "budget": self.reset_budget})
        with bad_request():
            cams, fps, video, depth = self._view(meta, "frames")
        if not self.done:
            self._end("reset")                       # the running episode is abandoned
        self.sim.reset()
        self.resets += 1
        self.ep_start, self.episode = self.journal_rows, []
        self.done, self.reason, self.success, self.t_end = False, None, False, None
        rec = Recorder(self.sim, cams, fps, depth, "frames" if video == "mp4" else video)   # no time: no video
        rec.start()
        rec.finish()
        self.calls += 1
        out = {**self.meta(), "ok": True}
        self._checkpoint("reset", cameras=cams)
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

    def _finalize(self) -> None:
        """The graded episode (every control step since the last reset) as a trajectory, its replay in a fresh
        simulator (success, and bit-exact agreement with the live run), and a video for humans."""
        try:
            rows = np.asarray(self.episode, dtype=np.float64).reshape(-1, self.sim.raw_dim)
            live_sha = self.sim.state_sha()
            self.sim.save_trajectory(rows, os.path.join(self.data, "trajectory.npz"),
                                     {"source": "standard-mode episode", "protocol": PROTOCOL, "reason": self.reason,
                                      "episode": self.resets + 1})
            rep = self.sim.verify(rows)
            self.verdict = {"n_actions": int(len(rows)), "replay_success": bool(rep["success"]),
                            "deterministic": rep["state_sha"] == live_sha, "state_sha": live_sha, "video": False}
            # Benchmark evidence from the adapter's verify() (`extra`, e.g. LIBERO-MAX's event record): recorded in
            # final.json, never part of the success rule, never overriding a verdict field.
            self.verdict.update({k: v for k, v in (rep.get("extra") or {}).items() if k not in self.verdict})
            self.log("replay", **self.verdict)
            self._write_final()                      # the verdict is on disk before any video is rendered
            try:
                self.sim.render_video(rows, os.path.join(self.data, "replay.mp4"))
                self.verdict["video"] = True
            except Exception:  # noqa: BLE001 -- the video is for humans; it never decides the verdict
                traceback.print_exc()
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self.log("finalize_error", error=repr(exc)[:500])
            self.verdict = {"finalize_error": repr(exc)[:300]}
        self.finalized = True
        self._write_final()

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
    faulthandler.dump_traceback_later(float(env("RCB_STARTUP_TIMEOUT_S", "300")), exit=True)
    sim = build()
    faulthandler.cancel_dump_traceback_later()       # a resume replay may take minutes
    svc = Service(sim, data=data, reset_budget=int(env("RCB_RESET_BUDGET") or 0),
                  wall_clock_s=float(env("RCB_WALL_CLOCK_S") or 3600), max_resumes=int(env("RCB_MAX_RESUMES") or 2))
    try:
        svc.start()
    except GiveUp as exc:
        print(f"restart refused: {exc}", flush=True)
        signal.signal(signal.SIGUSR1, lambda *_: None)
        while True:
            time.sleep(3600)
    if pending:
        svc.on_sigusr1()
    svc.serve(port)
