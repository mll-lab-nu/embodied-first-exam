"""Reference player for the single-player 8-ball game: plays through the service's HTTP interface (the same calls the
`game` command makes) from the top camera image, the documented geometry and the rules only (eight_player.py)."""
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eight_player as P  # noqa: E402

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
P.set_table(spec["table"])
os.makedirs("/app/output", exist_ok=True)
log = open("/app/output/reference.jsonl", "a", buffering=1)
r = call("/start", {})
obs = r.get("observation")
while True:
    st = r.get("state", {})
    if r.get("done") or st.get("done"):
        break
    if st.get("turn") == "review":
        r = call("/ready", {"why": "reference player: shot recorded", "plan": "reference player: easiest legal pot next"})
        obs = r.get("next")
        continue
    if st.get("turn") != "you":
        time.sleep(1); r = call("/status"); continue
    if not obs or "images_png_b64" not in obs:
        r = call("/observe", {}); obs = r.get("observation"); continue
    table = P.perceive(base64.b64decode(obs["images_png_b64"]["top"]), obs["cameras"][0], obs.get("balls_on_table"))
    dec = P.decide(table, st)
    plan = dec.pop("plan")
    r = call("/act", dec)
    for fix in ("cue", "call"):              # a placement or a call the rules refuse (a misread ball): simplify
        if r.get("http_status") != 400:
            break
        log.write(json.dumps({"refused": r.get("error"), "shot": dec}) + "\n")
        if fix == "cue":
            dec.pop("cue_x", None); dec.pop("cue_y", None)
        elif "call" in dec:
            dec["call"] = "safety"
        r = call("/act", dec)
    log.write(json.dumps({"plan": plan, "shot": dec, "result": r.get("your_shot"), "state": r.get("state")}) + "\n")
    obs = None
print("final:", json.dumps(r)[:2000])
