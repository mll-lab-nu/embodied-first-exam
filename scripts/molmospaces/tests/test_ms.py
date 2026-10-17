"""MolmoSpaces: graders, collect hook and service on synthetic inputs (no MuJoCo, no docker)."""
import json, os, re, runpy, shutil, subprocess, sys, tempfile, textwrap, threading, time
from http.server import HTTPServer
import numpy as np, requests
REPO, HERE, PY = (sys.argv[1] if len(sys.argv) > 1 else os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))), os.path.dirname(os.path.abspath(__file__)), sys.executable
T_STD = os.path.join(REPO, "tasks/molmospaces-pick-i00-standard"); T_PRIV = os.path.join(REPO, "tasks/molmospaces-pick-i00-privileged")
td = tempfile.mkdtemp(); n_ok = 0
def check(c, what, detail=""):
    global n_ok
    if not c: raise AssertionError(f"{what}: {detail}")
    n_ok += 1; print("ok", what)

# ------------------------------------------------------------------ standard grade.py
def std_grade(final, name):
    d = os.path.join(td, "std_" + name); data, log = os.path.join(d, "data"), os.path.join(d, "log"); os.makedirs(data); os.makedirs(log)
    if final is not None:
        open(os.path.join(data, "final.json"), "w").write(final if isinstance(final, str) else json.dumps(final))
    src = open(os.path.join(T_STD, "tests/grade.py")).read().replace('LOG = "/logs/verifier"', f"LOG = {log!r}").replace('DATA = "/data"', f"DATA = {data!r}")
    assert log in src and data in src
    g = os.path.join(d, "grade.py"); open(g, "w").write(src)
    p = subprocess.run([PY, g], capture_output=True, text=True); assert p.returncode == 0, p.stderr
    r = json.load(open(os.path.join(log, "reward.json"))); txt = open(os.path.join(log, "reward.txt")).read().strip()
    assert all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in r.values()), r
    assert txt == str(r["success"]) and all(k in r for k in ("deterministic", "infra_error", "grader_error", "finalized", "missing_log")), (txt, r)
    return r
GOOD = {"success": True, "finalized": True, "replay_success": True, "deterministic": True, "live_matches_replay": True, "n_actions": 30, "control_steps": 30, "reason": "done", "video": True}
r = std_grade(GOOD, "pass"); check(r["success"] == 1 and r["infra_error"] == 0 and r["grader_error"] == 0, "standard: a pass stays a pass", r)
r = std_grade({**GOOD, "success": False, "replay_success": False, "reason": "horizon"}, "fail"); check(r["success"] == 0 and r["infra_error"] == 0 and r["grader_error"] == 0, "standard: the agent's failure stays the agent's 0", r)
r = std_grade(None, "missing"); check(r == {"success": 0, "finalized": 0, "deterministic": 0, "infra_error": 1, "missing_log": 1, "grader_error": 0}, "standard: no final.json -> infra_error (was the agent's 0)", r)
r = std_grade('{"success": true, "fin', "corrupt"); check(r["success"] == 0 and r["infra_error"] == 1 and r["grader_error"] == 1, "standard: a truncated final.json -> infra_error + grader_error, reward written (was no reward)", r)
r = std_grade("null", "null"); check(r["infra_error"] == 1 and r["grader_error"] == 1, "standard: final.json = null -> infra_error", r)
r = std_grade({"success": True, "finalized": False, "done": True, "reason": "done"}, "unfinalized"); check(r["success"] == 0 and r["infra_error"] == 1 and r["live_success"] == 1 and r["finalized"] == 0, "standard: the service's unfinalized copy (hook killed) -> infra_error (was the agent's 0)", r)
r = std_grade({**GOOD, "replay_success": False, "deterministic": False, "replay_failed": 1, "infra_error": 1}, "replayfailed"); check(r["infra_error"] == 1 and r["grader_error"] == 1 and r["success"] == 0, "standard: replay_failed -> infra_error + grader_error", r)
r = std_grade({**GOOD, "instance_mismatch": 1, "infra_error": 1}, "mismatch"); check(r["infra_error"] == 1 and r["instance_mismatch"] == 1 and r["success"] == 0, "standard: instance_mismatch -> infra_error", r)
r = std_grade({"success": False, "done": True, "reason": "sim_crashed_on_call", "finalized": True, "gave_up": True}, "giveup_call"); check(r["success"] == 0 and r["infra_error"] == 0 and r["gave_up"] == 1 and r["sim_crashed_on_call"] == 1, "standard: give-up after crashes during a call stays the agent's failure", r)
r = std_grade({"success": False, "done": True, "reason": "resume_failed", "finalized": True, "gave_up": True, "infra_error": 1}, "giveup_infra"); check(r["infra_error"] == 1 and r["success"] == 0, "standard: give-up with infra_error -> infra_error", r)

