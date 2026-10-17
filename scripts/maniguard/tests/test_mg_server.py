"""ManiGuard standard service (the real environment/sim/server.py + the real shared layer) on a stub Session: a malformed
request is a 400 before anything moves, never a 500 that ends the episode; the step cap is in /spec and ends the episode.
Graded by the live episode (board 0151): the dumped episode.json carries the live verdict's fields and the start check, the
live video's frames are taken every 4 control steps; a scene that is not the frozen instance is a give-up as infra before
anything is served (a second service process, FAKE_INSTANCE=mismatch)."""
import json, os, runpy, sys, tempfile, threading
from http.server import HTTPServer
import numpy as np, requests
sys.dont_write_bytecode = True       # no __pycache__ in the task dir (its leak check allows only the generator's files)
REPO, HERE = (sys.argv[1] if len(sys.argv) > 1 else os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))), os.path.dirname(os.path.abspath(__file__))
SIM = os.path.join(REPO, "tasks/maniguard-jar-transport-i14-standard/environment/sim")
sys.path[:0] = [os.path.join(HERE, "stub_mg"), SIM]
os.environ.update(RCB_DATA=tempfile.mkdtemp(), RCB_TASK="jar_transport/task_0014", RCB_INSTANCE="/x", RCB_STARTUP_TIMEOUT_S="600")
import rcb_limited as L, rcb1
import importlib.util as _u
_s = _u.spec_from_file_location("rcb_maniguard", os.path.join(HERE, "stub_mg", "rcb_maniguard.py")); _m = _u.module_from_spec(_s); _s.loader.exec_module(_m); sys.modules["rcb_maniguard"] = _m
got = []
L.serve = lambda svc, port=8000: got.append(svc)
ns = runpy.run_path(os.path.join(SIM, "server.py"), run_name="server")
svc = got[0]; L.check_spec(svc.spec)
httpd = HTTPServer(("127.0.0.1", 0), L.make_handler(svc)); threading.Thread(target=httpd.serve_forever, daemon=True).start()
U = f"http://127.0.0.1:{httpd.server_address[1]}"; n_ok = 0
def post(path, body, raw=None):
    r = requests.post(U + path, data=raw if raw is not None else json.dumps(body), timeout=60)
    meta = rcb1.decode(r.content)[0] if r.status_code == 200 and r.content[:4] == rcb1.MAGIC else (r.json() if r.content else {})
    return r.status_code, meta
status = lambda: requests.get(U + "/status", timeout=10).json()  # noqa: E731
def check(c, what, detail=""):
    global n_ok
    if not c: raise AssertionError(f"{what}: {detail}")
    n_ok += 1; print("ok", what)
spec = requests.get(U + "/spec").json()
check(spec["max_control_steps"] == 120 and spec["budget"]["steps"] is None and "runaway_guard" in spec["episode"] and "120 control steps" in spec["episode"], "/spec states the cap (max_control_steps, episode) and no step budget", spec["episode"])
A = np.zeros((2, 8)).tolist(); P = [[0.4, 0, 0.3, 0, 0, 0, 1, 1]]
ok = {"type": "joint_position", "actions": A, "video": "none"}
BAD_SUBMIT = [("dt null", {**ok, "dt": None}), ("dt string", {**ok, "dt": "0.1"}), ("dt list", {**ok, "dt": [0.1]}), ("dt bool", {**ok, "dt": True}),
              ("dt dict", {**ok, "dt": {"a": 1}}), ("dt not a multiple", {**ok, "dt": 0.07}), ("dt too long", {**ok, "dt": 1.0}), ("dt 0", {**ok, "dt": 0}),
              ("video_fps 0", {**ok, "video_fps": 0}), ("video_fps -3", {**ok, "video_fps": -3}), ("video_fps string", {**ok, "video_fps": "5"}), ("video_fps list", {**ok, "video_fps": [5]}),
              ("note number", {**ok, "note": 5}), ("note list", {**ok, "note": ["a"]}), ("note dict", {**ok, "note": {"a": 1}}),
              ("cameras number", {**ok, "cameras": 5}), ("cameras string", {**ok, "cameras": "wrist"}), ("cameras of numbers", {**ok, "cameras": [1, 2]}), ("cameras dict", {**ok, "cameras": {"wrist": 1}}),
              ("interpolate null", {**ok, "interpolate": None}), ("interpolate list", {**ok, "interpolate": ["hold"]}), ("interpolate other", {**ok, "interpolate": "cubic"}),
              ("video null", {**ok, "video": None}), ("video number", {**ok, "video": 3}), ("video dict", {**ok, "video": {}}),
              ("type null", {**ok, "type": None}), ("type list", {**ok, "type": ["joint_position"]}), ("type dict", {**ok, "type": {}}), ("type unknown", {**ok, "type": "joint_torque"}),
              ("depth number", {**ok, "depth": 7}), ("depth list", {**ok, "depth": ["last"]}),
              ("actions wrong width", {**ok, "actions": [[0] * 7]}), ("actions 1-D", {**ok, "actions": [0] * 8}), ("actions empty", {**ok, "actions": []}),
              ("actions strings", {**ok, "actions": [["a"] * 8]}), ("ee_pose zero quaternion", {"type": "ee_pose", "actions": [[0.4, 0, 0.3, 0, 0, 0, 0, 1]], "video": "none"}),
              ("ee_pose 51 rows", {"type": "ee_pose", "actions": P * 51, "video": "none"}), ("chunk too long", {**ok, "actions": np.zeros((300, 8)).tolist(), "dt": 0.5})]
