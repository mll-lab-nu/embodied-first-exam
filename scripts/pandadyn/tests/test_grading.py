"""Panda Dynamic Scenes grading without a simulator.

Privileged (template/privileged/tests/grade.py, the file the tasks ship, unedited except its time constants in the time-out
case): the grader run on trajectory files with a stand-in for the tooling (stub_tool.py, copied next to it as
rcb_pandadyn.py). Two fresh-process replays decide: reward 1 iff both succeed, end in the same state and rebuilt the
frozen start; a replay without a result, out of its time, or one that rebuilt another start is the verifier's failure
(`grader_error` = `infra_error` = 1); a file that is not a trajectory of the task is the agent's 0; the video never decides.

Standard and standard-realtime (since board 0153 one adapter, template/realtime/environment/sim/server.py, on the shared
service layer scripts/humanoidbench/shared/standard/rcb_service.py, whose grader and finalize the HumanoidBench tests
cover): the adapter is read, not run (it needs SAPIEN): no verify() (a grading replay), the frozen start as start_sha, a
reset(), a live_verdict() that never returns a "success", no processes started; and the standard twins' copy
(mk_tasks.std_adapter) is the same code under its own docstring. Needs numpy (the privileged grader reads the npz)."""
import json, os, shutil, subprocess, sys, tempfile
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PRIV = os.path.join(HERE, "..", "template", "privileged", "tests", "grade.py")
GOOD = {"task": "S00-Stub", "actions": np.zeros((5, 8))}
INSTANCE = {"task": "S00-Stub", "action_dim": 8}
# name: (trajectory entries (None: no file; a str: raw bytes), STUB_PLAN, want reward, want reward.json subset, replay processes)
PRIV_CASES = {
    "both replays succeed in the same state": (GOOD, "ok,ok", 1, {"success": 1, "all_success": 1, "deterministic": 1, "instance_ok": 1, "replays": 2,
                                                                 "grader_error": 0, "infra_error": 0, "video_rendered": 1, "n_actions": 5}, 3),
    "one replay fails": (GOOD, "ok,fail", 0, {"success": 0, "all_success": 0, "deterministic": 1, "grader_error": 0, "infra_error": 0}, 3),
    "the replays end in different states": (GOOD, "ok,diff", 0, {"success": 0, "all_success": 1, "deterministic": 0, "infra_error": 0}, 3),
    "a replay rebuilt another start": (GOOD, "ok,mismatch", 0, {"success": 0, "instance_ok": 0, "grader_error": 1, "infra_error": 1,
                                                                 "video_rendered": 0}, 2),
    "a replay process dies": (GOOD, "ok,die", 0, {"success": 0, "replay_failed": 1, "grader_error": 1, "infra_error": 1}, 2),
    "a replay prints no result": (GOOD, "error,ok", 0, {"success": 0, "replay_failed": 1, "grader_error": 1, "infra_error": 1}, 2),
    "a replay runs out of its time": (GOOD, "sleep", 0, {"success": 0, "replay_timed_out": 1, "grader_error": 1, "infra_error": 1}, 1),
    "the verdict stands without a video": (GOOD, "novideo", 1, {"success": 1, "video_rendered": 0, "infra_error": 0}, 3),
    "no trajectory": (None, "ok", 0, {"success": 0, "missing_trajectory": 1, "grader_error": 0, "infra_error": 0}, 0),
    "another task's trajectory": ({**GOOD, "task": "S99-Other"}, "ok", 0, {"success": 0, "wrong_task": 1, "infra_error": 0}, 0),
    "a wrong row width": ({"task": "S00-Stub", "actions": np.zeros((5, 16))}, "ok", 0, {"success": 0, "bad_trajectory": 1, "infra_error": 0}, 0),
    "more rows than a trajectory may have": ({"task": "S00-Stub", "actions": np.zeros((4501, 8))}, "ok", 0, {"success": 0, "bad_trajectory": 1}, 0),
    "a NaN": ({"task": "S00-Stub", "actions": np.full((5, 8), np.nan)}, "ok", 0, {"success": 0, "bad_trajectory": 1}, 0),
    "not an npz": ("not an npz", "ok", 0, {"success": 0, "bad_trajectory": 1, "infra_error": 0}, 0),
    "no actions entry": ({"task": "S00-Stub"}, "ok", 0, {"success": 0, "bad_trajectory": 1}, 0),
}
def check(name, got_reward, out, want_reward, want) -> list:
    bad = [] if got_reward == want_reward else [f"reward {got_reward} != {want_reward}"]
    bad += [f"{k}={out.get(k)} (want {v})" for k, v in want.items() if out.get(k) != v]
    if any(not isinstance(v, (int, float)) or isinstance(v, bool) for v in out.values()):
        bad.append("reward.json has a non-numeric field")
    return [f"{name}: {b}" for b in bad]


