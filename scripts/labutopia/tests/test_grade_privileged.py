"""Synthetic test of the privileged graders (LabUtopia, AutoBio) with a fake replay tool: deliverable defects are the
agent's 0 (bad_trajectory, never grader_error), a replay without a result is grader_error + infra_error, a reward is
always written, the time limits hold, and no byte in the agent's session log changes a verdict."""
import io, json, os, re, shutil, subprocess, sys, tempfile, time, zipfile
import numpy as np
ROOT, HERE = (sys.argv[1] if len(sys.argv) > 1 else os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))), os.path.dirname(os.path.abspath(__file__))
N = {"labutopia": 18, "autobio": 7}

def npz(path, **kw): np.savez(path, **kw)
def make(kind, path, n_act, fam, max_rows):
    A = np.zeros((20, n_act))
    if kind == "good": npz(path, actions=A, task=fam)
    elif kind == "no_task": npz(path, actions=A)                      # accepted: the family is the instance's
    elif kind == "missing": return
    elif kind == "not_npz": open(path, "wb").write(b"this is not a zip file")
    elif kind == "empty_file": open(path, "wb").write(b"")
    elif kind == "no_actions": npz(path, task=fam, rows=A)
    elif kind == "object_array": np.savez(path, actions=np.array([{"a": 1}, None], dtype=object), task=fam)
    elif kind == "object_extra": np.savez(path, actions=A, task=fam, extra=np.array([{"a": 1}], dtype=object))
    elif kind == "string_actions": npz(path, actions=np.array(["a", "b"]), task=fam)
    elif kind == "wrong_family": npz(path, actions=A, task="another_family")
    elif kind == "wrong_width": npz(path, actions=np.zeros((20, n_act + 1)), task=fam)
    elif kind == "one_dim": npz(path, actions=np.zeros(20), task=fam)
    elif kind == "zero_rows": npz(path, actions=np.zeros((0, n_act)), task=fam)
    elif kind == "nan": npz(path, actions=np.full((20, n_act), np.nan), task=fam)
    elif kind == "too_long": npz(path, actions=np.zeros((max_rows + 1, n_act), dtype=np.float32), task=fam)
    elif kind == "truncated_zip":
        b = io.BytesIO(); np.savez(b, actions=A, task=fam); open(path, "wb").write(b.getvalue()[:150])
    else: raise KeyError(kind)

