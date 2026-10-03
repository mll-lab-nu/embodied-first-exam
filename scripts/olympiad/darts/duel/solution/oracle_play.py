"""Harbor oracle for darts-duel-program-standard, usable on either seat (SEAT=A or B): the reference player
(darts_ref.py: camera images and the documented physics only) plays its turns through the seat's HTTP calls."""
import base64
import json
import os
import time
import urllib.error
import urllib.request

import darts_ref

BASE = os.environ.get("SIM_URL", "http://sim:8000") + "/" + os.environ["SEAT"]


def call(ep, body=None):
    req = urllib.request.Request(BASE + "/" + ep, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return json.load(e)


for _ in range(180):
    try:
        spec = call("spec")
        break
    except OSError:
        time.sleep(1)
else:
    raise SystemExit("game service unreachable")
P = darts_ref.Player(spec)
os.makedirs("/app/output", exist_ok=True)
with open("/app/output/reference.jsonl", "w", buffering=1) as log:
    r = call("start", {})
    while True:
        st = r.get("state") or {}
        if st.get("done"):
            break
        if not st.get("your_turn"):
            r = call("wait", {"timeout_s": 60})
            continue
        if st.get("awaiting_review"):
            r = call("ready", {"why": "reference player: dart recorded", "plan": f"drag estimate k = {P.k:.4f}"})
            continue
        cmd = P.command(st["remaining"]["you"], st["darts_left_in_visit"])
        r = call("act", {"type": "throw", "yaw": cmd[0], "pitch": cmd[1], "speed": cmd[2]})
        if "error" in r:
            log.write(json.dumps({"error": r["error"]}) + "\n")
            r = call("status")
            continue
        uv = P.learn(base64.b64decode(r["landed_image_b64"]), r["dart"], cmd) if "landed_image_b64" in r else None
        log.write(json.dumps({"cmd": cmd, "caller": r.get("caller"), "seen_uv": uv, "k": P.k}) + "\n")
print("final:", json.dumps(st))
