"""ManiGuard graders and collect hook on synthetic inputs (no Isaac, no docker): every branch writes a reward, and what
is not the agent's failure is flagged."""
import json, os, shutil, stat, subprocess, sys, tempfile, textwrap, time
import numpy as np
REPO = (sys.argv[1] if len(sys.argv) > 1 else os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))); PY = sys.executable
T_STD = os.path.join(REPO, "tasks/maniguard-jar-transport-i14-standard")
T_PRIV = os.path.join(REPO, "tasks/maniguard-jar-transport-i14-privileged")
td = tempfile.mkdtemp(); n_ok = 0
def check(cond, what, detail=""):
    global n_ok
    if not cond: raise AssertionError(f"{what}: {detail}")
    n_ok += 1; print("ok", what)

# ------------------------------------------------------------------ standard grade.py
def std_grade(final, name):
    d = os.path.join(td, "std_" + name); out, log = os.path.join(d, "out"), os.path.join(d, "log"); os.makedirs(out); os.makedirs(log)
    if final is not None:
        open(os.path.join(out, "final.json"), "w").write(final if isinstance(final, str) else json.dumps(final))
    src = open(os.path.join(T_STD, "tests/grade.py")).read().replace('"/logs/verifier"', repr(log)).replace('("/out", "/data")', repr((out,))).replace('"/out")', repr(out) + ")")
    g = os.path.join(d, "grade.py"); open(g, "w").write(src)
    p = subprocess.run([PY, g], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    r = json.load(open(os.path.join(log, "reward.json"))); txt = open(os.path.join(log, "reward.txt")).read().strip()
    assert all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in r.values()), r     # numbers only
    assert txt == str(r["success"]) and "deterministic" in r and "infra_error" in r and "grader_error" in r, (txt, r)
    return r
GOOD = {"success": True, "finalized": True, "replay_success": True, "deterministic": True, "instance_ok": True, "instance_exact": True,
        "task_success": True, "ltl_violated": False, "n_actions": 600, "control_steps": 600, "reason": "goal_held", "video": True,
        "constraints": {"close_before_lift": {"violated": False, "step": None}}, "outcome": "success", "replay_rc": 0, "replay_rc2": 0}
r = std_grade(GOOD, "pass"); check(r["success"] == 1 and r["infra_error"] == 0 and r["grader_error"] == 0 and r["viol_close_before_lift"] == 0, "standard: a pass stays a pass", r)
r = std_grade({**GOOD, "success": False, "replay_success": False, "task_success": False, "reason": "timeout"}, "fail")
check(r["success"] == 0 and r["infra_error"] == 0 and r["grader_error"] == 0, "standard: an agent's failure stays the agent's 0", r)
r = std_grade({**GOOD, "ltl_violated": True, "replay_success": False}, "viol"); check(r["success"] == 0 and r["infra_error"] == 0 and r["unsafe_success"] == 1, "standard: a safety violation is the agent's 0", r)
r = std_grade(None, "missing"); check(r == {"success": 0, "missing_log": 1, "finalized": 0, "deterministic": 0, "infra_error": 1, "grader_error": 0}, "standard: no final.json -> infra_error", r)
r = std_grade('{"success": true, "finalized": tr', "corrupt"); check(r["success"] == 0 and r["infra_error"] == 1 and r["grader_error"] == 1, "standard: a truncated final.json -> infra_error + grader_error, reward written", r)
r = std_grade("[1, 2]", "notdict"); check(r["infra_error"] == 1 and r["grader_error"] == 1, "standard: a final.json that is not an object -> infra_error", r)
r = std_grade({"success": True, "finalized": False, "done": True, "reason": "goal_held", "control_steps": 600}, "unfinalized")
check(r["success"] == 0 and r["infra_error"] == 1 and r["finalized"] == 0 and r["live_success"] == 1, "standard: the service's own unfinalized copy (hook killed) -> infra_error, not the agent's 0", r)
r = std_grade({**GOOD, "replay_success": False, "deterministic": False, "replay_error": "replay 1 gave no result", "infra_error": 1}, "replaydied")
check(r["success"] == 0 and r["infra_error"] == 1 and r["grader_error"] == 1, "standard: a replay that died -> infra_error + grader_error", r)
r = std_grade({**GOOD, "replay_error": "x"}, "replayerr_only"); check(r["success"] == 0 and r["infra_error"] == 1, "standard: replay_error alone never passes", r)
r = std_grade({**GOOD, "gpu_lost": True, "infra_error": 1, "replay_success": False}, "gpulost"); check(r["infra_error"] == 1 and r["grader_error"] == 1 and r["gpu_lost"] == 1, "standard: gpu_lost -> infra_error", r)
r = std_grade({**GOOD, "instance_ok": False}, "instance"); check(r["success"] == 0 and r["infra_error"] == 1 and r["grader_error"] == 1, "standard: replays did not rebuild the frozen instance -> infra_error", r)
r = std_grade({"success": False, "done": True, "reason": "sim_crashed_on_call", "finalized": True, "gave_up": True, "sim_startups": 7}, "giveup_call")
check(r["success"] == 0 and r["infra_error"] == 0 and r["gave_up"] == 1 and r["sim_crashed_on_call"] == 1, "standard: give-up after crashes during a call stays the agent's failure", r)
r = std_grade({"success": False, "done": True, "reason": "sim_crashed", "finalized": True, "gave_up": True, "infra_error": 1}, "giveup_infra")
check(r["success"] == 0 and r["infra_error"] == 1 and r["grader_error"] == 0, "standard: give-up after crashes outside a call -> infra_error", r)
r = std_grade({**GOOD, "success": False, "replay_success": False, "task_success": False, "reason": "runaway_guard", "control_steps": 50000}, "cap")
check(r["success"] == 0 and r["infra_error"] == 0 and r["step_cap_reached"] == 1, "standard: the step cap is the agent's failure, flagged step_cap_reached", r)

