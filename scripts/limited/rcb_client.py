"""rcb-limited/1.1 client: the one implementation every limited-mode task ships as environment/rcb_client.py.

Each simulator's copy, scripts/<sim>/shared/limited/rcb_client.py, is this code under its own docstring: the agent's
whole API reference (docs/LIMITED_MODE_1_1.md). ci_checks/check-tooling-sync.sh holds every task's client code to this
file's, so a protocol change is made here and then in each copy below its docstring.
"""
from __future__ import annotations
import base64, io, os, time
import numpy as np
import requests

PROTOCOL = "rcb-limited/1."   # any 1.x service; 1.1 only adds optional fields


class EpisodeOver(RuntimeError):
    pass


class ResetDenied(RuntimeError):
    pass


class Robot:
    def __init__(self, base: str | None = None, timeout: float = 600.0):
        cands = [base or os.environ.get("SIM_URL"), "http://sim:8000", "http://localhost:8000"]
        t0 = time.time(); last = None
        while time.time() - t0 < timeout:
            for b in [c for c in cands if c]:
                try:
                    r = requests.get(b + "/spec", timeout=5)
                    if r.status_code == 503:
                        last = "warming up"; break
                    r.raise_for_status(); self.base = b; self._spec = r.json()
                    assert str(self._spec.get("protocol")).startswith(PROTOCOL), self._spec.get("protocol")
                    return
                except requests.exceptions.ConnectionError as e:
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
        for k, v in list(obs.get("depth", {}).items()):   # a 16-bit PNG in millimetres
            obs["depth"][k] = np.asarray(Image.open(io.BytesIO(base64.b64decode(v)))).astype(np.float32) / 1000.0
        return obs

    @staticmethod
    def _check(r: requests.Response) -> dict:
        if r.status_code == 409:
            d = r.json(); left = d.get("resets_left") or 0
            raise EpisodeOver(f"{d.get('reason')}" + (f" ({left} reset(s) left: call reset())" if left else ""))
        if r.status_code == 429:
            raise ResetDenied(r.json().get("error"))
        if r.status_code == 400:
            raise ValueError(r.json().get("error"))
        r.raise_for_status(); return Robot._decode(r.json())

    def observe(self, images=True) -> dict:
        q = "" if images is True else "?images=" + ("0" if images is False else ",".join(images))
        return self._check(requests.get(self.base + "/observe" + q))

    def step(self, type: str, action, images=True) -> dict:
        a = np.asarray(action, dtype=np.float64)
        if not np.all(np.isfinite(a)):
            raise ValueError("action contains NaN/inf")   # JSON cannot carry them; the service would refuse them too
        body = {"type": type, "images": images if isinstance(images, bool) else list(images)}
        body["actions" if a.ndim == 2 else "action"] = a.tolist()
        return self._check(requests.post(self.base + "/step", json=body))

    def reset(self, images=True) -> dict:
        return self._check(requests.post(self.base + "/reset", json={"images": images if isinstance(images, bool) else list(images)}))

    def status(self) -> dict:
        r = requests.get(self.base + "/status"); r.raise_for_status(); return r.json()
