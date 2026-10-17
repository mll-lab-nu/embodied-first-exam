"""AM-Bench standard grading, end to end without a simulator: the collect hook (template/standard/environment/sim/
finalize.sh, with stand-ins for `rcb_limited.py end` (RCB_SRV) and the tooling's `film` / count_gpu_faults (RCB_TOOL))
writes final.json, then the standard grader (template/standard/tests/grade.py) scores it. Graded by the LIVE episode since
2026-10-17 (owner, board 0151): success = live success; the one film pass after the verdict never decides; no case may
replay (the stand-in records any other command); final.json / reward.json carry no replay fields. Also: the hook's budget
is task.toml's [[verifier.collect]] timeout_sec and holds the end wait + the film, and the `main` kill hook runs before
the sim's. Standard library only."""
import json, os, re, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); TPL = os.path.join(HERE, "..", "template", "standard")
EP = {"success": True, "steps": 5, "calls": 2, "control_steps": 5, "physics_steps": 5, "elapsed_s": 9.0, "reason": "success",
      "task": "t", "protocol": "eai-standard/2.2", "n_actions": 5, "hold_pad_rows": 0, "live_sha": "aa", "sim_startups": 1, "resumes": 0,
      "instance_exact": True, "instance_matches": True, "determinism_verdict_mode": False}
GAVE_UP = {**EP, "success": False, "done": True, "finalized": True, "gave_up": True}
LIVE = {"finalized": True, "graded_by": "live", "replays": 0}
FAULT = "2026 [Error] PhysX error: GPU solver fail to launch (stub)\n"
MARK = "[rcb] the episode's physics starts (live_gpu_faults are counted from here)\n"
DIED = "[sim] service exited (1): leaving, so compose restarts the container\n"
# name: (env, episode.json, final.json before the hook (None: the service's copy), server.log, want final subset, want reward, want reward.json subset)
CASES = {
    "live success": ({}, EP, None, "", {**LIVE, "success": True, "live_success": True, "video": True, "video_pending": False, "video_source": "render",
                                         "live_gpu_faults": 0}, 1, {"success": 1, "live_success": 1, "graded_by_live": 1, "replays": 0, "infra_error": 0,
                                                                    "video_rendered": 1, "hold_pad_rows": 0}),
    "live failure at the task's time-out": ({}, {**EP, "success": False, "reason": "episode_timeout"}, None, "", {**LIVE, "success": False}, 0,
                                            {"success": 0, "infra_error": 0, "episode_timeout": 1}),
    "live failure at the cutoff": ({}, {**EP, "success": False, "reason": "time_up"}, None, "", {**LIVE}, 0, {"success": 0, "infra_error": 0, "time_up": 1}),
    "graded by verdict: live success": ({}, {**EP, "determinism_verdict_mode": True}, None, "", {**LIVE, "success": True}, 1, {"success": 1, "determinism_verdict_mode": 1}),
    "a simulator error in a call is the agent's 0": ({}, {**EP, "success": False, "reason": "error"}, None, "", {**LIVE}, 0, {"success": 0, "infra_error": 0, "sim_error": 1}),
    "live GPU faults are infra (a success too)": ({}, EP, None, FAULT * 2, {**LIVE, "infra_error": 1, "live_gpu_faults": 2}, 0, {"success": 0, "infra_error": 1, "live_gpu_faults": 2}),
    "live GPU faults are infra (a failure too)": ({}, {**EP, "success": False, "reason": "time_up"}, None, FAULT, {**LIVE, "infra_error": 1}, 0, {"success": 0, "infra_error": 1}),
    "GPU faults of a start that died building the scene do not count": ({}, EP, None, None, {**LIVE, "success": True, "live_gpu_faults": 0}, 1,
                                                                          {"success": 1, "infra_error": 0, "live_gpu_faults": 0}),
    "GPU faults of the episode's start after a restart count": ({}, EP, None, "restart", {**LIVE, "infra_error": 1, "live_gpu_faults": 1}, 0,
                                                                {"success": 0, "infra_error": 1}),
    "dumped but not exited: the live record decides": ({"STUB_END_RC": "1"}, EP, None, "", {**LIVE, "success": True, "service_exit_timed_out": True}, 1,
                                                       {"success": 1, "infra_error": 0}),
    "the film fails: the verdict stands": ({"STUB_FILM": "fail"}, EP, None, "", {**LIVE, "success": True, "video": False, "video_pending": False}, 1,
                                           {"success": 1, "video_rendered": 0, "infra_error": 0}),
    "the film crashes: the verdict stands": ({"STUB_FILM": "crash"}, EP, None, "", {**LIVE, "video": False}, 1, {"success": 1, "infra_error": 0}),
    "the film hangs: the verdict stands": ({"STUB_FILM": "sleep", "RCB_FILM_LIMIT_S": "130", "RCB_COLLECT_TIMEOUT_S": "300"}, EP, None, "",
                                           {**LIVE, "video": False}, 1, {"success": 1, "infra_error": 0}),
    "no time for the film": ({"RCB_COLLECT_TIMEOUT_S": "100"}, EP, None, "", {**LIVE, "video": False}, 1, {"success": 1, "infra_error": 0}),
    "no episode.json is infra": ({}, None, None, "", {**LIVE, "success": False, "infra_error": 1}, 0, {"success": 0, "infra_error": 1}),
    "the service never ended is infra": ({"STUB_END_RC": "1"}, None, None, "", {**LIVE, "success": False, "infra_error": 1}, 0, {"success": 0, "infra_error": 1, "finalized": 1}),
    "a give-up after crashes between calls is infra": ({"STUB_END_RC": "2"}, None, {**GAVE_UP, "reason": "sim_crashed", "infra_error": 1}, "",
                                                       {"gave_up": True, "infra_error": 1}, 0, {"success": 0, "infra_error": 1, "gave_up": 1}),
    "a crash inside the agent's calls is its 0": ({"STUB_END_RC": "2"}, None, {**GAVE_UP, "reason": "sim_crashed_on_call"}, "", {"gave_up": True}, 0,
                                                  {"success": 0, "infra_error": 0, "sim_crashed_on_call": 1}),
    "an instance mismatch at the start is infra": ({"STUB_END_RC": "2"}, None, {"task": "t", "instance_mismatch": True, "instance_matches": False, "success": False,
                                                                                 "done": True, "reason": "instance_mismatch: x", "finalized": True, "gave_up": True, "infra_error": 1},
                                                   "", {"instance_mismatch": True, "infra_error": 1}, 0, {"success": 0, "infra_error": 1, "instance_mismatch": 1}),
}
src_path = os.path.join(TPL, "environment", "sim", "finalize.sh"); src = open(src_path).read()
grade = os.path.join(TPL, "tests", "grade.py"); bad = 0
code = src.split("set -u", 1)[1]
if " replay " in code or "replay1" in code or "replay --" in code:
    print("FAIL finalize.sh still runs a replay"); bad += 1