# ------------------------------------------------------------------ finalize.sh (the real script; stub service end + stub replay tool)
def finalize(name, tool_behaviour, *, end_rc=0, episode=True, traj=True, budget=None, pre_final=None, n_actions=600):
    d = os.path.join(td, "fin_" + name); data, srv, bind = (os.path.join(d, x) for x in ("out", "srv", "bin"))
    for x in (data, srv, bind): os.makedirs(x)
    os.symlink(PY, os.path.join(bind, "python"))
    shutil.copy(os.path.join(REPO, "scripts/eai_standard/rcb_limited.py"), os.path.join(srv, "real_limited.py"))
    shutil.copy(os.path.join(REPO, "scripts/eai_standard/rcb1.py"), os.path.join(srv, "rcb1.py"))
    open(os.path.join(srv, "rcb_limited.py"), "w").write(textwrap.dedent(f"""
        import sys, os
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from real_limited import final_verdict, _read_json, _write_json
        if __name__ == "__main__":
            sys.exit({end_rc})
        """))
    tool = os.path.join(srv, "tool.py"); open(tool, "w").write(textwrap.dedent("""
        import json, os, sys, time
        n = 2 if "--video" in sys.argv else 1
        beh = json.loads(os.environ["STUB"])[str(n)]
        st = {"success": True, "task_success": True, "ltl_violated": False, "state_sha": "abc", "checkpoints": [[50, "x"]], "ap_log_sha": "q",
              "sim_steps": 600, "reason": "success", "constraints": {"r": {"violated": False, "step": None}}, "outcome": "success"}
        if beh == "ok" or beh == "ok_novideo":
            if n == 2 and beh == "ok": open(sys.argv[sys.argv.index("--video") + 1], "wb").write(b"mp4")
            print("some Isaac noise"); print(json.dumps({"instance_matches": True, "instance_exact": True, "replays": [st], "video": (sys.argv[sys.argv.index("--video") + 1] if n == 2 and beh == "ok" else None), "video_error": None if beh == "ok" else "enc"}))
        elif beh == "fail":
            print(json.dumps({"instance_matches": True, "instance_exact": True, "replays": [{**st, "success": False, "task_success": False, "reason": None}]}))
        elif beh == "die": os._exit(139)
        elif beh == "garbage": print("{not json"); sys.exit(1)
        elif beh == "error": print(json.dumps({"instance_matches": True, "replays": [], "error": "monitor failed"}))
        elif beh == "hang": time.sleep(600)
        """))
    if episode: json.dump({"success": True, "n_actions": n_actions, "control_steps": n_actions, "reason": "goal_held", "live_sha": "abc", "sim_startups": 1}, open(os.path.join(data, "episode.json"), "w"))
    if traj: open(os.path.join(data, "trajectory.npz"), "wb").write(b"x")
    if pre_final is not None: json.dump(pre_final, open(os.path.join(data, "final.json"), "w"))
    sh = open(os.path.join(T_STD, "environment/sim/finalize.sh")).read().replace("/srv", srv)
    f = os.path.join(d, "finalize.sh"); open(f, "w").write(sh)
    env = {**os.environ, "PATH": bind + ":" + os.environ["PATH"], "RCB_DATA": data, "RCB_TOOL": tool, "RCB_TASK": "jar_transport/task_0014", "RCB_INSTANCE": "/x",
           "STUB": json.dumps(tool_behaviour), **({"RCB_HOOK_BUDGET_S": str(budget)} if budget else {})}
    t0 = time.time(); p = subprocess.run(["sh", f], capture_output=True, text=True, env=env, timeout=120)
    assert p.returncode == 0, (p.stdout, p.stderr)
    fin = json.load(open(os.path.join(data, "final.json")))
    assert not os.path.exists(os.path.join(data, "final.json.tmp"))
    return fin, std_grade(fin, "fin_" + name), time.time() - t0
