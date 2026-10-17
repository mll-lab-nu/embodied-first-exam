"""eai-standard/2.3 client (standard-realtime mode): your whole interface to the robot (installed at /opt/tools/rcb_client.py, on
PYTHONPATH).

    from rcb_client import Robot, EpisodeOver
    r = Robot()            # finds the service (SIM_URL, http://sim:8000, http://localhost:8000), waits until it is ready

TIME DOES NOT STOP (spec()["timing"]). An episode starts paused; its clock starts at its first submit() or
get_obs(seconds > 0) (again after every reset()) and from then on runs one control step every spec()["control_dt"] x
spec()["timing"]["slowdown"] seconds of wall time, whether or not you call, until the episode ends. The service keeps a
plan, one servo-target row per coming control step: submit() writes into it and answers at once; when the plan runs out
the last target is held. Whatever you do in between -- think, print, run a model -- the robot keeps executing.

Calls (each is one HTTP request; every answer that carries data is an RCB1 frame, decoded into a Result):
    r.spec()                                 GET /spec, fetched when connecting: the robot's facts. "action_types"
                                             ("joint_position": dim, layout (actuator order), lower/upper, range_rad,
                                             units, semantics), "control_dt" (0.02 s), "max_control_steps" (the
                                             episode), "timing" (realtime, slowdown, max_ahead_steps), "cameras" {name:
                                             rgb, depth, hw, fovy_deg, pose, mounted}, "proprio_layout" and "proprio"
                                             (joints, axes, positions), "imu", "links" (masses, centres of mass, the
                                             feet's boxes), "depth", "budget" {"reset", "wall_clock_s"}, "episode"
    r.status()                               GET /status: calls, rows, control_steps, done, reason, elapsed_s, running,
                                             planned_steps, lag_s (and episode, resets_left with a reset budget)
    r.get_obs(cameras=None, seconds=0.0, video_fps=10, include_depth=False, video="frames")
                                             POST /observe. seconds=0: the robot now, at once. seconds>0 (at most
                                             spec()["max_watch_s"]): waits while that much robot time runs (starting the
                                             clock if it is not running) and returns what the cameras saw; it never
                                             changes the plan
    r.submit("joint_position", actions, dt=None, interpolate="linear", at=None, cameras=None, video_fps=10,
             video="none", include_depth=False, note="")
                                             POST /submit: answers at once with the robot as it is now (the rows
                                             have not run yet). actions (T, dim): rows dt apart (a multiple of
                                             control_dt, the default; T x dt at most spec()["max_chunk_s"]); each step's
                                             target is the row (interpolate="hold") or a straight line from the previous
                                             row's ("linear", starting from the target in force just before `at`). They
                                             become the plan from control step `at` (an episode step number; None = the
                                             next step), replacing whatever was planned from `at` on and keeping what is
                                             planned before it; at most spec()["timing"]["max_ahead_steps"] ahead. Rows
                                             for steps already gone when the request arrives are dropped
                                             (meta["late_steps"]). The first submit of an episode starts its clock
    r.reset(cameras=None, include_depth=False)
                                             POST /reset, only when spec()["budget"]["reset"] > 0: abandons the
                                             running episode and starts a new one, paused, from the same starting state;
                                             only the last episode is graded, and a success ends the trial

cameras=None means every camera in spec()["cameras"]; cameras=[] means no images at all, only proprioception (the
fastest call: what a controller loop wants). video: "mp4" (one H.264 file per camera), "frames" (the images as arrays),
"both" or "none" (only the last frame); a submit returns no video (no time passes inside it). include_depth adds depth
for the cameras that have it.

Result (what get_obs / submit / reset return):
    res.meta                 dict: calls, rows, control_steps (steps run in this episode: the next one is this number),
                             sim_time_s, time_s, time_left_s, proprio {"layout", "now"}, done, reason ("success" |
                             "failed" | "timeout" | "error"; None while the episode runs), running, planned_steps,
                             lag_s; per submit: start_step, late_steps, plan_end_step, clipped [{row, index, reason}]
                             (values outside [-1, 1] are clipped, not refused); with a reset budget also episode,
                             resets_left
    res.last[cam]            uint8 H x W x 3: the last frame (unless cameras=[])
    res.frames[cam]          uint8 N x H x W x 3 (get_obs, video="frames"/"both")     res.video[cam]   mp4 bytes
    res.depth[cam]           float16 N x H x W, metres, 0 = nothing in range (include_depth)
    res.proprio              float32 rows of spec()["proprio_layout"]: one at the call's start, one every 1/video_fps s
                             of a watch, one at its end
    res.done                 the episode is over
    res.save(dir)            meta.json, <cam>.mp4, last/<cam>.jpg, frames/<cam>/NNN.jpg, depth_<cam>.npy, proprio.npy

Errors: ValueError -- refused, nothing changed (400: wrong type or shape, NaN, a bad dt or at, too many frames, an
unknown camera; or a request over 64 MB, refused before it is sent); EpisodeOver -- the episode, or the trial, is over
(409); RuntimeError -- the service failed (5xx: see spec()["on_service_error"]) or the endpoint does not exist in this
run (404).
"""
from __future__ import annotations

import json
import os
import pathlib
import time

import numpy as np
import requests

import rcb1

PROTOCOLS = ("eai-standard/2.", "rcb-limited/2.")   # any 2.x service, under either name (rcb-limited is the old one)
MAX_BODY = 64 * 1024 * 1024                          # the protocol's request limit: a larger request is refused


class EpisodeOver(RuntimeError):
    pass


