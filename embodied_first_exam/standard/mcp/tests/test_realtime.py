"""The efe-robot MCP server on the toy eai-standard/2.1 (standard) and 2.3 (realtime) services (CPU, ~40 s):

0. 2.1, standard mode (a benchmark's own rcb_service.py): a closed-loop oracle over HTTP and through the tools leaves
   the same record and verdict.

1. API path vs MCP path: an oracle written for the realtime rcb_client (a plan with `at`, the robot's own
   proprioception, a read after the plan has run) runs once over HTTP and once through the endpoint tools; the executed trajectory, every submitted
   row and the verdict are the same (tests/equivalence.py; the clock's own timings are left out, they are wall time).
2. The tools hold no clock: `submit` answers at once (the plan is the service's), and the tool's own time on top of the
   HTTP call is measured: observe(cameras=[]) over HTTP vs through the tool (`tool_s`, and the client's round trip).
3. The eai-standard/3.0 rules of the realtime layer, in process (rules_v3): /observe never starts the clock and refuses
   seconds > 0; the first /submit starts it and answers duration_s / planned_duration_s / end_step; last_s = n reads
   the frames the recorder (here the simulator thread's: the toy has no render hooks) took; a hold chunk plans the
   target in force for n seconds; rows with seconds are a 400.

    python3 embodied_first_exam/standard/mcp/tests/test_realtime.py
"""
import json, os, pathlib, shutil, socket, statistics, subprocess, sys, tempfile, textwrap, time, urllib.request
HERE = pathlib.Path(__file__).resolve().parent
MCP = HERE.parent
STD = MCP.parent
sys.path.insert(0, str(MCP))
from mcp_client import McpClient  # noqa: E402

ORACLE = textwrap.dedent('''
    from rcb_client import Robot
    import time
    import numpy as np
    r = Robot(); spec = r.spec()
    assert spec["protocol"] == "eai-standard/2.3", spec["protocol"]
    o = r.get_obs(cameras=[])
    print("now", o.meta["proprio"]["now"])
    dx = 1 / 64                             # exact in binary: x reaches 1 at the 64th row in both runs
    rows = np.zeros((48, 2)); rows[:, 0] = dx
    a = r.submit("joint_position", rows, cameras=[])
    print("plan", a.meta["start_step"], a.meta["plan_end_step"], a.meta["late_steps"])
    # a second chunk joined to the first one's end: `at` = where the plan ends, so no step is late or held (it has the
    # first chunk's 0.96 s to arrive, a loaded host's round trip through the tools included)
    b = r.submit("joint_position", np.vstack([np.full((16, 1), dx), np.zeros((16, 1))]).repeat(2, 1) * [1, 0],
                 at=a.meta["plan_end_step"], cameras=[])
    print("plan", b.meta["start_step"], b.meta["plan_end_step"], b.meta["late_steps"])
    time.sleep(2.5)                         # the plan (1.6 s) runs out on the clock; then a read of the robot as it is
    w = r.get_obs(cameras=["top"])
    print("watched", round(w.meta["proprio"]["now"][0], 4), w.meta["done"], w.meta["reason"], int(w.last["top"].sum()))
''')

ORACLE_21 = textwrap.dedent('''
    from rcb_client import Robot
    import numpy as np
    r = Robot(); spec = r.spec()
    assert spec["protocol"] == "eai-standard/2.1", spec["protocol"]
    o = r.get_obs(cameras=["top"])
    x = o.meta["proprio"]["now"][0]
    print("now", x, int(o.last["top"].sum()))
    while True:                              # closed loop on the measured x: steps of at most 0.05 (the toy's clip)
        n = 10
        rows = np.zeros((n, 2)); rows[:, 0] = min(0.05, (1.0 - x) / n + 1e-6)
        res = r.submit("joint_position", rows, cameras=["top"], video="frames")
        x = res.meta["proprio"]["now"][0]
        print("step", round(x, 6), res.meta["done"], res.meta["reason"], int(res.last["top"].sum()))
        if res.meta["done"]:
            break
''')

