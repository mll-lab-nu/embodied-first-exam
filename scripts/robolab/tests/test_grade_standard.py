"""Synthetic test of the standard graders (RoboLab, YAMLab): every final.json shape -> reward.txt / reward.json."""
import json, os, subprocess, sys, tempfile
ROOT = (sys.argv[1] if len(sys.argv) > 1 else os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")))
SERVICE = {"success": True, "steps": 10, "calls": 3, "control_steps": 100, "physics_steps": 800, "elapsed_s": 50.0, "reason": "success",
           "done": True, "task": "t", "protocol": "eai-standard/2.2", "finalized": False, "n_actions": 100, "live_sha": "aa",
           "sim_startups": 1, "resumes": 0}
FINAL = {**SERVICE, "finalized": True, "graded_by": "live", "replays": 0, "live_success": True, "video": True, "video_pending": False,
         "video_source": "live", "instance_exact": True, "instance_matches": True}
CASES = {   # name: (final.json content or None (missing) or raw string, expected reward, expected subset of reward.json)
    "missing": (None, 0, {"success": 0, "missing_log": 1, "infra_error": 1, "grader_error": 0, "finalized": 0, "graded_by_live": 1}),
    "corrupt_truncated": ('{"success": true, "graded_b', 0, {"success": 0, "infra_error": 1, "grader_error": 1, "missing_log": 0}),
    "corrupt_empty": ("", 0, {"success": 0, "infra_error": 1, "grader_error": 1}),
    "not_an_object": ("[1, 2]", 0, {"success": 0, "infra_error": 1, "grader_error": 1}),
    "unfinalized_live_success": (SERVICE, 0, {"success": 0, "live_success": 1, "finalized": 0, "infra_error": 1, "grader_error": 0}),
    "live_success": (FINAL, 1, {"success": 1, "live_success": 1, "graded_by_live": 1, "replays": 0, "finalized": 1, "infra_error": 0,
                                "grader_error": 0, "missing_log": 0, "sim_error": 0, "n_actions": 100, "sim_steps": 100, "video_rendered": 1}),
    "live_failure": ({**FINAL, "success": False, "live_success": False, "reason": "timeout"}, 0, {"success": 0, "infra_error": 0, "grader_error": 0, "finalized": 1}),
    "settle_failure": ({**FINAL, "success": False, "reason": "timeout", "settle_steps": 30}, 0, {"success": 0, "infra_error": 0}),
    "replay_fields_never_grant": ({**FINAL, "success": False, "replay_success": True, "deterministic": True}, 0, {"success": 0, "infra_error": 0}),
    "replay_fields_never_take": ({**FINAL, "replay_success": False, "deterministic": False}, 1, {"success": 1, "infra_error": 0}),
    "sim_error_agents_zero": ({**FINAL, "success": False, "reason": "error"}, 0, {"success": 0, "sim_error": 1, "infra_error": 0}),
    "video_failed_verdict_stands": ({**FINAL, "video": False, "video_error": "x"}, 1, {"success": 1, "video_rendered": 0, "infra_error": 0}),
    "video_pending_verdict_stands": ({**FINAL, "video": False, "video_pending": True}, 1, {"success": 1, "infra_error": 0}),
    "infra_flag_blocks_pass": ({**FINAL, "infra_error": 1}, 0, {"success": 0, "infra_error": 1}),
    "no_episode_json": ({**FINAL, "success": False, "infra_error": 1, "error": "infrastructure: no episode.json"}, 0, {"success": 0, "infra_error": 1}),
    "instance_mismatch_at_start": ({"task": "t", "instance_mismatch": True, "instance_exact": False, "success": False, "finalized": True, "gave_up": True,
                                    "reason": "instance_mismatch: x", "infra_error": 1}, 0, {"success": 0, "infra_error": 1, "instance_mismatch": 1, "gave_up": 1}),
    "gave_up_sim_crashed": ({**SERVICE, "success": False, "reason": "sim_crashed", "finalized": True, "gave_up": True, "infra_error": 1}, 0,
                            {"success": 0, "gave_up": 1, "infra_error": 1, "grader_error": 0, "finalized": 1, "sim_crashed_on_call": 0}),
    "gave_up_on_call_agent_zero": ({**SERVICE, "success": False, "reason": "sim_crashed_on_call", "finalized": True, "gave_up": True}, 0,
                                   {"success": 0, "gave_up": 1, "infra_error": 0, "grader_error": 0, "finalized": 1, "sim_crashed_on_call": 1}),
    "resume_failed": ({**SERVICE, "success": False, "reason": "resume_failed", "finalized": True, "gave_up": True, "infra_error": 1}, 0,
                      {"success": 0, "infra_error": 1}),
    "never_ended": ({**SERVICE, "finalized": True, "success": False, "infra_error": 1,
                     "error": "collect hook: the sim service did not end and dump the episode in time"}, 0, {"success": 0, "infra_error": 1}),
    "junk_numbers": ({**FINAL, "n_actions": [1], "elapsed_s": "x", "resumes": None}, 1, {"success": 1, "n_actions": 0, "elapsed_s": 0.0}),
}
bad = 0
for bench in ("robolab", "yamlab"):
    grade = os.path.join(ROOT, "scripts", bench, "template/standard/tests/grade.py")
    for name, (content, want_reward, want) in CASES.items():
        with tempfile.TemporaryDirectory() as td:
            data, log = os.path.join(td, "data"), os.path.join(td, "log"); os.makedirs(data)
            if content is not None:
                open(os.path.join(data, "final.json"), "w").write(content if isinstance(content, str) else json.dumps(content))
            open(os.path.join(data, "live.mp4"), "w").write("x")
            p = subprocess.run([sys.executable, "-I", grade], env={"RCB_DATA": data, "RCB_VERIFIER_LOG_DIR": log, "PATH": os.environ["PATH"]},
                               capture_output=True, text=True)
            try:
                reward = int(open(os.path.join(log, "reward.txt")).read().strip()); rj = json.load(open(os.path.join(log, "reward.json")))
            except Exception as exc:
                print(f"FAIL {bench} {name}: no reward written ({exc!r}); rc {p.returncode}; {p.stderr[-300:]}"); bad += 1; continue
            errs = [f"{k}={rj.get(k)!r} (want {v!r})" for k, v in want.items() if rj.get(k) != v]
            if reward != want_reward: errs.append(f"reward {reward} (want {want_reward})")
            if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in rj.values()): errs.append("non-numeric reward.json")
            for k in ("success", "live_success", "graded_by_live", "replays", "infra_error", "grader_error", "finalized", "missing_log"):
                if k not in rj: errs.append(f"{k} missing")
            if p.returncode != 0: errs.append(f"rc {p.returncode}")
            if any(k in rj for k in ("replay_success", "deterministic")): errs.append("reward.json still reports replay fields")
            if content is not None and name not in ("corrupt_truncated", "corrupt_empty", "not_an_object") and not os.path.exists(os.path.join(log, "live.mp4")):
                errs.append("evidence not copied")
            print(("FAIL" if errs else "ok  "), bench, name, "; ".join(errs)); bad += bool(errs)
print("standard grader:", "ALL OK" if not bad else f"{bad} FAILED"); sys.exit(1 if bad else 0)
