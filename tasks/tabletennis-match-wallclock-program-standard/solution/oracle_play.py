"""Harbor oracle for the WALL-CLOCK table-tennis match: a fast scripted reference player that uses only the public
interface (the `observe` camera images and frame steps, the heard bounces, the camera intrinsics of `spec`), the same
HTTP endpoints the `game` command calls. No ball state, no simulator: it detects the orange ball in the images,
triangulates it from the two cameras, fits its flight and acts (wc_player.py). It plays against the live clock, so
its result can vary with machine load; the match it played is graded by the service's own logged replay.

    python3 oracle_play.py            (SIM_URL, default http://sim:8000)
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
import base64

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wc_player as W  # noqa: E402

OUT = os.environ.get("RCB_OUT", "/app/output")
os.makedirs(OUT, exist_ok=True)


def base():
    for b in [os.environ.get("SIM_URL"), "http://sim:8000", "http://127.0.0.1:8000"]:
        if not b:
            continue
        for _ in range(60):
            try:
                urllib.request.urlopen(b + "/spec", timeout=3)
                return b
            except urllib.error.HTTPError:
                return b
            except Exception:  # noqa: BLE001
                time.sleep(1)
    sys.exit("game service unreachable")


BASE = base()


def call(path, body=None):
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        return json.load(urllib.request.urlopen(req, timeout=600))
    except urllib.error.HTTPError as e:
        return json.load(e)


spec = call("/spec")
SLOW = float(spec["timing"]["slowdown"])
PERIOD = W.DT * SLOW
cams = [W.Cam(c) for c in spec["cameras"]]
P = W.Player(cams)
log = open(os.path.join(OUT, "oracle_log.jsonl"), "w")
stats = {"observe": 0, "act": 0, "wait": 0, "ready": 0, "act_step_mismatch": 0, "obs_wall_s": []}


def review(o):
    if o.get("review_prompt"):
        r = call("/ready", {"why": "reference player: scripted", "plan": "reference player: same policy"})
        stats["ready"] += 1
        log.write(json.dumps({"ready": r.get("accepted") or r.get("error")}) + "\n")
        return True
    return False


o = call("/start", {})
log.write(json.dumps({"start": o.get("note")}) + "\n")
done = False
next_frame = None          # (local time, step) estimate of when the next camera frame exists (every 2 steps)
while not done:
    if next_frame is not None:  # no new frame yet: do not ask the service to render the same frames again
        dt = next_frame - time.monotonic()
        if dt > 0:
            time.sleep(min(dt, 0.5))
    t_send = time.monotonic()
    o = call("/observe", {})
    t_recv = time.monotonic()
    if o.get("done"):
        break
    if review(o):
        continue
    ob = o.get("observation")
    if not ob:
        if "error" in o:
            log.write(json.dumps({"observe_error": o["error"][:200]}) + "\n")
            time.sleep(PERIOD)
        continue
    stats["observe"] += 1
    stats["obs_wall_s"].append(round(t_recv - t_send, 4))
    k_req = int(ob["step"]) + float(ob.get("step_phase", 0.0))
    vs = ob.get("view_steps") or [int(ob["step"])]
    next_frame = t_send + max(0.0, (vs[-1] + 2 - k_req + 0.05)) * PERIOD
    incoming = ob.get("ball_state") == "coming to you" and ob.get("ball_in_play")
    img = W.decode(base64.b64decode(ob["image_png_b64"])) if incoming else None
    P.update(ob, img, int(ob["step"]))
    # game time when the act will reach the service: request time + everything since (+2 ms to get there)
    a = P.decide(lambda: k_req + (time.monotonic() - t_send + 0.002) / PERIOD) if incoming else None
    if a:
        r = call("/act", {"type": "act", **a})
        stats["act"] += 1
        te = r.get("took_effect") or {}
        P.on_act_reply(r.get("stroke"))
        last = P.leg["acts"][-1] if P.leg and P.leg["acts"] else None
        if last is not None and te:
            last["k_true"] = te.get("step")
            if te.get("step") != last["k_eff"]:
                stats["act_step_mismatch"] += 1
        log.write(json.dumps({"act": a, "k_assumed": last and last["k_eff"], "took_effect": te,
                              "stroke": r.get("stroke"), "phase": last and last["phase"]}, default=float) + "\n")
        if r.get("done"):
            break
        review(r)
        next_frame = None
        continue
    if not incoming:
        next_frame = None
        # nothing to look at: let 20 ms of game time pass (cheap: no image)
        r = call("/wait", {"dt": 0.02})
        stats["wait"] += 1
        if r.get("done"):
            break
        review(r)
final = call("/status")
s = {k: v for k, v in stats.items() if k != "obs_wall_s"}
ow = sorted(stats["obs_wall_s"])
if ow:
    s["obs_wall_ms_median"] = round(1000 * ow[len(ow) // 2], 1)
    s["obs_wall_ms_p90"] = round(1000 * ow[int(0.9 * (len(ow) - 1))], 1)
print("final:", json.dumps({"status": final, "stats": s}))
log.write(json.dumps({"final": final, "stats": s}) + "\n")
