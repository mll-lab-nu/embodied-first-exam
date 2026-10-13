"""RoboDojo standard grading, end to end without a simulator: the collect hook (template/standard/environment/sim/
finalize.sh, with stand-ins for `rcb_limited.py end` and the replay CLI) writes final.json, then the standard grader
(template/standard/tests/grade.py) scores it. ONE fresh-process replay since 2026-10-12 (the owner's decision; two before).
Two rules (docs/benchmarks/robodojo.md):
- `state` tasks: success = live success AND the replay succeeds; one successful replay is enough, so a replay that
  succeeds in another end state than the live episode still passes (`deterministic` = 0 is reported, it does not decide).
  The AND works both ways: a replay that succeeds where the live episode did not is 0, and a live success whose replay
  fails is 0. A replay that gives no result (it died twice, an error line, its time limit, a layout rebuilt to another
  state) is an infrastructure failure, no verdict on the agent; a replay that dies once, or that runs out of its own
  allowance (max(1800 s, 1200 s + actions / 2.5), the privileged grader's; a hung Isaac) while the hook has time left, is
  run once more; one that the hook's own deadline ended is not;
- tasks whose physics does not replay bit for bit (instance.json "determinism": "verdict"; standard-only): the LIVE
  episode decides (success = live success); the replay is recorded and never decides, and a replay that gives no result
  does not void the live verdict. A missing live record is an infrastructure failure under both rules.
Every case also checks that the hook ran the number of replay processes the case expects (1; 2 when the first died
without a result), that the one replay is the filmed one, that no second replay's files appear, and `replays` = 1.
The only edit to the script under test: /srv/rcb_limited.py -> the stand-in's path. Standard library only."""
import json, os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); TPL = os.path.join(HERE, "..", "template", "standard")
EP = {"success": True, "steps": 5, "calls": 2, "control_steps": 5, "physics_steps": 50, "elapsed_s": 9.0, "reason": "success",
      "task": "t", "protocol": "eai-standard/2.2", "n_actions": 5, "live_sha": "aa", "sim_startups": 1, "resumes": 0}
