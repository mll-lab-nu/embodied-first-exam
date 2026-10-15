"""finalize.sh end to end with stand-ins for the simulator (the `end` half and the replay CLI), then the standard grader on
the final.json it wrote. The only edit to the script under test: /srv/rcb_limited.py -> the stand-in's path."""
import json, os, subprocess, sys, tempfile, time
ROOT = (sys.argv[1] if len(sys.argv) > 1 else os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))); HERE = os.path.dirname(os.path.abspath(__file__))
EP = {"success": True, "steps": 5, "calls": 2, "control_steps": 5, "physics_steps": 40, "elapsed_s": 9.0, "reason": "success", "task": "t",
      "protocol": "eai-standard/2.2", "n_actions": 5, "live_sha": "aa", "sim_startups": 1, "resumes": 0}
SERVICE_FINAL = {**EP, "done": True, "finalized": False}
# name: (env, episode.json?, want final.json subset, want reward, want reward.json subset, max seconds)
CASES = {
    "pass": ({"STUB_PLAN": "ok,ok"}, True, {"finalized": True, "replay_success": True, "deterministic": True, "live_matches_replay": True, "video": True, "replay_rc": [0, 0]},
             1, {"success": 1, "infra_error": 0, "replay_error": 0}, 30),
    "replay_fail_is_agents_zero": ({"STUB_PLAN": "fail,fail"}, True, {"replay_success": False, "deterministic": True}, 0, {"success": 0, "infra_error": 0, "grader_error": 0}, 30),
    "nondeterministic": ({"STUB_PLAN": "ok,diff"}, True, {"replay_success": True, "deterministic": False}, 0, {"success": 0, "infra_error": 0, "deterministic": 0}, 30),
    "replay1_dies_twice": ({"STUB_PLAN": "die,die,ok"}, True, {"finalized": True, "replay_success": False, "infra_error": 1, "replay_rc": [139, None]},
                           0, {"success": 0, "live_success": 1, "infra_error": 1, "replay_error": 1, "grader_error": 1, "finalized": 1, "replay_timed_out": 0}, 30),
    "replay1_dies_once_retry_ok": ({"STUB_PLAN": "die,ok,ok"}, True, {"replay_success": True, "deterministic": True, "replay_rc": [0, 0]}, 1, {"success": 1, "infra_error": 0}, 30),
    "replay2_dies_twice": ({"STUB_PLAN": "ok,die,die"}, True, {"replay_success": False, "deterministic": False, "infra_error": 1, "replay_rc": [0, 139]},
                           0, {"success": 0, "infra_error": 1, "replay_error": 1}, 30),
    "replay2_dies_once_retry_ok": ({"STUB_PLAN": "ok,die,ok"}, True, {"replay_success": True, "deterministic": True}, 1, {"success": 1}, 30),
    "crash_after_result_counts": ({"STUB_PLAN": "crash_after,crash_after"}, True, {"replay_success": True, "deterministic": True, "replay_rc": [139, 139]},
                                  1, {"success": 1, "infra_error": 0}, 30),
    "replay_error_line": ({"STUB_PLAN": "error,error"}, True, {"infra_error": 1}, 0, {"success": 0, "infra_error": 1, "replay_error": 1}, 30),
    "replay1_times_out": ({"STUB_PLAN": "sleep", "RCB_COLLECT_TIMEOUT_S": "430"}, True, {"infra_error": 1, "replay_rc": [124, None]},
                          0, {"success": 0, "infra_error": 1, "replay_error": 1, "replay_timed_out": 1}, 120),      # limit = (430 - 300) / 2 = 65 s
    "oom_kill_137_is_retried": ({"STUB_PLAN": "kill9,ok,ok"}, True, {"replay_success": True, "deterministic": True, "replay_rc": [0, 0]}, 1, {"success": 1, "infra_error": 0, "replay_timed_out": 0}, 30),
    "no_time_left": ({"STUB_PLAN": "ok,ok", "RCB_COLLECT_TIMEOUT_S": "300"}, True, {"infra_error": 1, "replay_rc": [124, None]}, 0, {"success": 0, "infra_error": 1}, 30),
    "video_failed_verdict_stands": ({"STUB_PLAN": "novideo,ok"}, True, {"replay_success": True, "deterministic": True, "video": False}, 1, {"success": 1, "video_rendered": 0}, 30),
    "no_episode_json": ({"STUB_PLAN": "ok,ok"}, False, {"infra_error": 1}, 0, {"success": 0, "infra_error": 1}, 30),
    "service_never_ended": ({"STUB_END_RC": "1"}, True, {"finalized": True, "success": False, "infra_error": 1}, 0, {"success": 0, "infra_error": 1, "finalized": 1}, 30),
    "verdict_already_there": ({"STUB_END_RC": "2"}, True, {"finalized": False}, 0, {"success": 0, "infra_error": 1, "finalized": 0}, 30),   # final.json untouched (here: the service's copy)
}
bad = 0
for bench in ("robolab", "yamlab"):
    src = open(os.path.join(ROOT, "scripts", bench, "template/standard/environment/sim/finalize.sh")).read()
    assert src.count("/srv/rcb_limited.py") == 1
    grade = os.path.join(ROOT, "scripts", bench, "template/standard/tests/grade.py")
    for name, (env, has_ep, want_fin, want_reward, want_rj, max_s) in CASES.items():
        with tempfile.TemporaryDirectory() as td:
            data, log, bindir = (os.path.join(td, x) for x in ("data", "log", "bin")); os.makedirs(data); os.makedirs(bindir)
            os.symlink(sys.executable, os.path.join(bindir, "python"))
            sh = os.path.join(td, "finalize.sh"); open(sh, "w").write(src.replace("/srv/rcb_limited.py", os.path.join(HERE, "stub_end.py")))
            json.dump(SERVICE_FINAL, open(os.path.join(data, "final.json"), "w"))
            if has_ep: json.dump(EP, open(os.path.join(data, "episode.json"), "w"))
            open(os.path.join(data, "trajectory.npz"), "w").write("x")
            e = {"PATH": bindir + ":/usr/bin:/bin", "RCB_DATA": data, "RCB_TOOL": os.path.join(HERE, "stub_tool.py"), "RCB_TASK": "t", "RCB_INSTANCE": "i", **env}
            t0 = time.time(); p = subprocess.run(["sh", sh], env=e, capture_output=True, text=True); dt = time.time() - t0
            errs = []
            try:
                fin = json.load(open(os.path.join(data, "final.json")))
            except Exception as exc:
                fin = {}; errs.append(f"final.json unreadable {exc!r}")
            errs += [f"final {k}={fin.get(k)!r} (want {v!r})" for k, v in want_fin.items() if fin.get(k) != v]
            if [f for f in os.listdir(data) if f.endswith(".tmp")]: errs.append("temporary file left behind")
            if p.returncode != 0: errs.append(f"hook rc {p.returncode}: {p.stderr[-200:]}")
            if dt > max_s: errs.append(f"took {dt:.0f} s")
            g = subprocess.run([sys.executable, "-I", grade], env={"RCB_DATA": data, "RCB_VERIFIER_LOG_DIR": log, "PATH": e["PATH"]}, capture_output=True, text=True)
            reward = int(open(os.path.join(log, "reward.txt")).read().strip()); rj = json.load(open(os.path.join(log, "reward.json")))
            if reward != want_reward: errs.append(f"reward {reward} (want {want_reward})")
            errs += [f"reward.json {k}={rj.get(k)!r} (want {v!r})" for k, v in want_rj.items() if rj.get(k) != v]
            print(("FAIL" if errs else "ok  "), bench, name, f"({dt:.0f} s)", "; ".join(errs)); bad += bool(errs)
            if errs: print("   hook stdout:", p.stdout[-600:].replace("\n", " | "))
print("finalize.sh:", "ALL OK" if not bad else f"{bad} FAILED"); sys.exit(1 if bad else 0)
