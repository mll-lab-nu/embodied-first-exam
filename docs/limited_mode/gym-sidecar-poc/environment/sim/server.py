"""Toy 'robot as a service': the only thing the agent can reach. Holds hidden state, enforces a reset budget,
returns observations only (no privileged state), and logs every call to /data/episode.jsonl."""
import json, time, os
from http.server import BaseHTTPRequestHandler, HTTPServer
LOG = "/data/episode.jsonl"; os.makedirs("/data", exist_ok=True)
S = {"target": 7, "pos": 0, "t": 0, "resets": 0, "reset_budget": 2, "done": False, "success": False}
def log(ev):
    with open(LOG, "a") as f: f.write(json.dumps({"ts": time.time(), **ev}) + "\n")
class H(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        b = json.dumps(obj).encode(); self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0)); body = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/reset":
            if S["resets"] >= S["reset_budget"]:
                log({"ev": "reset_denied"}); return self._send(429, {"error": "reset budget exhausted"})
            S.update(pos=0, t=0, done=False, success=False); S["resets"] += 1; log({"ev": "reset", "n": S["resets"]})
            return self._send(200, {"obs": {"rgb_hint": "you see a marker to the right", "t": 0}})
        if self.path == "/step":
            if S["done"]: return self._send(400, {"error": "episode done; reset"})
            a = int(body.get("action", 0)); S["pos"] += a; S["t"] += 1
            S["success"] = S["pos"] == S["target"]; S["done"] = S["success"] or S["t"] >= 20
            log({"ev": "step", "action": a, "t": S["t"], "success": S["success"]})
            return self._send(200, {"obs": {"rgb_hint": "marker is " + ("here" if S["success"] else ("right" if S["pos"] < S["target"] else "left")), "t": S["t"]}, "done": S["done"]})
        return self._send(404, {"error": "no such endpoint"})
    def log_message(self, *a): pass
log({"ev": "boot"}); HTTPServer(("0.0.0.0", 8000), H).serve_forever()
