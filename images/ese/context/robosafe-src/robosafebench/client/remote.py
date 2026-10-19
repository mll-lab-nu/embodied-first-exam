"""Client for the robot service. `connect()` returns the robot; `robot.call(tool, **args)` makes one call, and every
tool is also a method: `robot.observe()`, `robot.pick(camera="front", u=320, v=240)`."""
# This file and `__main__.py` are all an agent's container holds, installed there as the package `robot_client`.
# Nothing in either may name this repository, the benchmark or anything else that says what the robot is used for.
from __future__ import annotations

import base64
import json
import os
import urllib.request


class Robot:
    def call(self, tool: str, **args) -> dict:
        raise NotImplementedError

    def save_images(self, out: dict, directory: str = "frames", prefix: str | None = None) -> dict:
        """Write the images of a call's result as PNG files; returns {camera: path}."""
        from pathlib import Path
        d = Path(directory)
        d.mkdir(parents=True, exist_ok=True)
        self._n = getattr(self, "_n", 0) + 1
        paths = {}
        images = dict(out.get("images") or {})
        images.update({f"{cam}_depth": img for cam, img in (out.get("depth") or {}).items()})     # depth: 16-bit, millimetres
        for cam, img in images.items():
            path = d / f"{prefix or f'{self._n:03d}'}_{cam}.png"
            if isinstance(img, (bytes, bytearray)):
                path.write_bytes(img)
            else:
                self._write_array(path, img)
            paths[cam] = str(path)
        return paths

    def _write_array(self, path, img) -> None:
        raise TypeError("an image must be PNG bytes")

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        return lambda **args: self.call(name, **args)


class _Remote(Robot):
    def __init__(self, url: str, timeout: float = 600.0):
        self._url, self._timeout = url.rstrip("/"), timeout

    def call(self, tool: str, **args) -> dict:
        req = urllib.request.Request(self._url + "/call", data=json.dumps({"tool": tool, "args": args}).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self._timeout) as r:
            out = json.loads(r.read())
        if isinstance(out.get("images"), dict):
            out["images"] = {k: base64.b64decode(v) for k, v in out["images"].items()}       # PNG bytes
        if isinstance(out.get("depth"), dict):
            out["depth"] = {k: base64.b64decode(v) for k, v in out["depth"].items()}         # 16-bit PNG bytes, millimetres
        return out

    def brief(self) -> str:
        with urllib.request.urlopen(self._url + "/brief", timeout=30) as r:
            return r.read().decode()


def connect(url: str | None = None) -> Robot:
    return _Remote(url or os.environ.get("ROBOT_URL", "http://127.0.0.1:8765"))
