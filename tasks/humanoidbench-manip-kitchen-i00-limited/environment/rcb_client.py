"""rcb-limited/1.1 client: the robot's whole API, and this docstring is its full reference
(installed at /opt/tools/rcb_client.py, which is on PYTHONPATH).

    from rcb_client import Robot, EpisodeOver, ResetDenied
    r = Robot()      # finds the service (SIM_URL, sim:8000, localhost:8000) and waits while it warms up

Calls. spec() was fetched when connecting; every other call is one HTTP request.
    r.spec()                          static facts: action types; "qpos": dim, layout (actuator order), limits,
                                      units; control_hz; max_episode_steps; "proprio" / "imu" (None if absent);
                                      "cameras" {name: {"hw", ...}}; "budget" {"reset": resets allowed, "wall_clock_s"}
    r.observe(images=True)            the current observation; simulated time does not move
    r.step(type, a, images=True)      a is one action, shape (D,), or a batch, shape (K, D): K control steps
                                      in order, in one request, with the same physics as K single steps. obs
                                      comes after the last step run; obs["executed"] says how many ran (fewer
                                      than K if the episode ended). type is one of spec()["action_types"].
    r.reset(images=True)              back to the same starting state, a new episode; spec()["budget"]["reset"]
                                      times in all. Only the last episode is graded.
    r.status()                        step, steps, resets_left, done, reason, over, elapsed_s; no observation

images= on observe/step/reset: True (every camera in spec()["cameras"]) | False (none) | a list of camera
names, e.g. ["left_eye_camera"]. Images cost time; ask for them when you look.

obs, a dict:
    obs["images"][camera]             uint8 array, H x W x 3, for the cameras asked for
    obs["proprio"]                    {"joint_pos", "joint_vel"} in spec()["proprio"]["joints"] order, if the
                                      robot has it
    obs["imu"]                        {"gyro", "gravity"}, if spec()["imu"] is not None
    obs["step"]                       control steps in the current episode
    obs["done"], obs["reason"]        episode over? why: "success" | "failed" (ended without success) |
                                      "timeout" | "error"
    obs["resets_left"], obs["time_s"] resets still allowed; seconds since the service started

Errors:
    ValueError     refused, nothing moved: wrong length, outside the limits, NaN, unknown type or camera
                   (in a batch, one bad row refuses the whole batch)
    EpisodeOver    step() after the episode ended (the message says if a reset is left), or reset() after the
                   trial ended
    ResetDenied    reset() with no resets left
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
        for k, v in list(obs.get("depth", {}).items()):
            d = obs["depth"][k]; obs["depth"][k] = np.frombuffer(base64.b64decode(v), dtype="<f2").reshape(d["h"], d["w"]) if isinstance(d, dict) else v
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
