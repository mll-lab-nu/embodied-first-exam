"""eai-standard/2.2 client (formerly rcb-limited/2.x) — the only thing a standard-mode agent gets (installed at
/opt/tools/rcb_client.py).

    from rcb_client import Robot
    r = Robot()                                  # finds the service (sim:8000, then localhost:8000), waits for warm-up
    spec = r.spec()                              # actions, cameras (+ intrinsics, mounting), robot_spec, world, budget, kinematics
    obs = r.get_obs()                            # current frames: obs.last[cam] -> uint8 (H,W,3); obs.meta["proprio"]
    obs = r.get_obs(depth=True)                  # + obs.last_depth[cam] -> float32 (H,W) z-depth in metres, 0 = no reading
    res = r.submit("joint_position", A, dt=0.1)  # A: (T, dim) rows dt apart; returns the execution video
    res = r.submit("ee_pose", P)                 # (T, dim) end-effector targets (see spec()["action_types"])
    res.video[cam] -> mp4 bytes    res.frames[cam] -> uint8 (N,H,W,3) if video="frames"/"both"    res.last[cam]
    res.proprio -> float32 (N, D), one row per frame (names: spec()["proprio_layout"]; res.group("tcp_pose"))
    res.frame_step -> int64 (N,) control step of each frame    res.frame_time_s -> float64 (N,) simulated time
    res.extrinsic_cv[cam] -> float64 (N,3,4) world->camera per frame (res.meta["cameras"]: intrinsics + the last frame's pose)
    res = r.submit(..., depth="frames")          # + res.depth[cam] -> float32 (N,H,W) metres, one per frame (1 mm steps)
    r.fk(q)                                      # {"ok", "poses": {frame: [x,y,z, quaternion]}}: forward kinematics, no physics
    r.ik({frame: pose}, seed=q)                  # {"ok", "q", "error": {frame: {"pos_m", "rot_rad"}}}: inverse kinematics
    res.save("/app/runs/003")                    # meta.json, <cam>.mp4, last/<cam>.jpg, frames/<cam>/NNN.jpg, proprio.npy, depth, frame_meta.npz
    obs = r.get_obs(seconds=3, video="both")     # hold the last command, let physics run 3 s, return the video
    r.status()                                   # calls, control steps, done, reason, elapsed time

Nothing is put into your context automatically: what you look at, and where you store it, is your code's decision.

If a call fails with a connection error or a 5xx, the service may have crashed; it restarts and resumes the SAME episode
(never a reset) in the state after the last call it completed, which you may not have received. r.wait_ready() waits
until it answers again (resuming replays the episode so far: long episodes can take minutes); then check r.status()
before you continue (spec()["on_service_error"]).
"""
from __future__ import annotations
import json, os, pathlib, sys, time, zlib
import numpy as np
import requests
import rcb1

PROTOCOL = "eai-standard/2.2"         # also talks to 2.0 / 2.1 services (they ignore depth and send no frame metadata)
ACCEPTED = ("eai-standard/2.", "rcb-limited/2.")   # every 2.x service, under the protocol's current and former name


class EpisodeOver(RuntimeError):
    pass


def _decode_depth_frames(p: dict) -> np.ndarray:
    a = np.frombuffer(zlib.decompress(p["data"]), dtype="<u2").reshape(p["shape"])
    return a.astype(np.float32) / 1000.0


