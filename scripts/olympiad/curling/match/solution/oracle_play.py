"""Reference player for the single-player curling match: plays through the service's HTTP interface (the same calls
the `game` command makes) from the house camera image and the documented ice model only (curling_player.py)."""
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import curling_player as P  # noqa: E402

BASE = os.environ.get("SIM_URL", "http://sim:8000")


def call(path, body=None):
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        out = json.load(e)
        out["http_status"] = e.code
        return out


for _ in range(180):
    try:
        spec = call("/spec")
        break
    except OSError:
        time.sleep(2)
else:
    raise SystemExit("game service unreachable")
cam = next(c for c in spec["cameras"] if c["name"] == "house")
mine = spec["match"].get("your_colour", "yellow")
os.makedirs("/app/output", exist_ok=True)
log = open("/app/output/reference.jsonl", "a", buffering=1)
P.path("ccw"); P.path("cw")                   # integrate the ice law once
r = call("/start", {})
obs = r.get("observation")
while True:
    st = r.get("state", {})
    if r.get("done") or st.get("done"):
        break
    if st.get("turn") == "review":
        r = call("/ready", {"why": "reference player: throw recorded", "plan": "reference player: same policy"})
        obs = r.get("next")
        continue
    if st.get("turn") != "you":
        time.sleep(1); r = call("/status"); continue
    if not obs or "images_png_b64" not in obs:
        r = call("/observe", {}); obs = r.get("observation"); continue
    stones = P.perceive(base64.b64decode(obs["images_png_b64"]["house"]), cam)
    n_in_end = obs.get("throw_in_end") or st.get("throw_in_end") or 99
    v, a, spin, desc = P.plan(stones, mine, fgz=n_in_end <= 5)
    r = call("/act", {"type": "throw", "speed": round(v, 6), "angle": round(a, 6), "spin": spin})
    log.write(json.dumps({"plan": desc, "throw": [v, a, spin], "seen": stones, "result": r.get("your_throw"),
                          "state": r.get("state")}) + "\n")
    obs = None
print("final:", json.dumps(r)[:2000])
