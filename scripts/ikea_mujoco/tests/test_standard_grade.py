#!/usr/bin/env python3
"""Unit test of the IKEA MuJoCo standard-mode grading (board 0151: graded by the live episode, no grading replay), without
MuJoCo or a simulator: scripts/ikea_mujoco/standard/finalize.sh runs with a stub `python /srv/rcb_limited.py end` (its
exit code chosen per case) on a synthetic /data, then scripts/ikea_mujoco/standard/grade.py on the result. A
sitecustomize records any subprocess the grader starts (it must start none: no replay).
    python3 scripts/ikea_mujoco/tests/test_standard_grade.py   (also run by test_grade.py)"""
import json, os, pathlib, shutil, subprocess, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
STD = HERE.parent / "standard"
SITE = r'''
import os, subprocess
_orig = subprocess.Popen.__init__
def _rec(self, *a, **k):
    open(os.environ["SPAWN_LOG"], "a").write(repr(a[:1]) + "\n")
    return _orig(self, *a, **k)
subprocess.Popen.__init__ = _rec
'''
# stand-in for `python`: `python /srv/rcb_limited.py end ...` exits with $END_RC; anything else runs the real interpreter
PYSTUB = f'''#!/bin/sh
if [ "$1" = "/srv/rcb_limited.py" ]; then exit "$END_RC"; fi
exec {sys.executable} "$@"
'''

LIVE_OK = {"success": True, "infra_error": 0, "sim_error": 0, "reason": "success", "live_rows": 3, "live_sha": "abc",
           "control_steps": 3, "physics_steps": 12, "calls": 2, "settle_failed": 0, "sim_startups": 1, "resumes": 0}


def run(case: dict) -> tuple[dict, dict, list]:
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        data, log, bin_ = td / "data", td / "logs", td / "bin"
        for p in (data, log, bin_):
            p.mkdir()
        (bin_ / "python").write_text(PYSTUB); (bin_ / "python").chmod(0o755)
        (td / "site").mkdir(); (td / "site/sitecustomize.py").write_text(SITE)
        if case.get("final") is not None:
            (data / "final.json").write_text(case["final"] if isinstance(case["final"], str) else json.dumps(case["final"]))
        if case.get("episode") is not None:
            (data / "episode.json").write_text(json.dumps(case["episode"]))
        if case.get("traj", True):
            (data / "trajectory.npz").write_bytes(b"x")
        if case.get("video", True):
            (data / "live.mp4").write_bytes(b"x")
        env = dict(os.environ, RCB_DATA=str(data), END_RC=str(case.get("rc", 0)), PATH=f"{bin_}:{os.environ['PATH']}")
        if case.get("hook", True):
            subprocess.run(["sh", str(STD / "finalize.sh")], env=env, check=True, capture_output=True)
        spawn = td / "spawn.log"
        genv = dict(os.environ, RCB_VERIFIER_DATA=str(data), RCB_VERIFIER_LOG_DIR=str(log), SPAWN_LOG=str(spawn),
                    PYTHONPATH=str(td / "site"))
        subprocess.run([sys.executable, str(STD / "grade.py"), "lack"], env=genv, check=True, capture_output=True)
        try:
            fin = json.loads((data / "final.json").read_text())
        except (OSError, ValueError):
            fin = {}
        r = json.loads((log / "reward.json").read_text())
        assert (log / "reward.txt").read_text().strip() == str(r["success"]), r
        assert all(isinstance(v, (int, float)) for v in r.values()), r     # reward.json: numbers only
        spawned = spawn.read_text().splitlines() if spawn.is_file() else []
        return fin, r, spawned


