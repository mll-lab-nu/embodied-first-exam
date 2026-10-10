"""The real environment/sim/server.py of RoboLab and YAMLab + the real eai-standard/2.2 layer, on a fake simulator:
malformed requests are 400s that execute nothing and leave the episode alive; valid requests still run; the step cap is in
/spec and ends the episode with reason step_guard."""
import json, os, socket, subprocess, sys, tempfile, time, urllib.error, urllib.request
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
    def __init__(self, bench, env=None):
        self.td = tempfile.mkdtemp(prefix=f"srv_{bench}_"); self.port = free_port(); self.bench = bench
        e = {"PATH": "/usr/bin:/bin", "RCB_DATA": os.path.join(self.td, "data"), "TEST_PORT": str(self.port), "RCB_WALL_CLOCK_S": "5400",
             "PYTHONDONTWRITEBYTECODE": "1", **(env or {})}
        self.log = open(os.path.join(self.td, "server.log"), "w")
        self.p = subprocess.Popen([sys.executable, os.path.join(HERE, "run_server.py"), os.path.join(ROOT, "scripts", bench, "template/standard/environment/sim/server.py"),
                                   os.path.join(HERE, "stubs", bench), LAYER], env=e, stdout=self.log, stderr=subprocess.STDOUT, cwd=self.td)
        for _ in range(100):
            try:
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
run("robolab", 8, 8, 15); run("yamlab", 14, 16, 30)
print("server:", "ALL OK" if not bad else f"{bad} FAILED"); sys.exit(1 if bad else 0)
