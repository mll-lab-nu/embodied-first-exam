"""Synthetic test of the collect hooks (finalize.sh of LabUtopia and AutoBio) with a fake service end and fake replays,
then the standard grader on what the hook wrote."""
import json, os, subprocess, sys, tempfile, time
ROOT, HERE = (sys.argv[1] if len(sys.argv) > 1 else os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))), os.path.dirname(os.path.abspath(__file__))
EPISODE = {"success": True, "score": 1.0, "reason": "success", "live_sha": "aaa", "n_actions": 5, "control_steps": 5}
GAVE_UP = {"success": False, "done": True, "reason": "sim_crashed_on_call", "finalized": True, "gave_up": True}
# name: (env, episode.json (dict | None | str), preexisting final.json, expected final.json fields, expected (reward, infra_error))
CASES = {
    "pass":            ({}, EPISODE, None, {"finalized": True, "success": True, "replay_success": True, "deterministic": True,
                                             "live_matches_replay": True, "replay_rc": [0, 0], "video": True, "infra_error": None}, (1, 0)),
    "live_fail":       ({"FAKE_1": "fail", "FAKE_2": "fail"}, {**EPISODE, "success": False, "reason": "timeout"}, None,
                        {"finalized": True, "replay_success": False, "deterministic": True, "infra_error": None}, (0, 0)),
    "replay1_dies":    ({"FAKE_1": "die"}, EPISODE, None, {"finalized": True, "replay_failed": 1, "infra_error": 1, "replay_timed_out": 0,
                                                             "replay_rc": [139, 0], "deterministic": False}, (0, 1)),
    "replay2_hangs":   ({"FAKE_2": "hang", "RCB_REPLAY_TIMEOUT_S": "2"}, EPISODE, None,
                        {"finalized": True, "replay_failed": 1, "infra_error": 1, "replay_timed_out": 1, "replay_rc": [0, 124]}, (0, 1)),
    "result_then_crash": ({"FAKE_1": "ok_crash", "FAKE_2": "ok_crash"}, EPISODE, None,
                          {"finalized": True, "success": True, "replay_success": True, "deterministic": True, "replay_rc": [139, 139],
                           "infra_error": None}, (1, 0)),
    "garbage_result":  ({"FAKE_2": "garbage"}, EPISODE, None, {"finalized": True, "replay_failed": 1, "infra_error": 1}, (0, 1)),
    "nondeterministic": ({"FAKE_2": "sha2"}, EPISODE, None, {"finalized": True, "deterministic": False, "replay_success": True, "infra_error": None}, (0, 0)),
    "instance_mismatch": ({"FAKE_1": "inst"}, EPISODE, None, {"finalized": True, "instance_mismatch": 1, "infra_error": 1}, (0, 1)),
    "no_episode_json": ({}, None, None, {"finalized": True, "success": False, "infra_error": 1}, (0, 1)),
    "corrupt_episode_json": ({}, '{"success": tr', None, {"finalized": True, "success": False, "infra_error": 1}, (0, 1)),
    "end_rc2_verdict_kept": ({"FAKE_END_RC": "2"}, EPISODE, GAVE_UP, dict(GAVE_UP), (0, 0)),
    "end_rc1_timeout": ({"FAKE_END_RC": "1"}, None, {"success": True, "finalized": False}, {"finalized": True, "success": False, "infra_error": 1,
                                                                                                "deterministic": False}, (0, 1)),
    "end_rc1_corrupt_final": ({"FAKE_END_RC": "1"}, None, '{"succ', {"finalized": True, "success": False, "infra_error": 1}, (0, 1)),
    "video_dies":      ({"FAKE_3": "die"}, EPISODE, None, {"finalized": True, "success": True, "replay_success": True, "deterministic": True, "video": False}, (1, 0)),
    "video_garbage":   ({"FAKE_3": "garbage"}, EPISODE, None, {"finalized": True, "success": True, "deterministic": True, "video": False}, (1, 0)),
    "no_time_for_video": ({"RCB_COLLECT_BUDGET_S": "300"}, EPISODE, None, {"finalized": True, "success": True, "deterministic": True, "video": False}, (1, 0)),
}
bad = 0
for bench in ("labutopia", "autobio"):
    fin = os.path.join(ROOT, "scripts", bench, "shared/standard/finalize.sh")
    grader = os.path.join(ROOT, "scripts", bench, "shared/standard/grade.py")
    for name, (env, episode, pre, want, (reward, infra)) in CASES.items():
        with tempfile.TemporaryDirectory() as tmp:
            data, log = os.path.join(tmp, "data"), os.path.join(tmp, "log"); os.makedirs(data)
            for fn, content in (("episode.json", episode), ("final.json", pre)):
                if content is not None:
                    open(os.path.join(data, fn), "w").write(content if isinstance(content, str) else json.dumps(content))
            open(os.path.join(data, "trajectory.npz"), "wb").write(b"x")
            e = {**os.environ, "PATH": os.path.join(HERE, "shim") + ":" + os.environ["PATH"], "RCB_DATA": data, "RCB_TOOL": "/fake/tool.py",
                 "FAKE_TOOL": os.path.join(HERE, "fake_tool.py"), "RCB_INSTANCE": "/fake/instance.json", **env}
            t0 = time.time()
            r = subprocess.run(["sh", fin], env=e, capture_output=True, text=True, timeout=120)
            errs = []
            if r.returncode != 0: errs.append(f"hook rc {r.returncode}: {r.stderr[-200:]}")
            if "shim: unexpected" in r.stderr: errs.append(r.stderr[-200:])
            try:
                d = json.load(open(os.path.join(data, "final.json")))
            except Exception as exc:
                d = {}; errs.append(f"final.json unreadable: {exc!r}")
            errs += [f"{k}={d.get(k)!r} (want {v!r})" for k, v in want.items() if d.get(k) != v]
            if any(f.endswith(".tmp") for f in os.listdir(data)): errs.append("a .tmp file was left behind")
            g = subprocess.run([sys.executable, "-B", grader], env={**os.environ, "RCB_DATA": data, "RCB_VERIFIER_LOG_DIR": log}, capture_output=True, text=True)
            try:
                rw = int(open(os.path.join(log, "reward.txt")).read()); rj = json.load(open(os.path.join(log, "reward.json")))
                if (rw, rj["infra_error"]) != (reward, infra): errs.append(f"grader (reward, infra_error) = {(rw, rj['infra_error'])}, want {(reward, infra)}")
            except Exception as exc:
                errs.append(f"grader wrote no reward: {exc!r} {g.stderr[-200:]}")
            print(("FAIL" if errs else "ok  "), bench, name, f"({time.time() - t0:.1f} s)", "; ".join(errs)); bad += bool(errs)
print("ALL PASS" if not bad else f"{bad} FAILED"); sys.exit(bool(bad))