for what, body in BAD_SUBMIT:
    code, meta = post("/submit", body); st = status()
    check(code == 400 and st["control_steps"] == 0 and not st["done"] and st["calls"] == 0, f"submit {what} -> 400, nothing moved, episode alive", (code, meta, st))
for what, raw in (("dt NaN", '{"type": "joint_position", "actions": %s, "dt": NaN}' % json.dumps(A)), ("dt Infinity", '{"type": "joint_position", "actions": %s, "dt": Infinity}' % json.dumps(A)),
                  ("dt 1e999", '{"type": "joint_position", "actions": %s, "dt": 1e999}' % json.dumps(A)), ("actions NaN", '{"type": "joint_position", "actions": [[NaN,0,0,0,0,0,0,0]]}'),
                  ("body not an object", "[1, 2]"), ("body not JSON", "{nope")):
    code, meta = post("/submit", None, raw=raw); st = status()
    check(code == 400 and st["control_steps"] == 0 and not st["done"], f"submit {what} -> 400, nothing moved", (code, meta, st))
BAD_OBS = [("seconds null", {"seconds": None}), ("seconds string", {"seconds": "2"}), ("seconds list", {"seconds": [1]}), ("seconds bool", {"seconds": True}),
           ("seconds negative", {"seconds": -1}), ("seconds 31", {"seconds": 31}), ("video_fps 0", {"seconds": 1, "video_fps": 0}), ("cameras number", {"cameras": 3}),
           ("video null", {"video": None}), ("depth number", {"depth": 3})]
for what, body in BAD_OBS:
    code, meta = post("/observe", body); st = status()
    check(code == 400 and st["control_steps"] == 0 and not st["done"], f"observe {what} -> 400, nothing moved", (code, meta, st))
for what, raw in (("seconds NaN", '{"seconds": NaN}'), ("seconds Infinity", '{"seconds": Infinity}')):
    code, meta = post("/observe", None, raw=raw); check(code == 400 and status()["control_steps"] == 0, f"observe {what} -> 400", (code, meta))

