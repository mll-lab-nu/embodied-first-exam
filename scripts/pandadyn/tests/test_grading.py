"""Panda Dynamic Scenes grading without a simulator.

Privileged (template/privileged/tests/grade.py, the file the tasks ship, unedited except its time constants in the time-out
case): the grader run on trajectory files with a stand-in for the tooling (stub_tool.py, copied next to it as
rcb_pandadyn.py). Two fresh-process replays decide: reward 1 iff both succeed, end in the same state and rebuilt the
frozen start; a replay without a result, out of its time, or one that rebuilt another start is the verifier's failure
(`grader_error` = `infra_error` = 1); a file that is not a trajectory of the task is the agent's 0; the video never decides.

Standard (template/standard/tests/grade.py): the verifier run on final.json files: success = live ∧ replay ∧ deterministic,
no infrastructure error; a missing, unreadable or unfinished final.json, a replay error (which includes a replay that did
not rebuild the frozen start) or a lost GPU is `infra_error`; a give-up after crashes inside the agent's calls stays the
agent's 0. Needs numpy (the privileged grader reads the npz)."""
import json, os, shutil, subprocess, sys, tempfile
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PRIV = os.path.join(HERE, "..", "template", "privileged", "tests", "grade.py")
STD = os.path.join(HERE, "..", "template", "standard", "tests", "grade.py")
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
STD_CASES = {
    "success": ({"finalized": True, "success": True, "replay_success": True, "deterministic": True, "live_matches_replay": True,
                 "video": True, "phase": 5, "reason": "success"}, 1, {"success": 1, "live_success": 1, "replay_success": 1, "infra_error": 0,
                                                                     "phases_done": 5, "video_rendered": 1}),
    "live success, replay failure": ({"finalized": True, "success": True, "replay_success": False, "deterministic": True}, 0,
                                     {"success": 0, "infra_error": 0}),
    "nondeterministic": ({"finalized": True, "success": True, "replay_success": True, "deterministic": False}, 0, {"success": 0, "infra_error": 0}),
    "the task failed live": ({"finalized": True, "success": False, "replay_success": False, "deterministic": True, "reason": "limit_violation"}, 0,
                             {"success": 0, "limit_violation": 1, "infra_error": 0}),
    "the horizon": ({"finalized": True, "success": False, "replay_success": False, "deterministic": True, "reason": "timeout"}, 0,
                    {"success": 0, "timed_out": 1, "infra_error": 0}),
    "unfinished hook": ({"finalized": False, "success": True, "replay_success": True, "deterministic": True}, 0, {"success": 0, "infra_error": 1}),
    "a replay error": ({"finalized": True, "success": True, "replay_success": False, "deterministic": False, "replay_error": "replay 1 gave no result",
                        "infra_error": 1}, 0, {"success": 0, "replay_error": 1, "grader_error": 1, "infra_error": 1}),
    "a replay that rebuilt another start": ({"finalized": True, "success": True, "replay_success": True, "deterministic": True, "instance_mismatch": True,
                                             "replay_error": "replay [1] rebuilt a scene that differs", "infra_error": 1}, 0,
                                            {"success": 0, "instance_mismatch": 1, "infra_error": 1}),
    "the GPU lost": ({"finalized": True, "success": True, "gpu_lost": True, "infra_error": 1}, 0, {"success": 0, "gpu_lost": 1, "infra_error": 1}),
    "a give-up inside the agent's calls": ({"finalized": True, "success": False, "reason": "sim_crashed_on_call", "gave_up": True}, 0,
                                           {"success": 0, "sim_crashed_on_call": 1, "infra_error": 0}),
    "a give-up between calls": ({"finalized": True, "success": False, "reason": "sim_crashed", "gave_up": True, "infra_error": 1}, 0,
                                {"success": 0, "infra_error": 1}),
    "no final.json": (None, 0, {"success": 0, "missing_log": 1, "infra_error": 1}),
    "a truncated final.json": ("{\"success\": tr", 0, {"success": 0, "grader_error": 1, "infra_error": 1}),
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


def run_std(name, final, want_reward, want) -> list:
    with tempfile.TemporaryDirectory() as td:
        data, logs = os.path.join(td, "data"), os.path.join(td, "logs")
        os.makedirs(data); os.makedirs(logs)
        if isinstance(final, str):
            open(os.path.join(data, "final.json"), "w").write(final)
        elif final is not None:
            json.dump(final, open(os.path.join(data, "final.json"), "w"))
        env = {**os.environ, "RCB_VERIFIER_LOG_DIR": logs, "RCB_DATA": data}
        subprocess.run([sys.executable, STD], env=env, capture_output=True, timeout=60)
        out = json.load(open(os.path.join(logs, "reward.json")))
        return check(name, int(open(os.path.join(logs, "reward.txt")).read()), out, want_reward, want)


def main() -> int:
    bad = []
    for name, case in PRIV_CASES.items():
        bad += run_priv("privileged: " + name, *case)
    for name, case in STD_CASES.items():
        bad += run_std("standard: " + name, *case)
    for b in bad:
        print("FAIL", b)
    print(f"{len(PRIV_CASES) + len(STD_CASES) - len({b.split(':')[0] + ':' + b.split(':')[1] for b in bad})} / "
          f"{len(PRIV_CASES) + len(STD_CASES)} cases pass" if bad else f"{len(PRIV_CASES)} privileged + {len(STD_CASES)} standard grading cases pass")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
