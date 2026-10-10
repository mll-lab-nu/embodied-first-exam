"""Synthetic test of the privileged graders (RoboLab, YAMLab) with a stand-in tooling module: every deliverable shape and
replay outcome -> reward.txt / reward.json; the time limits against the generated task.toml."""
import io, json, os, re, shutil, subprocess, sys, tempfile, zipfile
import numpy as np
sys.dont_write_bytecode = True
ROOT = (sys.argv[1] if len(sys.argv) > 1 else os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))); HERE = os.path.dirname(os.path.abspath(__file__))
def npz(path, **kw): np.savez(path, **kw)
def make(kind, path, fam, dim):
    A = np.zeros((20, dim), np.float32)
    if kind == "missing": return
    if kind == "good": npz(path, actions=A, task=fam)
    elif kind == "good_extra_object":                       # an extra pickled entry next to a valid trajectory
        np.savez(path, actions=A, task=fam, junk=np.array([{"a": 1}], dtype=object))
    elif kind == "text": open(path, "w").write("not an npz")
    elif kind == "empty": open(path, "w").close()
    elif kind == "npy": np.save(open(path, "wb"), A)
    elif kind == "no_task": npz(path, actions=A)
    elif kind == "no_actions": npz(path, task=fam)
    elif kind == "object_actions": np.savez(path, actions=np.array([[{"a": 1}] * dim], dtype=object), task=fam)
    elif kind == "object_task": np.savez(path, actions=A, task=np.array([{"a": 1}], dtype=object))
    elif kind == "string_actions": npz(path, actions=np.array([["x"] * dim]), task=fam)
    elif kind == "truncated_zip":
        b = io.BytesIO(); np.savez(b, actions=A, task=fam); open(path, "wb").write(b.getvalue()[:-40])
    elif kind == "corrupt_member":
        b = io.BytesIO(); np.savez(b, actions=np.random.rand(200, dim).astype(np.float32), task=fam); raw = bytearray(b.getvalue())
        i = raw.find(b"actions.npy") + 200; raw[i:i + 50] = b"\xff" * 50; open(path, "wb").write(bytes(raw))
    elif kind == "wrong_family": npz(path, actions=A, task="other_task")
    elif kind == "wrong_dim": npz(path, actions=np.zeros((20, dim + 1), np.float32), task=fam)
    elif kind == "one_d": npz(path, actions=np.zeros((20,), np.float32), task=fam)
    elif kind == "nan": A[3, 1] = np.nan; npz(path, actions=A, task=fam)
    elif kind == "too_long": npz(path, actions=np.zeros((100_001, dim), np.float32), task=fam)
    elif kind == "max_len": npz(path, actions=np.zeros((100_000, dim), np.float32), task=fam)
