"""Harbor oracle for golf putting (single player or either duel seat): plays through the same HTTP calls a player
program uses (spec, start, status, wait, observe, act, ready). Its strokes were computed offline for each official seed by the
privileged reference player (oracle_decisions.json); for another seed it putts straight along the green. A play-off
hole repeats that hole's strokes. Seat B aims 0.2 degrees further counter-clockwise than seat A (two identical
references would tie). It never
reads simulator state."""
import json
import os
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.environ.get("SIM_URL", "http://sim:8000").rstrip("/") + ("/" + os.environ["SEAT"] if os.environ.get("SEAT") else "")
FALLBACK = {"aim_deg": 0.0, "speed": 2.5}
# The two seats' references differ slightly so that two references do not tie every round and play-off: seat B aims
# 0.2 degrees further counter-clockwise (README; on the official seeds A takes 5 / 6 / 5 strokes, B 6 / 22 / 10).
AIM_OFFSET = float(os.environ.get("ORACLE_AIM_OFFSET", "0.2" if os.environ.get("SEAT") == "B" else "0"))
SPEED_SCALE = float(os.environ.get("ORACLE_SPEED_SCALE", "1"))


def call(ep, body=None):
    req = urllib.request.Request(f"{BASE}/{ep}", data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return json.load(e)


for _ in range(300):
    try:
        spec = call("spec")
        break
    except OSError:
        time.sleep(1)
else:
    raise SystemExit("service unreachable")
plan = json.load(open(os.path.join(HERE, "oracle_decisions.json")))["seeds"].get(str(spec["match"]["seed"])) or []
table = {}
for d in plan:                                   # the k-th stroke on a hole is the k-th entry for that hole
    table.setdefault(d["hole"], []).append(d)
os.makedirs("/app/output", exist_ok=True)
log = open("/app/output/reference.jsonl", "a", buffering=1)
print("start:", call("start", {}).get("state"))
while True:
    s = call("status")["state"]
    if s["phase"] == "over":
        break
    if s["awaiting_review"]:
        call("ready", {"why": "reference player: no review", "plan": "reference player: precomputed strokes"})
        continue
    if s["phase"] != "running" or not s["your_turn"]:
        call("wait", {"max_s": 60})              # returns when it is our turn or the match is over
        continue
    dec = call("observe")["observation"]["decision"]
    strokes = table.get(dec["hole"], [])
    d = strokes[dec["stroke"] - 1] if dec["stroke"] <= len(strokes) else FALLBACK
    r = call("act", {"type": "putt", "aim_deg": d["aim_deg"] + AIM_OFFSET, "speed": round(d["speed"] * SPEED_SCALE, 4)})
    log.write(json.dumps({"hole": dec["hole"], "stroke": dec["stroke"], "result": r.get("result"),
                          "error": r.get("error")}) + "\n")
    print(r.get("result") or r)
print("final:", json.dumps(s))