# ------------------------------------------------------------------ finalize.sh (the real script; stub `end` and stub tool)
def finalize(name, beh, *, end_rc=0, episode=True, pre_final=None, budget=None):
    d = os.path.join(td, "fin_" + name); data, srv, bind = (os.path.join(d, x) for x in ("data", "srv", "bin"))
    for x in (data, srv, bind): os.makedirs(x)
    os.symlink(PY, os.path.join(bind, "python"))
    open(os.path.join(srv, "rcb_limited.py"), "w").write(f"import sys\nsys.exit({end_rc})\n")
    tool = os.path.join(srv, "tool.py"); open(tool, "w").write(textwrap.dedent("""
        import json, os, sys, time
        out = sys.argv[sys.argv.index("--out") + 1]; n = os.path.basename(out)[6]
        beh = json.loads(os.environ["STUB"]).get(n, "ok")
        res = {"success": True, "state_sha": "abc", "instance_ok": True, "video": "--video" in sys.argv}
        if beh == "die": os._exit(137)
        if beh == "hang": time.sleep(600)
        if beh == "fail": res["success"] = False
        if beh == "mismatch": res["instance_ok"] = False
        if beh == "othersha": res["state_sha"] = "zzz"
        if beh == "novideo": res["video"] = False
        open(out, "w").write(json.dumps(res))
        """))
    if episode: json.dump({"success": True, "n_actions": 30, "control_steps": 30, "reason": "done", "live_sha": "abc"}, open(os.path.join(data, "episode.json"), "w"))
    if pre_final is not None: json.dump(pre_final, open(os.path.join(data, "final.json"), "w"))
    open(os.path.join(data, "trajectory.npz"), "wb").write(b"x")
    f = os.path.join(d, "finalize.sh"); open(f, "w").write(open(os.path.join(T_STD, "environment/sim/finalize.sh")).read().replace("/srv", srv))
    env = {**os.environ, "PATH": bind + ":" + os.environ["PATH"], "RCB_DATA": data, "RCB_TOOL": tool, "RCB_INSTANCE": "/x", "STUB": json.dumps(beh),
           **({"RCB_HOOK_BUDGET_S": str(budget)} if budget else {})}
    t0 = time.time(); p = subprocess.run(["sh", f], capture_output=True, text=True, env=env, timeout=200); assert p.returncode == 0, (p.stdout, p.stderr)
    fin = json.load(open(os.path.join(data, "final.json"))); assert not os.path.exists(os.path.join(data, "final.json.tmp"))
    return fin, std_grade(fin, "fin_" + name), time.time() - t0, p.stdout
fin, r, _, _ = finalize("ok", {}); check(fin["finalized"] and fin["replay_success"] and fin["deterministic"] and fin["video"] is True and r["success"] == 1 and r["video_rendered"] == 1, "finalize: good replays -> pass, video flagged", (fin, r))
fin, r, _, _ = finalize("novideo", {"3": "die"}); check(fin["replay_success"] and fin["video"] is False and r["success"] == 1, "finalize: the video replay dying does not touch the verdict", (fin, r))
fin, r, _, _ = finalize("fail", {"1": "fail", "2": "fail"}); check(not fin["replay_success"] and "infra_error" not in fin and r["success"] == 0 and r["infra_error"] == 0, "finalize: failing replays -> the agent's 0", (fin, r))
fin, r, _, _ = finalize("die", {"2": "die"}); check(fin.get("replay_failed") == 1 and fin["infra_error"] == 1 and r["infra_error"] == 1 and r["grader_error"] == 1, "finalize: a replay process that died -> replay_failed + infra_error", (fin, r))
fin, r, _, _ = finalize("mismatch", {"1": "mismatch"}); check(fin.get("instance_mismatch") == 1 and r["infra_error"] == 1, "finalize: replay not from the t = 0 state -> instance_mismatch + infra_error", (fin, r))
fin, r, _, _ = finalize("nondet", {"2": "othersha"}); check(not fin["deterministic"] and r["success"] == 0 and r["infra_error"] == 0, "finalize: replays ending in different states -> deterministic 0", (fin, r))
fin, r, dt, out = finalize("hang", {"1": "hang"}, budget=44); check(fin["finalized"] and fin.get("replay_failed") == 1 and fin["infra_error"] == 1 and r["infra_error"] == 1 and dt < 60, f"finalize: a hanging replay is ended at its share of the hook's time ({dt:.0f} s) and recorded as infra_error in a finalized final.json", (fin, r, out))
fin, r, _, _ = finalize("endrc1", {}, end_rc=1, pre_final={"success": True, "finalized": False}); check(fin["finalized"] and fin["infra_error"] == 1 and r["infra_error"] == 1 and r["success"] == 0, "finalize: the service never ended the episode -> infra_error", (fin, r))
gave = {"success": False, "finalized": True, "gave_up": True, "reason": "sim_crashed_on_call"}
fin, r, _, _ = finalize("endrc2", {}, end_rc=2, pre_final=gave); check(fin == gave and r["infra_error"] == 0, "finalize: a give-up verdict on disk is kept", (fin, r))
ct = float(re.search(r'command = "sh /srv/finalize.sh".*\ntimeout_sec = (\d+)', open(os.path.join(T_STD, "task.toml")).read()).group(1))
hb = float(re.search(r"RCB_HOOK_BUDGET_S:-(\d+)", open(os.path.join(T_STD, "environment/sim/finalize.sh")).read()).group(1))
check(hb < ct, "finalize: the hook's own deadline is before the collect timeout", (hb, ct))

