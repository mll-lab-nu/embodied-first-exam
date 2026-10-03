"""Harbor oracle for darts-501-program-standard: the reference player (darts_ref.py: camera images and the documented
physics only) plays the match through the same HTTP calls a program would use (spec, start, act, ready)."""
import base64
import json
import os
import time
import urllib.error
import urllib.request

import darts_ref

BASE = os.environ.get("SIM_URL", "http://sim:8000")


def call(path, body=None):
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return json.load(e)


for _ in range(180):
    try:
        spec = call("/spec")
        break
    except OSError:
        time.sleep(1)
else:
    raise SystemExit("game service unreachable")
P = darts_ref.Player(spec)
os.makedirs("/app/output", exist_ok=True)
with open("/app/output/reference.jsonl", "w", buffering=1) as log:
    r = call("/start", {})
    while True:
        st = r.get("state") or r
        if st.get("done"):
            break
        if st.get("awaiting_review"):
            r = call("/ready", {"why": "reference player: dart recorded", "plan": f"drag estimate k = {P.k:.4f}"})
            continue
        cmd = P.command(st["remaining"]["you"], st["darts_left_in_visit"])
        r = call("/act", {"type": "throw", "yaw": cmd[0], "pitch": cmd[1], "speed": cmd[2]})
        if "error" in r:
            log.write(json.dumps({"error": r["error"]}) + "\n")
            r = call("/status")
            continue
        uv = P.learn(base64.b64decode(r["landed_image_b64"]), r["dart"], cmd) if "landed_image_b64" in r else None
        log.write(json.dumps({"cmd": cmd, "caller": r.get("caller"), "seen_uv": uv, "k": P.k}) + "\n")
print("final:", json.dumps(st))
