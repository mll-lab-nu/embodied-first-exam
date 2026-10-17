"""The real environment/sim/server.py of RoboLab and YAMLab + the real eai-standard/2.2 layer, on a fake simulator:
malformed requests are 400s that execute nothing and leave the episode alive; valid requests still run; the step cap is in
/spec and ends the episode with reason step_guard. Graded by the live episode (board 0151): the start-state check gives up
as an infrastructure failure before serving (instance_mismatch); the live video's frames are written during the episode
and a broken camera stops the video, never the episode."""
import json, os, signal, socket, subprocess, sys, tempfile, time, urllib.error, urllib.request
ROOT = (sys.argv[1] if len(sys.argv) > 1 else os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))); HERE = os.path.dirname(os.path.abspath(__file__)); LAYER = os.path.join(ROOT, "scripts/eai_standard")
sys.dont_write_bytecode = True; sys.path.insert(0, LAYER)
import rcb1
bad = 0
def check(ok, what):
    global bad
    if not ok: bad += 1
    print("ok  " if ok else "FAIL", what)
def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p
class Srv:
    def __init__(self, bench, env=None, probe="status"):
        self.td = tempfile.mkdtemp(prefix=f"srv_{bench}_"); self.port = free_port(); self.bench = bench
        e = {"PATH": "/usr/bin:/bin", "RCB_DATA": os.path.join(self.td, "data"), "TEST_PORT": str(self.port), "RCB_WALL_CLOCK_S": "5400",
             "PYTHONDONTWRITEBYTECODE": "1", **(env or {})}
        self.log = open(os.path.join(self.td, "server.log"), "w")
        self.p = subprocess.Popen([sys.executable, os.path.join(HERE, "run_server.py"), os.path.join(ROOT, "scripts", bench, "template/standard/environment/sim/server.py"),
                                   os.path.join(HERE, "stubs", bench), LAYER], env=e, stdout=self.log, stderr=subprocess.STDOUT, cwd=self.td)
        for _ in range(100):
            try:
                if probe == "connect":       # ready, found without a request (what a healthcheck may do): the agent's clock stays at 0
                    socket.create_connection(("127.0.0.1", self.port), timeout=2).close(); return
                self.get("/status"); return
            except Exception:
                if self.p.poll() is not None: break
                time.sleep(0.1)
        raise RuntimeError(f"server did not start: {open(os.path.join(self.td, 'server.log')).read()[-1500:]}")
    def get(self, path):
        return json.loads(urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=30).read())
    def post(self, path, body, raw=None):
        data = raw if raw is not None else json.dumps(body).encode()
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, method="POST")
        try:
            r = urllib.request.urlopen(req, timeout=60); b = r.read()
            return r.status, (rcb1.decode(b)[0] if b[:4] == rcb1.MAGIC else json.loads(b))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read() or b"{}")
    def stop(self):
        self.p.kill(); self.p.wait(); self.log.close()

