"""finalize.sh end to end with stand-ins for the simulator side (the `end` half of rcb_limited.py and live_video.py's
encode), then the standard grader on the final.json it wrote (RoboLab, YAMLab: graded by the live episode, board 0151).
The script under test runs unmodified: RCB_SRV points it at the stand-ins. No case may start a replay: the hook has no
replay any more, and RCB_TOOL points at a tool that records any call."""
import json, os, subprocess, sys, tempfile, time
ROOT = (sys.argv[1] if len(sys.argv) > 1 else os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))); HERE = os.path.dirname(os.path.abspath(__file__))
EP = {"success": True, "steps": 5, "calls": 2, "control_steps": 5, "physics_steps": 40, "elapsed_s": 9.0, "reason": "success", "task": "t",
      "protocol": "eai-standard/2.2", "n_actions": 5, "live_sha": "aa", "sim_startups": 1, "resumes": 0, "instance_exact": True, "instance_matches": True}
SERVICE_FINAL = {**EP, "done": True, "finalized": False}
GAVE_UP = {**SERVICE_FINAL, "success": False, "done": True, "finalized": True, "gave_up": True}
LIVE = {"finalized": True, "graded_by": "live", "replays": 0}
# name: (env, episode.json (None: none), final.json before the hook, want final.json subset, want reward, want reward.json subset, max s)
CASES = {
    "live_success": ({}, EP, SERVICE_FINAL, {**LIVE, "success": True, "live_success": True, "video": True, "video_pending": False, "video_source": "live",
                                             "video_frames": 7}, 1, {"success": 1, "live_success": 1, "graded_by_live": 1, "replays": 0, "infra_error": 0, "video_rendered": 1}, 30),
    "live_failure_timeout": ({}, {**EP, "success": False, "reason": "timeout"}, SERVICE_FINAL, {**LIVE, "success": False, "live_success": False},
                             0, {"success": 0, "infra_error": 0, "grader_error": 0}, 30),
    "settle_failure_is_agents_zero": ({}, {**EP, "success": False, "reason": "timeout", "settle_steps": 30}, SERVICE_FINAL, {**LIVE, "success": False},
                                      0, {"success": 0, "infra_error": 0, "settle_steps": 30}, 30),
    "sim_error_in_call_is_agents_zero": ({}, {**EP, "success": False, "reason": "error"}, SERVICE_FINAL, {**LIVE, "success": False},
                                         0, {"success": 0, "infra_error": 0, "sim_error": 1}, 30),
    "video_fails_verdict_stands": ({"STUB_VIDEO": "fail"}, EP, SERVICE_FINAL, {**LIVE, "success": True, "video": False, "video_pending": False},
                                   1, {"success": 1, "infra_error": 0, "video_rendered": 0}, 30),
    "video_crashes_verdict_stands": ({"STUB_VIDEO": "crash"}, EP, SERVICE_FINAL, {**LIVE, "success": True, "video": False}, 1, {"success": 1, "infra_error": 0}, 30),
    "video_times_out_verdict_stands": ({"STUB_VIDEO": "sleep", "RCB_VIDEO_LIMIT_S": "30"}, EP, SERVICE_FINAL, {**LIVE, "success": True, "video": False},
                                       1, {"success": 1, "infra_error": 0, "video_rendered": 0}, 60),
    "no_time_for_video": ({"RCB_COLLECT_TIMEOUT_S": "60"}, EP, SERVICE_FINAL, {**LIVE, "success": True, "video": False}, 1, {"success": 1, "infra_error": 0}, 30),
    "no_episode_json_is_infra": ({}, None, SERVICE_FINAL, {**LIVE, "success": False, "infra_error": 1}, 0, {"success": 0, "infra_error": 1}, 30),
    "service_never_ended_is_infra": ({"STUB_END_RC": "1"}, None, SERVICE_FINAL, {**LIVE, "success": False, "infra_error": 1}, 0, {"success": 0, "infra_error": 1, "finalized": 1}, 30),
    "dumped_but_not_exited_live_decides": ({"STUB_END_RC": "1"}, EP, SERVICE_FINAL, {**LIVE, "success": True, "service_exit_timed_out": True},
                                           1, {"success": 1, "infra_error": 0}, 30),
    "gave_up_between_calls_is_infra": ({"STUB_END_RC": "2"}, None, {**GAVE_UP, "reason": "sim_crashed", "infra_error": 1}, {"finalized": True, "gave_up": True, "infra_error": 1},
                                       0, {"success": 0, "infra_error": 1, "gave_up": 1}, 30),
    "crash_in_calls_is_agents_zero": ({"STUB_END_RC": "2"}, None, {**GAVE_UP, "reason": "sim_crashed_on_call"}, {"finalized": True, "gave_up": True, "success": False},
                                      0, {"success": 0, "infra_error": 0, "sim_crashed_on_call": 1}, 30),
    "instance_mismatch_at_start_is_infra": ({"STUB_END_RC": "2"}, None, {"task": "t", "instance_mismatch": True, "instance_exact": False, "instance_matches": False,
                                             "success": False, "done": True, "reason": "instance_mismatch: ...", "finalized": True, "gave_up": True, "infra_error": 1},
                                            {"instance_mismatch": True, "infra_error": 1}, 0, {"success": 0, "infra_error": 1, "instance_mismatch": 1}, 30),
}
bad = 0
for bench in ("robolab", "yamlab"):
    sh_src = os.path.join(ROOT, "scripts", bench, "template/standard/environment/sim/finalize.sh")
    src = open(sh_src).read()
    code = src.split("set -u", 1)[1]                # the code after the header comment
    if "RCB_TOOL" in code or " replay " in code or "replay1" in code:
        print(f"FAIL {bench}: finalize.sh still runs a replay"); bad += 1
    grade = os.path.join(ROOT, "scripts", bench, "template/standard/tests/grade.py")
    toml = open(os.path.join(ROOT, "scripts", bench, "template/standard/task.toml.tmpl")).read()
    budget = src.split('HOOK_BUDGET_S="${RCB_COLLECT_TIMEOUT_S:-', 1)[1].split("}", 1)[0]
    if f"timeout_sec = {budget} " not in toml.split('command = "sh /srv/finalize.sh"', 1)[1].split("[agent]", 1)[0]:
        print(f"FAIL {bench}: finalize.sh HOOK_BUDGET_S {budget} is not task.toml.tmpl's [[verifier.collect]] timeout_sec"); bad += 1
    if not (0 <= toml.find('service = "main"\ncommand = "kill -9 -1 2>/dev/null; exit 0"') < toml.find('service = "sim"\ncommand = "sh /srv/finalize.sh"')):
        print(f"FAIL {bench}: task.toml.tmpl: the main kill hook must come before the sim's"); bad += 1
    for name, (env, ep, fin0, want_fin, want_reward, want_rj, max_s) in CASES.items():
        if bench == "yamlab" and name.startswith("settle"):
            continue                                   # YAMLab has no end-of-episode hold
        with tempfile.TemporaryDirectory() as td:
            data, log, bindir, srv = (os.path.join(td, x) for x in ("data", "log", "bin", "srv"))
            for x in (data, bindir, srv): os.makedirs(x)
            os.symlink(sys.executable, os.path.join(bindir, "python"))
            os.symlink(os.path.join(HERE, "stub_end.py"), os.path.join(srv, "rcb_limited.py"))
            os.symlink(os.path.join(HERE, "stub_video.py"), os.path.join(srv, "live_video.py"))
            tool = os.path.join(td, "tool.py"); open(tool, "w").write(f"open({os.path.join(data, 'tool_called')!r}, 'w').write('x')\n")
            json.dump(fin0, open(os.path.join(data, "final.json"), "w"))
            if ep is not None: json.dump(ep, open(os.path.join(data, "episode.json"), "w"))
            open(os.path.join(data, "trajectory.npz"), "w").write("x")
            e = {"PATH": bindir + ":/usr/bin:/bin", "RCB_DATA": data, "RCB_SRV": srv, "RCB_TOOL": tool, "RCB_TASK": "t", "RCB_INSTANCE": "i", **env}
            t0 = time.time(); p = subprocess.run(["sh", sh_src], env=e, capture_output=True, text=True); dt = time.time() - t0
            errs = []
            try:
                fin = json.load(open(os.path.join(data, "final.json")))
            except Exception as exc:
                fin = {}; errs.append(f"final.json unreadable {exc!r}")
            errs += [f"final {k}={fin.get(k)!r} (want {v!r})" for k, v in want_fin.items() if fin.get(k) != v]
            for k in ("replay_success", "deterministic", "replay_sha"):
                if k in fin: errs.append(f"final.json has {k}")
            if os.path.exists(os.path.join(data, "tool_called")): errs.append("a replay was started")
            if [f for f in os.listdir(data) if f.endswith(".tmp")]: errs.append("temporary file left behind")
            if p.returncode != 0: errs.append(f"hook rc {p.returncode}: {p.stderr[-200:]}")
            if dt > max_s: errs.append(f"took {dt:.0f} s")
            g = subprocess.run([sys.executable, "-I", grade], env={"RCB_DATA": data, "RCB_VERIFIER_LOG_DIR": log, "PATH": e["PATH"]}, capture_output=True, text=True)
            reward = int(open(os.path.join(log, "reward.txt")).read().strip()); rj = json.load(open(os.path.join(log, "reward.json")))
            if reward != want_reward: errs.append(f"reward {reward} (want {want_reward})")
            errs += [f"reward.json {k}={rj.get(k)!r} (want {v!r})" for k, v in want_rj.items() if rj.get(k) != v]
            print(("FAIL" if errs else "ok  "), bench, name, f"({dt:.0f} s)", "; ".join(errs)); bad += bool(errs)
            if errs: print("   hook stdout:", p.stdout[-600:].replace("\n", " | "))
print("finalize.sh:", "ALL OK" if not bad else f"{bad} FAILED"); sys.exit(1 if bad else 0)
