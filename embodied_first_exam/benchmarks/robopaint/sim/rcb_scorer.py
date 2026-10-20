"""
rcb_scorer.py — the RoboPaint scoring service of the UNLIMITED mode. It runs in the `scorer` sidecar of the task's compose file,
never in the agent's container, with the graders' copy of the frozen instance (/srv/instance.json: it holds what the score needs)
and the tooling module (RCB_TOOL_MODULE: rcb_paint for line drawings, rcb_brush for the brush families).

The agent's Session.score() posts the actions it has executed since its last reset; the service replays them on its own Session
(same frozen instance, same deterministic simulation, so the canvas is the agent's canvas bit for bit) and answers with the task's
metrics only: the tooling's agent_metrics() of the grader's score. A request that extends the previous one (same client id, same
prefix) steps only the new actions, so scoring after every stroke costs no more than painting it.

  POST /score    body: float32 (T, 7) joint-target actions, header X-RCB-Client: <id>
                 -> {"metrics": {...}, "steps": T, "stepped": n, "reset": bool}
  GET  /health   -> {"ok": true, "protocol": "rcb-score/1", "instance_sha": "..."}

Nothing else is served: no images, masks, target data, per-pixel maps or files; errors carry no data. The service scores only
canvases that the simulation produces from actions (it never accepts a canvas), so every query costs the robot time it replays.
"""
from __future__ import annotations
import importlib
import json
import os
import sys
import time
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
M = importlib.import_module(os.environ.get("RCB_TOOL_MODULE", "rcb_paint"))
INSTANCE = os.environ.get("RCB_INSTANCE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "instance.json"))
PORT = int(os.environ.get("RCB_SCORER_PORT", "8001"))
MAX_ACTIONS = int(os.environ.get("RCB_SCORER_MAX_ACTIONS", str(M.MAX_STEPS)))
DIM = M.ACTION_DIM
PROTOCOL = "rcb-score/1"


def log(*a) -> None:
    print("[scorer]", *a, file=sys.stderr, flush=True)


t0 = time.time()
S = M.Session(instance=INSTANCE, render=False, max_steps=MAX_ACTIONS)
if getattr(S, "truth", None) is None:
    raise SystemExit("the scorer's instance has no scoring data")
STATE = {"log": np.zeros((0, DIM), np.float32), "client": None, "n": 0}
log(f"ready in {time.time() - t0:.1f}s; instance_sha={S.instance_sha}; port {PORT}")


def score_actions(A: np.ndarray, client: str) -> dict:
    L = STATE["log"]
    k = len(L)
    if client == STATE["client"] and len(A) >= k and np.array_equal(A[:k], L):
        new, reset = A[k:], False
    else:
        S.reset(); new, reset = A, True
    STATE["log"], STATE["client"] = np.zeros((0, DIM), np.float32), None       # invalid until the steps went through
    for a in new:
        S.step(a)
    STATE["log"], STATE["client"] = A.copy(), client
    STATE["n"] += 1
    return {"metrics": M.agent_metrics(S.score()), "steps": int(len(A)), "stepped": int(len(new)), "reset": bool(reset)}


class Handler(BaseHTTPRequestHandler):
    server_version = "rcb-scorer"
    sys_version = ""

    def _send(self, code: int, obj: dict) -> None:
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            return self._send(200, {"ok": True, "protocol": PROTOCOL, "instance_sha": S.instance_sha})
        self._send(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/score":
            return self._send(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._send(400, {"error": "bad Content-Length"})
        if n < 0 or n % (4 * DIM) or n > 4 * DIM * MAX_ACTIONS:
            return self._send(400, {"error": f"the body must be float32 (T, {DIM}) actions, T <= {MAX_ACTIONS}"})
        A = np.frombuffer(self.rfile.read(n), dtype="<f4").reshape(-1, DIM).copy() if n else np.zeros((0, DIM), np.float32)
        if not np.all(np.isfinite(A)):
            return self._send(400, {"error": "actions contain nan/inf"})
        client = (self.headers.get("X-RCB-Client") or "")[:64]
        try:
            return self._send(200, score_actions(A, client))
        except Exception as exc:  # noqa: BLE001 — the message only (a runaway guard, a bad action); state is rebuilt next time
            traceback.print_exc(file=sys.stderr)
            STATE["log"], STATE["client"] = np.zeros((0, DIM), np.float32), None
            return self._send(400, {"error": f"{type(exc).__name__}: {str(exc)[:200]}"})

    def log_message(self, fmt, *args) -> None:  # quiet
        pass


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
