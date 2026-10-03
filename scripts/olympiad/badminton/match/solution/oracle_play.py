"""Harbor oracle for the WALL-CLOCK badminton match: the privileged reference player, playing LIVE against the running
clock through the same HTTP endpoints the `game` command calls (start / observe / act / wait / ready).

Privileged part: with RCB_PLAYER_MODE=oracle (set by the runner) the service exposes POST /oracle, which reports the
true state and, on request, the reference decision computed from an exact copy of the match (true shuttle flight ->
contact point and time; scheme A's stroke planner -> face normal and head velocity; environment/sim/oracle_ref.py,
the same reference as the lock-step tasks' recorded oracle). The decision is still sent as an ordinary `act` (racket
state at contact, T s from the step the act takes effect), so it pays every wall-clock cost a model pays: the advice
computation itself (~0.3-1 s of real time), the HTTP round trips and the act's fixed planning lead
(`spec.timing.act_lead_steps`). A recorded call sequence cannot be used here: the world does not wait.

Per shuttle coming to us: as soon as it has been played (READ_S of game time), ask for the advice; align with a
control step (`wait` one step returns right after a step); act with T = contact time - (effect step - launch) x 10 ms,
where effect step = current step + lead; if the reply's `took_effect.step` differs from the assumed one, re-act once
with the corrected T. Then one `observe` (not needed by the policy; it exercises the camera path like a model would).
Its result depends on machine load (it plays the live clock); the match is graded on the service's logged replay.

    python3 oracle_play.py            (SIM_URL, default http://sim:8000)
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

OUT = os.environ.get("RCB_OUT", "/app/output")
os.makedirs(OUT, exist_ok=True)
READ_S = float(os.environ.get("ORACLE_READ_S", "0.02"))
DT = 0.01


def base():
    for b in [os.environ.get("SIM_URL"), "http://sim:8000", "http://127.0.0.1:8000"]:
        if not b:
            continue
        for _ in range(120):
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
        return json.load(urllib.request.urlopen(req, timeout=900))
    except urllib.error.HTTPError as e:
        return json.load(e)


spec = call("/spec")
SLOW = float(spec["timing"]["slowdown"])
LEAD = int(spec["timing"]["act_lead_steps"])
PERIOD = DT * SLOW
log = open(os.path.join(OUT, "oracle_log.jsonl"), "w")
stats = {"advice": 0, "act": 0, "react": 0, "skipped": 0, "observe": 0, "wait": 0, "ready": 0, "step_mismatch": 0,
         "advice_wall_ms": [], "render_ms": []}


def L(**kw):
    log.write(json.dumps(kw, default=float) + "\n"); log.flush()


def review(o):
    if o.get("review_prompt"):
        r = call("/ready", {"why": "reference player: scripted", "plan": "reference player: same policy"})
        stats["ready"] += 1
        L(ready=r.get("accepted") or r.get("error"))
        return True
    return False


def act_at(adv, k_now):
    """Act so that the contact is at the advised time: T counts from the effect step k_now + LEAD."""
    k_e = k_now + LEAD
    T = round(adv["t_hit"] - (k_e - adv["launch"]) * DT, 4)
    if T < 0.03:
        return None, k_e, T
    r = call("/act", {"type": "act", "t": T, "pos": adv["pos"], "normal": adv["normal"], "vel": adv["vel"]})
    stats["act"] += 1
    return r, k_e, T


o = call("/start", {})
L(start=o.get("note"))
acted = set()
while True:
    st = call("/oracle", {})
    if st.get("done"):
        break
    if "error" in st and "k" not in st:
        L(oracle_error=st["error"]); break
    if st.get("awaiting_review"):
        review({"review_prompt": True}); continue
    if not st.get("running"):
        time.sleep(PERIOD); continue
    leg = st["leg_id"]
    if (st["leg_state"] == "incoming" and st["in_play"] and leg not in acted
            and st["t_since_launch"] >= READ_S - 1e-9):
        acted.add(leg)
        t0 = time.monotonic()
        a = call("/oracle", {"advise": True})
        stats["advice"] += 1
        stats["advice_wall_ms"].append(round((time.monotonic() - t0) * 1e3, 1))
        adv = a.get("advice") or {}
        if a.get("done"):
            break
        if not adv.get("pos") or adv.get("leg_id") != leg:
            stats["skipped"] += 1; L(advice=adv); continue
        w = call("/wait", {"dt": DT})              # returns right after a control step: act early in the next slot
        stats["wait"] += 1
        if w.get("done"):
            break
        if review(w) or "now" not in w:
            continue
        r, k_e, T = act_at(adv, int(w["now"]["step"]))
        if r is None:
            stats["skipped"] += 1; L(skip="too late", T=T); continue
        te = (r.get("took_effect") or {}).get("step")
        L(leg=leg, advice={k: adv.get(k) for k in ("k_snap", "k_reply", "t_hit", "pos", "advice_ms")},
          act_T=T, k_assumed=k_e, took_effect=te, stroke=r.get("stroke"))
        if r.get("done"):
            break
        if review(r):
            continue
        if te is not None and te != k_e:          # the act arrived a step late: correct T once
            stats["step_mismatch"] += 1
            w = call("/wait", {"dt": DT}); stats["wait"] += 1
            if w.get("done"):
                break
            if review(w) or "now" not in w:
                continue
            r2, k_e2, T2 = act_at(adv, int(w["now"]["step"]))
            stats["react"] += 1
            L(react=True, act_T=T2, k_assumed=k_e2, took_effect=(r2 or {}).get("took_effect"))
            if r2 and r2.get("done"):
                break
            if r2 and review(r2):
                continue
        ob = call("/observe", {})
        stats["observe"] += 1
        if ob.get("observation"):
            stats["render_ms"].append(round(1e3 * ob["observation"].get("render_wall_s", 0.0), 1))
        if ob.get("done"):
            break
        review(ob)
        continue
    w = call("/wait", {"dt": 0.02})
    stats["wait"] += 1
    if w.get("done"):
        break
    review(w)
final = call("/status")
s = {k: v for k, v in stats.items() if not isinstance(v, list)}
for k in ("advice_wall_ms", "render_ms"):
    v = sorted(stats[k])
    if v:
        s[k + "_median"] = v[len(v) // 2]; s[k + "_max"] = v[-1]
print("final:", json.dumps({"status": final, "stats": s}))
L(final=final, stats=s)