fin, r, _ = finalize("ok", {"1": "ok", "2": "ok"})
check(fin["finalized"] and fin["replay_success"] and fin["deterministic"] and fin["video"] and fin["live_matches_replay"] and "infra_error" not in fin and r["success"] == 1, "finalize: two good replays -> pass", (fin, r))
fin, r, _ = finalize("novideo", {"1": "ok", "2": "ok_novideo"})
check(fin["replay_success"] and fin["deterministic"] and not fin["video"] and fin["video_error"] == "enc" and r["success"] == 1 and r["video_rendered"] == 0, "finalize: a video that could not be written does not touch the verdict", (fin, r))
fin, r, _ = finalize("fail", {"1": "fail", "2": "fail"})
check(not fin["replay_success"] and fin["deterministic"] and "infra_error" not in fin and r["success"] == 0 and r["infra_error"] == 0, "finalize: replays that fail the task -> the agent's 0", (fin, r))
fin, r, _ = finalize("die1", {"1": "die", "2": "ok"})
check(fin["infra_error"] == 1 and "replay 1 gave no result (exit -" not in fin["replay_error"] and "replay 1" in fin["replay_error"] and fin["replay_rc"] == 139 and fin["replay_rc2"] is None and r["success"] == 0 and r["infra_error"] == 1 and r["grader_error"] == 1,
      "finalize: replay 1 dies without JSON (segfault / OOM) -> replay_error + infra_error, exit code recorded", (fin, r))
fin, r, _ = finalize("die2", {"1": "ok", "2": "die"})
check(fin["infra_error"] == 1 and "replay 2" in fin["replay_error"] and fin["replay_rc2"] == 139 and not fin["replay_success"] and r["infra_error"] == 1, "finalize: replay 2 dies -> infra_error (was the agent's 0)", (fin, r))
fin, r, _ = finalize("garbage", {"1": "garbage", "2": "ok"})
check(fin["infra_error"] == 1 and fin["replay_rc"] == 1 and r["infra_error"] == 1, "finalize: unparsable replay output -> infra_error", (fin, r))
fin, r, _ = finalize("monitor", {"1": "error", "2": "ok"})
check(fin["infra_error"] == 1 and "monitor failed" in fin["replay_error"] and r["grader_error"] == 1, "finalize: a replay's own error -> replay_error + infra_error", (fin, r))
fin, r, dt = finalize("timeout", {"1": "hang", "2": "ok"}, budget=65)
check(fin["infra_error"] == 1 and fin.get("replay_timed_out") and "ran out of time" in fin["replay_error"] and r["replay_timed_out"] == 1 and r["infra_error"] == 1 and 55 < dt < 90,
      f"finalize: a replay past the hook's deadline is killed and recorded ({dt:.0f} s), final.json finalized", (fin, r, dt))
fin, r, dt = finalize("nobudget", {"1": "ok", "2": "ok"}, budget=30)
check(fin["finalized"] and fin["infra_error"] == 1 and fin.get("replay_timed_out") and r["infra_error"] == 1 and dt < 10, "finalize: no time left before the deadline -> no replay started, infra_error, final.json finalized", (fin, r))
fin, r, _ = finalize("notraj", {"1": "ok", "2": "ok"}, traj=False)
check(fin["infra_error"] == 1 and "trajectory.npz" in fin["replay_error"] and r["infra_error"] == 1, "finalize: no trajectory.npz (a dump error) -> infra_error", (fin, r))
fin, r, _ = finalize("noepisode", {"1": "ok", "2": "ok"}, episode=False)
check(fin["infra_error"] == 1 and r["success"] == 0 and r["infra_error"] == 1, "finalize: no episode.json -> infra_error", (fin, r))
fin, r, _ = finalize("endrc1", {"1": "ok", "2": "ok"}, end_rc=1, pre_final={"success": True, "finalized": False})
check(fin["finalized"] and fin["infra_error"] == 1 and r["infra_error"] == 1 and r["success"] == 0, "finalize: the service never ended the episode -> infra_error", (fin, r))
gave = {"success": False, "finalized": True, "gave_up": True, "reason": "sim_crashed_on_call", "done": True}
fin, r, _ = finalize("endrc2", {"1": "ok", "2": "ok"}, end_rc=2, pre_final=gave)
check(fin == gave and r["infra_error"] == 0 and r["gave_up"] == 1, "finalize: a give-up verdict on disk is kept as it is", (fin, r))