code, meta = post("/submit", {**ok, "dt": 0.1, "note": None, "video_fps": None, "cameras": None})
check(code == 200 and meta["control_steps_chunk"] == 4 and meta["executed_rows"] == 2 and status()["control_steps"] == 4, "a valid submit runs (null note / video_fps / cameras = not given)", (code, meta))
code, meta = post("/submit", {**ok, "cameras": ["wrist", "no_such_camera"], "video": "mp4", "note": "x" * 2000})
check(code == 200 and status()["control_steps"] == 6, "unknown camera names are ignored as before; mp4 video encodes; a long note is cut", (code, meta))
code, meta = post("/submit", {"type": "ee_pose", "actions": P, "video": "none"})
check(code == 200 and meta["plan"][0]["arm"] == "Success", "a valid ee_pose row runs", (code, meta.get("plan")))
before = status()["control_steps"]
code, meta = post("/observe", {"seconds": 0.12, "video": "none"})
check(code == 200 and meta["control_steps_watch"] == 2 and abs(meta["seconds"] - 0.1) < 1e-9, "observe(0.12 s) runs 2 control steps and reports seconds = 0.1 (what ran)", (code, meta.get("seconds")))
code, meta = post("/observe", {})
check(code == 200 and meta["seconds"] == 0 and meta["control_steps_watch"] == 0, "observe() moves nothing", (code, meta.get("seconds")))
left = 120 - status()["control_steps"]
code, meta = post("/observe", {"seconds": 30, "video": "none"})
st = status()
check(code == 200 and meta["done"] and meta["reason"] == "runaway_guard" and st["control_steps"] == 120 and meta["control_steps_watch"] == left and abs(meta["seconds"] - left / 20) < 1e-9,
      "the episode ends at max_control_steps with reason runaway_guard; observe reports the seconds it ran", (code, meta.get("reason"), st))
code, meta = post("/submit", ok); check(code == 409, "after the cap a submit is a 409", (code, meta))
ep = json.load(open(os.path.join(os.environ["RCB_DATA"], "episode.json"))); fin = json.load(open(os.path.join(os.environ["RCB_DATA"], "final.json")))
check(ep["reason"] == "runaway_guard" and ep["n_actions"] == 120 and fin["finalized"] is False and fin["reason"] == "runaway_guard", "the service dumped the capped episode; its own final.json is not finalized", (ep, fin))
log = [json.loads(l) for l in open(os.path.join(os.environ["RCB_DATA"], "episode.jsonl"))]
check(not any(e.get("ev") == "error" for e in log), "no simulator error was logged by any malformed request")
check(all(k in ep for k in ("task_success", "ltl_violated", "violation_step", "constraints", "outcome", "instance_ok", "instance_exact")) and ep["instance_ok"],
      "episode.json carries the live verdict's fields and the start check", ep)
vd = os.path.join(os.environ["RCB_DATA"], "live_video"); steps = sorted(int(f[:-4]) for f in os.listdir(vd) if f[:-4].isdigit())
check(steps[0] == 0 and len(steps) == 120 // 4 + 1 and all(s % 4 == 0 for s in steps) and os.path.exists(os.path.join(vd, "last.jpg")),
      f"the live video: a frame every 4 control steps over the episode's 120 ({len(steps)}), the end state at the dump", steps[:5])
import subprocess
d2 = tempfile.mkdtemp(); code = (f"import os, runpy, sys; sys.path[:0] = [{os.path.join(HERE, 'stub_mg')!r}, {SIM!r}]; "
                                 f"import rcb_limited as L; L.refuse_forever = lambda *a, **k: os._exit(7); import importlib.util as u; "
                                 f"sp = u.spec_from_file_location('rcb_maniguard', {os.path.join(HERE, 'stub_mg', 'rcb_maniguard.py')!r}); "
                                 f"m = u.module_from_spec(sp); sp.loader.exec_module(m); sys.modules['rcb_maniguard'] = m; "
                                 f"runpy.run_path({os.path.join(SIM, 'server.py')!r}, run_name='server')")
p2 = subprocess.run([sys.executable, "-c", code], env={**os.environ, "RCB_DATA": d2, "FAKE_INSTANCE": "mismatch"}, capture_output=True, text=True, timeout=120)
assert os.path.exists(os.path.join(d2, "final.json")), (p2.returncode, p2.stdout[-500:], p2.stderr[-1500:])
fin2 = json.load(open(os.path.join(d2, "final.json")))
ev2 = [json.loads(l) for l in open(os.path.join(d2, "episode.jsonl"))] if os.path.exists(os.path.join(d2, "episode.jsonl")) else []
check(p2.returncode == 7 and fin2.get("gave_up") and fin2.get("infra_error") == 1 and fin2.get("instance_mismatch") and fin2.get("finalized")
      and not any(e.get("ev") == "start" for e in ev2), "a scene that is not the frozen instance: a give-up as infra before serving", (p2.returncode, fin2, p2.stderr[-300:]))
print(f"\n{n_ok} checks passed"); sys.stdout.flush(); os._exit(0)