FAILED = {**EP, "success": False, "reason": "failed_check", "live_sha": "zz"}
BOX7 = {"RCB_REPLAY_FLOOR_S": "5", "RCB_REPLAY_STARTUP_S": "5"}   # the replay's allowance for EP's 5 actions: 5 + 5 / 2.5 = 7 s
# name: (instance determinism, env, episode.json (None: none), want reward, want reward.json subset, replay processes run)
CASES = {
    "state: pass": ("state", {"STUB_PLAN": "ok"}, EP, 1,
                    {"success": 1, "live_success": 1, "replay_success": 1, "deterministic": 1, "state_identical": 1,
                     "live_matches_replay": 1, "determinism_checked": 1, "replays": 1, "graded_by_live": 0, "infra_error": 0,
                     "grader_error": 0, "instance_exact": 1, "video_rendered": 1, "finalized": 1, "n_actions": 5}, 1),
    "state: live success, the replay fails": ("state", {"STUB_PLAN": "fail"}, EP, 0,
                                              {"success": 0, "live_success": 1, "replay_success": 0, "infra_error": 0, "grader_error": 0}, 1),
    # the owner's rule: one successful replay is enough, the end state's hash no longer decides
    "state: live success, the replay succeeds in another end state": ("state", {"STUB_PLAN": "diff"}, EP, 1,
                                                                      {"success": 1, "replay_success": 1, "deterministic": 0, "state_identical": 0,
                                                                       "live_matches_replay": 0, "determinism_checked": 1, "infra_error": 0}, 1),
    # the AND with the live result: a replay that succeeds where the live episode did not is not a success
    "state: live failure, the replay succeeds": ("state", {"STUB_PLAN": "ok"}, FAILED, 0,
                                                 {"success": 0, "live_success": 0, "replay_success": 1, "deterministic": 0, "infra_error": 0}, 1),
    "state: live failure, the replay fails the same way": ("state", {"STUB_PLAN": "fail"}, FAILED, 0,
                                                           {"success": 0, "live_success": 0, "replay_success": 0, "deterministic": 1, "infra_error": 0}, 1),
    "state: the replay dies twice": ("state", {"STUB_PLAN": "die,die"}, EP, 0,
                                     {"success": 0, "infra_error": 1, "replay_error": 1, "grader_error": 1, "replay_timed_out": 0}, 2),
    "state: the replay dies once, its second attempt decides": ("state", {"STUB_PLAN": "die,ok"}, EP, 1,
                                                                {"success": 1, "replay_success": 1, "infra_error": 0, "replay_error": 0}, 2),
    "state: the replay dies once, its second attempt fails": ("state", {"STUB_PLAN": "die,fail"}, EP, 0,
                                                              {"success": 0, "replay_success": 0, "infra_error": 0, "replay_error": 0}, 2),
    "state: replay error line": ("state", {"STUB_PLAN": "error,error"}, EP, 0, {"infra_error": 1, "replay_error": 1}, 2),
    "state: the replay's layout rebuilt to another state": ("state", {"STUB_PLAN": "inexact"}, EP, 0,
                                                            {"success": 0, "infra_error": 1, "replay_error": 1, "instance_mismatch": 1,
                                                             "instance_exact": 0, "grader_error": 1}, 1),
    "state: no time left for the replay": ("state", {"STUB_PLAN": "ok", "RCB_COLLECT_TIMEOUT_S": "300"}, EP, 0,
                                           {"success": 0, "infra_error": 1, "replay_error": 1, "replay_timed_out": 1}, 0),
    # the hook's own deadline ends the replay (62 s are left, the allowance is 1800 s): no second attempt
    "state: the hook's deadline ends the replay": ("state", {"STUB_PLAN": "sleep,ok", "RCB_COLLECT_TIMEOUT_S": "362"}, EP, 0,
                                                   {"success": 0, "infra_error": 1, "replay_error": 1, "replay_timed_out": 1}, 1),
    # the replay's own allowance ends it (a hung Isaac; here 7 s for the 5 actions) and the hook has time: run once more
    "state: the replay hangs past its allowance, its second attempt decides": ("state", {"STUB_PLAN": "sleep,ok", **BOX7}, EP, 1,
                                                                               {"success": 1, "replay_success": 1, "infra_error": 0,
                                                                                "replay_error": 0, "replay_timed_out": 0}, 2),
    "state: the replay hangs past its allowance twice": ("state", {"STUB_PLAN": "sleep,sleep", **BOX7}, EP, 0,
                                                         {"success": 0, "infra_error": 1, "replay_error": 1, "replay_timed_out": 1,
                                                          "grader_error": 1}, 2),
    # the allowance grows with the episode: 25 actions have 3 + 25 / 2.5 = 13 s, enough for a replay of 10 s (the floor
    # alone, or the start alone, would end it)
    "state: a longer episode has a longer allowance": ("state", {"STUB_PLAN": "slow", "RCB_REPLAY_FLOOR_S": "3", "RCB_REPLAY_STARTUP_S": "3"},
                                                       {**EP, "n_actions": 25}, 1, {"success": 1, "infra_error": 0, "replay_timed_out": 0}, 1),
    # the replay dies after 5 s with 62 s left: no time for a second attempt (under 60 s), and the record says that it
    # died (exit code 139), not that it ran out of time
    "state: the replay dies and no time is left to run it again": ("state", {"STUB_PLAN": "die_slow,ok", "RCB_COLLECT_TIMEOUT_S": "362"}, EP, 0,
                                                                   {"success": 0, "infra_error": 1, "replay_error": 1, "replay_timed_out": 0}, 1),
    # the result line counts even when the process crashes after it (Isaac's shutdown)
    "state: the result, then a crash at shutdown": ("state", {"STUB_PLAN": "ok_crash"}, EP, 1, {"success": 1, "infra_error": 0, "replay_error": 0}, 1),
    # an episode whose length cannot be read keeps the whole remaining budget: a replay of 10 s, longer than the 7 s
    # allowance its length would have had, is not ended
    "state: no n_actions in episode.json": ("state", {"STUB_PLAN": "slow", **BOX7}, {k: v for k, v in EP.items() if k != "n_actions"}, 1,
                                            {"success": 1, "infra_error": 0, "replay_timed_out": 0}, 1),
    # a video that could not be written never decides
    "state: pass without a video": ("state", {"STUB_PLAN": "novideo"}, EP, 1, {"success": 1, "video_rendered": 0, "infra_error": 0}, 1),
    "state: pass with a part of a video": ("state", {"STUB_PLAN": "partvideo"}, EP, 1, {"success": 1, "video_rendered": 0, "infra_error": 0}, 1),
    "state: no episode.json": ("state", {"STUB_PLAN": "ok"}, None, 0, {"infra_error": 1}, 1),
    "state: service never ended": ("state", {"STUB_END_RC": "1"}, EP, 0, {"success": 0, "infra_error": 1, "finalized": 1}, 0),
    "live: pass": ("verdict", {"STUB_PLAN": "ok"}, EP, 1,
                   {"success": 1, "graded_by_live": 1, "replay_success": 1, "deterministic": 1, "replays": 1, "infra_error": 0}, 1),
    "live: live success, the replay fails": ("verdict", {"STUB_PLAN": "fail"}, EP, 1,
                                             {"success": 1, "live_success": 1, "replay_success": 0, "deterministic": 0,
                                              "infra_error": 0, "grader_error": 0}, 1),
    "live: live success, the replay ends in another state": ("verdict", {"STUB_PLAN": "diff"}, EP, 1,
                                                             {"success": 1, "state_identical": 0, "deterministic": 1}, 1),
    "live: live success, the replay hangs past its allowance twice": ("verdict", {"STUB_PLAN": "sleep,sleep", **BOX7}, EP, 1,
                                                                      {"success": 1, "replay_error": 1, "replay_timed_out": 1,
                                                                       "infra_error": 0, "grader_error": 0}, 2),
    "live: live success, the replay dies twice": ("verdict", {"STUB_PLAN": "die,die"}, EP, 1,
                                                  {"success": 1, "replay_error": 1, "infra_error": 0, "grader_error": 0}, 2),
    "live: live success, replay error line": ("verdict", {"STUB_PLAN": "error,error"}, EP, 1, {"success": 1, "replay_error": 1, "infra_error": 0}, 2),
    "live: live success, the replay's layout rebuilt to another state": ("verdict", {"STUB_PLAN": "inexact"}, EP, 1,
                                                                         {"success": 1, "instance_exact": 0, "instance_mismatch": 0, "infra_error": 0}, 1),
    "live: live failure, the replay succeeds": ("verdict", {"STUB_PLAN": "ok"}, FAILED, 0,
                                                {"success": 0, "live_success": 0, "replay_success": 1, "deterministic": 0, "infra_error": 0}, 1),
    "live: no episode.json": ("verdict", {"STUB_PLAN": "ok"}, None, 0, {"success": 0, "infra_error": 1}, 1),
    "live: service never ended": ("verdict", {"STUB_END_RC": "1"}, EP, 0, {"success": 0, "infra_error": 1, "finalized": 1}, 0),
}
src = open(os.path.join(TPL, "environment", "sim", "finalize.sh")).read()
assert src.count("/srv/rcb_limited.py") == 1
grade = os.path.join(TPL, "tests", "grade.py"); bad = 0
# the declared limit and the hook's own budget are one number (task.toml says "keep them equal")
toml = open(os.path.join(TPL, "task.toml.tmpl")).read()
hook_budget = src.split('HOOK_BUDGET_S="${RCB_COLLECT_TIMEOUT_S:-', 1)[1].split("}", 1)[0]
if f"timeout_sec = {hook_budget} " not in toml.split('command = "sh /srv/finalize.sh"', 1)[1].split("[agent]", 1)[0]:
    print(f"FAIL finalize.sh HOOK_BUDGET_S {hook_budget} is not task.toml.tmpl's [[verifier.collect]] timeout_sec"); bad += 1