class Result:
    """Decoded RCB1 response: meta (dict), video (cam -> mp4 bytes), frames (cam -> uint8 (N,H,W,3)), last (cam -> uint8
    (H,W,3)), last_depth (cam -> float32 (H,W) m), depth (cam -> float32 (N,H,W) m, one per frame), proprio (float32 (N,D)),
    frame_step (int64 (N,)), frame_time_s (float64 (N,)), extrinsic_cv (cam -> float64 (N,3,4)). save(dir) writes it out;
    show(cam, k) returns one frame; group(name) the proprio columns of one spec()["proprio_groups"] group. stopped: None,
    or why the service stopped the call early ("max_call_wall_s": it ran longer than spec()["max_call_wall_s"]); then
    meta["executed_rows"] < the rows sent, and meta["proprio"]["now"] is where the robot is."""
    def __init__(self, meta: dict, parts: dict, spec: dict | None = None):
        self.meta = meta; self.raw = parts; self._spec = spec or {}; self.stopped = meta.get("stopped")
        self.video, self.frames, self.last, self.last_depth, self.depth, self.extrinsic_cv = {}, {}, {}, {}, {}, {}
        self.proprio = None; self.frame_step = None; self.frame_time_s = None
        for name, p in parts.items():
            kind, data = p["kind"], p["data"]
            if name.startswith("video/") and kind == "mp4": self.video[name[6:]] = data
            elif name.startswith("frames/") and kind == "array": self.frames[name[7:]] = data
            elif name.startswith("last/") and kind == "array": self.last[name[5:]] = data
            elif name.startswith("last_depth/") and kind == "array": self.last_depth[name[11:]] = np.asarray(data, dtype=np.float32)
            elif name.startswith("depth_frames/") and p.get("codec") == "zlib": self.depth[name[13:]] = _decode_depth_frames(p)
            elif name.startswith("depth/") and kind == "array": self.depth[name[6:]] = np.asarray(data, dtype=np.float32)   # 2.1 form
            elif name.startswith("extrinsic_cv/") and kind == "array": self.extrinsic_cv[name[13:]] = data
            elif name == "proprio": self.proprio = data
            elif name == "frame_step": self.frame_step = data
            elif name == "frame_time_s": self.frame_time_s = data

    @property
    def done(self) -> bool: return bool(self.meta.get("done"))

    def show(self, camera: str, k: int = -1) -> np.ndarray:
        if camera in self.frames: return self.frames[camera][k]
        return self.last[camera]

    def group(self, name: str, now: bool = False) -> np.ndarray:
        """Columns of proprio group `name` (spec()["proprio_groups"]): (N, n) over the frames, or (n,) of meta["proprio"]["now"]."""
        first, n = self._spec["proprio_groups"][name][:2]
        if now: return np.asarray(self.meta["proprio"]["now"], dtype=np.float64)[first:first + n]
        return self.proprio[:, first:first + n]

    def save(self, out_dir: str) -> str:
        out = pathlib.Path(out_dir); out.mkdir(parents=True, exist_ok=True)
        (out / "meta.json").write_text(json.dumps(self.meta, indent=1))
        for cam, b in self.video.items(): (out / f"{cam}.mp4").write_bytes(b)
        try:
            from PIL import Image
            for cam, img in self.last.items():
                (out / "last").mkdir(exist_ok=True); Image.fromarray(np.ascontiguousarray(img)).save(out / "last" / f"{cam}.jpg", quality=90)
            for cam, arr in self.frames.items():
                d = out / "frames" / cam; d.mkdir(parents=True, exist_ok=True)
                for i, f in enumerate(arr): Image.fromarray(np.ascontiguousarray(f)).save(d / f"{i:03d}.jpg", quality=85)
        except ImportError:
            for cam, img in self.last.items(): np.save(out / f"last_{cam}.npy", img)
            for cam, arr in self.frames.items(): np.save(out / f"frames_{cam}.npy", arr)
        for cam, arr in self.last_depth.items(): np.save(out / f"last_depth_{cam}.npy", arr)
        for cam, arr in self.depth.items(): np.savez_compressed(out / f"depth_{cam}.npz", depth_mm=np.rint(arr * 1000).astype(np.uint16))
        if self.proprio is not None: np.save(out / "proprio.npy", self.proprio)
        if self.frame_step is not None:
            np.savez(out / "frame_meta.npz", frame_step=self.frame_step, frame_time_s=self.frame_time_s,
                     **{f"extrinsic_cv/{c}": e for c, e in self.extrinsic_cv.items()})
        return str(out)


