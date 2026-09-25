"""rcb-limited/1.1 sim service: the simulator-agnostic half of a limited-mode sidecar.

Started as a copy of robotwin_2_0_stack_blocks_two-limited/environment/sim/server.py (rcb-limited/1.0, on
dev/kangrui) and split along one line: everything simulator-specific comes in through an adapter object
(the `Sim` contract below), so this file imports no simulator and can move to a shared place unchanged.

What 1.1 adds to 1.0 -- each optional, a 1.0 client never notices (docs/LIMITED_MODE_1_1.md):
  batch step    POST /step {"type", "actions": [[...], ...]}: K actions, in order, in one request
  images        "images": true | false | [camera, ...] on /step and /reset, ?images=... on /observe
  reset budget  POST /reset, allowed `reset_budget` times (default 0: one episode, as on a real robot)

Evidence, where the agent cannot reach it: /data/episode.jsonl (one line per event), /data/final.json (kept
current; "finalized": true once the collect hook's SIGUSR1 has been handled), /data/trajectory.npz and
/data/replay.mp4 (the graded episode, replayed from the frozen instance).
"""
from __future__ import annotations

import json
import os
import signal
import time
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import numpy as np

PROTOCOL = "rcb-limited/1.1"
DATA = os.environ.get("RCB_DATA", "/data")


class Sim:
    """The adapter contract, duck-typed (this class only documents it). One object = one frozen scene."""
    cameras: tuple[str, ...] = ()                                          # the names `images` may ask for

    def spec(self) -> dict: ...                                            # static facts for /spec (action types, layouts, limits, cameras)
    def observe(self, cameras: list[str]) -> dict: ...                     # JSON-ready observation, images for exactly `cameras`
    def validate(self, type: str, action: np.ndarray) -> str | None: ...   # why the action is illegal, or None
    def apply(self, type: str, action: np.ndarray) -> tuple[bool, bool, dict]: ...  # one action -> (done, success, info)
    def reset(self) -> None: ...                                           # back to the frozen instance; the take restarts
    def actions(self) -> np.ndarray: ...                                   # (T, D) applied since the last reset: the deliverable
    def state_sha(self) -> str: ...
    def save_trajectory(self, actions: np.ndarray, path: str, meta: dict) -> None: ...
    def replay(self, actions: np.ndarray) -> dict: ...                     # from the frozen instance -> {"success", "state_sha"}
    def render_video(self, actions: np.ndarray, path: str) -> None: ...