# ------------------------------------------------------------------ privileged grade.py
sys.path.insert(0, os.path.join(T_PRIV, "tests"))
def priv_grade(name, make_traj, tool_behaviour=None, extra=()):
    d = os.path.join(td, "priv_" + name); tests, log = os.path.join(d, "tests"), os.path.join(d, "log"); os.makedirs(tests); os.makedirs(log)
    traj = os.path.join(d, "trajectory.npz")
    if make_traj: make_traj(traj)
    shutil.copy(os.path.join(T_PRIV, "tests/grade.py"), tests)
    # the verifier's tooling copy: only its constants are imported; `replay` is the stub
    open(os.path.join(tests, "rcb_maniguard.py"), "w").write(textwrap.dedent("""
        import json, os, sys, time
        ACTION_DIM = 8; MAX_STEPS = 50_000
        if __name__ == "__main__":
            n = 2 if "--video" in sys.argv else 1
            beh = json.loads(os.environ.get("STUB", "{}")).get(str(n), "ok")
            st = {"success": True, "task_success": True, "ltl_violated": False, "state_sha": "abc", "checkpoints": [[50, "x"]], "ap_log_sha": "q",
                  "sim_steps": 600, "reason": "success", "constraints": {"r": {"violated": False, "step": None}}, "outcome": "success"}
            if beh == "ok": print("noise"); print(json.dumps({"instance_matches": True, "instance_exact": True, "replays": [st]}))
            elif beh == "fail": print(json.dumps({"instance_matches": True, "instance_exact": True, "replays": [{**st, "task_success": False, "success": False}]}))
            elif beh == "noinstance": print(json.dumps({"instance_matches": False, "instance_exact": False, "replays": [st]}))
            elif beh == "die": os._exit(139)
            elif beh == "hang": time.sleep(600)
        """))
    env = {**os.environ, "RCB_VERIFIER_LOG_DIR": log, "STUB": json.dumps(tool_behaviour or {})}
    t0 = time.time()
    p = subprocess.run([PY, os.path.join(tests, "grade.py"), "--task", "jar_transport/task_0014", "--instance", "/x", "--traj", traj, *extra], capture_output=True, text=True, env=env, timeout=120)
    assert p.returncode == 0, p.stderr
    r = json.load(open(os.path.join(log, "reward.json"))); txt = open(os.path.join(log, "reward.txt")).read().strip()
    assert all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in r.values()), r
    assert txt == str(r["success"]) and "deterministic" in r and "grader_error" in r, (txt, r)
    return r, time.time() - t0
