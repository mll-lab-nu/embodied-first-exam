"""RoboDojo standard grading, end to end without a simulator: the collect hook (template/standard/environment/sim/
finalize.sh, with stand-ins for `rcb_limited.py end` and the replay CLI) writes final.json, then the standard grader
(template/standard/tests/grade.py) scores it. Two rules (docs/benchmarks/robodojo.md):
- `state` tasks: success = live success AND both fresh replays succeed AND end in the same state; a replay that gives no
  result is an infrastructure failure (no verdict on the agent);
- tasks whose physics does not replay bit for bit (instance.json "determinism": "verdict"; standard-only): the LIVE
  episode decides (success = live success); the replays are recorded and never decide, and a replay that gives no result
  does not void the live verdict. A missing live record is an infrastructure failure under both rules.
The only edit to the script under test: /srv/rcb_limited.py -> the stand-in's path. Standard library only."""
import json, os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); TPL = os.path.join(HERE, "..", "template", "standard")
EP = {"success": True, "steps": 5, "calls": 2, "control_steps": 5, "physics_steps": 50, "elapsed_s": 9.0, "reason": "success",
      "task": "t", "protocol": "eai-standard/2.2", "n_actions": 5, "live_sha": "aa", "sim_startups": 1, "resumes": 0}
FAILED = {**EP, "success": False, "reason": "failed_check", "live_sha": "zz"}
# name: (instance determinism, env, episode.json (None: none), want reward, want reward.json subset)
CASES = {
    "state: pass": ("state", {"STUB_PLAN": "ok,ok"}, EP, 1, {"success": 1, "graded_by_live": 0, "infra_error": 0, "live_matches_replay": 1}),
    "state: replays fail": ("state", {"STUB_PLAN": "fail,fail"}, EP, 0, {"live_success": 1, "replay_success": 0, "infra_error": 0}),
    "state: replays differ": ("state", {"STUB_PLAN": "ok,diff"}, EP, 0, {"deterministic": 0, "infra_error": 0}),
    "state: replay 1 dies twice": ("state", {"STUB_PLAN": "die,die"}, EP, 0, {"infra_error": 1, "replay_error": 1, "grader_error": 1}),
    "state: replay error line": ("state", {"STUB_PLAN": "error,error"}, EP, 0, {"infra_error": 1, "replay_error": 1}),
    "state: no episode.json": ("state", {"STUB_PLAN": "ok,ok"}, None, 0, {"infra_error": 1}),
    "live: pass": ("verdict", {"STUB_PLAN": "ok,ok"}, EP, 1, {"success": 1, "graded_by_live": 1, "replay_success": 1, "infra_error": 0}),
    "live: live success, replays fail": ("verdict", {"STUB_PLAN": "fail,fail"}, EP, 1,
                                         {"success": 1, "live_success": 1, "replay_success": 0, "infra_error": 0, "grader_error": 0}),
    "live: live success, replays differ": ("verdict", {"STUB_PLAN": "ok,diff"}, EP, 1, {"success": 1, "state_identical": 0}),
    "live: live success, replay 1 dies twice": ("verdict", {"STUB_PLAN": "die,die"}, EP, 1,
                                                {"success": 1, "replay_error": 1, "infra_error": 0, "grader_error": 0}),
    "live: live success, replay error line": ("verdict", {"STUB_PLAN": "error,error"}, EP, 1, {"success": 1, "replay_error": 1, "infra_error": 0}),
    "live: live failure, replays succeed": ("verdict", {"STUB_PLAN": "ok,ok"}, FAILED, 0,
                                            {"success": 0, "live_success": 0, "replay_success": 1, "infra_error": 0}),
    "live: no episode.json": ("verdict", {"STUB_PLAN": "ok,ok"}, None, 0, {"success": 0, "infra_error": 1}),
    "live: service never ended": ("verdict", {"STUB_END_RC": "1"}, EP, 0, {"success": 0, "infra_error": 1, "finalized": 1}),
}
src = open(os.path.join(TPL, "environment", "sim", "finalize.sh")).read()
assert src.count("/srv/rcb_limited.py") == 1
grade = os.path.join(TPL, "tests", "grade.py"); bad = 0
for name, (det, env, ep, want_reward, want_rj) in CASES.items():
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
        p = subprocess.run(["sh", sh], env=e, capture_output=True, text=True, timeout=120)
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
        print(("FAIL" if errs else "ok  "), name, "; ".join(errs)); bad += bool(errs)
        if errs: print("   hook stdout:", p.stdout[-600:].replace("\n", " | "))
print("robodojo standard grading:", "ALL OK" if not bad else f"{bad} FAILED"); sys.exit(1 if bad else 0)
