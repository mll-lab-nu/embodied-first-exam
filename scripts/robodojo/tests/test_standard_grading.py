"""RoboDojo standard grading, end to end without a simulator: the collect hook (template/standard/environment/sim/
finalize.sh, with stand-ins for `rcb_limited.py end` and `live_video.py encode`, RCB_SRV) writes final.json, then the
standard grader (template/standard/tests/grade.py) scores it. Graded by the LIVE episode since 2026-10-17 (owner, board
0151): success = live success, the same rule for every task (one fresh-process replay decided before, except for the
tasks graded by verdict); no case may start a replay (RCB_TOOL records any call), and final.json / reward.json carry no
replay fields. Also: the hook's budget is task.toml's [[verifier.collect]] timeout_sec, and the `main` kill hook runs
before the sim's. Standard library only."""
import json, os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); TPL = os.path.join(HERE, "..", "template", "standard")
EP = {"success": True, "steps": 5, "calls": 2, "control_steps": 5, "physics_steps": 50, "elapsed_s": 9.0, "reason": "success",
      "task": "t", "protocol": "eai-standard/2.2", "n_actions": 5, "live_sha": "aa", "sim_startups": 1, "resumes": 0,
      "instance_exact": True, "instance_checked": True, "determinism_verdict_mode": False}
FAILED = {**EP, "success": False, "reason": "failed_check", "live_sha": "zz"}
GAVE_UP = {**EP, "success": False, "done": True, "finalized": True, "gave_up": True}
LIVE = {"finalized": True, "graded_by": "live", "replays": 0}
# name: (env, episode.json (None: none), final.json before the hook (None: the service's copy of the episode), want final subset, want reward, want reward.json subset)
CASES = {
    "live success": ({}, EP, None, {**LIVE, "success": True, "live_success": True, "video": True, "video_pending": False, "video_source": "live"},
                     1, {"success": 1, "live_success": 1, "graded_by_live": 1, "replays": 0, "infra_error": 0, "grader_error": 0, "video_rendered": 1,
                         "instance_exact": 1, "n_actions": 5}),
    "live failure (a failed check)": ({}, FAILED, None, {**LIVE, "success": False}, 0, {"success": 0, "infra_error": 0, "ended_failed_check": 1}),
    "live failure at the cutoff": ({}, {**EP, "success": False, "reason": "timeout"}, None, {**LIVE, "success": False}, 0, {"success": 0, "infra_error": 0}),
    "step guard": ({}, {**EP, "success": False, "reason": "step_guard"}, None, {**LIVE}, 0, {"success": 0, "infra_error": 0, "ended_step_guard": 1}),
    "a simulator error in a call is the agent's 0": ({}, {**EP, "success": False, "reason": "error"}, None, {**LIVE}, 0, {"success": 0, "infra_error": 0, "sim_error": 1}),
    "graded by verdict: live success": ({}, {**EP, "determinism_verdict_mode": True, "instance_exact": False, "instance_checked": False}, None,
                                        {**LIVE, "success": True}, 1, {"success": 1, "determinism_verdict_mode": 1, "infra_error": 0}),
    "graded by verdict: live failure": ({}, {**FAILED, "determinism_verdict_mode": True}, None, {**LIVE, "success": False}, 0, {"success": 0, "infra_error": 0}),
    "the video fails: the verdict stands": ({"STUB_VIDEO": "fail"}, EP, None, {**LIVE, "success": True, "video": False, "video_pending": False},
                                            1, {"success": 1, "video_rendered": 0, "infra_error": 0}),
    "the encode crashes: the verdict stands": ({"STUB_VIDEO": "crash"}, EP, None, {**LIVE, "success": True, "video": False}, 1, {"success": 1, "infra_error": 0}),
    "the encode hangs: the verdict stands": ({"STUB_VIDEO": "sleep", "RCB_VIDEO_LIMIT_S": "30"}, EP, None, {**LIVE, "success": True, "video": False},
                                             1, {"success": 1, "infra_error": 0}),
    "no episode.json is infra": ({}, None, None, {**LIVE, "success": False, "infra_error": 1}, 0, {"success": 0, "infra_error": 1}),
    "dumped but not exited: the live record decides": ({"STUB_END_RC": "1"}, EP, None, {**LIVE, "success": True, "service_exit_timed_out": True},
                                                        1, {"success": 1, "infra_error": 0}),
    "the service never ended is infra": ({"STUB_END_RC": "1"}, None, None, {**LIVE, "success": False, "infra_error": 1}, 0, {"success": 0, "infra_error": 1, "finalized": 1}),
    "a give-up after crashes between calls is infra": ({"STUB_END_RC": "2"}, None, {**GAVE_UP, "reason": "sim_crashed", "infra_error": 1},
                                                       {"gave_up": True, "infra_error": 1}, 0, {"success": 0, "infra_error": 1, "gave_up": 1}),
    "a crash inside the agent's calls is its 0": ({"STUB_END_RC": "2"}, None, {**GAVE_UP, "reason": "sim_crashed_on_call"}, {"gave_up": True, "success": False},
                                                  0, {"success": 0, "infra_error": 0, "sim_crashed_on_call": 1}),
    "an instance mismatch at the start is infra": ({"STUB_END_RC": "2"}, None, {"task": "t", "instance_mismatch": True, "instance_exact": False, "success": False,
                                                                                 "done": True, "reason": "instance_mismatch: x", "finalized": True, "gave_up": True, "infra_error": 1},
                                                   {"instance_mismatch": True, "infra_error": 1}, 0, {"success": 0, "infra_error": 1, "instance_mismatch": 1}),
}
src_path = os.path.join(TPL, "environment", "sim", "finalize.sh"); src = open(src_path).read()
grade = os.path.join(TPL, "tests", "grade.py"); bad = 0
code = src.split("set -u", 1)[1]
if "RCB_TOOL" in code or " replay " in code or "replay1" in code:
    print("FAIL finalize.sh still runs a replay"); bad += 1