def run(bench, dim, ee_dim, hz):
    s = Srv(bench); spec = s.get("/spec")
    check(spec.get("max_control_steps") == 100000 and spec["budget"]["steps"] is None and "step_guard" in spec["episode"] and "100,000" in spec["episode"],
          f"{bench} /spec: max_control_steps 100000, budget.steps null, the cap in `episode`")
    row = [0.0] * dim; good = {"type": "joint_position", "actions": [row], "dt": 1.0 / hz}
    ee = ([0.4, 0.0, 0.5, 1, 0, 0, 0, 0.0] * (ee_dim // 8))
    def eerow(**kw):
        r = list(ee)
        for i, v in kw.items(): r[int(i[1:])] = v
        return {"type": "ee_pose", "actions": [r]}
    submits = {
        "dt string": {**good, "dt": "0.1"}, "dt list": {**good, "dt": [0.1]}, "dt bool": {**good, "dt": True}, "dt object": {**good, "dt": {"a": 1}},
        "dt 0": {**good, "dt": 0}, "dt negative": {**good, "dt": -0.1}, "dt too long": {**good, "dt": 0.6}, "dt not a multiple": {**good, "dt": 1.5 / hz},
        "video_fps 0": {**good, "video_fps": 0}, "video_fps -1": {**good, "video_fps": -1}, "video_fps string": {**good, "video_fps": "5"},
        "video_fps bool": {**good, "video_fps": True}, "video_fps 31": {**good, "video_fps": 31}, "video_fps list": {**good, "video_fps": [5]},
        "note int": {**good, "note": 5}, "note list": {**good, "note": ["x"]}, "note object": {**good, "note": {"a": 1}},
        "cameras int": {**good, "cameras": 5}, "cameras object": {**good, "cameras": {"a": 1}}, "cameras list of ints": {**good, "cameras": [1, 2]},
        "cameras a string": {**good, "cameras": "cam"},   # a list of names since the shared layer's parse_request (#132), never a bare string
        "interpolate int": {**good, "interpolate": 3}, "interpolate unknown": {**good, "interpolate": "cubic"}, "interpolate list": {**good, "interpolate": ["hold"]},
        "video int": {**good, "video": 7}, "video unknown": {**good, "video": "gif"}, "video object": {**good, "video": {}},
        "type null": {**good, "type": None}, "type int": {**good, "type": 5}, "type list": {**good, "type": ["joint_position"]},
        "type object": {**good, "type": {"a": 1}}, "type not yet": {**good, "type": "joint_velocity"}, "type missing": {"actions": [row]},
        "depth unknown": {**good, "depth": "bogus"}, "depth int": {**good, "depth": 3},
        "actions wrong dim": {**good, "actions": [row + [0.0]]}, "actions 1-D": {**good, "actions": row}, "actions null": {**good, "actions": None},
        "actions string": {**good, "actions": "abc"}, "actions ragged": {**good, "actions": [row, row[:-1]]}, "actions empty": {**good, "actions": []},
        "chunk too long": {**good, "actions": [row] * (10 * hz + 1)},
        "ee far (5 m)": eerow(i0=5.0), "ee huge (1e300)": eerow(i1=1e300), "ee huge negative": eerow(i2=-1e200), "ee zero quaternion": eerow(i3=0.0),
        "ee 51 rows": {"type": "ee_pose", "actions": [ee] * 51}, "ee wrong dim": {"type": "ee_pose", "actions": [ee[:-1]]},
    }
    if ee_dim == 16: submits.update({"ee right arm far": eerow(i8=9.0), "ee right zero quaternion": eerow(i11=0.0)})
    raws = {"dt 1e400 (inf)": json.dumps(good).replace(f'"dt": {1.0 / hz}', '"dt": 1e400'), "dt 10**400 (int)": json.dumps(good).replace(f'"dt": {1.0 / hz}', '"dt": 1' + "0" * 400),
            "actions NaN": json.dumps({**good, "actions": [[float("nan")] * dim]}), "body is a list": "[1, 2]", "body not JSON": "{nope"}
    observes = {"seconds string": {"seconds": "1"}, "seconds negative": {"seconds": -1}, "seconds 31": {"seconds": 31}, "seconds list": {"seconds": [1]},
                "seconds bool": {"seconds": True}, "seconds object": {"seconds": {}}, "obs video_fps 0": {"seconds": 0.1, "video_fps": 0},
                "obs cameras int": {"cameras": 7}, "obs video int": {"video": 1}, "obs depth unknown": {"depth": "x"}}
    n_bad = 0
    for name, body in submits.items():
        code, out = s.post("/submit", body); n_bad += code != 400
        if code != 400: check(False, f"{bench} submit {name}: {code} {str(out)[:160]}")
    for name, raw in raws.items():
        code, out = s.post("/submit", None, raw=raw.encode()); n_bad += code != 400
        if code != 400: check(False, f"{bench} submit {name}: {code} {str(out)[:160]}")
    for name, body in observes.items():
        code, out = s.post("/observe", body); n_bad += code != 400
        if code != 400: check(False, f"{bench} observe {name}: {code} {str(out)[:160]}")
    st = s.get("/status")
    check(n_bad == 0 and st["control_steps"] == 0 and st["done"] is False and st["calls"] == 0,
          f"{bench}: {len(submits) + len(raws) + len(observes)} malformed requests -> 400 each, nothing executed, episode alive ({st})")
    # valid requests, null fields included (null = the default, as the client never sends them)
    code, m = s.post("/submit", {**good, "actions": [row] * 3, "note": "hello"}); check(code == 200 and m["control_steps_chunk"] == 3 and m["executed_rows"] == 3, f"{bench} valid joint_position: {code}")
    code, m = s.post("/submit", {**good, "dt": None, "video_fps": None, "note": None, "cameras": None, "interpolate": None, "video": None, "depth": None})
    check(code == 200 and m["control_steps_chunk"] == 1, f"{bench} null fields take their defaults: {code} {str(m)[:120] if code != 200 else ''}")
    code, m = s.post("/submit", {**good, "dt": 2.0 / hz, "interpolate": "hold", "cameras": [spec["default_cameras"][0]], "video": "none"})
    check(code == 200 and m["control_steps_chunk"] == 2, f"{bench} dt = 2 periods, one camera: {code}")
    code, m = s.post("/submit", {**good, "cameras": ["no_such_camera"]}); check(code == 200, f"{bench} unknown camera name falls back to all (unchanged): {code}")
    code, m = s.post("/submit", eerow(i0=0.45)); plan = (m.get("plan") or [{}])[0]
    check(code == 200 and all(v == "Success" for k, v in plan.items() if k.endswith("arm")) and 0 < m["control_steps_chunk"] < 200, f"{bench} valid ee_pose: {code} plan {plan}")
    code, m = s.post("/observe", {"seconds": 0.2}); check(code == 200 and m["control_steps_watch"] == round(0.2 * hz), f"{bench} valid observe 0.2 s: {code}")
    code, m = s.post("/observe", {"seconds": None, "video_fps": None}); check(code == 200 and m["control_steps_watch"] == 0, f"{bench} observe with null fields: {code}")
    st = s.get("/status"); check(st["done"] is False and st["control_steps"] > 7, f"{bench} episode still alive after the valid calls ({st['control_steps']} control steps)")
    ev = [json.loads(l) for l in open(os.path.join(s.td, "data", "episode.jsonl"))]
    check(any(e.get("ev") == "submit" and e.get("note") == "hello" for e in ev) and not any(e.get("ev") == "error" for e in ev), f"{bench} log: the note is recorded, no error event")
    # the residual in the shared layer (scripts/eai_standard/rcb_limited.py, not this slice): actions that numpy refuses with a
    # TypeError are converted before the adapter sees them -> 500, the episode ends. Reported, not asserted as fixed.
    code, m = s.post("/submit", {**good, "actions": {"a": 1}})
    print(f"note {bench} shared-layer residual: actions = an object -> {code} {str(m)[:90]}; done = {s.get('/status')['done']}")
    s.stop()
    # the step cap: the fake tooling's MAX_STEPS = 40
    s = Srv(bench, {"FAKE_MAX_STEPS": "40"}); spec = s.get("/spec"); check(spec["max_control_steps"] == 40, f"{bench} /spec max_control_steps follows the tooling's MAX_STEPS")
    code, m = s.post("/submit", {**good, "actions": [row] * 60})
    check(code == 200 and m["done"] is True and m["reason"] == "step_guard" and m["control_steps"] == 40, f"{bench} the cap ends the episode: reason {m.get('reason')}, {m.get('control_steps')} steps")
    code, m = s.post("/submit", good); check(code == 409, f"{bench} submit after the cap: {code}")
    fin = json.load(open(os.path.join(s.td, "data", "final.json"))); check(fin["reason"] == "step_guard" and fin["finalized"] is False and os.path.exists(os.path.join(s.td, "data", "trajectory.npz")),
                                                                         f"{bench} episode dumped for the collect hook (final.json reason {fin['reason']})")
    s.stop()
def clock(bench):
    """meta time_s / time_left_s count from the agent's first request (rcb_limited.agent_time), not from the service's start."""
    s = Srv(bench, probe="connect"); time.sleep(1.5)                  # up and idle: the harness is still being installed
    t = time.time(); spec = s.get("/spec"); code, m = s.post("/observe", {"seconds": None}); lag = time.time() - t
    check("first request" in spec["budget"].get("clock", "") and code == 200 and m["time_s"] <= lag + 0.1 and m["time_left_s"] >= 5400 - lag - 0.2,
          f"{bench} the clock starts at the first request, not with the service: time_s {m.get('time_s')}, time_left_s {m.get('time_left_s')} of 5400 ({lag:.2f} s after it)")
    s.stop()
def start_check(bench):
    """FAKE_INSTANCE=mismatch: the service gives up before serving (final.json: gave_up, infra_error 1, instance_mismatch) and
    answers 409; FAKE_INSTANCE=sha (hash differs, poses within tolerance): served, recorded instance_exact false."""
    td = tempfile.mkdtemp(prefix=f"inst_{bench}_"); port = free_port(); data = os.path.join(td, "data")
    e = {"PATH": "/usr/bin:/bin", "RCB_DATA": data, "TEST_PORT": str(port), "RCB_WALL_CLOCK_S": "5400", "PYTHONDONTWRITEBYTECODE": "1",
         "FAKE_INSTANCE": "mismatch", "RCB_PORT": str(port)}   # the refusal binds RCB_PORT
    log = open(os.path.join(td, "server.log"), "w")
    p = subprocess.Popen([sys.executable, os.path.join(HERE, "run_server.py"), os.path.join(ROOT, "scripts", bench, "template/standard/environment/sim/server.py"),
                          os.path.join(HERE, "stubs", bench), os.path.join(ROOT, "scripts/eai_standard")], env=e, stdout=log, stderr=subprocess.STDOUT, cwd=td)
    fin, code = {}, None
    for _ in range(200):
        try:
            fin = json.load(open(os.path.join(data, "final.json")))
            if fin.get("gave_up"): break
        except Exception:
            pass
        time.sleep(0.1)
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/status", timeout=5); code = 200; break
        except urllib.error.HTTPError as exc:
            code = exc.code; break
        except Exception:
            time.sleep(0.1)
    p.kill(); p.wait(); log.close()
    ev = [json.loads(l) for l in open(os.path.join(data, "episode.jsonl"))] if os.path.exists(os.path.join(data, "episode.jsonl")) else []
    check(fin.get("gave_up") and fin.get("infra_error") == 1 and fin.get("instance_mismatch") is True and fin.get("finalized") is True
          and fin.get("success") is False and code == 409 and not any(e.get("ev") == "start" for e in ev),
          f"{bench} instance mismatch at the start: a give-up as infra before anything is served (final {fin}, /status {code})")
    s = Srv(bench, {"FAKE_INSTANCE": "sha"}); code, m = s.post("/submit", {"type": "joint_position", "actions": [[0.0] * (8 if bench == "robolab" else 14)]})
    check(code == 200, f"{bench} instance hash differs but poses match: served ({code})")
    os.kill(s.p.pid, signal.SIGUSR1); s.p.wait(timeout=60); s.log.close()
    ep = json.load(open(os.path.join(s.td, "data", "episode.json")))
    check(ep.get("instance_exact") is False and ep.get("instance_matches") is True, f"{bench} episode.json records the start check ({ep.get('instance_exact')}, {ep.get('instance_matches')})")
def video(bench, dim, hz):
    """The live video: frames during the episode (RoboLab: every 3 control steps; YAMLab: only at steps a call rendered),
    the end state's frame at the dump; a broken camera stops the video and nothing else."""
    s = Srv(bench); row = [0.0] * dim
    code, m = s.post("/submit", {"type": "joint_position", "actions": [row] * 60, "dt": 1.0 / hz, "video_fps": 5})
    vd = os.path.join(s.td, "data", "live_video"); frames = sorted(f for f in os.listdir(vd) if f[:-4].isdigit())
    steps = [int(f[:-4]) for f in frames]; every = max(1, round(hz / 5))
    check(code == 200 and len(steps) >= 60 // every and all(b - a >= 1 for a, b in zip(steps, steps[1:])) and steps[0] == 0,
          f"{bench} live video: {len(steps)} frames over 60 control steps (one per {every}), first at step 0 ({steps[:6]})")
    os.kill(s.p.pid, signal.SIGUSR1); s.p.wait(timeout=60); s.log.close()
    check(os.path.exists(os.path.join(vd, "last.jpg")) and os.path.exists(os.path.join(s.td, "data", "episode.json")), f"{bench} the end state's frame is taken at the dump")
    s = Srv(bench, {"FAKE_VIDEO": "broken"})
    code, m = s.post("/submit", {"type": "joint_position", "actions": [row] * 10, "dt": 1.0 / hz}); st = s.get("/status")
    ev = [json.loads(l) for l in open(os.path.join(s.td, "data", "episode.jsonl"))]
    check(code == 200 and st["control_steps"] == 10 and not st["done"] and any(e.get("ev") == "live_video_stopped" for e in ev),
          f"{bench} a broken camera stops the video, not the episode ({code}, {st['control_steps']} steps, done {st['done']})")
    s.stop()
run("robolab", 8, 8, 15); run("yamlab", 14, 16, 30); clock("robolab"); clock("yamlab")
start_check("robolab"); start_check("yamlab"); video("robolab", 8, 15); video("yamlab", 14, 30)
print("server:", "ALL OK" if not bad else f"{bad} FAILED"); sys.exit(1 if bad else 0)