# the replay's allowance in the hook is the privileged grader's (the same three numbers), and the hook's budget holds the
# episode end, one replay of the longest episode at that allowance, and the merge margin
import re
priv = open(os.path.join(TPL, "..", "privileged", "tests", "grade.py")).read()
floor, startup, rate = (float(x) for x in re.search(r"REPLAY_FLOOR_S, REPLAY_STARTUP_S, REPLAY_MIN_RATE = ([\d.]+), ([\d.]+), ([\d.]+)", priv).groups())
hook = tuple(float(re.search(r'%s="\$\{RCB_%s:-([\d.]+)\}"' % (k, k), src).group(1)) for k in ("REPLAY_FLOOR_S", "REPLAY_STARTUP_S", "REPLAY_MIN_RATE"))
if hook != (floor, startup, rate):
    print(f"FAIL finalize.sh's replay allowance {hook} is not the privileged grader's {(floor, startup, rate)}"); bad += 1
end_s = float(re.search(r'RCB_COLLECT_END_TIMEOUT_S:-(\d+)', src).group(1)); margin = float(re.search(r"MERGE_MARGIN_S=(\d+)", src).group(1))
if float(hook_budget) < end_s + max(floor, startup + 15000 / rate) + margin:
    print(f"FAIL the hook's budget {hook_budget} s does not hold the episode end ({end_s:.0f}) + one replay of 15,000 actions + {margin:.0f}"); bad += 1
