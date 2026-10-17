#!/usr/bin/env python3
"""Unit test of the RoboARC standard grading (board 0151: graded by the live episode, no grading replay), standard library
only, no simulator: scripts/roboarc/shared/standard/sim/finalize.sh runs with a stub `python` that answers
`/srv/rcb_limited.py end` with the case's exit code and stands in for `/srv/replay.py` (the video-only pass: it renders,
fails, or records what final.json held when it started), and a stub rcb_topogym (atomic_json, breakdown_words); then
scripts/roboarc/shared/standard/grade.py runs on the result.
    python3 scripts/roboarc/tests/test_live_grade.py   (also run at the end of test_server_requests.py)"""
import hashlib, json, os, pathlib, subprocess, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
STD = HERE.parent / "shared/standard"
TOPO = '''
import json, os
def atomic_json(p, obj):
    t = p + ".tmp"; json.dump(obj, open(t, "w"), allow_nan=False); os.replace(t, p)   # as the tooling: no NaN
def breakdown_words(ev): return "a cloth particle too fast"
'''
REPLAY = r'''
import json, os, sys
a = sys.argv[1:]; d = a[a.index("--data") + 1]
fin = json.load(open(os.path.join(d, "final.json")))
open(os.path.join(d, "replay.started"), "w").write(json.dumps({k: fin.get(k) for k in ("finalized", "graded_by", "success", "video_pending")}))
mode = os.environ.get("VIDEO", "ok")
if mode == "crash":
    sys.exit(139)
open(os.path.join(d, "replay.mp4"), "wb").write(b"x")
json.dump({"video": True, "media_status": "complete", "wall_s": 1.0}, open(os.path.join(d, "replay.video.json"), "w"))
'''
PYSTUB = f'''#!/bin/sh
if [ "$1" = "/srv/rcb_limited.py" ]; then exit "$END_RC"; fi
if [ "$1" = "/srv/replay.py" ]; then shift; exec {sys.executable} "$STUB_DIR/replay_stub.py" "$@"; fi
exec {sys.executable} "$@"
'''
BINDING = {"binding_id": None, "instance_sha256": "abc", "tooling_sha256": "t"}
WANTED = hashlib.sha256(json.dumps(BINDING, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
STARTUP = {"instance_exact": True, "runtime_binding": {"binding_id": WANTED}, "instance_generated": False, "instance_sha": "abc",
           "instance_realized": False, "assets_exact": True, "initial_state": None}
LIVE_OK = {"success": True, "infra_error": 0, "simulator_instability": False, "instability": None, "review": None, "forcing": None,
           "reason": "success", "live_rows": 3, "n_actions": 3, "live_sha": "s1", "control_steps": 3, "physics_steps": 30,
           "steps": 2, "calls": 2, "sim_startups": 1, "resumes": 0}


def run(case: dict) -> tuple[dict, dict, dict | None]:
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        data, log, bin_, tests = td / "data", td / "logs", td / "bin", td / "tests"
        for p in (data, log, bin_, tests):
            p.mkdir()
        (bin_ / "python").write_text(PYSTUB); (bin_ / "python").chmod(0o755)
        (bin_ / "replay_stub.py").write_text(REPLAY)
        (td / "site").mkdir(); (td / "site/rcb_topogym.py").write_text(TOPO)
        (tests / "runtime_binding.json").write_text(json.dumps(BINDING))
        for name, key in (("final.json", "final"), ("episode.json", "episode"), ("startup_binding.json", "startup")):
            v = case.get(key, STARTUP if key == "startup" else None)
            if v is not None:
                (data / name).write_text(v if isinstance(v, str) else json.dumps(v))
        if case.get("episode") is not None and case.get("traj", True):
            (data / "trajectory.npz").write_bytes(b"x")
        env = dict(os.environ, RCB_DATA=str(data), RCB_TASK="blanket_flatten", RCB_INSTANCE="/srv/instance.json",
                   END_RC=str(case.get("rc", 0)), STUB_DIR=str(bin_), VIDEO=case.get("video", "ok"),
                   PATH=f"{bin_}:{os.environ['PATH']}", PYTHONPATH=str(td / "site"))
        if case.get("hook", True):
            subprocess.run(["sh", str(STD / "sim/finalize.sh")], env=env, check=True, capture_output=True, timeout=60)
        genv = dict(os.environ, RCB_VERIFIER_DATA=str(data), RCB_VERIFIER_LOG_DIR=str(log), RCB_VERIFIER_TESTS=str(tests))
        subprocess.run([sys.executable, str(STD / "grade.py")], env=genv, check=True, capture_output=True, timeout=60)
        try:
            fin = json.loads((data / "final.json").read_text())
        except (OSError, ValueError):
            fin = {}
        started = json.loads((data / "replay.started").read_text()) if (data / "replay.started").is_file() else None
        r = json.loads((log / "reward.json").read_text())
        assert (log / "reward.txt").read_text().strip() == str(r["success"]), r
        assert all(isinstance(v, (int, float)) for v in r.values()), r       # reward.json: numbers only
        assert "replay_success" not in r and "deterministic" not in r, r
        return fin, r, started


def main() -> int:
    # live success -> 1; the verdict is in final.json before the video pass starts; the pass only adds the video
    fin, r, st = run({"final": {"finalized": False}, "episode": LIVE_OK})
    assert r["success"] == 1 and r["live_success"] == 1 and r["graded_by_live"] == 1 and r["replays"] == 0, r
    assert r["infra_error"] == 0 and r["video_rendered"] == 1 and r["video_pending"] == 0, r
    assert st == {"finalized": True, "graded_by": "live", "success": True, "video_pending": True}, st
    assert fin["graded_by"] == "live" and fin["replays"] == 0 and fin["video_source"] == "render" and fin["state_sha"] == "s1", fin
    assert "replay_success" not in fin and "deterministic" not in fin, fin
    # live failure -> 0 (the task's failure predicate, or the wall clock with the confirmation window not complete)
    for reason in ("task_failed", "timeout", "forced_breakdown: a cloth particle too fast"):
        _, r, _ = run({"episode": dict(LIVE_OK, success=False, reason=reason)})
        assert r["success"] == 0 and r["infra_error"] == 0, (reason, r)
    # a breakdown without forcing in the live episode -> infra
    fin, r, _ = run({"episode": dict(LIVE_OK, success=False, reason="simulator_instability", simulator_instability=True)})
    assert r["success"] == 0 and r["infra_error"] == 1 and r["simulator_instability"] == 1, r
    assert fin["error"].startswith("simulator_instability"), fin
    # a live success with a deep task contact -> held for review (success 0, pending 1)
    fin, r, _ = run({"episode": dict(LIVE_OK, review={"count": 2, "max_depth_mm": 3.5, "events": []}, forcing={"count": 1, "events": []})})
    assert r["success"] == 0 and r["success_pending_review"] == 1 and r["review_events"] == 2 and r["forcing_events"] == 1, r
    assert r["infra_error"] == 0 and fin["success"] is False and fin["live_success"] is True and fin["held_for_review"], (fin, r)
    # the service dumped the episode but did not exit in time (end rc 1): the live verdict stands, no video pass
    fin, r, st = run({"episode": LIVE_OK, "rc": 1})
    assert r["success"] == 1 and r["infra_error"] == 0 and fin["service_exit_timed_out"] and st is None, (fin, r)
    # no trajectory.npz dumped: recorded in final.json (dump_error), the live verdict unchanged
    fin, r, _ = run({"episode": LIVE_OK, "traj": False})
    assert fin["dump_error"] and r["success"] == 1, (fin, r)
    # a non-finite number in the live record never leaves final.json unfinalized
    fin, r, _ = run({"episode": dict(LIVE_OK, sim_time_s=float("nan"), instability={"v": float("inf")})})
    assert fin["finalized"] and r["success"] == 1 and fin["sim_time_s"] is None, (fin, r)
    # an infrastructure end: final.json success false, the raw live value kept in live_success
    fin, r, _ = run({"episode": dict(LIVE_OK, reason="error", infra_error=1)})
    assert fin["success"] is False and fin["live_success"] is True and r["infra_error"] == 1 and r["success"] == 0, (fin, r)
    # give-up after crashes not all inside the agent's calls -> infra, no video pass
    gave = {"success": False, "done": True, "finalized": True, "gave_up": True, "reason": "sim_crashed", "infra_error": 1}
    fin, r, st = run({"final": gave, "rc": 2})
    assert r["success"] == 0 and r["infra_error"] == 1 and st is None and fin["graded_by"] == "live", (fin, r)
    # every crash inside the agent's calls -> the agent's 0, not infra
    _, r, st = run({"final": dict(gave, reason="sim_crashed_on_call", infra_error=0), "rc": 2})
    assert r["success"] == 0 and r["infra_error"] == 0 and r["gave_up"] == 1 and st is None, r
    # the frozen instance mismatched at the live start -> infra
    mm = {"success": False, "done": True, "finalized": True, "gave_up": True, "instance_mismatch": True, "infra_error": 1,
          "reason": "instance_mismatch"}
    _, r, _ = run({"final": mm, "rc": 2, "startup": None})
    assert r["success"] == 0 and r["infra_error"] == 1 and r["instance_mismatch"] == 1, r
    # the live start was another runtime binding than this task's -> infra
    _, r, _ = run({"episode": LIVE_OK, "startup": dict(STARTUP, runtime_binding={"binding_id": "other"})})
    assert r["success"] == 0 and r["infra_error"] == 1 and r["instance_mismatch"] == 1 and r["runtime_binding_ok"] == 0, r
    # the video pass crashes: the verdict is unchanged, no video, not infra
    fin, r, _ = run({"episode": LIVE_OK, "video": "crash"})
    assert r["success"] == 1 and r["video_rendered"] == 0 and r["infra_error"] == 0, r
    assert fin["media_status"] == "error" and fin["video_pending"] is False, fin
    # the service did not end in time and dumped nothing -> infra, no video pass
    _, r, st = run({"final": {"finalized": False, "success": True}, "rc": 1})
    assert r["success"] == 0 and r["infra_error"] == 1 and st is None, r
    # an old-style record: replay success and determinism do not stand in for a live failure
    _, r, _ = run({"hook": False, "final": dict(LIVE_OK, success=False, finalized=True, replay_success=True, deterministic=True)})
    assert r["success"] == 0 and r["infra_error"] == 0, r
    # a live rule recorded beside the live success took it away: success decides
    _, r, _ = run({"hook": False, "final": dict(LIVE_OK, finalized=True, success=False, live_success=True, live_rule=False)})
    assert r["success"] == 0 and r["infra_error"] == 0, r
    # missing / unreadable / unfinalized final.json -> infra
    _, r, _ = run({"hook": False})
    assert r["success"] == 0 and r["infra_error"] == 1 and r["missing_log"] == 1, r
    _, r, _ = run({"hook": False, "final": "{not json"})
    assert r["success"] == 0 and r["infra_error"] == 1, r
    _, r, _ = run({"hook": False, "final": dict(LIVE_OK, finalized=False)})
    assert r["success"] == 0 and r["infra_error"] == 1, r
    print("test_live_grade: ok (live success, verdict before the video pass; live failures; instability; review hold; crash "
          "give-ups; instance and binding mismatch; video crash; end timeout; old-style record; missing final.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