TIMING = ("max_lag_s,clock_s,max_queue_wait_s,request_busy_s,stalled_s,lag_s,stalled_share,request_mb,stalls,"
          "elapsed_s,control_steps,control_steps_total,held_steps,render_s_max,render_s_p50")   # render_s_*: camera_worker's


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def tools_dir(tmp):
    t = tmp / "tools"; t.mkdir()
    shutil.copy(STD / "realtime/rcb_client.py", t / "rcb_client.py"); shutil.copy(STD / "rcb1.py", t / "rcb1.py")
    return t


def manifest(tmp):
    m = {"manifest": "efe-mcp-manifest/1", "kind": "rcb", "suite": "toy", "task": "toy-realtime",
         "protocol": "eai-standard/2.3", "realtime": True, "tools": ["spec", "observe", "submit", "finish"]}
    p = tmp / "manifest.json"; p.write_text(json.dumps(m)); return p


def equivalence(tmp, tools, man):
    (tmp / "oracle.py").write_text(ORACLE)
    cmd = [sys.executable, str(HERE / "equivalence.py"), "--service", f"{sys.executable} {HERE / 'toy_realtime.py'} {{port}}",
           "--tools", str(tools), "--manifest", str(man), "--oracle", f"{sys.executable} {tmp / 'oracle.py'}",
           "--out", str(tmp), "--compare", "trajectory_live.f64,submitted.f64,final.json", "--ignore-keys", TIMING]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    s = json.loads(p.stdout.strip().splitlines()[-1])
    assert p.returncode == 0, p.stdout + p.stderr
    assert {"trajectory_live.f64", "submitted.f64", "final.json"} <= set(s["same"]), s
    out = (pathlib.Path(s["out"]) / "mcp" / "oracle.out").read_text()
    assert "True success" in out and "plan 48 80 0" in out, out
    return s


def standard_21(tmp):
    """The same toy robot behind the 2.1 service itself (a benchmark's own 2.1 service, standard mode)."""
    d = tmp / "v21"; d.mkdir()
    shutil.copy(STD / "sidecar/rcb_client.py", d / "rcb_client.py"); shutil.copy(STD / "rcb1.py", d / "rcb1.py")
    m = {"manifest": "efe-mcp-manifest/1", "kind": "rcb", "suite": "toy", "task": "toy-standard",
         "protocol": "eai-standard/2.1", "realtime": False, "tools": ["spec", "observe", "submit", "finish"]}
    (d / "manifest.json").write_text(json.dumps(m))
    (d / "oracle.py").write_text(ORACLE_21)
    cmd = [sys.executable, str(HERE / "equivalence.py"),
           "--service", f"{sys.executable} {HERE / 'toy_realtime.py'} {{port}} --standard",
           "--tools", str(d), "--manifest", str(d / "manifest.json"), "--oracle", f"{sys.executable} {d / 'oracle.py'}",
           "--out", str(d)]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    s = json.loads(p.stdout.strip().splitlines()[-1])
    assert p.returncode == 0, p.stdout + p.stderr
    assert s["same"] and s["verdict"]["api"] == s["verdict"]["mcp"] and s["verdict"]["api"].get("done"), s
    return s


