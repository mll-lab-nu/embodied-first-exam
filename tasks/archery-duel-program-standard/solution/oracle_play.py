"""Harbor oracle for archery-duel-program-standard, usable on either seat (SEAT=A or B): the reference archer
(archery_ref.py: camera images and the documented physics only) shoots its turns through the seat's HTTP calls."""
import base64
import json
import os
import time
import urllib.error
import urllib.request

import archery_ref

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
P = archery_ref.Archer(spec)
# The two seats' reference archers aim 3 mm apart, so that a match of two references cannot tie forever (shoot-offs
# repeat until the tie is broken, and both seats meet the same wind and scatter).
AIM = (0.0, 0.0) if os.environ["SEAT"] == "A" else (0.003, 0.0)
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
            r = call("ready", {"why": "reference archer: arrow recorded", "plan": "read the windsocks again"})
            continue
        ob = call("observe", {})
        if "observation" not in ob:
            r = ob
            continue
        cmd, wind = P.command(base64.b64decode(ob["observation"]["image_png_b64"]), ob["state"]["distance_m"], AIM)
        r = call("act", {"type": "shoot", "elev_deg": cmd[0], "azim_deg": cmd[1], "draw": cmd[2]})
        log.write(json.dumps({"cmd": cmd, "wind_read": wind, "result": r.get("last_arrow"), "error": r.get("error")}) + "\n")
        if "error" in r:
            r = call("status")
print("final:", json.dumps(st))
