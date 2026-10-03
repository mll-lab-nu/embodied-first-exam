"""Harbor oracle for basketball-duel-program-standard, usable on either seat (SEAT=A or B): the reference shooter
(bb_ref.py: camera images and the documented physics only) takes its shots through the seat's HTTP calls."""
import base64
import json
import os
import time
import urllib.error
import urllib.request

import bb_ref

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
P = bb_ref.Shooter(spec)
# Seat B's reference shoots 1 % faster and 0.3 degrees left of seat A's: two references meet the same spots and the
# same scatter, so identical shooters would tie every extra pair.
YAW_OFFSET, SPEED_SCALE = (0.0, 1.0) if os.environ["SEAT"] == "A" else (0.3, 1.01)
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
            r = call("ready", {"why": "reference shooter: shot recorded", "plan": "find the rim again"})
            continue
        ob = call("observe", {})
        if "observation" not in ob:
            r = ob
            continue
        spot = ob["state"]["spot"]
        dec, seen = P.command(base64.b64decode(ob["observation"]["image_png_b64"]), spot)
        dec["yaw_deg"] = round(dec["yaw_deg"] + YAW_OFFSET, 4)
        dec["speed"] = round(dec["speed"] * SPEED_SCALE, 4)
        r = call("act", {"type": "shoot", **dec})
        if "error" in r:
            log.write(json.dumps({"error": r["error"]}) + "\n")
            r = call("status")
            continue
        P.learn(spot, r)
        log.write(json.dumps({"dec": dec, "hoop_seen": seen, "result": r.get("result")}) + "\n")
print("final:", json.dumps(st))