def latency(tmp, tools, man, n=40):
    port = free_port()
    data = tmp / "lat_data"
    sim = subprocess.Popen([sys.executable, str(HERE / "toy_realtime.py"), str(port)],
                           env={**os.environ, "RCB_DATA": str(data)}, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        sys.path.insert(0, str(tools))
        import rcb_client
        for _ in range(600):                          # /spec up first: the client would try other addresses
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/spec", timeout=2):
                    break
            except (OSError, ValueError):
                time.sleep(0.1)
        r = rcb_client.Robot(f"http://127.0.0.1:{port}")
        c = McpClient(cmd=[sys.executable, str(MCP / "server.py"), "--manifest", str(man)],
                      env={"SIM_URL": f"http://127.0.0.1:{port}", "EFE_MCP_TOOLS_DIR": str(tools),
                           "EFE_MCP_WORKSPACE": str(tmp / "app"), "EFE_MCP_LOG": str(tmp / "lat.jsonl")})
        assert "at" in c.tools["submit"]["inputSchema"]["properties"] and "last_s" in c.tools["observe"]["inputSchema"]["properties"]
        c.call("spec")
        http, rt, tool = [], [], []
        for _ in range(n):
            t0 = time.perf_counter(); r.get_obs(cameras=[]); http.append(time.perf_counter() - t0)
            t0 = time.perf_counter(); res = c.call("observe", cameras=[]); rt.append(time.perf_counter() - t0)
            tool.append(res["tool_s"])
        # a submit through the tool answers at once while the clock runs
        t0 = time.perf_counter()
        a = c.call("submit", type="joint_position", actions=[[0.01, 0]] * 50, cameras=[])
        sub = time.perf_counter() - t0
        # at once: well before its 50 rows (1 s of clock) have run, with room for a loaded host
        assert a["meta"]["plan_end_step"] - a["meta"]["start_step"] == 50 and sub < 0.9, (a["meta"], sub)
        assert a["step"]["plan_end_step"] == a["meta"]["plan_end_step"], a["step"]
        c.close() if hasattr(c, "close") else None
        med = lambda v: round(statistics.median(v) * 1000, 2)
        return {"observe_http_ms": med(http), "observe_tool_roundtrip_ms": med(rt), "observe_tool_s_ms": med(tool),
                "submit_50_rows_tool_roundtrip_ms": round(sub * 1000, 1), "n": n}
    finally:
        os.killpg(sim.pid, 15); sim.wait(30)


def rules_v3(tmp):
    """Docstring, 3. In process: the realtime service on the toy, requests through dispatch(), the clock by tick()."""
    import importlib.util
    sys.path.insert(0, str(STD))
    import rcb1

    def load(path, name):
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod

    toy = load(HERE / "toy_realtime.py", "toy_realtime_v3")
    load(STD.parent / "benchmarks/humanoidbench/sim/rcb_service.py", "rcb_service")
    R = load(STD / "realtime/rcb_realtime.py", "rcb_realtime")
    d = tmp / "v3"; d.mkdir()
    svc = R.RealtimeService(toy.Toy(), data=str(d), slowdown=1.0, agent_end=True)
    svc.start()

    def call(svc, path, body):
        j = R._Job("POST", path, json.dumps(body).encode())
        svc.dispatch(j)
        kind, *rest = j.reply
        if kind == "raw":
            code, ctype, out = rest
            if ctype == "application/json":
                return code, json.loads(out), {}
            m, p = rcb1.decode(bytes(out))
            return code, m, p
        meta, payload = rest
        m, p = rcb1.decode(bytes(svc._reply_rcb1(meta, payload.parts() if kind == "rec" else payload)[2]))
        return 200, m, p

    req = lambda path, body: call(svc, path, body)  # noqa: E731

    sp = svc.spec
    assert sp["standard"] == "eai-standard/3.0" and sp["timing"]["recorder"]["cameras"] == ["top"], sp["timing"]
    assert "first submit" in sp["timing"]["clock"], sp["timing"]["clock"]
    code, m, _ = req("/observe", {"seconds": 1.0})
    assert code == 400 and "never waits" in m["error"], (code, m)
    code, m, _ = req("/observe", {"last_s": 1.0, "cameras": ["top"]})
    assert code == 200 and not svc.running and m["last_s"] == 0.0, (code, m, svc.running)
    code, m, _ = req("/submit", {"type": "joint_position", "dt": 0.04, "actions": [[0.01, 0]] * 10, "cameras": []})
    assert code == 200 and svc.running and m["duration_s"] == 0.4 and m["planned_duration_s"] == 0.4 \
        and m["end_step"] == m["plan_end_step"] == 20, (code, m)
    for _ in range(20):
        svc.tick()
    code, m, p = req("/observe", {"last_s": 0.4, "cameras": ["top"], "video": "frames"})
    n = p["frames/top"]["data"].shape[0]
    assert code == 200 and m["frame_step"] == 20 and m["last_s"] == 0.4 and n == 5, (code, m, n)
    code, m, _ = req("/submit", {"type": "joint_position", "interpolate": "hold", "seconds": 0.2, "cameras": []})
    assert code == 200 and m["hold"] is True and m["duration_s"] == 0.2 and m["n_rows"] == 0 \
        and m["plan_end_step"] - m["start_step"] == 10, (code, m)
    code, m, _ = req("/submit", {"type": "joint_position", "interpolate": "hold", "seconds": 0.2, "actions": [[0, 0]]})
    assert code == 400 and "no rows" in m["error"], (code, m)
    code, m, _ = req("/submit", {"type": "joint_position", "seconds": 0.2})
    assert code == 400 and "hold chunk" in m["error"], (code, m)
    code, m, _ = req("/finish", {})
    assert code == 200 and not svc.running, (code, m)
    code, m, _ = req("/observe", {"last_s": 0})
    assert code == 409, (code, m)
    svc.on_sigusr1(); svc.poll()

    # depth with last_s > 0 only for cameras the recorder keeps depth for (as 2.1 and 2.2/2.4): mixed cameras are a 400
    t2 = toy.Toy(); t2.cameras = ["top", "side"]; t2.depth_cameras = ["top"]
    t2.spec = lambda: {"cameras": {"top": {"shape": [8, 8, 3]}, "side": {"shape": [8, 8, 3]}},
                       "action_types": {"joint_position": {"dim": 2, "layout": ["dx", "unused"]}}}
    d2 = tmp / "v3_depth"; d2.mkdir()
    svc2 = R.RealtimeService(t2, data=str(d2), slowdown=1.0, agent_end=True)
    svc2.start()
    assert svc2.spec["timing"]["recorder"]["depth"] == ["top"], svc2.spec["timing"]["recorder"]
    code, m, _ = call(svc2, "/observe", {"last_s": 0.4, "cameras": ["top", "side"], "include_depth": True})
    assert code == 400 and "keeps no depth" in m["error"], (code, m)
    code, m, _ = call(svc2, "/observe", {"last_s": 0.4, "cameras": ["top"], "include_depth": True})
    assert code == 200, (code, m)
    svc2.on_sigusr1(); svc2.poll()

    # a service without a recorder (record_frames not True) still answers /submit's images with meta.frame_step
    t3 = toy.Toy(); t3.record_frames = False
    d3 = tmp / "v3_norec"; d3.mkdir()
    svc3 = R.RealtimeService(t3, data=str(d3), slowdown=1.0, agent_end=True)
    svc3.start()
    assert not svc3.recording
    code, m, _ = call(svc3, "/submit", {"type": "joint_position", "dt": 0.04, "actions": [[0.01, 0]] * 2, "cameras": ["top"]})
    assert code == 200 and "frame_step" in m, (code, m)
    code, m, _ = call(svc3, "/submit", {"type": "joint_position", "dt": 0.04, "actions": [[0.01, 0]] * 2, "cameras": []})
    assert code == 200 and "frame_step" not in m, (code, m)
    svc3.on_sigusr1(); svc3.poll()
    return {"observe_refused_seconds": True, "clock_from_submit": True, "last_s_frames": n, "hold_chunk": True,
            "depth_past_mixed_refused": True, "frame_step_without_recorder": True}


def main():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="efe_mcp_rt_"))
    v3 = rules_v3(tmp)
    print("ok realtime eai-standard/3.0 rules:", json.dumps(v3))
    tools, man = tools_dir(tmp), manifest(tmp)
    s21 = standard_21(tmp)
    print("ok eai-standard/2.1 (standard): API path = MCP path:", ", ".join(s21["same"]), "identical; verdicts",
          s21["verdict"], "; evidence", s21["out"])
    s = equivalence(tmp, tools, man)
    lat = latency(tmp, tools, man)
    (tmp / "latency.json").write_text(json.dumps(lat))
    print("ok realtime: API path = MCP path:", ", ".join(s["same"]), "identical (clock timings aside); verdicts",
          s["verdict"], "; latency", json.dumps(lat), "; evidence", s["out"])


if __name__ == "__main__":
    main()