AG = {"deterministic": 0, "grader_error": 0, "infra_error": 0, "success": 0}
ERR = {"deterministic": 0, "grader_error": 1, "infra_error": 1, "success": 0}
CASES = {   # name: (deliverable, STUB_PLAN, tiny limits?, want reward, want subset, forbidden keys)
    "missing": ("missing", "ok", False, 0, {**AG, "missing_trajectory": 1}, ()),
    "text_file": ("text", "ok", False, 0, {**AG, "bad_trajectory": 1}, ()),
    "empty_file": ("empty", "ok", False, 0, {**AG, "bad_trajectory": 1}, ()),
    "npy_not_npz": ("npy", "ok", False, 0, {**AG, "bad_trajectory": 1}, ()),
    "no_task_key": ("no_task", "ok", False, 0, {**AG, "bad_trajectory": 1}, ()),
    "no_actions_key": ("no_actions", "ok", False, 0, {**AG, "bad_trajectory": 1}, ()),
    "object_actions": ("object_actions", "ok", False, 0, {**AG, "bad_trajectory": 1}, ()),
    "object_task": ("object_task", "ok", False, 0, {**AG, "bad_trajectory": 1}, ()),
    "string_actions": ("string_actions", "ok", False, 0, {**AG, "bad_trajectory": 1}, ()),
    "truncated_zip": ("truncated_zip", "ok", False, 0, {**AG, "bad_trajectory": 1}, ()),
    "corrupt_member": ("corrupt_member", "ok", False, 0, {**AG, "bad_trajectory": 1}, ()),
    "wrong_family": ("wrong_family", "ok", False, 0, {**AG, "wrong_family": 1}, ("bad_trajectory",)),
    "wrong_dim": ("wrong_dim", "ok", False, 0, {**AG, "bad_trajectory": 1, "n_actions": 20}, ()),
    "one_d": ("one_d", "ok", False, 0, {**AG, "bad_trajectory": 1, "n_actions": 0}, ()),
    "nan": ("nan", "ok", False, 0, {**AG, "bad_trajectory": 1}, ()),
    "too_long": ("too_long", "ok", False, 0, {**AG, "bad_trajectory": 1, "n_actions": 100_001}, ()),
    "max_len_accepted": ("max_len", "ok,ok", False, 1, {"success": 1, "n_actions": 100_000}, ("bad_trajectory",)),
    "pass": ("good", "ok,ok", False, 1, {"success": 1, "all_success": 1, "deterministic": 1, "instance_ok": 1, "grader_error": 0, "infra_error": 0,
                                         "n_actions": 20, "video_rendered": 1, "replay_timeout_s": 1800.0}, ("bad_trajectory",)),
    "pass_with_extra_object_entry": ("good_extra_object", "ok,ok", False, 1, {"success": 1}, ("bad_trajectory",)),
    "pass_isaac_crash_after_result": ("good", "crash_after,crash_after", False, 1, {"success": 1}, ()),
    "fail": ("good", "fail,fail", False, 0, {"success": 0, "all_success": 0, "deterministic": 1, "grader_error": 0, "infra_error": 0}, ()),
    "fail_one": ("good", "ok,fail", False, 0, {"success": 0, "all_success": 0, "grader_error": 0, "infra_error": 0}, ()),
    "nondeterministic": ("good", "ok,diff", False, 0, {"success": 0, "all_success": 1, "deterministic": 0, "grader_error": 0, "infra_error": 0}, ()),
    "instance_mismatch": ("good", "inst,inst", False, 0, {"success": 0, "all_success": 1, "instance_ok": 0, "grader_error": 1, "infra_error": 1}, ()),
    "replay_dies": ("good", "die", False, 0, {**ERR, "replay_failed": 1}, ("bad_trajectory",)),
    "replay2_dies": ("good", "ok,die", False, 0, {**ERR, "replay_failed": 1}, ()),
    "replay_times_out": ("good", "sleep", True, 0, {**ERR, "replay_timed_out": 1, "replay_timeout_s": 3.0, "n_actions": 20}, ()),
}
bad = 0
for bench, mod, dim in (("robolab", "rcb_robolab", 8), ("yamlab", "rcb_yamlab", 14)):
    fam = "fam_x"
    for name, (kind, plan, tiny, want_reward, want, forbid) in CASES.items():
        with tempfile.TemporaryDirectory() as td:
            tests, log, out = (os.path.join(td, x) for x in ("tests", "log", "out")); os.makedirs(tests); os.makedirs(out)
            shutil.copy(os.path.join(ROOT, "scripts", bench, "template/privileged/tests/grade.py"), os.path.join(tests, "grade.py"))
            shutil.copy(os.path.join(HERE, "stub_priv_tool.py"), os.path.join(tests, mod + ".py"))
            traj = os.path.join(out, "trajectory.npz"); make(kind, traj, fam, dim)
            env = {"PATH": "/usr/bin:/bin", "RCB_VERIFIER_LOG_DIR": log, "STUB_DIR": td, "STUB_PLAN": plan, "STUB_DIM": str(dim)}
            args = ["--family", fam, "--instance", "/nonexistent/instance.json", "--traj", traj, "--repeat", "2"]
            if tiny:      # the time-out path with the limits shrunk to 3 s (the stand-in sleeps 120 s)
                cmd = [sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); import grade; grade.REPLAY_FLOOR_S = 3.0; grade.REPLAY_STARTUP_S = 0.0; "
                       "sys.argv = ['grade.py'] + sys.argv[2:]; sys.exit(grade.main())", tests] + args
            else:
                cmd = [sys.executable, os.path.join(tests, "grade.py")] + args
            p = subprocess.run(cmd, env=env, capture_output=True, text=True, cwd=td)
            errs = []
            try:
                reward = int(open(os.path.join(log, "reward.txt")).read().strip()); rj = json.load(open(os.path.join(log, "reward.json")))
            except Exception as exc:
                print(f"FAIL {bench} {name}: no reward written ({exc!r}); rc {p.returncode}; {p.stderr[-400:]}"); bad += 1; continue
            if reward != want_reward: errs.append(f"reward {reward} (want {want_reward})")
            errs += [f"{k}={rj.get(k)!r} (want {v!r})" for k, v in want.items() if rj.get(k) != v]
            errs += [f"{k} present" for k in forbid if rj.get(k)]
            for k in ("success", "deterministic", "grader_error", "infra_error"):
                if k not in rj: errs.append(f"{k} missing")
            if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in rj.values()): errs.append("non-numeric reward.json")
            if p.returncode != 0: errs.append(f"rc {p.returncode}")
            print(("FAIL" if errs else "ok  "), bench, name, "; ".join(errs)); bad += bool(errs)
            if errs: print("   stderr:", p.stderr[-500:].replace("\n", " | "))
    # the time limits: two replays of the longest accepted trajectory fit the verifier's timeout
    sys.path.insert(0, os.path.join(ROOT, "scripts", bench, "template/privileged/tests")); sys.modules.pop("grade", None)
    import grade
    t = sorted(d for d in os.listdir(os.path.join(ROOT, "tasks")) if d.startswith(bench + "-") and d.endswith("-privileged"))
    vt = {float(re.search(r"^\[verifier\]\ntimeout_sec = ([0-9.]+)", open(os.path.join(ROOT, "tasks", d, "task.toml")).read(), re.M).group(1)) for d in t}
    lim = grade.replay_timeout(100_000); ok = len(vt) == 1 and 2 * lim + 300 <= min(vt) and grade.replay_timeout(0) == 1800.0
    print(("ok  " if ok else "FAIL"), bench, f"limits: replay_timeout(100k) = {lim:.0f} s, 2x + 300 <= verifier timeout {sorted(vt)} over {len(t)} tasks"); bad += not ok
    sys.path.pop(0)
    # the standard hook: task.toml's collect timeout == finalize.sh's HOOK_BUDGET_S default
    ts = sorted(d for d in os.listdir(os.path.join(ROOT, "tasks")) if d.startswith(bench + "-") and d.endswith("-standard"))
    budgets = set()
    for d in ts:
        hook = re.findall(r'^service = "sim"\ncommand = "sh /srv/finalize.sh".*\ntimeout_sec = (\d+)', open(os.path.join(ROOT, "tasks", d, "task.toml")).read(), re.M)
        assert len(hook) == 1, d
        sh = open(os.path.join(ROOT, "tasks", d, "environment/sim/finalize.sh")).read()
        budgets.add((int(hook[0]), int(re.search(r'HOOK_BUDGET_S="\$\{RCB_COLLECT_TIMEOUT_S:-(\d+)\}"', sh).group(1))))
    ok = len(budgets) == 1 and all(a == b for a, b in budgets)
    print(("ok  " if ok else "FAIL"), bench, f"collect timeout == HOOK_BUDGET_S: {sorted(budgets)} over {len(ts)} tasks"); bad += not ok
print("privileged grader:", "ALL OK" if not bad else f"{bad} FAILED"); sys.exit(1 if bad else 0)