# ------------------------------------------------------------------ privileged grade.py
def priv_grade(name, make_traj, beh=None, log_bytes=None, budget=None):
    d = os.path.join(td, "priv_" + name); tests, log = os.path.join(d, "tests"), os.path.join(d, "log"); os.makedirs(tests); os.makedirs(log)
    traj = os.path.join(d, "trajectory.npz")
    if make_traj: make_traj(traj)
    shutil.copy(os.path.join(T_PRIV, "tests/grade.py"), tests)
    if log_bytes is not None:                              # the agent's session log (self-reported cost), read from here instead of /app/output
        slog = os.path.join(d, "rcb_session_log.jsonl"); open(slog, "wb").write(log_bytes); g = os.path.join(tests, "grade.py")
        src = open(g).read(); assert '"/app/output/rcb_session_log.jsonl"' in src; open(g, "w").write(src.replace('"/app/output/rcb_session_log.jsonl"', repr(slog)))
    json.dump({"family": "pick", "t0": {"action_dim": 8}}, open(os.path.join(tests, "instance.json"), "w"))
    open(os.path.join(tests, "rcb_molmospaces.py"), "w").write(textwrap.dedent("""
        import json, os, sys, time
        out = sys.argv[sys.argv.index("--out") + 1]; beh = os.environ.get("STUB", "ok")
        if beh == "die": os._exit(137)
        if beh == "hang": time.sleep(600)
        res = {"success": beh != "fail", "state_sha": "abc", "instance_ok": beh != "mismatch", "executed_rows": 30, "horizon": 30, "reached_horizon": True, "replay_s": 1.0, "video": "--video" in sys.argv}
        open(out, "w").write(json.dumps(res))
        """))
    p = subprocess.run([PY, os.path.join(tests, "grade.py"), "--instance", os.path.join(tests, "instance.json"), "--traj", traj], capture_output=True, text=True,
                       env={**os.environ, "RCB_VERIFIER_LOG_DIR": log, "STUB": beh or "ok", **({"RCB_VERIFIER_BUDGET_S": str(budget)} if budget else {})}, timeout=120)
    assert p.returncode == 0, p.stderr
    r = json.load(open(os.path.join(log, "reward.json"))); txt = open(os.path.join(log, "reward.txt")).read().strip()
    assert all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in r.values()), r
    assert txt == str(r["success"]) and "deterministic" in r and "grader_error" in r, (txt, r)
    return r