# name: (deliverable, env, expected reward, expected flags)
CASES = {
    "pass":         ("good", {}, 1, {"grader_error": 0, "infra_error": 0, "deterministic": 1, "video_rendered": 1}),
    "pass_no_task": ("no_task", {}, 1, {"grader_error": 0, "infra_error": 0}),
    "pass_object_extra": ("object_extra", {}, 1, {"grader_error": 0}),   # only actions / task are read; the rest never crosses
    # the agent's session log (self-reported cost) with bytes that are not UTF-8, a NUL and a 1 MB line (where the count stops): never an error
    "pass_bad_log": ("good", {}, 1, {"grader_error": 0, "infra_error": 0, "deterministic": 1, "agent_sessions": 2, "agent_resets": 1}),
    "missing_bad_log": ("missing", {}, 0, {"missing_trajectory": 1, "grader_error": 0, "infra_error": 0, "agent_sessions": 2}),
    "fail":         ("good", {"FAKE_MODE": "fail"}, 0, {"grader_error": 0, "infra_error": 0, "deterministic": 1, "replay_success": 0}),
    "missing":      ("missing", {}, 0, {"missing_trajectory": 1, "grader_error": 0, "infra_error": 0, "deterministic": 0}),
    "not_npz":      ("not_npz", {}, 0, {"bad_trajectory": 1, "grader_error": 0, "infra_error": 0, "deterministic": 0}),
    "empty_file":   ("empty_file", {}, 0, {"bad_trajectory": 1, "grader_error": 0}),
    "truncated_zip": ("truncated_zip", {}, 0, {"bad_trajectory": 1, "grader_error": 0}),
    "no_actions":   ("no_actions", {}, 0, {"bad_trajectory": 1, "grader_error": 0}),
    "object_array": ("object_array", {}, 0, {"bad_trajectory": 1, "grader_error": 0}),
    "string_actions": ("string_actions", {}, 0, {"bad_trajectory": 1, "grader_error": 0}),
    "wrong_family": ("wrong_family", {}, 0, {"wrong_family": 1, "grader_error": 0, "deterministic": 0}),
    "wrong_width":  ("wrong_width", {}, 0, {"bad_trajectory": 1, "grader_error": 0}),
    "one_dim":      ("one_dim", {}, 0, {"bad_trajectory": 1, "grader_error": 0}),
    "zero_rows":    ("zero_rows", {}, 0, {"bad_trajectory": 1, "grader_error": 0}),
    "nan":          ("nan", {}, 0, {"bad_trajectory": 1, "grader_error": 0}),
    "too_long":     ("too_long", {}, 0, {"bad_trajectory": 1, "too_long": 1, "grader_error": 0}),
    "replay_dies":  ("good", {"FAKE_MODE": "die"}, 0, {"grader_error": 1, "infra_error": 1, "replay_failed": 1, "replay_timed_out": 0, "deterministic": 0}),
    "replay_hangs": ("good", {"FAKE_MODE": "hang"}, 0, {"grader_error": 1, "infra_error": 1, "replay_failed": 1, "replay_timed_out": 1}),
    "result_then_crash": ("good", {"FAKE_MODE": "ok_crash"}, 1, {"grader_error": 0, "infra_error": 0}),
    "nondeterministic": ("good", {"FAKE_MODE": "sha"}, 0, {"grader_error": 0, "infra_error": 0, "deterministic": 0, "replay_success": 1}),
    "instance_mismatch": ("good", {"FAKE_MODE": "inst"}, 0, {"grader_error": 1, "infra_error": 1, "instance_ok": 0}),
    "video_dies":   ("good", {"FAKE_VIDEO": "die"}, 1, {"grader_error": 0, "video_rendered": 0}),
    "video_hangs":  ("good", {"FAKE_VIDEO": "hang"}, 1, {"grader_error": 0, "video_rendered": 0}),
}
BAD_LOG = b'{"ev": "session_start"}\n{"ev": "reset", "note": "\xff\xfe"}\n\x00\n{"ev": "session_start"}\n' + b"x" * 2**20 + b"\n"
bad = 0
for bench, n_act in N.items():
    src = open(os.path.join(ROOT, "scripts", bench, "shared/grade.py")).read()
    max_rows = int(re.search(r"^MAX_ROWS = ([\d_]+)", src, re.M).group(1).replace("_", ""))
    ver = int(re.search(r"^VERIFIER_TIMEOUT_S = (\d+)", src, re.M).group(1)); vd = int(re.search(r"^VERDICT_TIMEOUT_S = (\d+)", src, re.M).group(1))
    vid = int(re.search(r"^VIDEO_TIMEOUT_S = (\d+)", src, re.M).group(1)); mg = int(re.search(r"^MARGIN_S = (\d+)", src, re.M).group(1))
    print(f"{bench}: limits verifier {ver}, verdict 2 x {vd}, video <= {vid}, margin {mg}:", "ok" if 2 * vd + mg + 120 <= ver else "FAIL")
    bad += not (2 * vd + mg + 120 <= ver)
    with tempfile.TemporaryDirectory() as tmp:
        tests = os.path.join(tmp, "tests"); os.makedirs(tests)
        # the grader under test, with only its time limits shortened (3 s per verdict replay; the video: what is left of 127 s, at most 3 s)
        fast = src.replace(f"VERDICT_TIMEOUT_S = {vd}\n", "VERDICT_TIMEOUT_S = 3\n").replace(f"VIDEO_TIMEOUT_S = {vid}\n", "VIDEO_TIMEOUT_S = 123\n") \
                  .replace(f"VERIFIER_TIMEOUT_S = {ver}\n", "VERIFIER_TIMEOUT_S = 126\n").replace(f"MARGIN_S = {mg}\n", "MARGIN_S = 0\n")
        assert fast != src
        slog = os.path.join(tmp, "rcb_session_log.jsonl")        # the agent's log, read from here instead of /app/output
        fast = fast.replace('"/app/output/rcb_session_log.jsonl"', repr(slog)); assert repr(slog) in fast
        open(os.path.join(tests, "grade.py"), "w").write(fast)
        shutil.copy(os.path.join(HERE, "fake_priv_tool.py"), os.path.join(tests, f"rcb_{bench}.py"))
        inst = os.path.join(tests, "instance.json"); json.dump({"family": "fam", "n_action": n_act}, open(inst, "w"))
        for name, (kind, env, want, flags) in CASES.items():
            if name == "video_hangs":   # the video limit is what is left (>= 120 s to start at all): too slow for a unit test of the same code path as replay_hangs
                continue
            work = os.path.join(tmp, name); os.makedirs(work); traj = os.path.join(work, "trajectory.npz"); log = os.path.join(work, "log")
            make(kind, traj, n_act, "fam", max_rows)
            if os.path.exists(slog): os.remove(slog)
            if name.endswith("_bad_log"): open(slog, "wb").write(BAD_LOG)
            t0 = time.time()
            r = subprocess.run([sys.executable, "-B", os.path.join(tests, "grade.py"), "--instance", inst, "--traj", traj],
                               env={**os.environ, "RCB_VERIFIER_LOG_DIR": log, **env}, capture_output=True, text=True, timeout=300)
            errs = []
            try:
                got = int(open(os.path.join(log, "reward.txt")).read()); out = json.load(open(os.path.join(log, "reward.json")))
            except Exception as exc:
                print(f"FAIL {bench} {name}: no reward ({exc!r}); rc {r.returncode}; {r.stderr[-300:]}"); bad += 1; continue
            if got != want or out.get("success") != want: errs.append(f"reward {got}/{out.get('success')} != {want}")
            errs += [f"{k}={out.get(k)!r} (want {v})" for k, v in flags.items() if out.get(k) != v]
            errs += [f"non-numeric {k}" for k, v in out.items() if isinstance(v, bool) or not isinstance(v, (int, float))]
            errs += [f"missing {k}" for k in ("deterministic", "grader_error", "infra_error") if k not in out]
            print(("FAIL" if errs else "ok  "), bench, name, f"({time.time() - t0:.1f} s)", "; ".join(errs)); bad += bool(errs)
print("ALL PASS" if not bad else f"{bad} FAILED"); sys.exit(bool(bad))
