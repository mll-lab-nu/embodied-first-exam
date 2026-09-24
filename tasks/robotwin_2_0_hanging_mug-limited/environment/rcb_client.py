"""rcb-limited/1.0 client — the only thing a limited-mode agent gets (copied to /opt/tools/rcb_client.py).

    from rcb_client import Robot
    r = Robot()                      # finds the service (sim:8000, then localhost:8000), waits for warm-up
    spec = r.spec()                  # action layouts, joint limits, cameras
    obs = r.observe()                # images (numpy uint8 HxWx3 per camera), joint, endpose
    obs = r.step("qpos", [...14...]) # or r.step("ee", [...16...]); obs["done"], obs["reason"], obs["plan"]
"""
from __future__ import annotations
import base64, io, os, time
import numpy as np
import requests

PROTOCOL = "rcb-limited/1.0"


class EpisodeOver(RuntimeError):
    pass


class Robot:
    def __init__(self, base: str | None = None, timeout: float = 600.0):
        cands = [base or os.environ.get("SIM_URL"), "http://sim:8000", "http://localhost:8000"]
        t0 = time.time(); last = None
        while time.time() - t0 < timeout:
            for b in [c for c in cands if c]:
                try:
                    r = requests.get(b + "/spec", timeout=(5, 30))
                    if r.status_code == 503:
                        last = "warming up"; break
                    r.raise_for_status(); self.base = b; self._spec = r.json()
                    assert self._spec.get("protocol") == PROTOCOL, self._spec.get("protocol")
                    return
                except requests.exceptions.RequestException as e:  # connection refused (not ready yet), timeouts, resets
                    last = e
            time.sleep(2)
        raise RuntimeError(f"sim service unavailable: {last}")

    def spec(self) -> dict:
        return self._spec

    @staticmethod
    def _decode(obs: dict) -> dict:
        from PIL import Image
        for k, v in list(obs.get("images", {}).items()):
            obs["images"][k] = np.asarray(Image.open(io.BytesIO(base64.b64decode(v))).convert("RGB"))
        for k, v in list(obs.get("depth", {}).items()):
            d = obs["depth"][k]; obs["depth"][k] = np.frombuffer(base64.b64decode(v), dtype="<f2").reshape(d["h"], d["w"]) if isinstance(d, dict) else v
        return obs

    def observe(self) -> dict:
        r = requests.get(self.base + "/observe", timeout=(5, 600)); r.raise_for_status(); return self._decode(r.json())

    def step(self, type: str, action) -> dict:
        r = requests.post(self.base + "/step", json={"type": type, "action": [float(x) for x in np.asarray(action).reshape(-1)]}, timeout=(5, 900))
        if r.status_code == 409:
            raise EpisodeOver(r.json().get("reason"))
        if r.status_code == 400:
            raise ValueError(r.json().get("error"))
        r.raise_for_status(); return self._decode(r.json())

    def status(self) -> dict:
        r = requests.get(self.base + "/status", timeout=(5, 60)); r.raise_for_status(); return r.json()
