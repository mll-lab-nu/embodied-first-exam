"""The agent's only handle on the robot: reset() (budgeted) and step(action) -> observation.
Under Harbor's egress control the sidecar shares main's network namespace (localhost); otherwise it is the
compose service name."""
import os, requests
def _base():
    for b in [os.environ.get("SIM_URL"), "http://sim:8000", "http://localhost:8000"]:
        if not b: continue
        try:
            requests.post(b + "/noop", json={}, timeout=2); return b
        except requests.exceptions.ConnectionError:
            continue
    raise RuntimeError("sim service unreachable")
BASE = _base()
def reset(): r = requests.post(BASE + "/reset", json={}); r.raise_for_status(); return r.json()["obs"]
def step(action): r = requests.post(BASE + "/step", json={"action": action}); r.raise_for_status(); d = r.json(); return d["obs"], d["done"]
