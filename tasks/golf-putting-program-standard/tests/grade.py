"""Trusted grader (separate sandbox, no network) for the mini-golf putting task: reads what the sim service wrote
(final.json, the fresh-process replay replay_check.json, trajectory.json, the metering files). valid_trial = the replay
reproduces every seat's state and score from the recorded actions and there is no simulator, metering or model-API
failure. success = a valid game, played out (no clock out), that reaches the success line. Numeric-only reward.json."""
import hashlib
import json
import os
import shutil
from pathlib import Path

DATA = Path(os.environ.get("RCB_DATA", "/data"))
LOG = Path(os.environ.get("RCB_LOG", "/logs/verifier"))
PROTOCOL = "eai-standard-turn/1.0"
DUEL = False
# Official configurations of this parameterized task (scripts/olympiad/golf/spec.py) and the success line (par).
OFFICIAL_SEEDS = [20260928, 13, 14]
SUCCESS_LINE = 9


def line_met(sc):
    return bool(sc["complete"]) and int(sc["total"]) <= SUCCESS_LINE


def extra(sc):
    h = list(sc["holes"]) + [None] * 4
    return {"to_par": int(sc["total"]) - int(sc["par_of_holes_scored"]), "picked_up_holes": int(sum(bool(x) for x in sc["picked_up"])),
            **{f"score_h{i + 1}": int(h[i] or 0) for i in range(4)}}


def sha(actions):
    return hashlib.sha256(json.dumps(actions, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load(name, default=None):
    p = DATA / name
    if not p.exists():
        if default is not None:
            return default
        raise FileNotFoundError(name)
    return json.loads(p.read_text())


def grade(d, r, t, usage):
    seats = list(d["seats"])
    assert seats == (["A", "B"] if DUEL else ["A"]) and bool(d["duel"]) == DUEL and d["protocol"] == PROTOCOL
    replay = (d["graded_ready"] and not d.get("finalize_error") and d.get("deterministic") is True
              and d["actions_sha"] == r["actions_sha"] == sha(t["actions"]) and t["actions"] == d["actions"]
              and d["source_sha"] == r["source_sha"] == t["source_sha"]
              and d["seed"] == r["seed"] == t["seed"] and d["first_player"] == t["first_player"]
              and all(r["seats"][s]["state_sha"] == d["state_sha"][s] and r["seats"][s]["score"] == d["scores"][s]
                      for s in seats)
              # the decision (winner and how: score, tie-break, the recorded chess clocks, a forfeit) replays too
              and r["decision"]["winner"] == d["winner"] and r["decision"]["decided_by"] == d.get("decided_by"))
    meter = any(d["meter_error"].values()) or any(
        d["player_mode"][s] == "model" and (not usage[s].get("epoch") or usage[s].get("requests", 0) < 1) for s in seats)
    proxy = any(d["proxy_error"].values())   # the server's model-API rule (api_errors.py): unrecovered, or > 5 transient
    sim = bool(d.get("sim_error") or d["reason"] == "error")
    valid = bool(replay and not (meter or proxy or sim))
    st = d["seat_stats"]
    out = {"valid_trial": int(valid), "technical_failure": int(not valid), "deterministic": int(bool(replay)),
           "replay_error": int(not replay), "sim_error": int(sim), "meter_error": int(meter), "proxy_error": int(proxy),
           "grader_error": 0, "missing_log": 0, "seed": int(d["seed"]), "official_config": 0,
           "match_over": int(d["reason"] == "match_over"), "video_rendered": int(bool(d.get("video"))),
           "elapsed_s": float(d.get("elapsed_s") or 0)}
    for s in seats:
        p = (s + "_") if DUEL else ""
        sc = d["scores"][s]
        out[p + "total"] = int(sc["total"])
        out[p + "complete"] = int(bool(sc["complete"]))
        out[p + "clock_out"] = int(bool(d["clock_out"][s]))
        for k in ("n_shots", "n_reviews", "refused_busy", "refused_not_model", "refused_turn"):
            out[p + k] = int(st[s][k])
        out[p + "clock_used_s"] = float(st[s]["clock_used_s"])
        out[p + "metered_requests"] = int(usage[s].get("requests", 0))
        out[p + "metered_output_tokens"] = int(usage[s].get("output_tokens", 0))
        out.update({p + k: v for k, v in extra(sc).items()})
        out[p + "transient_api_errors"] = int((d.get("transient_api_errors") or {}).get(s, 0))
        out[p + "unrecovered_api_errors"] = int((d.get("unrecovered_api_errors") or {}).get(s, 0))
    if DUEL:
        first = d["first_player"]
        out["first_player_B"] = int(first == "B")
        out["official_config"] = int(d["seed"] in OFFICIAL_SEEDS and first in ("A", "B"))
        decided = d["reason"] in ("match_over", "clock_out", "start_timeout")
        out["success"] = int(valid and decided)
        for s in seats:
            out[s + "_won"] = int(valid and decided and d["winner"] == s)
        out["draw"] = int(valid and d["reason"] == "match_over" and d["winner"] is None)
        out["clock_forfeit"] = int(d["reason"] == "clock_out")
        out["start_forfeit"] = int(d["reason"] == "start_timeout")
    else:
        sc = d["scores"]["A"]
        out["official_config"] = int(d["seed"] in OFFICIAL_SEEDS)
        out["success_line"] = SUCCESS_LINE
        out["success"] = int(valid and d["reason"] == "match_over" and line_met(sc))
    return out


def main():
    LOG.mkdir(parents=True, exist_ok=True)
    try:
        d = load("final.json")
        usage = {s: load(f"think_usage_{s}.json" if DUEL else "think_usage.json", {}) for s in (["A", "B"] if DUEL else ["A"])}
        out = grade(d, load("replay_check.json"), load("trajectory.json"), usage)
        for f in ("final.json", "replay_check.json", "trajectory.json", "episode.jsonl", "replay.mp4", "replay_A.mp4",
                  "replay_B.mp4"):
            if (DATA / f).exists():
                shutil.copyfile(DATA / f, LOG / f)
    except Exception:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        out = {"success": 0, "valid_trial": 0, "technical_failure": 1, "grader_error": 1,
               "missing_log": int(not (DATA / "final.json").exists())}
    assert all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in out.values()), out
    (LOG / "reward.txt").write_text(f"{out['success']}\n")
    (LOG / "reward.json").write_text(json.dumps(out, allow_nan=False))
    print(out)


if __name__ == "__main__":
    main()
