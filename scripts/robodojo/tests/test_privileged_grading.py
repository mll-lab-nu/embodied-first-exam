"""RoboDojo privileged grading without a simulator: the verifier's grader (template/privileged/tests/grade.py) run on
trajectory files, with a stand-in for the tooling (stub_tool.py, copied next to the grader as rcb_robodojo.py: the grader
imports ACTION_DIM / MAX_ACTIONS from it and runs its `replay` CLI in a fresh process per replay).
ONE replay decides since 2026-10-12 (the owner's decision; two before, which also had to end in the same state):
- reward 1 iff the one replay succeeds; it is the filmed one, and a video that could not be written does not decide;
- nothing is compared, so `deterministic` = `state_identical` = 1 with `determinism_checked` = 0 and `replays` = 1;
- a replay whose process rebuilt the frozen layout to another state than the recorded hash gives no verdict
  (`instance_mismatch`: `grader_error` = `infra_error` = 1), whatever it ended in; a replay process without a result is
  the verifier's failure too (`replay_failed`); a file that is not a trajectory of the task is the agent's 0;
- `--repeat 2` is still the earlier check (both succeed and end in the same state; `instance_unstable` when the two
  started from different states), for a determinism measurement by hand.
The grader is the file the tasks ship, unedited. Needs numpy (the grader reads the npz)."""
import json, os, shutil, subprocess, sys, tempfile
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); TPL = os.path.join(HERE, "..", "template", "privileged")
GOOD = {"task": "t", "actions": np.zeros((5, 14), dtype=np.float32)}
# name: (trajectory entries (None: no file), --repeat, STUB_PLAN, want reward, want reward.json subset, replay processes run)
CASES = {
    "one replay succeeds": (GOOD, 1, "ok", 1, {"success": 1, "all_success": 1, "replay_success": 1, "deterministic": 1,
                                               "state_identical": 1, "determinism_checked": 0, "replays": 1, "instance_exact": 1,
                                               "instance_mismatch": 0, "grader_error": 0, "infra_error": 0, "video_rendered": 1,
                                               "n_actions": 5, "sim_steps": 5}, 1),
    "one replay fails": (GOOD, 1, "fail", 0, {"success": 0, "all_success": 0, "replay_success": 0, "deterministic": 1,
                                              "determinism_checked": 0, "grader_error": 0, "infra_error": 0, "ended_failed_check": 1}, 1),
    "the replay stands without its video": (GOOD, 1, "novideo", 1, {"success": 1, "video_rendered": 0, "infra_error": 0}, 1),
    "the replay stands with a part of a video": (GOOD, 1, "partvideo", 1, {"success": 1, "video_rendered": 0, "infra_error": 0}, 1),
    "the result, then a crash at shutdown": (GOOD, 1, "ok_crash", 1, {"success": 1, "infra_error": 0, "grader_error": 0}, 1),
    # past its time limit: the verifier's failure, never the agent's 0 (the grader's three constants set to 3 s for this case)
    "the replay runs out of its time": (GOOD, 1, "sleep", 0, {"success": 0, "replay_timed_out": 1, "grader_error": 1, "infra_error": 1,
                                                              "n_actions": 5}, 1),
    "the layout rebuilt to another state, the replay succeeded": (GOOD, 1, "inexact", 0,
                                                                  {"success": 0, "instance_mismatch": 1, "instance_exact": 0,
                                                                   "grader_error": 1, "infra_error": 1, "replay_success": 1}, 1),
    "the layout rebuilt to another state, the replay failed": (GOOD, 1, "inexact_fail", 0,
                                                               {"success": 0, "instance_mismatch": 1, "grader_error": 1, "infra_error": 1}, 1),
    "the replay process dies": (GOOD, 1, "die", 0, {"success": 0, "replay_failed": 1, "grader_error": 1, "infra_error": 1}, 1),
    "the replay prints an error": (GOOD, 1, "error", 0, {"success": 0, "replay_failed": 1, "grader_error": 1, "infra_error": 1}, 1),
    "no trajectory": (None, 1, "ok", 0, {"success": 0, "missing_trajectory": 1, "grader_error": 0, "infra_error": 0}, 0),
    "another task's trajectory": ({**GOOD, "task": "other"}, 1, "ok", 0, {"success": 0, "wrong_task": 1, "infra_error": 0}, 0),
    "a wrong shape": ({"task": "t", "actions": np.zeros((5, 13), dtype=np.float32)}, 1, "ok", 0,
                      {"success": 0, "bad_trajectory": 1, "grader_error": 0, "infra_error": 0}, 0),
    "more rows than a trajectory may have": ({"task": "t", "actions": np.zeros((15001, 14), dtype=np.float32)}, 1, "ok", 0,
                                             {"success": 0, "bad_trajectory": 1, "infra_error": 0}, 0),
    # the earlier two-replay check, still there behind --repeat 2
    "--repeat 2: both succeed in the same state": (GOOD, 2, "ok,ok", 1, {"success": 1, "deterministic": 1, "determinism_checked": 1, "replays": 2}, 2),
    "--repeat 2: both succeed in different states": (GOOD, 2, "ok,diff", 0, {"success": 0, "all_success": 1, "deterministic": 0,
                                                                             "state_identical": 0, "infra_error": 0}, 2),
    # with two replays that started from the same state, a layout that hashes differently from the record is reported only
    "--repeat 2: same start, not the recorded hash": (GOOD, 2, "inexact,inexact", 1, {"success": 1, "instance_exact": 0, "instance_mismatch": 0,
                                                                                      "infra_error": 0}, 2),
    "--repeat 2: the replays started from different states": (GOOD, 2, "inst2,inst2", 0,
                                                              {"success": 0, "instance_unstable": 1, "grader_error": 1, "infra_error": 1}, 2),
}
bad = 0
sh = open(os.path.join(TPL, "tests", "test.sh.tmpl")).read()
if "--repeat 1 " not in sh or "--repeat 2 \\" in sh:
    print("FAIL test.sh.tmpl does not run the grader with --repeat 1"); bad += 1
