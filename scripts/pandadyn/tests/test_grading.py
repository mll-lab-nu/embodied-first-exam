"""Panda Dynamic Scenes grading without a simulator.

Privileged (template/privileged/tests/grade.py, the file the tasks ship, unedited except its time constants in the time-out
case): the grader run on trajectory files with a stand-in for the tooling (stub_tool.py, copied next to it as
rcb_pandadyn.py). Two fresh-process replays decide: reward 1 iff both succeed, end in the same state and rebuilt the
frozen start; a replay without a result, out of its time, or one that rebuilt another start is the verifier's failure
(`grader_error` = `infra_error` = 1); a file that is not a trajectory of the task is the agent's 0; the video never decides.

Standard (template/standard/tests/grade.py), graded by the live episode (board 0151): the verifier run on final.json files:
success = the live episode's success, no infrastructure error; a missing, unreadable or unfinished final.json, an episode
the service did not dump, a refused start (instance_mismatch) or a give-up between calls is `infra_error`; a give-up after
crashes inside the agent's calls and a simulator error from a call stay the agent's 0. And the collect hook
(template/standard/environment/sim/finalize.sh) run with stand-ins for rcb_limited.py `end` and the tooling: it writes the
live verdict from episode.json, starts no replay, builds one scene for the video only after the verdict, and a failed or
slow video leaves the verdict as it was. Needs numpy (the privileged grader reads the npz)."""
import json, os, shutil, subprocess, sys, tempfile
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PRIV = os.path.join(HERE, "..", "template", "privileged", "tests", "grade.py")
STD = os.path.join(HERE, "..", "template", "standard", "tests", "grade.py")
HOOK = os.path.join(HERE, "..", "template", "standard", "environment", "sim", "finalize.sh")
STD_SERVER = os.path.join(HERE, "..", "template", "standard", "environment", "sim", "server.py")
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
LIVE = {"finalized": True, "graded_by": "live", "replays": 0}
STD_CASES = {
    "live success": ({**LIVE, "success": True, "live_success": True, "video": True, "video_matches_live": True, "phase": 5,
                      "reason": "success"}, 1, {"success": 1, "live_success": 1, "graded_by_live": 1, "replays": 0, "infra_error": 0,
                                                "phases_done": 5, "video_rendered": 1, "video_matches_live": 1}),
    "live failure": ({**LIVE, "success": False, "live_success": False, "reason": "drop"}, 0, {"success": 0, "infra_error": 0}),
    "the task failed live (a limit)": ({**LIVE, "success": False, "reason": "limit_violation"}, 0,
                                       {"success": 0, "limit_violation": 1, "infra_error": 0}),
    "the time was up": ({**LIVE, "success": False, "reason": "timeout"}, 0, {"success": 0, "timed_out": 1, "infra_error": 0}),
    "a simulator error from a call": ({**LIVE, "success": False, "reason": "error"}, 0, {"success": 0, "sim_error": 1, "infra_error": 0}),
    "a success recorded with a simulator error": ({**LIVE, "success": True, "live_success": True, "reason": "error"}, 0,
                                                  {"success": 0, "sim_error": 1, "infra_error": 0}),
    "no video: the verdict stands": ({**LIVE, "success": True, "video": False, "video_error": "x"}, 1,
                                     {"success": 1, "video_rendered": 0, "infra_error": 0}),
    "the video still pending: the verdict stands": ({**LIVE, "success": True, "video_pending": True}, 1, {"success": 1, "infra_error": 0}),
    "unfinished hook": ({"finalized": False, "success": True}, 0, {"success": 0, "finalized": 0, "infra_error": 1}),
    "finalized without a verdict": ({"finalized": True, "success": True}, 0, {"success": 0, "infra_error": 1}),
    "the episode not dumped": ({**LIVE, "success": False, "dump_error": "no episode.json", "infra_error": 1}, 0,
                               {"success": 0, "dump_error": 1, "infra_error": 1}),
    "a refused start": ({"finalized": True, "gave_up": True, "success": False, "reason": "instance_mismatch: a != b", "infra_error": 1},
                        0, {"success": 0, "instance_mismatch": 1, "infra_error": 1}),
    "a give-up inside the agent's calls": ({"finalized": True, "success": False, "reason": "sim_crashed_on_call", "gave_up": True}, 0,
                                           {"success": 0, "sim_crashed_on_call": 1, "infra_error": 0}),
    "a give-up between calls": ({"finalized": True, "success": False, "reason": "sim_crashed", "gave_up": True, "infra_error": 1}, 0,
                                {"success": 0, "infra_error": 1}),
    "no final.json": (None, 0, {"success": 0, "missing_log": 1, "infra_error": 1}),
    "a truncated final.json": ("{\"success\": tr", 0, {"success": 0, "grader_error": 1, "infra_error": 1}),
}
# The collect hook: (end's exit code, the service's final.json, episode.json (None: none), a trajectory, STUB_VIDEO, extra
# env, want reward, want reward.json subset, want final.json subset, scenes built (the video pass's only)).
EP = {"success": True, "reason": "success", "phase": 5, "live_sha": "L", "n_actions": 5, "control_steps": 5}
SERVICE = {"finalized": False, "success": False, "reason": None}
HOOK_CASES = {
    "live success": (0, SERVICE, EP, True, "ok", {}, 1, {"success": 1, "live_success": 1, "replays": 0, "video_rendered": 1,
                     "video_matches_live": 1, "infra_error": 0}, {"graded_by": "live", "replays": 0, "video": True,
                                                                   "video_pending": False, "state_sha": "L"}, 1),
    "live failure": (0, SERVICE, {**EP, "success": False, "reason": "drop", "phase": 2}, True, "ok", {}, 0,
                     {"success": 0, "live_success": 0, "infra_error": 0, "phases_done": 2}, {"success": False}, 1),
    "the filmed run ends elsewhere: decides nothing": (0, SERVICE, EP, True, "ok", {"STUB_VIDEO_SHA": "X"}, 1,
                     {"success": 1, "video_matches_live": 0}, {"video_matches_live": False}, 1),
    "the video fails: the verdict stands": (0, SERVICE, EP, True, "fail", {}, 1, {"success": 1, "video_rendered": 0, "infra_error": 0},
                     {"video": False, "video_pending": False, "success": True}, 1),
    "the video is too slow: the verdict stands": (0, SERVICE, EP, True, "sleep", {"RCB_COLLECT_TIMEOUT_S": "63", "RCB_VIDEO_MIN_S": "1"},
                     1, {"success": 1, "video_rendered": 0, "infra_error": 0}, {"video": False, "success": True}, 1),
    "a success dumped with a simulator error": (0, SERVICE, {**EP, "reason": "error"}, True, "ok", {}, 0,
                     {"success": 0, "live_success": 0, "sim_error": 1, "infra_error": 0}, {"success": False}, 1),
    "no episode.json": (0, SERVICE, None, True, "ok", {}, 0, {"success": 0, "dump_error": 1, "infra_error": 1}, {"finalized": True}, 0),
    "no trajectory": (0, SERVICE, EP, False, "ok", {}, 0, {"success": 0, "dump_error": 1, "infra_error": 1}, {"finalized": True}, 0),
    "the service never dumped the episode": (1, SERVICE, None, False, "ok", {}, 0, {"success": 0, "infra_error": 1}, {"finalized": True}, 0),
    "a give-up between calls": (2, {"finalized": True, "gave_up": True, "success": False, "reason": "sim_crashed", "infra_error": 1},
                                None, False, "ok", {}, 0, {"success": 0, "infra_error": 1}, {"reason": "sim_crashed"}, 0),
    "a give-up inside the agent's calls": (2, {"finalized": True, "gave_up": True, "success": False, "reason": "sim_crashed_on_call"},
                                           None, False, "ok", {}, 0, {"success": 0, "sim_crashed_on_call": 1, "infra_error": 0},
                                           {"graded_by": "live", "replays": 0}, 0),
    "a refused start": (2, {"finalized": True, "gave_up": True, "success": False, "reason": "instance_mismatch: a != b", "infra_error": 1},
                        None, False, "ok", {}, 0, {"success": 0, "instance_mismatch": 1, "infra_error": 1}, {"instance_mismatch": True}, 0),
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


STUB_END = """import os, sys
sys.exit(int(os.environ.get("STUB_END_RC", "0")) if len(sys.argv) > 1 and sys.argv[1] == "end" else 2)
"""
STUB_PIL = {"__init__.py": "", "Image.py": "class _I:\n    def save(self, path):\n        open(path, 'wb').write(b'png')\n\n\n"
                                         "def fromarray(a):\n    return _I()\n"}


def run_hook(name, rc, service, episode, traj, video, extra, want_reward, want, want_final, n_scenes) -> list:
    """finalize.sh on a scratch /srv and /data, then the standard grader on what it wrote."""
    with tempfile.TemporaryDirectory() as td:
        srv, data, logs, bin_ = (os.path.join(td, n) for n in ("srv", "data", "logs", "bin"))
        for x in (srv, data, logs, bin_, os.path.join(srv, "PIL")):
            os.makedirs(x)
        open(os.path.join(srv, "rcb_limited.py"), "w").write(STUB_END)
        shutil.copy(os.path.join(HERE, "stub_tool.py"), os.path.join(srv, "rcb_pandadyn.py"))
        for f, text in STUB_PIL.items():
            open(os.path.join(srv, "PIL", f), "w").write(text)
        os.symlink(sys.executable, os.path.join(bin_, "python"))          # finalize.sh runs `python`, as in the image
        json.dump(service, open(os.path.join(data, "final.json"), "w"))
        if episode is not None:
            json.dump(episode, open(os.path.join(data, "episode.json"), "w"))
        if traj:
            np.savez(os.path.join(data, "trajectory.npz"), task=np.array("S00-Stub"), actions=np.zeros((5, 8)))
        env = {**os.environ, "PATH": bin_ + os.pathsep + os.environ.get("PATH", ""), "RCB_DATA": data, "RCB_SRV": srv,
               "RCB_TOOL": os.path.join(srv, "rcb_pandadyn.py"), "RCB_INSTANCE": os.path.join(srv, "instance.json"),
               "STUB_END_RC": str(rc), "STUB_VIDEO": video, "STUB_SESSIONS": os.path.join(td, "sessions"),
               "STUB_REPLAYS": os.path.join(td, "replays"), "RCB_VERIFIER_LOG_DIR": logs, **extra}
        subprocess.run(["sh", HOOK], env=env, capture_output=True, timeout=120)
        subprocess.run([sys.executable, STD], env=env, capture_output=True, timeout=60)
        out = json.load(open(os.path.join(logs, "reward.json")))
        bad = check(name, int(open(os.path.join(logs, "reward.txt")).read()), out, want_reward, want)
        fin = json.load(open(os.path.join(data, "final.json")))
        bad += [f"final.json {k}={fin.get(k)!r} (want {v!r})" for k, v in want_final.items() if fin.get(k) != v]
        n = {f: int(open(os.path.join(td, f)).read()) if os.path.exists(os.path.join(td, f)) else 0 for f in ("replays", "sessions")}
        if n["replays"]:
            bad.append(f"{n['replays']} replay process(es) started (the verdict is the live episode's)")
        if n["sessions"] != n_scenes:
            bad.append(f"{n['sessions']} scene(s) built, want {n_scenes} (the video pass's only)")
        return [b if b.startswith(name) else f"{name}: {b}" for b in bad]


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
    if not any(isinstance(n, ast.Attribute) and n.attr == "start_sha" and isinstance(n.ctx, ast.Store) for n in ast.walk(funcs["__init__"])):
        bad.append("realtime adapter: sets no start_sha (the frozen start is not checked)")
    lv = funcs.get("live_verdict")
    if lv is None or any(isinstance(n, ast.Constant) and n.value == "success" for n in ast.walk(lv)):
        bad.append("realtime adapter: live_verdict() missing or returns a success")
    if any(isinstance(n, (ast.Import, ast.ImportFrom)) and any(a.name == "subprocess" for a in n.names) for n in ast.walk(tree)):
        bad.append("realtime adapter: starts processes (a fresh-process replay)")
    return bad


def check_std_finish() -> list:
    """The standard service's finish() (it needs SAPIEN to run the service, so it runs alone, on stubs): an episode ended
    by a simulator error is no success even when the task's check passes on the failed step's state (review of #309)."""
    import ast
    src = open(STD_SERVER).read()
    fn = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "finish")
    bad = []
    for reason, want in (("error", False), ("timeout", True)):
        E = {"done": False, "success": False, "step": 0, "t0": 0.0}
        ns = {"E": E, "time": __import__("time"), "ctrl_steps": lambda: 0, "check_success": lambda: True,
              "log": lambda ev: None, "dump": lambda: None, "S": type("S", (), {"u": type("U", (), {"phase": 5})()})()}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), STD_SERVER, "exec"), ns)
        ns["finish"](reason)
        if bool(E["success"]) != want:
            bad.append(f"standard service: finish({reason!r}) with the task's check passing gives success {E['success']}")
    return bad


def main() -> int:
    bad = check_rt_adapter() + check_std_finish()
    for name, case in PRIV_CASES.items():
        bad += run_priv("privileged: " + name, *case)
    for name, case in STD_CASES.items():
        bad += run_std("standard: " + name, *case)
    for name, case in HOOK_CASES.items():
        bad += run_hook("collect hook: " + name, *case)
    for b in bad:
        print("FAIL", b)
    n = len(PRIV_CASES) + len(STD_CASES) + len(HOOK_CASES)
    print(f"{n - len({b.split(':')[0] + ':' + b.split(':')[1] for b in bad})} / {n} cases pass" if bad else
          f"{len(PRIV_CASES)} privileged + {len(STD_CASES)} standard grading + {len(HOOK_CASES)} collect-hook cases pass, "
          "and the realtime adapter replays nothing")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
