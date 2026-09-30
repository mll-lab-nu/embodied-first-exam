"""rcb-limited/2.0 client — the only thing a limited-mode agent gets (installed at /opt/tools/rcb_client.py).

    from rcb_client import Robot
    r = Robot()                                   # finds the service (sim:8000, then localhost:8000), waits for warm-up
    spec = r.spec()                               # action types + dims + limits, cameras, budgets
    obs = r.get_obs()                             # current frames: obs.last["head_camera"] -> uint8 HxWx3, obs.meta["proprio"]
    res = r.submit("joint_position", actions, dt=0.05)    # actions: (T, 14); returns the execution video
    res = r.submit("ee_pose", actions)                    # (T, 16); planner per row (see spec)
    res.video["head_camera"]  -> mp4 bytes     res.frames["head_camera"] -> uint8 (N,H,W,3) if video="frames"/"both"
    res.last["left_camera"]   -> uint8 HxWx3   res.proprio -> float32 (N, 30)   res.meta -> dict (done, plan, clipped, ...)
    res.save("/app/runs/003")                  # meta.json, <cam>.mp4, frames/<cam>/NNN.jpg, last/<cam>.jpg, proprio.npy
    obs = r.get_obs(seconds=3, video="both")   # hold the last command, let physics run 3 s, return the video

Nothing is put into your context automatically: what you look at, and where you store it, is your code's decision.
"""
from __future__ import annotations
import io, json, os, pathlib, time
import numpy as np
import requests
import rcb1

PROTOCOL = "rcb-limited/2.0"


class EpisodeOver(RuntimeError):
    pass


class Result:
    """Decoded RCB1 response: meta (dict), video (cam -> mp4 bytes), frames (cam -> uint8 array), last (cam -> uint8 image),
    depth (cam -> float16 array), proprio (float32 array). save(dir) writes it all out; show(cam, k) returns one frame."""
    def __init__(self, meta: dict, parts: dict):
        self.meta = meta; self.video = {}; self.frames = {}; self.last = {}; self.depth = {}; self.proprio = None; self.raw = parts
        for name, p in parts.items():
            kind, data = p["kind"], p["data"]
            if name.startswith("video/") and kind == "mp4": self.video[name[6:]] = data
            elif name.startswith("frames/") and kind == "array": self.frames[name[7:]] = data
            elif name.startswith("last/") and kind == "array": self.last[name[5:]] = data
            elif name.startswith("depth/") and kind == "array": self.depth[name[6:]] = data
            elif name == "proprio": self.proprio = data

    @property
    def done(self) -> bool: return bool(self.meta.get("done"))

    def show(self, camera: str = "head_camera", k: int = -1) -> np.ndarray:
        if camera in self.frames: return self.frames[camera][k]
        return self.last[camera]

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
        for cam, arr in self.depth.items(): np.save(out / f"depth_{cam}.npy", arr)
        if self.proprio is not None: np.save(out / "proprio.npy", self.proprio)
        return str(out)


class Robot:
    def __init__(self, base: str | None = None, timeout: float = 600.0):
        cands = [base or os.environ.get("SIM_URL"), "http://sim:8000", "http://localhost:8000"]
        t0 = time.time(); last = None
        while time.time() - t0 < timeout:
            for b in [c for c in cands if c]:
                try:
                    r = requests.get(b + "/spec", timeout=(5, 30))
                    if r.status_code == 503: last = "warming up"; break
                    r.raise_for_status(); self.base = b; self._spec = r.json()
                    assert self._spec.get("protocol") == PROTOCOL, self._spec.get("protocol")
                    return
                except requests.exceptions.RequestException as e:
                    last = e
            time.sleep(2)
        raise RuntimeError(f"sim service unavailable: {last}")

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
        m, p = rcb1.decode(r.content); return Result(m, p)

    def submit(self, action_type: str, actions, dt: float = 0.02, interpolate: str = "linear",
               cameras=("head_camera", "front_camera", "left_camera", "right_camera"), video_fps: int = 10,
               video: str = "mp4", include_depth: bool = False, note: str = "") -> Result:
        """Execute a chunk of low-level actions (T, dim). See spec()['action_types'] for dims and semantics
        (joint_position rows may carry 14 extra velocity feed-forward columns)."""
        a = np.asarray(actions, dtype=np.float32)
        if a.ndim == 1: a = a[None, :]
        meta = {"type": action_type, "dt": float(dt), "interpolate": interpolate, "cameras": list(cameras), "video_fps": int(video_fps),
                "video": video, "include_depth": bool(include_depth), "note": note}
        return self._post("/submit", meta, [rcb1.array_part("actions", a)], timeout=1800)

    def get_obs(self, cameras=("head_camera", "front_camera", "left_camera", "right_camera"), seconds: float = 0.0,
                video_fps: int = 10, include_depth: bool = False, video: str = "frames") -> Result:
        """Current frames (seconds=0, free) or hold the last command and watch for `seconds` (returns the video)."""
        meta = {"cameras": list(cameras), "seconds": float(seconds), "video_fps": int(video_fps), "include_depth": bool(include_depth), "video": video}
        return self._post("/observe", meta, [], timeout=600)

    def status(self) -> dict:
        r = requests.get(self.base + "/status", timeout=(5, 60)); r.raise_for_status(); return r.json()
