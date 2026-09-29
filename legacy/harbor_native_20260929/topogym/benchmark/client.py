"""Lightweight Robot client; only NumPy is required until images are saved.

This file and wire.py can be published as topogym_client.py/topogym_wire.py
inside a Harbor main container without installing the simulator.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import zlib

import numpy as np

try:
    from . import wire
except ImportError:  # standalone client publication
    import topogym_wire as wire


class EpisodeOver(RuntimeError):
    pass


class Result:
    def __init__(self, meta, parts, spec):
        self.meta, self.raw, self._spec = meta, parts, spec
        for name in ("video", "frames", "last", "last_depth", "depth", "extrinsic_cv"):
            setattr(self, name, {})
        self.proprio = self.frame_step = self.frame_time_s = None
        for name, part in parts.items():
            group, _, camera = name.partition("/")
            if group == "depth_frames":
                shape = part.get("shape", [])
                if (part.get("codec") != "zlib" or part.get("dtype") != "uint16"
                        or part.get("unit") != "mm" or len(shape) != 3
                        or any(type(n) is not int or n < 0 for n in shape)):
                    raise ValueError("Invalid depth descriptor")
                size = math.prod(shape) * 2
                if size > wire.MAX_RESPONSE:
                    raise ValueError("Depth allocation exceeds limit")
                decoder = zlib.decompressobj()
                raw = decoder.decompress(part["data"], size + 1)
                if len(raw) != size or not decoder.eof or decoder.unused_data:
                    raise ValueError("Invalid compressed depth")
                self.depth[camera] = np.frombuffer(raw, "<u2").reshape(shape).astype(np.float32) / 1000
            elif camera and group in {"video", "frames", "last", "last_depth", "depth", "extrinsic_cv"}:
                getattr(self, group)[camera] = part["data"]
            elif name in {"proprio", "frame_step", "frame_time_s"}:
                setattr(self, name, part["data"])

    @property
    def done(self):
        return bool(self.meta.get("done"))

    def group(self, name, now=False):
        start, size = self._spec["proprio_groups"][name][:2]
        values = np.asarray(self.meta["proprio"]["now"]) if now else self.proprio
        return values[..., start:start + size]

    def show(self, camera, k=-1):
        return self.frames[camera][k] if camera in self.frames else self.last[camera]

    def save(self, directory):
        root = Path(directory)
        root.mkdir(parents=True, exist_ok=True)
        (root / "meta.json").write_text(json.dumps(self.meta, indent=2, allow_nan=False) + "\n")
        for group in ("video", "frames", "last", "last_depth", "depth", "extrinsic_cv"):
            for camera, value in getattr(self, group).items():
                if not camera or not all(c.isalnum() or c in "_-" for c in camera):
                    raise ValueError("Unsafe camera name")
                folder = root / group
                folder.mkdir(exist_ok=True)
                if group == "video":
                    (folder / f"{camera}.mp4").write_bytes(value)
                else:
                    np.save(folder / f"{camera}.npy", value, allow_pickle=False)
                    if group == "last":
                        try:
                            from PIL import Image
                        except ImportError:
                            pass
                        else:
                            Image.fromarray(value).save(folder / f"{camera}.png")
        for name in ("proprio", "frame_step", "frame_time_s"):
            if getattr(self, name) is not None:
                np.save(root / f"{name}.npy", getattr(self, name), allow_pickle=False)
        return str(root)


class Robot:
    def __init__(self, base=None, timeout=600):
        candidates = list(dict.fromkeys(x.rstrip("/") for x in
            (base or os.environ.get("SIM_URL"), "http://sim:8000", "http://localhost:8000") if x))
        deadline, error = time.monotonic() + timeout, None
        while time.monotonic() < deadline:
            for self.base in candidates:
                try:
                    spec = self._get("/spec", timeout=min(5, max(.1, deadline - time.monotonic())))
                    if not str(spec.get("protocol", "")).startswith("rcb-limited/2."):
                        raise ValueError("Incompatible simulator protocol")
                    self._spec = spec
                    return
                except (URLError, OSError, TimeoutError) as exc:
                    error = exc
            time.sleep(min(1, max(0, deadline - time.monotonic())))
        raise TimeoutError(f"Simulator did not become ready: {error}")

    def _request(self, path, body=None, content_type=None, timeout=1800):
        req = Request(self.base + path, data=body,
                      headers={} if content_type is None else {"Content-Type": content_type})
        try:
            with urlopen(req, timeout=timeout) as response:
                data = response.read(wire.MAX_RESPONSE + 1)
        except HTTPError as exc:
            message = exc.read(8192).decode("utf-8", errors="replace")
            if exc.code == 409:
                raise EpisodeOver(message) from exc
            raise ValueError(f"Simulator HTTP {exc.code}: {message}") from exc
        if len(data) > wire.MAX_RESPONSE:
            raise ValueError("Simulator response too large")
        return data

    def _get(self, path, timeout=60):
        return wire.json_loads(self._request(path, timeout=timeout))

    def spec(self):
        return self._spec

    def status(self):
        return self._get("/status")

    def _observation(self, path, meta, parts=()):
        # Never retry submit: a lost response may follow executed physical actions.
        raw = self._request(path, wire.encode(meta, parts, limit=wire.MAX_REQUEST), "application/x-rcb1")
        meta, parts = wire.decode(raw)
        return Result(meta, parts, self._spec)

    def _options(self, cameras, video_fps, video, depth, include_depth):
        result = dict(cameras=self._spec.get("default_cameras") if cameras is None else list(cameras), video=video)
        if video_fps is not None:
            result["video_fps"] = video_fps
        if depth is not None:
            result["depth"] = "last" if depth is True else "none" if depth is False else depth
        elif include_depth:
            result["include_depth"] = True
        return result

    def get_obs(self, cameras=None, seconds=0, video_fps=None, depth=None, include_depth=False, video="frames"):
        return self._observation("/observe", dict(seconds=seconds,
            **self._options(cameras, video_fps, video, depth, include_depth)))

    def submit(self, action_type, actions, dt=None, interpolate="linear", cameras=None,
               video_fps=None, video="mp4", depth=None, include_depth=False, note=""):
        rows = np.asarray(actions, dtype=np.float32)
        if rows.ndim == 1:
            rows = rows[None, :]
        meta = dict(type=action_type, dt=1 / self._spec["control_hz"] if dt is None else dt,
                    interpolate=interpolate, note=note,
                    **self._options(cameras, video_fps, video, depth, include_depth))
        return self._observation("/submit", meta, [wire.array("actions", rows)])

    def kinematics(self, body):
        return wire.json_loads(self._request("/kinematics",
            json.dumps(body, allow_nan=False).encode(), "application/json", timeout=120))

    def fk(self, q, links=None, base_pose=None):
        body = dict(op="fk", q=np.asarray(q).tolist())
        if links is not None:
            body["links"] = list(links)
        if base_pose is not None:
            body["base_pose"] = list(base_pose)
        return self.kinematics(body)

    def ik(self, targets, seed=None, base_pose=None, **options):
        body = dict(op="ik", targets={k: list(v) for k, v in targets.items()}, **options)
        if seed is not None:
            body["seed"] = list(seed)
        if base_pose is not None:
            body["base_pose"] = list(base_pose)
        return self.kinematics(body)