class Robot:
    def __init__(self, base: str | None = None, timeout: float = 3600.0):
        """Connect to the sim service and wait until it answers GET /spec. `timeout` (seconds) is how long to wait for a
        service that is still starting: the default outlasts every task's start-up watchdog (the longest is 2400 s; an
        Isaac Sim start on a busy host takes 10-30 minutes), so the first Robot() returns when the simulator is up. The
        wait is part of your wall-clock budget; progress is printed to stderr once a minute."""
        cands = [base or os.environ.get("SIM_URL"), "http://sim:8000", "http://localhost:8000"]
        t0 = time.time(); last = None; told = t0
        while time.time() - t0 < timeout:
            for b in [c for c in cands if c]:
                try:
                    r = requests.get(b + "/spec", timeout=(5, 30))
                    if r.status_code == 503: last = "warming up"; break
                    r.raise_for_status(); self.base = b; self._spec = r.json()
                    if not str(self._spec.get("protocol", "")).startswith(ACCEPTED):
                        raise RuntimeError(f"not a 2.x service: protocol {self._spec.get('protocol')!r}")
                    return
                except requests.exceptions.RequestException as e:
                    last = e
            if time.time() - told >= 60:
                told = time.time()
                print(f"[rcb_client] still waiting for the sim service to start ({told - t0:.0f} s of at most {timeout:.0f} s; "
                      f"last answer: {str(last)[:200]})", file=sys.stderr, flush=True)
            time.sleep(2)
        raise RuntimeError(f"sim service unavailable after {time.time() - t0:.0f} s (Robot(timeout={timeout:.0f}); last answer: {last}). "
                           "If the simulator is still starting, call Robot() again: nothing has been executed.")

    def spec(self) -> dict:
        return self._spec

    def _post(self, path: str, meta: dict, parts: list, timeout: float) -> Result:
        body = rcb1.encode(meta, parts)
        r = requests.post(self.base + path, data=body, headers={"Content-Type": "application/x-rcb1"}, timeout=(5, timeout))
        if r.status_code == 409:
            raise EpisodeOver(r.json().get("reason") if r.headers.get("Content-Type", "").startswith("application/json") else "episode finished")
        if r.status_code >= 400:
            try: err = r.json()
            except Exception: err = {"error": r.text[:300]}
            raise ValueError(f"{r.status_code}: {err.get('error')} {err.get('detail', '')}".strip())
        m, p = rcb1.decode(r.content); return Result(m, p, self._spec)

    def _common(self, cameras, video_fps, depth, include_depth) -> dict:
        if isinstance(cameras, str): cameras = [cameras]      # one camera name, not its characters
        cams = list(cameras) if cameras is not None else self._spec.get("default_cameras")
        if depth is None or depth is False: depth = "frames" if include_depth else "none"
        elif depth is True: depth = "last"
        m = {"cameras": cams, "video_fps": None if video_fps is None else int(video_fps), "depth": depth}
        return {k: v for k, v in m.items() if v is not None}

    def submit(self, action_type: str, actions, dt: float | None = None, interpolate: str = "linear", cameras=None,
               video_fps: int | None = None, video: str = "mp4", depth=None, include_depth: bool = False, note: str = "") -> Result:
        """Execute a chunk of low-level actions (T, dim); see spec()['action_types'] for dims, layouts, limits and semantics.
        dt defaults to one control period, cameras to spec()['default_cameras']; depth: None | True (= "last") | "frames"."""
        a = np.asarray(actions, dtype=np.float32)
        if a.ndim == 1: a = a[None, :]
        if dt is None and self._spec.get("control_hz"): dt = 1.0 / float(self._spec["control_hz"])
        meta = {"type": action_type, "interpolate": interpolate, "video": video, "note": note,
                **({} if dt is None else {"dt": float(dt)}), **self._common(cameras, video_fps, depth, include_depth)}
        res = self._post("/submit", meta, [rcb1.array_part("actions", a)], timeout=1800)
        if res.stopped:
            print(f"[rcb_client] the service stopped this call early ({res.stopped}): {res.meta.get('executed_rows')} of {len(a)} rows "
                  "executed; meta['proprio']['now'] is where the robot is", file=sys.stderr)
        return res

    def get_obs(self, cameras=None, seconds: float = 0.0, video_fps: int | None = None, depth=None, include_depth: bool = False,
                video: str = "frames") -> Result:
        """Current frames (seconds=0, free) or hold the last command and watch for `seconds` (returns the video).
        depth: None | True (= "last": the last frame's depth) | "frames" (one depth map per frame)."""
        meta = {"seconds": float(seconds), "video": video, **self._common(cameras, video_fps, depth, include_depth)}
        res = self._post("/observe", meta, [], timeout=600)
        if res.stopped:
            print(f"[rcb_client] the service stopped this watch early ({res.stopped}) after {res.meta.get('control_steps_watch')} control "
                  "steps", file=sys.stderr)
        return res

    def status(self) -> dict:
        r = requests.get(self.base + "/status", timeout=(5, 60)); r.raise_for_status(); return r.json()

    def wait_ready(self, timeout: float = 3600.0) -> dict:
        """After a connection error: wait until the service answers GET /status again (it resumes the same episode after a
        crash), then return the status. Raises RuntimeError after `timeout` seconds."""
        t0 = time.time(); last = None
        while time.time() - t0 < timeout:
            try:
                return self.status()
            except requests.exceptions.RequestException as e:
                last = e
            time.sleep(5)
        raise RuntimeError(f"sim service did not come back within {timeout:.0f} s: {last}")

    def kinematics(self, body: dict) -> dict:
        """POST /kinematics (stateless: never moves the robot, never advances time). Raises ValueError on a bad request."""
        r = requests.post(self.base + "/kinematics", json=body, timeout=(5, 120))
        if r.status_code >= 400:
            try: err = r.json()
            except Exception: err = {"error": r.text[:300]}
            raise ValueError(f"{r.status_code}: {err.get('error')} {err.get('detail', '')}".strip())
        return r.json()

    def fk(self, q, links=None, base_pose=None) -> dict:
        """Forward kinematics: q in spec()['kinematics']['joint_names'] order -> {"ok", "frame", "poses": {link: [x,y,z, quat]}}
        (quaternion order spec()['world']['quaternion_order']; a mobile robot answers in its base frame unless base_pose is given)."""
        body = {"op": "fk", "q": [float(v) for v in np.asarray(q).reshape(-1)]}
        if links is not None: body["links"] = list(links)
        if base_pose is not None: body["base_pose"] = [float(v) for v in base_pose]
        return self.kinematics(body)

    def ik(self, targets: dict, seed=None, base_pose=None, **opts) -> dict:
        """Inverse kinematics: {frame: [x,y,z, quat]} (frames from spec()['kinematics']['ik_targets']) and an optional seed q ->
        {"ok", "q", "error": {frame: {"pos_m", "rot_rad"}}}. opts: tol_pos_m, tol_rot_rad, max_iters."""
        body = {"op": "ik", "targets": {k: [float(v) for v in p] for k, p in targets.items()}, **opts}
        if seed is not None: body["seed"] = [float(v) for v in np.asarray(seed).reshape(-1)]
        if base_pose is not None: body["base_pose"] = [float(v) for v in base_pose]
        return self.kinematics(body)
