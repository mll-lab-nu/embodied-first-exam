"""Harbor oracle for archery-program-standard: the reference archer (archery_ref.py: camera images and the documented
physics only) shoots the round through the same HTTP calls a program would use (spec, start, observe, act, ready)."""
import base64
import json
import os
import time
import urllib.error
import urllib.request

import archery_ref

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
P = archery_ref.Archer(spec)
os.makedirs("/app/output", exist_ok=True)
with open("/app/output/reference.jsonl", "w", buffering=1) as log:
    r = call("/start", {})
    while True:
        st = r.get("state") or r
        if st.get("done"):
            break
        if st.get("awaiting_review"):
            r = call("/ready", {"why": "reference archer: arrow recorded", "plan": "read the windsocks again"})
            continue
        ob = r.get("observation") or call("/observe", {})["observation"]
        cmd, wind = P.command(base64.b64decode(ob["image_png_b64"]), st["distance_m"])
        r = call("/act", {"type": "shoot", "elev_deg": cmd[0], "azim_deg": cmd[1], "draw": cmd[2]})
        log.write(json.dumps({"cmd": cmd, "wind_read": wind, "result": r.get("last_arrow"), "error": r.get("error")}) + "\n")
        if "error" in r:
            r = call("/status")
print("final:", json.dumps(st))