toml = open(os.path.join(TPL, "task.toml.tmpl")).read()
hook_budget = src.split('HOOK_BUDGET_S="${RCB_COLLECT_TIMEOUT_S:-', 1)[1].split("}", 1)[0]
if f"timeout_sec = {hook_budget} " not in toml.split('command = "sh /srv/finalize.sh"', 1)[1].split("[agent]", 1)[0]:
    print(f"FAIL finalize.sh HOOK_BUDGET_S {hook_budget} is not task.toml.tmpl's [[verifier.collect]] timeout_sec"); bad += 1
end_s = float(re.search(r'RCB_COLLECT_END_TIMEOUT_S:-(\d+)', src).group(1)); film_s = float(re.search(r'RCB_FILM_LIMIT_S:-(\d+)', src).group(1))
if float(hook_budget) < end_s + film_s + 60:
    print(f"FAIL the hook's budget {hook_budget} s does not hold the end wait ({end_s:.0f}) + the film ({film_s:.0f}) + 60"); bad += 1
compose = open(os.path.join(TPL, "environment", "docker-compose.yaml.tmpl")).read()
m = re.search(r'RCB_COLLECT_TIMEOUT_S: "(\d+)"', compose)
if m and m.group(1) != hook_budget:
    print(f"FAIL docker-compose.yaml.tmpl RCB_COLLECT_TIMEOUT_S {m.group(1)} is not finalize.sh's / task.toml's {hook_budget}"); bad += 1
srv = open(os.path.join(TPL, "environment", "sim", "server.py")).read()
if "[rcb] the episode's physics starts" not in srv or srv.index("[rcb] the episode's physics starts") > srv.index("EP.begin(") or \
        "[rcb] the episode's physics starts" not in src or "[sim] service exited (" not in src:
    print("FAIL the service's physics marker (printed before EP.begin) and finalize.sh's fault count must agree"); bad += 1
if not (0 <= toml.find('service = "main"\ncommand = "kill -9 -1 2>/dev/null; exit 0"') < toml.find('service = "sim"\ncommand = "sh /srv/finalize.sh"')):
    print("FAIL task.toml.tmpl: the main kill hook must come before the sim's"); bad += 1
for name, (env, ep, fin0, slog, want_fin, want_reward, want_rj) in CASES.items():
    with tempfile.TemporaryDirectory() as td:
        data, log, bindir, srv = (os.path.join(td, x) for x in ("data", "log", "bin", "srv"))
        for x in (data, bindir, srv): os.makedirs(x)
        os.symlink(sys.executable, os.path.join(bindir, "python"))
        os.symlink(os.path.join(HERE, "stub_end.py"), os.path.join(srv, "rcb_limited.py"))
        json.dump(fin0 if fin0 is not None else {**(ep or EP), "done": True, "finalized": False}, open(os.path.join(data, "final.json"), "w"))
        if ep is not None: json.dump(ep, open(os.path.join(data, "episode.json"), "w"))
        # server.log as run.sh appends it: the starts of the service one after the other; slog = the episode's start's output
        log_txt = ("isaac start\n" + FAULT + DIED + "isaac start\n" + MARK + "service output\n") if slog is None else \
                  ("isaac start\n" + FAULT + DIED + "isaac start\n" + MARK + FAULT) if slog == "restart" else ("isaac start\n" + MARK + "service output\n" + slog)
        open(os.path.join(data, "trajectory.npz"), "w").write("x"); open(os.path.join(data, "server.log"), "w").write(log_txt)
        e = {"PATH": bindir + ":/usr/bin:/bin", "RCB_DATA": data, "RCB_SRV": srv, "RCB_TOOL": os.path.join(HERE, "stub_tool.py"), "RCB_INSTANCE": "i", **env}
        try:
            p = subprocess.run(["sh", src_path], env=e, capture_output=True, text=True, timeout=300, start_new_session=True)
        except subprocess.TimeoutExpired:
            print("FAIL", name, "; the hook did not finish in 300 s"); bad += 1
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
        if os.path.exists(os.path.join(data, "tool_called")): errs.append("the tooling was run for something else than the film: " + open(os.path.join(data, "tool_called")).read())
        if [f for f in os.listdir(data) if f.endswith(".tmp")]: errs.append("temporary file left behind")
        print(("FAIL" if errs else "ok  "), name, "; ".join(errs)); bad += bool(errs)
        if errs: print("   hook stdout:", p.stdout[-600:].replace("\n", " | "))
print("ambench standard grading:", "ALL OK" if not bad else f"{bad} FAILED"); sys.exit(1 if bad else 0)