class Service:
    """Episode bookkeeping and the HTTP endpoints around one `Sim`. Everything runs on the main thread -- the
    single-threaded HTTP server's requests and, between them, the SIGUSR1 wrap-up and the finalize -- because a
    simulator's GL context belongs to the thread that made it (MuJoCo renders black frames from any other
    thread). One thread, so no locks."""

    def __init__(self, sim: Sim, *, reset_budget: int = 0):
        os.makedirs(DATA, exist_ok=True)
        self.sim, self.reset_budget = sim, int(reset_budget)
        self.t0 = time.time()
        self.step = 0            # actions in the current episode
        self.steps = 0           # actions over the whole trial (reported as cost)
        self.resets = 0
        self.done = False        # the current episode is over
        self.reason = None       # success | failed (ended without success) | timeout | error
        self.success = False
        self.over = False        # the trial is over: nothing more can be done
        self.stopping = False    # SIGUSR1 seen: stop mid-batch, then wrap up
        self.result: dict = {}   # what finalize() found
        self.spec = {"protocol": PROTOCOL, **sim.spec(), "batch": True,
                     "budget": {"reset": self.reset_budget, "steps": None}}

    # ------------------------------------------------------------------ evidence
    def log(self, ev: str, **kw) -> None:
        with open(os.path.join(DATA, "episode.jsonl"), "a") as f:
            f.write(json.dumps({"ts": time.time(), "ev": ev, **kw}) + "\n")

    def write_final(self) -> None:
        with open(os.path.join(DATA, "final.json"), "w") as f:
            json.dump({"success": self.success, "reason": self.reason, "done": self.done, "over": self.over,
                       "steps": self.steps, "resets": self.resets, "elapsed_s": round(time.time() - self.t0, 1),
                       "finalized": False, **self.result}, f)

    # ------------------------------------------------------------------ endpoints
    def cameras(self, want) -> list[str]:
        """The `images` field: omitted/true -> every camera, false -> none, [names] or "a,b" -> exactly those."""
        if want is None or want is True:
            return list(self.sim.cameras)
        if want is False:
            return []
        if not isinstance(want, (str, list)):
            raise ValueError("images must be true, false, or a list of camera names")
        names = [n for n in (want.split(",") if isinstance(want, str) else want) if n]
        if unknown := sorted(set(map(str, names)) - set(self.sim.cameras)):
            raise ValueError(f"unknown camera(s) {unknown}; the cameras are {list(self.sim.cameras)}")
        return names

    def observation(self, cameras: list[str]) -> dict:
        return {**self.sim.observe(cameras), "step": self.step, "done": self.done, "reason": self.reason,
                "resets_left": self.reset_budget - self.resets, "time_s": round(time.time() - self.t0, 2)}

    def status(self) -> dict:
        return {"step": self.step, "steps": self.steps, "resets": self.resets,
                "resets_left": self.reset_budget - self.resets, "done": self.done, "reason": self.reason,
                "over": self.over, "elapsed_s": round(time.time() - self.t0, 1)}

    def do_observe(self, images) -> tuple[int, dict]:
        cams = self.cameras(images)
        self.log("observe", step=self.step, images=cams)
        return 200, self.observation(cams)

    def do_step(self, body: dict) -> tuple[int, dict]:
        """One action ("action": [D numbers]) or a batch ("actions": [[D numbers], ...]), run in order. A batch
        is validated whole before any of it runs, and stops early when the episode ends. The observation is
        taken after the last action run; `executed` says how many that was."""
        typ, cams = body.get("type"), self.cameras(body.get("images"))
        try:
            acts = np.asarray(body["actions"] if "actions" in body else [body.get("action")], dtype=np.float64)
        except (TypeError, ValueError):
            acts = None
        if acts is None or acts.ndim != 2 or len(acts) == 0:
            return 400, {"error": "send 'action': [numbers] or 'actions': [[numbers], ...] (rows of equal length)"}
        if not np.all(np.isfinite(acts)):
            return 400, {"error": "action contains NaN/inf"}
        for i, a in enumerate(acts):
            if err := self.sim.validate(typ, a):
                return 400, {"error": err if len(acts) == 1 else f"actions[{i}]: {err}"}
        if self.done or self.over:
            return 409, {"error": "episode finished", "reason": self.reason,
                         "resets_left": 0 if self.over else self.reset_budget - self.resets}
        executed, info = 0, {}
        for a in acts:
            if self.stopping:
                break
            try:
                done, success, info = self.sim.apply(typ, a)
            except Exception as exc:  # noqa: BLE001 -- a simulator crash ends the trial, as on hardware
                traceback.print_exc(); self.log("error", error=repr(exc)); self.end_episode("error")
                return 500, {"error": "simulator error", "detail": repr(exc)[:200]}
            executed += 1; self.step += 1; self.steps += 1
            self.log("step", step=self.step, type=typ, action=[round(float(x), 5) for x in a], success=success, **info)
            if success or done:
                self.end_episode("success" if success else "failed")
                break
        if cams:   # the images this answer carries (an observe logs its own)
            self.log("images", step=self.step, images=cams)
        self.write_final()
        return 200, {**self.observation(cams), **info, "ok": True, "executed": executed}

    def do_reset(self, body: dict) -> tuple[int, dict]:
        cams = self.cameras(body.get("images"))
        if self.over:
            return 409, {"error": "trial finished", "reason": self.reason}
        if self.resets >= self.reset_budget:
            return 429, {"error": "reset budget exhausted", "budget": self.reset_budget}
        self.sim.reset(); self.resets += 1
        self.step, self.done, self.reason = 0, False, None
        self.log("reset", resets=self.resets, state_sha=self.sim.state_sha()); self.write_final()
        if cams:
            self.log("images", step=0, images=cams)
        return 200, {**self.observation(cams), "ok": True}

    # ------------------------------------------------------------------ the end
    def end_episode(self, reason: str) -> None:
        """A failed episode ends the trial only when no reset is left."""
        self.done, self.reason = True, reason
        self.success = self.success or reason == "success"
        self.log("end", reason=reason, step=self.step, steps=self.steps, resets=self.resets,
                 elapsed_s=round(time.time() - self.t0, 1))
        if reason != "failed" or self.resets >= self.reset_budget:
            self.finish()

    def finish(self) -> None:
        """Nothing more can be done; the evidence follows as soon as the current request is answered."""
        if not self.over:
            self.over = True; self.write_final()

    def finalize(self) -> None:
        """The deliverable and its evidence, made where the agent cannot reach: the graded episode (every
        action since the last reset) as a trajectory, its fresh replay from the frozen instance (success, and
        bit-exact agreement with the live run), and a replay video for humans."""
        r: dict = {}
        try:
            acts, live_sha = self.sim.actions(), self.sim.state_sha()
            self.sim.save_trajectory(acts, os.path.join(DATA, "trajectory.npz"),
                                     {"source": "limited-mode episode", "reason": self.reason, "resets": self.resets})
            rep = self.sim.replay(acts)
            r = {"n_actions": int(len(acts)), "replay_success": bool(rep["success"]),
                 "deterministic": rep["state_sha"] == live_sha, "state_sha": live_sha}
            self.log("replay", **r)
            try:
                self.sim.render_video(acts, os.path.join(DATA, "replay.mp4")); r["video"] = True
            except Exception:  # noqa: BLE001 -- the video is for humans; it never decides the verdict
                traceback.print_exc()
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc(); self.log("finalize_error", error=repr(exc))
        self.result = {**r, "finalized": True}; self.write_final()

    def on_sigusr1(self, *_) -> None:
        """The [[verifier.collect]] hook: the agent is gone. Only a flag -- the handler can fire in the middle
        of a request, so the wrap-up waits for between_requests()."""
        self.stopping = True

    def between_requests(self) -> None:
        """Called by the HTTP server's loop on the main thread, after every request and every 0.5 s."""
        if self.stopping and not self.over:
            if not self.done:
                self.end_episode("timeout")   # a running episode ends here ...
            self.finish()                     # ... and so does a failed one that still had resets left
        if self.over and not self.result:
            self.finalize()

    # ------------------------------------------------------------------ HTTP
    def serve(self, port: int = 8000) -> None:
        svc = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code: int, obj: dict) -> None:
                b = json.dumps(obj).encode()
                self.send_response(code); self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

            def _route(self, fn, arg) -> None:
                try:
                    self._send(*fn(arg))
                except ValueError as exc:  # a malformed `images` field
                    self._send(400, {"error": str(exc)})

            def do_GET(self):
                url = urlparse(self.path)
                if url.path == "/spec":
                    return self._send(200, svc.spec)
                if url.path == "/status":
                    return self._send(200, svc.status())
                if url.path == "/observe":
                    return self._route(svc.do_observe, _query_images(parse_qs(url.query)))
                self._send(404, {"error": "no such endpoint"})

            def do_POST(self):
                fn = {"/step": svc.do_step, "/reset": svc.do_reset}.get(urlparse(self.path).path)
                if fn is None:
                    return self._send(404, {"error": "no such endpoint"})
                try:
                    body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                except ValueError:
                    return self._send(400, {"error": "invalid JSON"})
                if not isinstance(body, dict):
                    return self._send(400, {"error": "the body must be a JSON object"})
                self._route(fn, body)

        class Server(HTTPServer):
            def service_actions(self):
                svc.between_requests()

        signal.signal(signal.SIGUSR1, self.on_sigusr1)
        self.log("start", protocol=PROTOCOL, state_sha=self.sim.state_sha(), reset_budget=self.reset_budget,
                 spec=self.spec)  # the configuration this trial ran under (budgets, sensors)
        self.write_final()
        with open(os.path.join(DATA, "server.pid"), "w") as f:  # the collect hook signals this PID
            f.write(str(os.getpid()))
        print(f"{PROTOCOL} sim service ready on :{port}", flush=True)
        Server(("0.0.0.0", port), Handler).serve_forever()


def _query_images(q: dict):
    """?images= on /observe: absent, 1, true, all -> every camera; 0, false, none -> none; a,b -> those."""
    v = q.get("images", [None])[0]
    if v is None or v.lower() in ("1", "true", "all"):
        return None
    if v.lower() in ("0", "false", "none"):
        return False
    return v