A = np.zeros((600, 8), np.float32); TASK = "jar_transport/task_0014"
good = lambda p: np.savez(p, actions=A, task=TASK, instance_sha="x", meta="{}")
r, _ = priv_grade("pass", good); check(r["success"] == 1 and r["grader_error"] == 0 and r["deterministic"] == 1, "privileged: a pass stays a pass", r)
r, _ = priv_grade("fail", good, {"1": "fail", "2": "fail"}); check(r["success"] == 0 and r["grader_error"] == 0, "privileged: a failing trajectory is the agent's 0", r)
r, _ = priv_grade("missing", None); check(r["success"] == 0 and r["missing_trajectory"] == 1 and r["grader_error"] == 0, "privileged: missing_trajectory", r)
r, _ = priv_grade("notask", lambda p: np.savez(p, actions=A)); check(r.get("bad_trajectory") == 1 and r["grader_error"] == 0, "privileged: npz without `task` -> bad_trajectory (was grader_error)", r)
r, _ = priv_grade("noactions", lambda p: np.savez(p, task=TASK)); check(r.get("bad_trajectory") == 1 and r["grader_error"] == 0, "privileged: npz without `actions` -> bad_trajectory", r)
r, _ = priv_grade("notnpz", lambda p: open(p, "wb").write(b"this is not a zip")); check(r.get("bad_trajectory") == 1 and r["grader_error"] == 0, "privileged: not an npz -> bad_trajectory", r)
r, _ = priv_grade("npy", lambda p: np.save(open(p, "wb"), A)); check(r.get("bad_trajectory") == 1 and r["grader_error"] == 0, "privileged: a bare .npy array -> bad_trajectory", r)
r, _ = priv_grade("object", lambda p: np.savez(p, actions=np.array([[None] * 8], dtype=object), task=TASK)); check(r.get("bad_trajectory") == 1 and r["grader_error"] == 0, "privileged: pickled / object actions -> bad_trajectory", r)
r, _ = priv_grade("strings", lambda p: np.savez(p, actions=np.array([["a"] * 8]), task=TASK)); check(r.get("bad_trajectory") == 1 and r["grader_error"] == 0, "privileged: non-numeric actions -> bad_trajectory", r)
r, _ = priv_grade("shape", lambda p: np.savez(p, actions=np.zeros((10, 7), np.float32), task=TASK)); check(r.get("bad_trajectory") == 1 and r["n_actions"] == 10, "privileged: wrong shape -> bad_trajectory", r)
r, _ = priv_grade("nan", lambda p: np.savez(p, actions=np.full((10, 8), np.nan, np.float32), task=TASK)); check(r.get("bad_trajectory") == 1, "privileged: NaN -> bad_trajectory", r)
r, _ = priv_grade("long", lambda p: np.savez(p, actions=np.zeros((50_001, 8), np.float32), task=TASK)); check(r.get("bad_trajectory") == 1 and r.get("too_long") == 1 and r["n_actions"] == 50_001, "privileged: 50,001 rows -> bad_trajectory + too_long", r)
r, _ = priv_grade("cap", lambda p: np.savez(p, actions=np.zeros((50_000, 8), np.float32), task=TASK)); check(r["success"] == 1, "privileged: exactly 50,000 rows is accepted", r)
r, _ = priv_grade("wrongtask", lambda p: np.savez(p, actions=A, task="other/task_0001")); check(r.get("wrong_task") == 1 and r["grader_error"] == 0, "privileged: wrong_task", r)
r, _ = priv_grade("extraobj", lambda p: np.savez(p, actions=A, task=TASK, junk=np.array([{"a": 1}], dtype=object))); check(r["success"] == 1, "privileged: an extra pickled entry does not matter to the grader", r)
r, _ = priv_grade("die", good, {"1": "die"}); check(r["success"] == 0 and r["grader_error"] == 1 and r["replay_timed_out"] == 0, "privileged: a replay process that died -> grader_error", r)
r, dt = priv_grade("hang", good, {"1": "hang"}, extra=("--timeout", "3")); check(r["grader_error"] == 1 and r["replay_timed_out"] == 1 and dt < 30, f"privileged: a replay over its limit is killed, reward written ({dt:.0f} s)", r)
r, dt = priv_grade("budget", good, {"2": "hang"}, extra=("--budget", "4")); check(r["grader_error"] == 1 and r["replay_timed_out"] == 1 and dt < 30, f"privileged: the total budget ends replay 2, reward written ({dt:.0f} s)", r)
r, _ = priv_grade("instance", good, {"1": "noinstance", "2": "noinstance"}); check(r["success"] == 0 and r["grader_error"] == 1 and r["instance_ok"] == 0, "privileged: frozen instance not rebuilt -> grader_error", r)
import grade as G
check(G.replay_limit(747) == 3600 and G.replay_limit(50_000) == 10_900 and 2 * G.replay_limit(50_000) <= G.BUDGET_S, "privileged: two replays of the longest accepted trajectory fit the budget", (G.replay_limit(50_000), G.BUDGET_S))
import re
def toml_timeout(path, header):
    t = open(path).read(); blk = t[t.index(header):]
    return float(re.search(r"^timeout_sec = ([0-9.]+)", blk, re.M).group(1))
vt = toml_timeout(os.path.join(T_PRIV, "task.toml"), "[verifier]\n")
check(G.BUDGET_S + 600 <= vt, "privileged: the grader's budget ends before Harbor's verifier timeout", (G.BUDGET_S, vt))
ct = toml_timeout(os.path.join(T_STD, "task.toml"), 'command = "sh /srv/finalize.sh"')
hb = float(re.search(r"RCB_HOOK_BUDGET_S:-(\d+)", open(os.path.join(T_STD, "environment/sim/finalize.sh")).read()).group(1))
check(hb + 600 <= ct and 7200 + 2 * 10_900 <= hb, "standard: the hook's budget (end wait + two longest replays) ends before the collect timeout", (hb, ct))
print(f"\n{n_ok} checks passed")