A = np.zeros((30, 8))
r = priv_grade("pass", lambda p: np.savez(p, actions=A, family="pick")); check(r["success"] == 1 and r["grader_error"] == 0, "privileged: a pass stays a pass", r)
r = priv_grade("fail", lambda p: np.savez(p, actions=A, family="pick"), "fail"); check(r["success"] == 0 and r["grader_error"] == 0, "privileged: a failing trajectory is the agent's 0", r)
r = priv_grade("missing", None); check(r["missing_trajectory"] == 1 and r["grader_error"] == 0, "privileged: missing_trajectory", r)
r = priv_grade("notnpz", lambda p: open(p, "wb").write(b"garbage")); check(r.get("bad_trajectory") == 1 and r["grader_error"] == 0, "privileged: not an npz -> bad_trajectory (was grader_error)", r)
r = priv_grade("object", lambda p: np.savez(p, actions=np.array([[None] * 8], dtype=object))); check(r.get("bad_trajectory") == 1 and r["grader_error"] == 0, "privileged: pickled / object actions -> bad_trajectory (was grader_error)", r)
r = priv_grade("strings", lambda p: np.savez(p, actions=np.array([["a"] * 8]))); check(r.get("bad_trajectory") == 1 and r["grader_error"] == 0, "privileged: non-numeric actions -> bad_trajectory", r)
r = priv_grade("npy", lambda p: np.save(open(p, "wb"), A)); check(r.get("bad_trajectory") == 1 and r["grader_error"] == 0, "privileged: a bare .npy -> bad_trajectory", r)
r = priv_grade("noactions", lambda p: np.savez(p, rows=A)); check(r.get("bad_trajectory") == 1, "privileged: no `actions` -> bad_trajectory", r)
r = priv_grade("shape", lambda p: np.savez(p, actions=np.zeros((30, 7)))); check(r.get("bad_trajectory") == 1 and r["n_actions"] == 30, "privileged: wrong width -> bad_trajectory", r)
r = priv_grade("family", lambda p: np.savez(p, actions=A, family="open")); check(r.get("wrong_family") == 1 and r["grader_error"] == 0, "privileged: wrong_family", r)
r = priv_grade("die", lambda p: np.savez(p, actions=A), "die"); check(r["grader_error"] == 1 and r["success"] == 0, "privileged: a replay process that died -> grader_error", r)
t0 = time.time(); r = priv_grade("hang", lambda p: np.savez(p, actions=A), "hang", budget=44); dt = time.time() - t0
check(r["grader_error"] == 1 and r["replay_timed_out"] == 1 and r["infra_error"] == 1 and dt < 60, f"privileged: hanging replays share the verifier's budget and end at it ({dt:.0f} s) -> replay_timed_out + infra_error", r)
r = priv_grade("mismatch", lambda p: np.savez(p, actions=A), "mismatch"); check(r["grader_error"] == 1 and r["instance_mismatch"] == 1, "privileged: instance_mismatch -> grader_error", r)
BAD_LOG = b'{"ev": "session_start"}\n{"ev": "reset", "note": "\xff\xfe"}\n\x00\n{"ev": "session_start"}\n' + b"x" * 2**20 + b"\n"   # not UTF-8, a NUL, a 1 MB line
r = priv_grade("badlog_pass", lambda p: np.savez(p, actions=A, family="pick"), log_bytes=BAD_LOG); check(r["success"] == 1 and r["grader_error"] == 0 and r["agent_sessions"] == 2 and r["agent_resets"] == 1, "privileged: a session log that is not UTF-8 costs no verdict (was no reward file)", r)
r = priv_grade("badlog_missing", None, log_bytes=BAD_LOG); check(r["missing_trajectory"] == 1 and r["grader_error"] == 0 and r["agent_sessions"] == 2, "privileged: the same log without a trajectory -> missing_trajectory", r)

# ------------------------------------------------------------------ the service: malformed requests
SIM = os.path.join(T_STD, "environment/sim")
sys.path[:0] = [SIM]
os.environ.update(RCB_DATA=tempfile.mkdtemp(), RCB_INSTANCE="/x", RCB_ACTION_UNITS="rad", RCB_STARTUP_TIMEOUT_S="600")
import importlib.util as _u
_s = _u.spec_from_file_location("rcb_molmospaces", os.path.join(HERE, "stub_ms", "rcb_molmospaces.py")); _m = _u.module_from_spec(_s); _s.loader.exec_module(_m); sys.modules["rcb_molmospaces"] = _m
import rcb_limited as L, rcb1
got = []; L.serve = lambda svc, port=8000: got.append(svc)
runpy.run_path(os.path.join(SIM, "server.py"), run_name="server"); svc = got[0]
httpd = HTTPServer(("127.0.0.1", 0), L.make_handler(svc)); threading.Thread(target=httpd.serve_forever, daemon=True).start()
U = f"http://127.0.0.1:{httpd.server_address[1]}"
def post(path, body, raw=None):
    r = requests.post(U + path, data=raw if raw is not None else json.dumps(body), timeout=60)
    return r.status_code, (rcb1.decode(r.content)[0] if r.status_code == 200 and r.content[:4] == rcb1.MAGIC else (r.json() if r.content else {}))