def main() -> int:
    # live success -> 1, graded by the live episode, no replay
    fin, r, sp = run({"final": {"finalized": False}, "episode": LIVE_OK})
    assert r["success"] == 1 and r["live_success"] == 1 and r["graded_by_live"] == 1 and r["replays"] == 0, r
    assert r["infra_error"] == 0 and r["grader_error"] == 0 and "replay_success" not in r and "deterministic" not in r, r
    assert fin["graded_by"] == "live" and fin["replays"] == 0 and fin["finalized"] and fin["video"] == "live.mp4", fin
    assert fin["video_source"] == "live" and fin["video_pending"] is False and fin["state_sha"] == "abc", fin
    assert "deterministic" not in fin and "replay_success" not in fin, fin
    assert sp == [], sp                                                    # no replay (no process at all)
    # live failure -> 0 (timeout, judged as it stands)
    _, r, _ = run({"episode": dict(LIVE_OK, success=False, reason="timeout")})
    assert r["success"] == 0 and r["live_success"] == 0 and r["infra_error"] == 0, r
    # settle failure -> 0: the terminal rules held at a call but the 1.0 s settled check failed, the episode timed out
    _, r, _ = run({"episode": dict(LIVE_OK, success=False, reason="timeout", settle_failed=2)})
    assert r["success"] == 0 and r["settle_failed"] == 2 and r["infra_error"] == 0, r
    # breakdown -> 0
    _, r, _ = run({"episode": dict(LIVE_OK, success=False, reason="sim_breakdown")})
    assert r["success"] == 0 and r["infra_error"] == 0, r
    # a simulator error the agent's rows caused -> 0, sim_error, not infra
    _, r, _ = run({"episode": dict(LIVE_OK, success=False, reason="error", sim_error=1)})
    assert r["success"] == 0 and r["sim_error"] == 1 and r["infra_error"] == 0, r
    # a service-side error in a call -> infra
    _, r, _ = run({"episode": dict(LIVE_OK, success=False, reason="error", infra_error=1)})
    assert r["success"] == 0 and r["infra_error"] == 1, r
    # give-up after crashes not all inside the agent's calls (the service wrote the verdict, end exits 2) -> infra
    gave = {"success": False, "done": True, "finalized": True, "gave_up": True, "reason": "sim_crashed", "infra_error": 1}
    fin, r, _ = run({"final": gave, "rc": 2})
    assert r["success"] == 0 and r["infra_error"] == 1 and r["gave_up"] == 1 and fin["graded_by"] == "live", (fin, r)
    # every crash inside the agent's calls -> the agent's 0, not infra
    fin, r, _ = run({"final": dict(gave, reason="sim_crashed_on_call", infra_error=0), "rc": 2})
    assert r["success"] == 0 and r["infra_error"] == 0 and r["gave_up"] == 1, (fin, r)
    # the frozen instance mismatched at the episode's start (server.py) -> infra
    mm = {"success": False, "done": True, "finalized": True, "gave_up": True, "graded_by": "live", "replays": 0,
          "instance_mismatch": True, "infra_error": 1, "reason": "instance_mismatch"}
    _, r, _ = run({"final": mm, "rc": 2})
    assert r["success"] == 0 and r["infra_error"] == 1 and r["instance_mismatch"] == 1, r
    # no live video (the encoder failed): the verdict is unchanged
    fin, r, _ = run({"episode": LIVE_OK, "video": False})
    assert r["success"] == 1 and r["video_rendered"] == 0 and r["infra_error"] == 0 and fin["video"] is None, (fin, r)
    # a live success whose trajectory (the deliverable) was not dumped -> infra (the service's fault)
    _, r, _ = run({"episode": LIVE_OK, "traj": False})
    assert r["success"] == 0 and r["infra_error"] == 1 and r["dump_lost"] == 1, r
    # the service never ended in time (end timed out) -> infra
    _, r, _ = run({"final": {"finalized": False, "success": True}, "rc": 1})
    assert r["success"] == 0 and r["infra_error"] == 1, r
    # missing / unreadable / unfinalized final.json -> infra
    _, r, _ = run({"hook": False})
    assert r["success"] == 0 and r["infra_error"] == 1 and r["missing_log"] == 1, r
    _, r, _ = run({"hook": False, "final": "{not json"})
    assert r["success"] == 0 and r["infra_error"] == 1, r
    _, r, _ = run({"hook": False, "final": dict(LIVE_OK, finalized=False)})
    assert r["success"] == 0 and r["infra_error"] == 1, r
    # a bad number in final.json never fails the grader; success decides over live_success
    _, r, _ = run({"hook": False, "final": dict(LIVE_OK, finalized=True, live_rows="x", elapsed_s=float("nan"), calls=None)})
    assert r["success"] == 1 and r["live_rows"] == 0 and r["elapsed_s"] == 0, r
    _, r, _ = run({"hook": False, "final": dict(LIVE_OK, finalized=True, success=False, live_success=True, live_rule=False)})
    assert r["success"] == 0 and r["infra_error"] == 0, r
    print("test_standard_grade: ok (live success / failure / settle failure / breakdown / sim error / service error; crash "
          "give-ups; instance mismatch; no video; lost dump; end timeout; missing final.json; no replay)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
