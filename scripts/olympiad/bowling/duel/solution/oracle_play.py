"""Harbor oracle for bowling (single player or either duel seat): plays through the same HTTP calls a player program
uses (spec, start, status, wait, observe, act, ready). Its releases were computed offline for each official seed by the privileged
reference player (oracle_decisions.json); for another seed it rolls a fixed release. A roll-off frame repeats the 10th
frame's releases. Seat B lays every ball down half a board further left than seat A (two identical references would
tie). It never reads simulator state."""
import json
import os
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.environ.get("SIM_URL", "http://sim:8000").rstrip("/") + ("/" + os.environ["SEAT"] if os.environ.get("SEAT") else "")
FIRST_BALL = {"board": 29.48, "angle_deg": -3.75, "speed": 8.5, "rpm": 450, "axis_deg": 60}
STRAIGHT = {"board": 20.0, "angle_deg": 0.0, "speed": 8.0, "rpm": 0, "axis_deg": 0}
# The two seats' references differ slightly so that two references do not tie every game and roll-off: seat B lays the
# ball down half a board further left (README; on the official seeds A bowls 300, B 244 / 247 / 160).
BOARD_OFFSET = float(os.environ.get("ORACLE_BOARD_OFFSET", "0.5" if os.environ.get("SEAT") == "B" else "0"))


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
plan = json.load(open(os.path.join(HERE, "oracle_decisions.json")))["seeds"].get(str(spec["match"]["seed"]))
table = {(d["frame"], d["ball"]): d for d in plan or []}
os.makedirs("/app/output", exist_ok=True)
log = open("/app/output/reference.jsonl", "a", buffering=1)
print("start:", call("start", {}).get("state"))
while True:
    s = call("status")["state"]
    if s["phase"] == "over":
        break
    if s["awaiting_review"]:
        call("ready", {"why": "reference player: no review", "plan": "reference player: precomputed releases"})
        continue
    if s["phase"] != "running" or not s["your_turn"]:
        call("wait", {"max_s": 60})              # returns when it is our turn or the match is over
        continue
    dec = call("observe")["observation"]["decision"]
    d = table.get((dec["frame"], dec["ball"])) or (FIRST_BALL if dec["fresh_rack"] else STRAIGHT)
    d = dict(d, board=min(39.0, d["board"] + BOARD_OFFSET))
    r = call("act", {"type": "roll", **{k: d[k] for k in FIRST_BALL}})
    log.write(json.dumps({"decision": dec.get("frame"), "ball": dec.get("ball"), "result": r.get("result"),
                          "error": r.get("error")}) + "\n")
    print(r.get("result") or r)
print("final:", json.dumps(s))