src = open(os.path.join(TPL, "tests", "grade.py")).read()
if 'ap.add_argument("--repeat", type=int, default=1)' not in src:
    print("FAIL grade.py's default is not one replay"); bad += 1
# [verifier] timeout_sec fits the one replay of the longest accepted trajectory, at the grader's own limit, plus 600 s
ns = {}
exec(src.split("def replay_timeout", 1)[0].split("LOG_DIR =", 1)[1].split("\n", 1)[1] + "def replay_timeout" +
     src.split("def replay_timeout", 1)[1].split("\n\n\n", 1)[0], ns)   # the three constants and replay_timeout()
toml = open(os.path.join(TPL, "task.toml.tmpl")).read()
declared = float(toml.split("[verifier]", 1)[1].split("timeout_sec =", 1)[1].split()[0])
if declared != ns["replay_timeout"](15000) + 600:
    print(f"FAIL [verifier] timeout_sec {declared} != replay_timeout(15000) + 600 = {ns['replay_timeout'](15000) + 600}"); bad += 1
for name, (traj, repeat, plan, want_reward, want_rj, want_calls) in CASES.items():
    with tempfile.TemporaryDirectory() as td:
        tests, log, out = (os.path.join(td, x) for x in ("tests", "log", "out")); os.makedirs(tests); os.makedirs(out)
        os.makedirs(log)                                   # test.sh makes /logs/verifier before the grader runs
        shutil.copy(os.path.join(TPL, "tests", "grade.py"), tests)
        if plan == "sleep":                                # the only edit of the grader, for this case: its time limit
            consts = "REPLAY_FLOOR_S, REPLAY_STARTUP_S, REPLAY_MIN_RATE = 1800.0, 1200.0, 2.5"
            assert src.count(consts) == 1
            open(os.path.join(tests, "grade.py"), "w").write(src.replace(consts, "REPLAY_FLOOR_S, REPLAY_STARTUP_S, REPLAY_MIN_RATE = 3.0, 3.0, 2.5"))
        shutil.copy(os.path.join(HERE, "stub_tool.py"), os.path.join(tests, "rcb_robodojo.py"))
        inst = os.path.join(tests, "instance.json"); json.dump({"task": "t", "state_sha": "ii"}, open(inst, "w"))
        tp = os.path.join(out, "trajectory.npz")
        if traj is not None: np.savez(tp, **traj)
        e = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "RCB_VERIFIER_LOG_DIR": log, "STUB_DIR": td, "STUB_PLAN": plan}
        g = subprocess.run([sys.executable, os.path.join(tests, "grade.py"), "--task", "t", "--instance", inst, "--traj", tp,
                            "--repeat", str(repeat)], env=e, capture_output=True, text=True, timeout=120)
        errs = [] if g.returncode == 0 else [f"grader rc {g.returncode}"]
        try:
            reward = int(open(os.path.join(log, "reward.txt")).read().strip()); rj = json.load(open(os.path.join(log, "reward.json")))
        except Exception as exc:  # noqa: BLE001
            reward, rj = None, {}; errs.append(f"no reward: {exc!r} {g.stderr[-300:]}")
        if reward != want_reward: errs.append(f"reward {reward} (want {want_reward})")
        errs += [f"reward.json {k}={rj.get(k)!r} (want {v!r})" for k, v in want_rj.items() if rj.get(k) != v]
        if not all(isinstance(v, (int, float)) for v in rj.values()): errs.append("reward.json has a non-numeric value")
        errs += [f"reward.json has no {k}" for k in ("success", "deterministic", "grader_error", "infra_error") if k not in rj]
        if rj.get("success") == 1 and (rj.get("infra_error") or rj.get("grader_error") or reward != 1):
            errs.append("success = 1 beside an infrastructure failure or reward 0")
        cf = os.path.join(td, "stub_calls"); calls = int(open(cf).read()) if os.path.exists(cf) else 0
        if calls != want_calls: errs.append(f"{calls} replay process(es) run (want {want_calls})")
        argv = [json.loads(l) for l in open(os.path.join(td, "stub_argv"))] if calls else []
        if calls and "--video" not in argv[-1]: errs.append("the last (with one replay: the only) replay was not filmed")
        print(("FAIL" if errs else "ok  "), name, "; ".join(errs)); bad += bool(errs)
        if errs: print("   grader stderr:", g.stderr[-600:].replace("\n", " | "))
print("robodojo privileged grading:", "ALL OK" if not bad else f"{bad} FAILED"); sys.exit(1 if bad else 0)
