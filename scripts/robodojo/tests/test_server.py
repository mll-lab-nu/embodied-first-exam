"""The real standard environment/sim/server.py of RoboDojo + the real eai-standard/2.2 layer, on a stub Session
(tests/stubs/rcb_robodojo.py): graded by the live episode (board 0151), so the service checks the start state before it
serves (a rebuilt layout with another state hash: a give-up as infra, `instance_mismatch`; a task graded by verdict: served,
the hash recorded), and keeps the live video's frames only at actions a call already rendered (no extra render), its end
state at the dump; a video that cannot be written stops, never the episode. Needs numpy (and requests); without Pillow
run_server.py writes stand-in frame files (the test checks which frames are taken, not their bytes)."""
import json, os, signal, socket, subprocess, sys, tempfile, time, urllib.error, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
LAYER = os.path.join(ROOT, "scripts/eai_standard"); SERVER = os.path.join(ROOT, "scripts/robodojo/template/standard/environment/sim/server.py")
sys.dont_write_bytecode = True; sys.path.insert(0, LAYER)
import rcb1
bad = 0
def check(ok, what):
    global bad
    bad += not ok; print("ok  " if ok else "FAIL", what)
def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p
def start(env, inst, broken_video=False):
    td = tempfile.mkdtemp(prefix="srv_robodojo_"); port = free_port(); data = os.path.join(td, "data")
    if broken_video:                     # the video's directory cannot be made: every frame fails
        os.makedirs(data); open(os.path.join(data, "live_video"), "w").write("not a directory")
    json.dump({"task": "t", "state_sha": "aa", **inst}, open(os.path.join(td, "instance.json"), "w"))
    e = {"PATH": "/usr/bin:/bin", "RCB_DATA": data, "TEST_PORT": str(port), "RCB_PORT": str(port), "RCB_WALL_CLOCK_S": "3600",
         "RCB_TASK": "t", "RCB_INSTANCE": os.path.join(td, "instance.json"), "PYTHONDONTWRITEBYTECODE": "1", **env}
    log = open(os.path.join(td, "server.log"), "w")
    p = subprocess.Popen([sys.executable, os.path.join(HERE, "run_server.py"), SERVER, os.path.join(HERE, "stubs"), LAYER], env=e,
                         stdout=log, stderr=subprocess.STDOUT, cwd=td)
    return td, port, data, p, log
def get(port, path):
    try:
        return 200, json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=30).read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")
def post(port, path, body):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(body).encode(), method="POST")
    try:
        r = urllib.request.urlopen(req, timeout=60); b = r.read(); return r.status, (rcb1.decode(b)[0] if b[:4] == rcb1.MAGIC else json.loads(b))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")
def wait_up(port, p, td):
    for _ in range(200):
        try:
            return get(port, "/status")
        except Exception:
            if p.poll() is not None: break
            time.sleep(0.1)
    raise RuntimeError(open(os.path.join(td, "server.log")).read()[-1500:])
def end(p, log):
    os.kill(p.pid, signal.SIGUSR1); p.wait(timeout=60); log.close()
# 1. a layout rebuilt to another state: a give-up as infra, nothing served
td, port, data, p, log = start({"FAKE_INSTANCE": "mismatch"}, {})
code, st = wait_up(port, p, td); fin = json.load(open(os.path.join(data, "final.json")))
ev = [json.loads(l) for l in open(os.path.join(data, "episode.jsonl"))] if os.path.exists(os.path.join(data, "episode.jsonl")) else []
check(code == 409 and fin.get("gave_up") and fin.get("infra_error") == 1 and fin.get("instance_mismatch") is True and fin.get("finalized")
      and not any(e.get("ev") == "start" for e in ev), f"instance mismatch at the start: a give-up as infra before serving ({code}, {fin.get('reason')})")
p.kill(); p.wait(); log.close()
# 2. a task graded by verdict: its hash differs by design, served and recorded
td, port, data, p, log = start({"FAKE_INSTANCE": "mismatch"}, {"determinism": "verdict"})
code, st = wait_up(port, p, td); code2, m = post(port, "/submit", {"type": "joint_position", "actions": [[0.0] * 14]})
end(p, log); ep = json.load(open(os.path.join(data, "episode.json")))
check(code == 200 and code2 == 200 and ep.get("instance_exact") is False and ep.get("instance_checked") is False and ep.get("determinism_verdict_mode") is True,
      f"graded by verdict: served, the start hash recorded, not compared ({code2}, {ep.get('instance_exact')}, {ep.get('instance_checked')})")
# 3. the live video: frames at the actions the call rendered (video_fps 5 -> every 5 actions), the end state at the dump
td, port, data, p, log = start({}, {})
wait_up(port, p, td)
code, m = post(port, "/submit", {"type": "joint_position", "actions": [[0.0] * 14] * 50, "dt": 0.04, "video_fps": 5})
code1, m1 = post(port, "/submit", {"type": "joint_position", "actions": [[0.0] * 14] * 50, "dt": 0.04, "video_fps": 1})
end(p, log)
vd = os.path.join(data, "live_video"); steps = sorted(int(f[:-4]) for f in os.listdir(vd) if f[:-4].isdigit())
first = [s for s in steps if s <= 50]; second = [s for s in steps if 50 < s <= 100]
check(code == 200 and code1 == 200 and steps[0] == 0 and len(first) >= 10 and 2 <= len(second) <= 4 and os.path.exists(os.path.join(vd, "last.jpg")),
      f"live video: {len(first)} frames over 50 actions at 5 fps, {len(second)} at 1 fps (only rendered actions), the end state at the dump")
# 4. the video cannot be written: it stops, the episode goes on
td, port, data, p, log = start({}, {}, broken_video=True)
wait_up(port, p, td); code, m = post(port, "/submit", {"type": "joint_position", "actions": [[0.0] * 14] * 10, "dt": 0.04})
code_s, st = get(port, "/status"); p.kill(); p.wait(); log.close()
ev = [json.loads(l) for l in open(os.path.join(data, "episode.jsonl"))]
check(code == 200 and st["control_steps"] == 10 and not st["done"] and any(e.get("ev") == "live_video_stopped" for e in ev),
      f"a video that cannot be written stops, not the episode ({code}, {st.get('control_steps')} steps)")
print("server:", "ALL OK" if not bad else f"{bad} FAILED"); sys.exit(1 if bad else 0)
