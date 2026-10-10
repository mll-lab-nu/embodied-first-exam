"""The LabUtopia sim service (the real shared/standard/server.py on the real shared layer rcb_limited.py) with a stand-in
simulator, over HTTP: malformed requests are 400s that execute nothing and leave the episode open; a valid chunk after
them still runs; a non-string note no longer ends the episode after the rows ran."""
import json, os, shutil, signal, socket, subprocess, sys, tempfile, time, urllib.request, urllib.error
ROOT, HERE = (sys.argv[1] if len(sys.argv) > 1 else os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))), os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp(); srv = os.path.join(tmp, "srv"); data = os.path.join(tmp, "data"); os.makedirs(srv); os.makedirs(data)
shutil.copy(os.path.join(ROOT, "scripts/labutopia/shared/standard/server.py"), srv)
for f in ("rcb_limited.py", "rcb1.py"): shutil.copy(os.path.join(ROOT, "scripts/eai_standard", f), srv)
shutil.copy(os.path.join(HERE, "stub_rcb_labutopia.py"), os.path.join(srv, "rcb_labutopia.py"))
json.dump({"family": "pick", "n_action": 18}, open(os.path.join(srv, "instance.json"), "w"))
json.dump({"task_text": "stub", "default_cameras": ["camera_1"], "static": {}}, open(os.path.join(srv, "task.json"), "w"))
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
log = open(os.path.join(tmp, "server.log"), "w")
p = subprocess.Popen([sys.executable, "-B", os.path.join(srv, "server.py")], cwd=tmp, stdout=log, stderr=subprocess.STDOUT,
                     env={**os.environ, "RCB_DATA": data, "RCB_PORT": str(port), "RCB_INSTANCE": os.path.join(srv, "instance.json")})
U = f"http://127.0.0.1:{port}"
def req(path, body=None):
    r = urllib.request.Request(U + path, data=None if body is None else json.dumps(body).encode(), method="GET" if body is None else "POST")
    try:
        with urllib.request.urlopen(r, timeout=60) as h: return h.status, h.read()
    except urllib.error.HTTPError as e: return e.code, e.read()
ok = True
try:
    for _ in range(100):
        try:
            if req("/status")[0] == 200: break
        except Exception: time.sleep(0.2)
    else: raise SystemExit("service did not start: " + open(os.path.join(tmp, "server.log")).read()[-2000:])
    row = [[0.1] * 9]
    bad_submit = [{"dt": None, "note": 5}, {"dt": "0.0167"}, {"dt": [1 / 60]}, {"dt": float("inf")}, {"dt": 0.02}, {"dt": True}, {"video_fps": 0},
                  {"cameras": 5}, {"cameras": "wrist_cam"}, {"cameras": [["camera_1"]]}, {"note": {"a": 1}}, {"note": 7}, {"interpolate": None},
                  {"video": []}, {"depth": {"x": 1}}, {"type": None}, {"type": ["joint_position"]}, {"actions": [[0.0] * 8]}, {"actions": [[float("nan")] * 9]},
                  {"actions": [[0.0] * 9, [0.0] * 8]}, {"actions": None}, {"actions": "rows"}]
    bad_observe = [{"seconds": "1"}, {"seconds": [1]}, {"seconds": -1}, {"seconds": float("inf")}, {"seconds": 31}, {"video_fps": -3}, {"video": 5},
                   {"depth": 9}, {"cameras": 5}, {"seconds": 1, "note": 5, "cameras": {"a": 1}}]
    errs = []
    for b in bad_submit:
        c, t = req("/submit", {"type": "joint_position", "actions": row, "video": "none", **b})
        if c != 400: errs.append(("submit", b, c, t[:100]))
    for b in bad_observe:
        c, t = req("/observe", {"video": "none", **b})
        if c != 400: errs.append(("observe", b, c, t[:100]))
    st = json.loads(req("/status")[1])
    print(f"{len(bad_submit) + len(bad_observe)} malformed requests; not 400: {errs}; status after: {st}")
    ok &= not errs and st["control_steps"] == 0 and not st["done"]
    c1, _ = req("/submit", {"type": "joint_position", "actions": row * 3, "dt": 2 / 60, "video": "none", "note": "ok"})
    c2, _ = req("/submit", {"type": "joint_position_velocity", "actions": [[0.0] * 18], "dt": None, "video": "none"})
    c3, _ = req("/observe", {"seconds": 0.5, "video": "none"}); c4, _ = req("/observe", {"seconds": None})
    st = json.loads(req("/status")[1])
    print("valid submit / submit(dt=null) / observe / observe(seconds=null):", c1, c2, c3, c4, "status:", st)
    ok &= (c1, c2, c3, c4) == (200, 200, 200, 200) and st["control_steps"] == 6 + 1 + 30 and not st["done"]
    c5, t5 = req("/submit", {"type": "joint_position", "actions": row, "video": "none", "note": 12345})   # before: 500 after the row ran, episode over
    st = json.loads(req("/status")[1])
    print("note of the wrong type:", c5, "status:", st); ok &= c5 == 400 and st["control_steps"] == 37 and not st["done"]
    # the shared layer's own case (scripts/eai_standard/rcb_limited.py converts `actions` before the adapter sees it): reported, not asserted
    c6, t6 = req("/submit", {"type": "joint_position", "actions": {"a": 1}, "video": "none"}); st = json.loads(req("/status")[1])
    print("SHARED LAYER (not this adapter): actions as a JSON object ->", c6, t6[:120], "| status:", {k: st[k] for k in ("done", "reason")})
finally:
    p.send_signal(signal.SIGKILL); p.wait(); log.close()
    if not ok: print(open(os.path.join(tmp, "server.log")).read()[-3000:])
    shutil.rmtree(tmp, ignore_errors=True)
print("PASS" if ok else "FAIL"); sys.exit(0 if ok else 1)