toml = open(os.path.join(TPL, "task.toml.tmpl")).read()
hook_budget = src.split('HOOK_BUDGET_S="${RCB_COLLECT_TIMEOUT_S:-', 1)[1].split("}", 1)[0]
if f"timeout_sec = {hook_budget} " not in toml.split('command = "sh /srv/finalize.sh"', 1)[1].split("[agent]", 1)[0]:
    print(f"FAIL finalize.sh HOOK_BUDGET_S {hook_budget} is not task.toml.tmpl's [[verifier.collect]] timeout_sec"); bad += 1
if not (0 <= toml.find('service = "main"\ncommand = "kill -9 -1 2>/dev/null; exit 0"') < toml.find('service = "sim"\ncommand = "sh /srv/finalize.sh"')):
    print("FAIL task.toml.tmpl: the main kill hook must come before the sim's"); bad += 1
for name, (env, ep, fin0, want_fin, want_reward, want_rj) in CASES.items():
    with tempfile.TemporaryDirectory() as td:
        data, log, bindir, srv = (os.path.join(td, x) for x in ("data", "log", "bin", "srv"))
        for x in (data, bindir, srv): os.makedirs(x)
        os.symlink(sys.executable, os.path.join(bindir, "python"))
        os.symlink(os.path.join(HERE, "stub_end.py"), os.path.join(srv, "rcb_limited.py"))
        os.symlink(os.path.join(HERE, "stub_video.py"), os.path.join(srv, "live_video.py"))
        tool = os.path.join(td, "tool.py"); open(tool, "w").write(f"open({os.path.join(data, 'tool_called')!r}, 'w').write('x')\n")
        json.dump(fin0 if fin0 is not None else {**(ep or EP), "done": True, "finalized": False}, open(os.path.join(data, "final.json"), "w"))
        if ep is not None: json.dump(ep, open(os.path.join(data, "episode.json"), "w"))
        open(os.path.join(data, "trajectory.npz"), "w").write("x")
        e = {"PATH": bindir + ":/usr/bin:/bin", "RCB_DATA": data, "RCB_SRV": srv, "RCB_TOOL": tool, "RCB_TASK": "t", "RCB_INSTANCE": "i", **env}
        try:
            p = subprocess.run(["sh", src_path], env=e, capture_output=True, text=True, timeout=240, start_new_session=True)
        except subprocess.TimeoutExpired:
            print("FAIL", name, "; the hook did not finish in 240 s"); bad += 1
            continue
        g = subprocess.run([sys.executable, "-I", grade], env={"RCB_DATA": data, "RCB_VERIFIER_LOG_DIR": log, "PATH": e["PATH"]},
                           capture_output=True, text=True, timeout=60)
        errs = [] if p.returncode == 0 else [f"hook rc {p.returncode}: {p.stderr[-200:]}"]
        try:
            fin = json.load(open(os.path.join(data, "final.json")))
        except Exception as exc:  # noqa: BLE001
            fin = {}; errs.append(f"final.json unreadable {exc!r}")
        errs += [f"final {k}={fin.get(k)!r} (want {v!r})" for k, v in want_fin.items() if fin.get(k) != v]
        try:
            reward = int(open(os.path.join(log, "reward.txt")).read().strip()); rj = json.load(open(os.path.join(log, "reward.json")))
        except Exception as exc:  # noqa: BLE001
            reward, rj = None, {}; errs.append(f"no reward: {exc!r} {g.stderr[-300:]}")
        if reward != want_reward: errs.append(f"reward {reward} (want {want_reward})")
        errs += [f"reward.json {k}={rj.get(k)!r} (want {v!r})" for k, v in want_rj.items() if rj.get(k) != v]
        if not all(isinstance(v, (int, float)) for v in rj.values()): errs.append("reward.json has a non-numeric value")
        errs += [f"reward.json has no {k}" for k in ("success", "live_success", "graded_by_live", "replays", "infra_error", "grader_error", "finalized") if k not in rj]
        errs += [f"{k} reported" for k in ("replay_success", "deterministic", "state_identical") if k in rj or k in fin]
        if os.path.exists(os.path.join(data, "tool_called")): errs.append("a replay was started")
        if [f for f in os.listdir(data) if f.endswith(".tmp")]: errs.append("temporary file left behind")
        print(("FAIL" if errs else "ok  "), name, "; ".join(errs)); bad += bool(errs)
        if errs: print("   hook stdout:", p.stdout[-600:].replace("\n", " | "))
print("robodojo standard grading:", "ALL OK" if not bad else f"{bad} FAILED"); sys.exit(1 if bad else 0)