class Result:
    """A decoded RCB1 answer: meta, video, frames, last, depth, proprio; save(dir) writes them all out."""

    def __init__(self, meta: dict, parts: dict):
        self.meta, self.raw = meta, parts
        self.video, self.frames, self.last, self.depth, self.proprio = {}, {}, {}, {}, None
        for name, p in parts.items():
            kind, data = p["kind"], p["data"]
            if name.startswith("video/") and kind == "mp4":
                self.video[name[6:]] = data
            elif name.startswith("frames/"):
                self.frames[name[7:]] = data
            elif name.startswith("last/"):
                self.last[name[5:]] = data
            elif name.startswith("depth/"):
                self.depth[name[6:]] = data
            elif name == "proprio":
                self.proprio = data

    @property
    def done(self) -> bool:
        return bool(self.meta.get("done"))

    def save(self, out_dir: str) -> str:
        from PIL import Image
        out = pathlib.Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "meta.json").write_text(json.dumps(self.meta, indent=1))
        for cam, b in self.video.items():
            (out / f"{cam}.mp4").write_bytes(b)
        for cam, img in self.last.items():
            (out / "last").mkdir(exist_ok=True)
            Image.fromarray(np.ascontiguousarray(img)).save(out / "last" / f"{cam}.jpg", quality=90)
        for cam, arr in self.frames.items():
            d = out / "frames" / cam
            d.mkdir(parents=True, exist_ok=True)
            for i, f in enumerate(arr):
                Image.fromarray(np.ascontiguousarray(f)).save(d / f"{i:03d}.jpg", quality=85)
        for cam, arr in self.depth.items():
            np.save(out / f"depth_{cam}.npy", arr)
        if self.proprio is not None:
            np.save(out / "proprio.npy", self.proprio)
        return str(out)


class Robot:
    def __init__(self, base: str | None = None, timeout: float = 600.0):
        candidates = [c for c in (base or os.environ.get("SIM_URL"), "http://sim:8000", "http://localhost:8000") if c]
        t0, last = time.time(), None
        while time.time() - t0 < timeout:
            for b in candidates:
                try:
                    r = requests.get(b + "/spec", timeout=(5, 60))
                    if r.status_code == 503:
                        last = "warming up"
                        continue
                    r.raise_for_status()
                    self.base, self._spec = b, r.json()
                    if not str(self._spec.get("protocol", "")).startswith(PROTOCOLS):
                        raise RuntimeError(f"not an eai-standard/2.x service: {self._spec.get('protocol')}")
                    return
                except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                    last = e                         # not up yet (the scene takes about a minute), or busy
            time.sleep(2)
        raise RuntimeError(f"sim service unavailable: {last}")

    def spec(self) -> dict:
        return self._spec

    def status(self) -> dict:
        r = requests.get(self.base + "/status", timeout=(5, 60))
        r.raise_for_status()
        return r.json()

    def get_obs(self, cameras=None, seconds: float = 0.0, video_fps: int = 10, include_depth: bool = False,
                video: str = "frames") -> Result:
        meta = {"cameras": _names(cameras), "seconds": float(seconds), "video_fps": int(video_fps),
                "include_depth": bool(include_depth), "video": video}
        return self._post("/observe", meta, [], timeout=900)

    def submit(self, action_type: str, actions, dt: float | None = None, interpolate: str = "linear",
               at: int | None = None, cameras=None, video_fps: int = 10, video: str = "none",
               include_depth: bool = False, note: str = "") -> Result:
        a = np.asarray(actions, dtype=np.float64)
        if a.ndim == 1:
            a = a[None, :]
        if not np.all(np.isfinite(a)):
            raise ValueError("actions contain NaN or inf")
        meta = {"type": action_type, "dt": None if dt is None else float(dt), "interpolate": interpolate,
                "at": None if at is None else int(at), "cameras": _names(cameras), "video_fps": int(video_fps),
                "video": video,
                "include_depth": bool(include_depth), "note": note}
        return self._post("/submit", meta, [rcb1.array_part("actions", a)], timeout=1800)

    def reset(self, cameras=None, include_depth: bool = False) -> Result:
        return self._post("/reset", {"cameras": _names(cameras), "include_depth": bool(include_depth)}, [], timeout=900)

    def _post(self, path: str, meta: dict, parts: list, timeout: float) -> Result:
        body = rcb1.encode(meta, parts)
        if len(body) > MAX_BODY:                     # the service would close the connection on it unread
            raise ValueError(f"{path}: {len(body)} bytes, over the protocol's {MAX_BODY}: send fewer rows")
        r = requests.post(self.base + path, data=body, headers={"Content-Type": "application/x-rcb1"},
                          timeout=(5, timeout))
        if r.headers.get("Content-Type", "").startswith("application/x-rcb1") and r.status_code == 200:
            return Result(*rcb1.decode(r.content))
        try:
            err = r.json()
        except ValueError:
            err = {"error": r.text[:300]}
        msg = f"{r.status_code} {path}: {err.get('error')}" + (f" ({err['detail']})" if err.get("detail") else "")
        if r.status_code == 409:
            raise EpisodeOver(msg + (f"; reason {err['reason']}" if err.get("reason") else "")
                              + (f"; resets_left {err['resets_left']}" if "resets_left" in err else ""))
        if r.status_code in (400, 413):
            raise ValueError(msg)
        raise RuntimeError(msg)


def _names(cameras) -> list[str] | None:
    return None if cameras is None else [cameras] if isinstance(cameras, str) else list(cameras)