status = lambda: requests.get(U + "/status", timeout=10).json()  # noqa: E731
A2 = np.zeros((2, 8)).tolist(); ok = {"type": "joint_position", "actions": A2, "video": "none"}
for what, body in [("dt null", {**ok, "dt": None}), ("dt string", {**ok, "dt": "0.066"}), ("dt list", {**ok, "dt": [0.066]}), ("dt bool", {**ok, "dt": True}), ("dt not a multiple", {**ok, "dt": 0.1}),
                   ("dt 0", {**ok, "dt": 0}), ("dt negative", {**ok, "dt": -0.066}), ("video_fps 0", {**ok, "video_fps": 0}), ("video_fps string", {**ok, "video_fps": "5"}),
                   ("note number", {**ok, "note": 7}), ("note list", {**ok, "note": []}) if False else ("note dict", {**ok, "note": {"a": 1}}), ("cameras number", {**ok, "cameras": 3}),
                   ("cameras string", {**ok, "cameras": "wrist"}), ("cameras of numbers", {**ok, "cameras": [1]}), ("cameras unknown", {**ok, "cameras": ["nope"]}), ("cameras dict", {**ok, "cameras": {"wrist": 1}}),
                   ("interpolate null", {**ok, "interpolate": None}), ("interpolate list", {**ok, "interpolate": ["hold"]}), ("video null", {**ok, "video": None}), ("video list", {**ok, "video": ["mp4"]}),
                   ("type null", {**ok, "type": None}), ("type list", {**ok, "type": ["done"]}), ("type unknown", {**ok, "type": "ee_pose"}), ("depth number", {**ok, "depth": 4}),
                   ("actions wrong width", {**ok, "actions": [[0] * 7]}), ("actions strings", {**ok, "actions": [["a"] * 8]}), ("done with cameras number", {"type": "done", "cameras": 5})]:
    code, meta = post("/submit", body); st = status()
    check(code == 400 and st["control_steps"] == 0 and not st["done"] and st["calls"] == 0, f"submit {what} -> 400, nothing moved, episode alive", (code, meta, st))
for what, raw in (("dt NaN", '{"type": "joint_position", "actions": %s, "dt": NaN}' % json.dumps(A2)), ("dt Infinity", '{"type": "joint_position", "actions": %s, "dt": Infinity}' % json.dumps(A2))):
    code, meta = post("/submit", None, raw=raw); check(code == 400 and status()["control_steps"] == 0, f"submit {what} -> 400", (code, meta))
for what, body in [("seconds null", {"seconds": None}), ("seconds string", {"seconds": "1"}), ("seconds list", {"seconds": [1]}), ("seconds negative", {"seconds": -1}), ("seconds 31", {"seconds": 31}),
                   ("cameras number", {"cameras": 3}), ("video null", {"video": None}), ("video_fps 0", {"seconds": 1, "video_fps": 0})]:
    code, meta = post("/observe", body); st = status()
    check(code == 400 and st["control_steps"] == 0 and not st["done"], f"observe {what} -> 400, nothing moved", (code, meta, st))
code, meta = post("/observe", None, raw='{"seconds": NaN}'); check(code == 400, "observe seconds NaN -> 400", (code, meta))
code, meta = post("/submit", {**ok, "note": None, "video_fps": None, "cameras": None, "dt": 0.132}); check(code == 200 and meta["control_steps_chunk"] == 4 and status()["control_steps"] == 4, "a valid submit runs (null note / video_fps / cameras = not given)", (code, meta))
code, meta = post("/observe", {"seconds": 0.2, "video": "none"})
check(code == 200 and meta["control_steps_watch"] == 3 and abs(meta["seconds"] - 0.198) < 1e-9, "observe(0.2 s) at a 66 ms period runs 3 control steps and reports seconds = 0.198 (what ran)", (code, meta.get("seconds")))
code, meta = post("/observe", {}); check(code == 200 and meta["seconds"] == 0 and meta["control_steps_watch"] == 0, "observe() moves nothing", meta.get("seconds"))
code, meta = post("/observe", {"seconds": 30, "video": "none"})
check(code == 200 and meta["done"] and meta["reason"] == "horizon" and meta["control_steps_watch"] == 23 and abs(meta["seconds"] - 23 * 0.066) < 1e-9, "observe past the horizon reports the seconds it ran before the episode ended", (code, meta.get("seconds"), meta.get("reason")))
log = [json.loads(l) for l in open(os.path.join(os.environ["RCB_DATA"], "episode.jsonl"))]
check(not any(e.get("ev") == "error" for e in log), "no simulator error was logged by any malformed request")
print(f"\n{n_ok} checks passed"); sys.stdout.flush(); os._exit(0)