for name, (det, env, ep, want_reward, want_rj, want_calls) in CASES.items():
    with tempfile.TemporaryDirectory() as td:
        data, log, bindir = (os.path.join(td, x) for x in ("data", "log", "bin")); os.makedirs(data); os.makedirs(bindir)
        os.symlink(sys.executable, os.path.join(bindir, "python"))
        sh = os.path.join(td, "finalize.sh"); open(sh, "w").write(src.replace("/srv/rcb_limited.py", os.path.join(HERE, "stub_end.py")))
        inst = os.path.join(td, "instance.json"); json.dump({"task": "t", **({"determinism": "verdict"} if det == "verdict" else {})}, open(inst, "w"))
        json.dump({**(ep or EP), "done": True, "finalized": False}, open(os.path.join(data, "final.json"), "w"))   # the service's copy
        if ep is not None: json.dump(ep, open(os.path.join(data, "episode.json"), "w"))
        open(os.path.join(data, "trajectory.npz"), "w").write("x")
        e = {"PATH": bindir + ":/usr/bin:/bin", "RCB_DATA": data, "RCB_TOOL": os.path.join(HERE, "stub_tool.py"), "RCB_TASK": "t",
             "RCB_INSTANCE": inst, **env}
        try:
            p = subprocess.run(["sh", sh], env=e, capture_output=True, text=True, timeout=240, start_new_session=True)
        except subprocess.TimeoutExpired:                  # a hook that does not end its replay: a failed case, not a traceback
            print("FAIL", name, "; the hook did not finish in 240 s"); bad += 1
            continue
        g = subprocess.run([sys.executable, "-I", grade], env={"RCB_DATA": data, "RCB_VERIFIER_LOG_DIR": log, "PATH": e["PATH"]},
                           capture_output=True, text=True, timeout=60)
        errs = [] if p.returncode == 0 else [f"hook rc {p.returncode}: {p.stderr[-200:]}"]
        try:
            reward = int(open(os.path.join(log, "reward.txt")).read().strip()); rj = json.load(open(os.path.join(log, "reward.json")))
        except Exception as exc:  # noqa: BLE001
            reward, rj = None, {}; errs.append(f"no reward: {exc!r} {g.stderr[-300:]}")
        if reward != want_reward: errs.append(f"reward {reward} (want {want_reward})")
        errs += [f"reward.json {k}={rj.get(k)!r} (want {v!r})" for k, v in want_rj.items() if rj.get(k) != v]
        if not all(isinstance(v, (int, float)) for v in rj.values()): errs.append("reward.json has a non-numeric value")
        # the fields the pool's collector and dashboard read are always there, whatever happened
        errs += [f"reward.json has no {k}" for k in ("success", "deterministic", "replay_success", "infra_error", "grader_error",
                                                     "live_success", "finalized") if k not in rj]
        if rj.get("success") == 1 and (rj.get("infra_error") or reward != 1): errs.append("success = 1 beside infra_error or reward 0")
        cf = os.path.join(data, "stub_calls"); calls = int(open(cf).read()) if os.path.exists(cf) else 0
        if calls != want_calls: errs.append(f"{calls} replay process(es) run (want {want_calls})")
        argv = [json.loads(l) for l in open(os.path.join(data, "stub_argv"))] if calls else []
        if any("--video" not in a for a in argv): errs.append("a replay was run without --video: the one replay is the filmed one")
        extra = sorted(f for f in os.listdir(data) if f.startswith("replay2"))
        if extra: errs.append(f"files of a second replay: {extra}")
        if env.get("STUB_END_RC") != "1":
            fin = json.load(open(os.path.join(data, "final.json")))
            if name.startswith("state: the replay dies and no time") and fin.get("replay_rc") != [139]:
                errs.append(f"replay_rc {fin.get('replay_rc')}: the first attempt's exit record was lost")
            if fin.get("replays") != 1 or "replay_sha2" in fin or len(fin.get("replay_rc") or []) != 1:
                errs.append(f"final.json does not describe one replay: replays={fin.get('replays')} replay_rc={fin.get('replay_rc')}")
            if "deterministic" not in fin or "replay_success" not in fin: errs.append("final.json lost deterministic / replay_success")
        print(("FAIL" if errs else "ok  "), name, "; ".join(errs)); bad += bool(errs)
        if errs: print("   hook stdout:", p.stdout[-600:].replace("\n", " | "))
print("robodojo standard grading:", "ALL OK" if not bad else f"{bad} FAILED"); sys.exit(1 if bad else 0)
