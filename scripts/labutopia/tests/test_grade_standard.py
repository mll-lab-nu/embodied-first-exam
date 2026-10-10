"""Synthetic test of the standard graders (LabUtopia, AutoBio): every final.json state -> reward.txt / reward.json."""
import json, os, subprocess, sys, tempfile
ROOT = (sys.argv[1] if len(sys.argv) > 1 else os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")))
FULL = {"success": True, "replay_success": True, "deterministic": True, "live_matches_replay": True, "finalized": True,
        "score": 1.0, "replay_score": 1.0, "n_actions": 10, "control_steps": 10, "reason": "success", "video": True}
CASES = {  # name: (final.json content or None (missing) or raw str, expected reward, expected flags)
    "missing":            (None, 0, {"infra_error": 1, "missing_log": 1, "grader_error": 0, "deterministic": 0}),
    "corrupt":            ('{"success": true, "repl', 0, {"infra_error": 1, "grader_error": 1, "missing_log": 0, "deterministic": 0}),
    "empty_file":         ("", 0, {"infra_error": 1, "grader_error": 1}),
    "not_object":         ("[1, 2]", 0, {"infra_error": 1, "grader_error": 1}),
    "bad_field_type":     ({**FULL, "n_actions": "many"}, 0, {"infra_error": 1, "grader_error": 1}),
    "unfinalized_live_ok": ({"success": True, "finalized": False, "reason": "success", "score": 1.0}, 0,
                           {"infra_error": 1, "no_verdict": 1, "finalized": 0, "live_success": 1, "grader_error": 0}),
    "unfinalized_live_fail": ({"success": False, "finalized": False, "reason": None}, 0, {"infra_error": 1, "no_verdict": 1}),
    "finalized_no_deterministic": ({"success": True, "finalized": True}, 0, {"infra_error": 1, "no_verdict": 1}),
    "pass":               (FULL, 1, {"infra_error": 0, "grader_error": 0, "success": 1, "deterministic": 1, "finalized": 1, "no_verdict": 0}),
    "fail_live":          ({**FULL, "success": False, "replay_success": False, "reason": "timeout", "score": 0.0}, 0,
                           {"infra_error": 0, "grader_error": 0, "deterministic": 1, "timeout": 1}),
    "fail_nondeterministic": ({**FULL, "deterministic": False}, 0, {"infra_error": 0, "grader_error": 0, "live_success": 1}),
    "replay_died":        ({**FULL, "replay_success": False, "deterministic": False, "replay_failed": 1, "infra_error": 1}, 0,
                           {"infra_error": 1, "grader_error": 1, "replay_failed": 1, "live_success": 1}),
    "replay_timed_out":   ({**FULL, "replay_success": False, "deterministic": False, "replay_failed": 1, "replay_timed_out": 1,
                            "infra_error": 1}, 0, {"infra_error": 1, "replay_timed_out": 1}),
    "instance_mismatch":  ({**FULL, "instance_mismatch": 1, "infra_error": 1}, 0, {"infra_error": 1, "grader_error": 1, "instance_mismatch": 1}),
    "hook_end_timeout":   ({"finalized": True, "success": False, "replay_success": False, "deterministic": False, "infra_error": 1}, 0,
                           {"infra_error": 1, "no_verdict": 0}),
    "gave_up_infra":      ({"success": False, "done": True, "reason": "sim_crashed", "finalized": True, "gave_up": True, "infra_error": 1}, 0,
                           {"infra_error": 1, "gave_up": 1, "no_verdict": 0, "sim_crashed_on_call": 0}),
    "gave_up_on_call":    ({"success": False, "done": True, "reason": "sim_crashed_on_call", "finalized": True, "gave_up": True}, 0,
                           {"infra_error": 0, "gave_up": 1, "no_verdict": 0, "sim_crashed_on_call": 1, "grader_error": 0}),
    "pass_but_infra_flag": ({**FULL, "infra_error": 1}, 0, {"infra_error": 1}),
}
bad = 0
for bench in ("labutopia", "autobio"):
    g = os.path.join(ROOT, "scripts", bench, "shared/standard/grade.py")
    for name, (content, want, flags) in CASES.items():
        with tempfile.TemporaryDirectory() as tmp:
            data, log = os.path.join(tmp, "data"), os.path.join(tmp, "log"); os.makedirs(data)
            if content is not None:
                open(os.path.join(data, "final.json"), "w").write(content if isinstance(content, str) else json.dumps(content))
            open(os.path.join(data, "trajectory.npz"), "wb").write(b"x")
            r = subprocess.run([sys.executable, "-B", g], env={**os.environ, "RCB_DATA": data, "RCB_VERIFIER_LOG_DIR": log},
                               capture_output=True, text=True)
            try:
                got = open(os.path.join(log, "reward.txt")).read().strip()
                out = json.load(open(os.path.join(log, "reward.json")))
            except Exception as exc:
                print(f"FAIL {bench} {name}: no reward ({exc!r}); rc {r.returncode}; {r.stderr[-300:]}"); bad += 1; continue
            errs = []
            if got != str(want): errs.append(f"reward.txt {got} != {want}")
            if out.get("success") != want: errs.append(f"success {out.get('success')}")
            errs += [f"{k}={out.get(k)!r} (want {v})" for k, v in flags.items() if out.get(k) != v]
            errs += [f"non-numeric {k}" for k, v in out.items() if isinstance(v, bool) or not isinstance(v, (int, float))]
            if "deterministic" not in out or "infra_error" not in out or "grader_error" not in out: errs.append("missing MUST key")
            if content is not None and name not in ("corrupt", "empty_file", "not_object", "bad_field_type") and not os.path.exists(os.path.join(log, "trajectory.npz")):
                errs.append("evidence not copied")
            print(("FAIL" if errs else "ok  "), bench, name, "; ".join(errs)); bad += bool(errs)
print("ALL PASS" if not bad else f"{bad} FAILED"); sys.exit(bool(bad))
