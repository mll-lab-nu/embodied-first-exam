"""Harbor oracle for basketball-shootout-program-standard: the reference shooter (bb_ref.py: camera images and the
documented physics only) takes the shots through the same HTTP calls a program would use."""
import base64
import json
import os
import time
import urllib.error
import urllib.request

import bb_ref

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
P = bb_ref.Shooter(spec)
os.makedirs("/app/output", exist_ok=True)
with open("/app/output/reference.jsonl", "w", buffering=1) as log:
    r = call("/start", {})
    while True:
        st = r.get("state") or r
        if st.get("done"):
            break
        if st.get("awaiting_review"):
            r = call("/ready", {"why": "reference shooter: shot recorded", "plan": "find the rim again"})
            continue
        ob = r.get("observation") or call("/observe", {})["observation"]
        spot = st["spot"]
        dec, seen = P.command(base64.b64decode(ob["image_png_b64"]), spot)
        r = call("/act", {"type": "shoot", **dec})
        if "error" in r:
            log.write(json.dumps({"error": r["error"]}) + "\n")
            r = call("/status")
            continue
        P.learn(spot, r)
        log.write(json.dumps({"dec": dec, "hoop_seen": seen, "result": r.get("result"), "touched": r.get("touched")}) + "\n")
print("final:", json.dumps(st))