def run_priv(name, traj, plan, want_reward, want, n_proc) -> list:
    with tempfile.TemporaryDirectory() as td:
        tests, logs = os.path.join(td, "tests"), os.path.join(td, "logs")
        os.makedirs(tests); os.makedirs(logs)
        grader = open(PRIV).read()
        if plan == "sleep":                    # the grader's time constants, small for this case
            grader = grader.replace("REPLAY_STARTUP_S, REPLAY_MIN_RATE = 300.0, 10.0", "REPLAY_STARTUP_S, REPLAY_MIN_RATE = 2.0, 1e9")
            assert "1e9" in grader
        open(os.path.join(tests, "grade.py"), "w").write(grader)
        shutil.copy(os.path.join(HERE, "stub_tool.py"), os.path.join(tests, "rcb_pandadyn.py"))
        json.dump(INSTANCE, open(os.path.join(tests, "instance.json"), "w"))
        path = os.path.join(td, "trajectory.npz")
        if isinstance(traj, str):
            open(path, "w").write(traj)
        elif traj is not None:
            np.savez(path, **{k: (np.array(v) if isinstance(v, str) else v) for k, v in traj.items()})
        env = {**os.environ, "RCB_VERIFIER_LOG_DIR": logs, "STUB_PLAN": plan, "STUB_STATE": os.path.join(td, "n")}
        subprocess.run([sys.executable, os.path.join(tests, "grade.py"), "--instance", os.path.join(tests, "instance.json"), "--traj", path,
                        "--repeat", "2"], env=env, capture_output=True, timeout=120)
        out = json.load(open(os.path.join(logs, "reward.json")))
        bad = check(name, int(open(os.path.join(logs, "reward.txt")).read()), out, want_reward, want)
        n = int(open(os.path.join(td, "n")).read()) if os.path.exists(os.path.join(td, "n")) else 0
        if n != n_proc:
            bad.append(f"{name}: {n} replay processes, want {n_proc}")
        return bad


RT_ADAPTER = os.path.join(HERE, "..", "template", "realtime", "environment", "sim", "server.py")


def check_rt_adapter() -> list:
    """The standard-realtime adapter on the shared layer (rcb_service.Sim; it needs SAPIEN to run, so read, not run): no
    verify() (the layer grades the live episode and replays nothing), the frozen start as start_sha, and a live_verdict()
    that never returns a "success" (the task's check already is the episode's end)."""
    import ast
    tree = ast.parse(open(RT_ADAPTER).read())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "PandaDyn")
    funcs = {f.name: f for f in cls.body if isinstance(f, ast.FunctionDef)}
    bad = []
    if "verify" in funcs:
        bad.append("realtime adapter: has verify() (a grading replay)")
    if "reset" not in funcs:
        bad.append("realtime adapter: no reset() (both standard modes have a reset budget)")
    if not any(isinstance(n, ast.Attribute) and n.attr == "start_sha" and isinstance(n.ctx, ast.Store) for n in ast.walk(funcs["__init__"])):
        bad.append("realtime adapter: sets no start_sha (the frozen start is not checked)")
    lv = funcs.get("live_verdict")
    if lv is None or any(isinstance(n, ast.Constant) and n.value == "success" for n in ast.walk(lv)):
        bad.append("realtime adapter: live_verdict() missing or returns a success")
    if any(isinstance(n, (ast.Import, ast.ImportFrom)) and any(a.name == "subprocess" for a in n.names) for n in ast.walk(tree)):
        bad.append("realtime adapter: starts processes (a fresh-process replay)")
    return bad


def check_std_adapter() -> list:
    """The standard twins' adapter is the realtime one's code under another docstring (mk_tasks.std_adapter)."""
    sys.path.insert(0, os.path.join(HERE, ".."))
    import mk_tasks
    std, rt = mk_tasks.std_adapter().decode(), open(RT_ADAPTER).read()
    body = lambda t: t[t.index('"""', 3) + 4:]   # noqa: E731 -- the module without its docstring
    bad = [] if body(std) == body(rt) else ["standard adapter: its code differs from the realtime adapter's"]
    if "eai-standard/2.1" not in std[:300] or "rcb_realtime" in std[:std.index('"""', 3)].split("Settings")[-1]:
        bad.append("standard adapter: its docstring is not the standard one")
    return bad


def main() -> int:
    bad = check_rt_adapter() + check_std_adapter()
    for name, case in PRIV_CASES.items():
        bad += run_priv("privileged: " + name, *case)
    for b in bad:
        print("FAIL", b)
    n = len(PRIV_CASES)
    print(f"{n - len({b.split(':')[0] + ':' + b.split(':')[1] for b in bad})} / {n} cases pass" if bad else
          f"{len(PRIV_CASES)} privileged grading cases pass; the standard modes' adapter replays nothing, resets, and both "
          "twins carry the same code")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
