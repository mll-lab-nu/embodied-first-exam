"""Synthetic test of the RoboWits standard verdict (board 0151: graded by the live episode, no grading replay):
scripts/robowits/shared/server.py on the real eai-standard/2.2 layer with a stub Session (needs numpy, no simulator, no
GPU; under a minute), ended the way the collect hook ends it (`rcb_limited.py end --wait-key video_done`), then graded by
scripts/robowits/shared/grade_standard.py. Cases: a live success (the settle window passes inside the call) -> 1; a
settle failure -> the episode goes on, and at the end of the agent's phase the window decides again on the live
simulator -> 0; a live failure at the cutoff -> 0, not infra; the only replay is the video's (rows only, after the
verdict is on disk); a failed video keeps the verdict; a simulator error from the agent's call -> 0, not infra; a frozen
instance that does not rebuild -> infra, before the agent is served; a give-up after crashes between calls -> infra,
after crashes inside the agent's calls -> 0; a crash in the end-of-phase settle window counts as inside the agent's last call
-> 0; no final.json -> infra.
usage: python3 scripts/robowits/tests/test_live_grading.py [repo root]"""
import hashlib, json, os, runpy, shutil, socket, subprocess, sys, tempfile, time, types, urllib.error, urllib.request
import numpy as np
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))


def serve(sim: str, data: str, port: int) -> None:
    """The launcher (a child process): the real server.py with a stub rcb_robowits. The goal holds while the right arm's
    first joint target is above 1 rad; the settle window passes unless RW_STUB_SETTLE=fail (it runs its 90 steps through
    the `step` it is given, as the real one does); RW_STUB_VIDEO_FAIL: start_video raises; RW_STUB_MISMATCH: the frozen
    instance does not rebuild; RW_STUB_STEP_RAISE: a step with the first joint below -2 raises; RW_STUB_SETTLE_CRASH: the
    process dies 10 steps into every settle window. Every replay is logged to
    replays.jsonl in the data directory."""
    sys.path.insert(0, sim)
    os.environ.update(RCB_DATA=data, RCB_SESSION_LOG="", RCB_INSTANCE=os.path.join(data, "instance.json"), RCB_TASK="stack_cubes")
    os.makedirs(data, exist_ok=True)
    if not os.path.exists(os.environ["RCB_INSTANCE"]): json.dump({}, open(os.environ["RCB_INSTANCE"], "w"))
    import rcb_limited as L
    _serve = L.serve
    L.serve = lambda svc, port=port: _serve(svc, port)
    env = os.environ

    class Session:
        def __init__(s, task, instance=None):
            s._t = np.zeros(16); s.n_steps = 0; s._recording = None; s.instance_sha = "s0"; s.eval_index = 0
            s.instance_matches = not env.get("RW_STUB_MISMATCH"); s.instance_exact = s.instance_matches
            s.max_steps = 200000; s.spec = {"text": "do it"}; s.robot = types.SimpleNamespace(); s.video = None
            opt = types.SimpleNamespace(near=0.05, far=10.0)
            s.env = types.SimpleNamespace(_cameras={c: types.SimpleNamespace(_options=opt) for c in ("ego", "wrist_right", "wrist_left")},
                                          _check_success=lambda: np.array(False), render_frame=lambda i, c: np.zeros((4, 6, 3), np.uint8))

        def camera_info(s, cams):
            return {c: dict(intrinsic_cv=np.eye(3).tolist(), extrinsic_cv=np.eye(4)[:3].tolist(), cam2world_gl=np.eye(4).tolist(),
                            image_size=[6, 4], mount={"type": "static"}) for c in cams}

        def robot_spec(s): return {"name": "stub"}

        def kinematics_spec(s):
            j = [f"Joint{i}_{a}" for a in "RL" for i in range(1, 8)]; tips = ["Gripper_Tip_R", "Gripper_Tip_L"]
            return dict(endpoint="/kinematics", joint_names=j, frame="world", quaternion_order="wxyz", links=tips, tcp_frames=tips,
                        ee_frames=tips, ik_targets=tips)

        def hold_action(s): return s._t.copy()
        def joint_positions(s): return s._t.copy()
        def joint_velocities(s): return np.zeros(16)
        def joint_efforts(s): return np.zeros(16)
        def ee_pose(s, arm): return np.zeros(3), np.array([1., 0, 0, 0])
        def render_depth(s, c): return np.ones((4, 6), np.float32)
        def state_sha(s): return hashlib.sha1(s._t.tobytes() + str(s.n_steps).encode()).hexdigest()[:16]
        def record_start(s): s._recording = []

        def record_stop(s):
            if env.get("RW_STUB_RECORD_FAIL"): raise MemoryError("rows (stub)")
            a = np.stack(s._recording) if s._recording else np.zeros((0, 16), np.float32); s._recording = None; return a

        def save_trajectory(s, acts, path, meta=None): np.savez(path, actions=acts, task="t", meta=json.dumps(meta or {}))
        def ik(s, arm, pos, q): return np.zeros(7), 0.0, 0.0
        def kinematics(s, req): return {"ok": True}
        def reset(s): s._t = np.zeros(16); s.n_steps = 0

        def goal(s):
            ok = bool(s._t[0] > 1.0)
            return {"success": ok, "predicate": ok, "clause": True, "touching": [], "objects": []}

        def settle_check(s, step=None):
            step = step or s.step
            hold = s.hold_action()
            for k in range(90):
                if k == 10 and env.get("RW_STUB_SETTLE_CRASH"): os._exit(1)   # the simulator dies inside the window
                if step(hold): return {"success": False, "why": "the step cap", "steps": 0, "max_move_m": 0.0}
            ok = s.goal()["success"] and env.get("RW_STUB_SETTLE") != "fail"
            return {"success": ok, "why": "held and at rest" if ok else "an object moved 3 mm", "steps": 90, "max_move_m": 0.0}

        def replay(s, acts, settle=True):
            with open(os.path.join(data, "replays.jsonl"), "a") as f:
                f.write(json.dumps({"settle": settle, "rows": int(len(acts)), "video": s.video is not None,
                                    "verdict_on_disk": bool(json.load(open(os.path.join(data, "final.json"))).get("graded_by"))}) + "\n")
            s.reset()
            for a in acts: s.step(a)
            return {"success": s.goal()["success"], "state_sha": s.state_sha(), "state_sha_rows": s.state_sha()}

        def start_video(s, path, fps=15):
            if env.get("RW_STUB_VIDEO_FAIL"): raise RuntimeError("EGL context lost (stub)")
            s.video = path

        def stop_video(s):
            open(s.video, "wb").write(b"stub"); s.video = None

        def step(s, row):
            s._t = np.asarray(row, np.float64).reshape(-1).copy(); s.n_steps += 1
            if env.get("RW_STUB_STEP_RAISE") and s._t[0] < -2.0: raise RuntimeError("Genesis: solver diverged (stub)")
            if s._recording is not None: s._recording.append(s._t.astype(np.float32))
            return False

    sys.modules["rcb_robowits"] = types.SimpleNamespace(Session=Session, GRIPPER_OPEN=0.1, MAX_STEPS=200000)
    sys.argv = [os.path.join(sim, "server.py")]
    runpy.run_path(os.path.join(sim, "server.py"), run_name="__main__")


if len(sys.argv) > 1 and sys.argv[1] == "--serve":
    serve(sys.argv[2], sys.argv[3], int(sys.argv[4])); sys.exit(0)
ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts/eai_standard"))
import rcb1  # noqa: E402
TMP = tempfile.mkdtemp(prefix="rw_live_"); SIM = os.path.join(TMP, "sim"); os.makedirs(SIM)
for src in ("scripts/robowits/shared/server.py", "scripts/eai_standard/rcb_limited.py", "scripts/eai_standard/rcb1.py"):
    shutil.copy(os.path.join(ROOT, src), SIM)
GRADER = os.path.join(ROOT, "scripts/robowits/shared/grade_standard.py")
errs = []; n = 0


class Svc:
    def __init__(self, name, **env):
        self.data = os.path.join(TMP, name); self.env = {k: str(v) for k, v in env.items()}; self.proc = None

    def start(self, serve=True):
        with socket.socket() as k:
            k.bind(("127.0.0.1", 0)); self.port = k.getsockname()[1]
        self.out = open(self.data + ".out", "a")
        self.proc = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--serve", SIM, self.data, str(self.port)], stdout=self.out,
                                     stderr=subprocess.STDOUT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", **self.env})
        for _ in range(300):
            if not serve and os.path.exists(os.path.join(self.data, "server.pid")): return self
            try:
                self.get("/status"); return self
            except Exception:  # noqa: BLE001
                if self.proc.poll() is not None: break
                time.sleep(0.1)
        if serve:
            raise RuntimeError("the service did not start:\n" + open(self.data + ".out").read()[-3000:])
        return self

    def get(self, path):
        return json.loads(urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=30).read())

    def submit(self, rows, **meta):
        raw = rcb1.encode({"type": "joint_position", "video": "none", **meta}, [rcb1.array_part("actions", np.asarray(rows, np.float32))])
        try:
            r = urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{self.port}/submit", data=raw, method="POST"), timeout=60)
            return r.status, rcb1.decode(r.read())[0]
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def end(self):
        """The collect hook: SIGUSR1 to the service and wait for the verdict and the video."""
        r = subprocess.run([sys.executable, os.path.join(SIM, "rcb_limited.py"), "end", self.data, "--wait-key", "video_done", "--timeout", "60"],
                           capture_output=True, text=True, timeout=120)
        return r.returncode

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.kill(); self.proc.wait()
        if self.proc: self.out.close()

    def final(self):
        try: return json.load(open(os.path.join(self.data, "final.json")))
        except (OSError, ValueError): return {}

    def replays(self):
        p = os.path.join(self.data, "replays.jsonl")
        return [json.loads(x) for x in open(p)] if os.path.exists(p) else []

    def grade(self):
        return grade(self.data)


def grade(data):
    log = data + ".verifier"; shutil.rmtree(log, ignore_errors=True)
    subprocess.run([sys.executable, GRADER], check=True, capture_output=True, env={**os.environ, "RCB_DATA": data, "RCB_VERIFIER_LOG_DIR": log})
    out = json.load(open(os.path.join(log, "reward.json")))
    assert open(os.path.join(log, "reward.txt")).read().strip() == str(out["success"]), out
    assert all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in out.values()), out
    assert "replay_success" not in out and "deterministic" not in out and out["replays"] == 0, out
    return out


def expect(name, got, want):
    global n
    n += 1
    if got != want:
        errs.append(f"{name}: got {got}, want {want}")


def row(j0):
    r = np.zeros(16); r[0] = j0; return [r]


svcs = []
try:
    # 1. a live success: the goal holds after the call, the settle window passes inside it, the episode ends
    s = Svc("success"); svcs.append(s); s.start()
    code, m = s.submit(row(1.5))
    expect("success: the call", (code, m.get("done"), m.get("reason")), (200, True, "success"))
    expect("success: the hook", s.end(), 2)
    d = s.final(); out = s.grade()
    expect("success: final.json", (d.get("success"), d.get("live_success"), d.get("graded_by"), d.get("replays"), d.get("video_done"), d.get("video_pending")),
           (True, True, "live", 0, True, False))
    expect("success: no replay fields", [k for k in ("replay_success", "deterministic", "replay_sha", "replay_settle") if k in d], [])
    expect("success: reward", (out["success"], out["live_success"], out["graded_by_live"], out["infra_error"], out["settle_passed"]), (1, 1, 1, 0, 1))
    expect("success: the one replay is the video's, rows only, after the verdict",
           s.replays(), [{"settle": False, "rows": d.get("n_actions"), "video": True, "verdict_on_disk": True}])
    expect("success: the rows end with the live window", (d.get("n_actions"), d.get("final_window")), (91, 90))
    s.stop()

    # 2. a settle failure: the episode goes on; at the end of the agent's phase the window decides again, on the live sim
    s = Svc("settle_fail", RW_STUB_SETTLE="fail"); svcs.append(s); s.start()
    code, m = s.submit(row(1.5))
    expect("settle failure: the call", (code, m.get("done"), (m.get("settle") or {}).get("success")), (200, False, False))
    expect("settle failure: the hook", s.end(), 2)
    d = s.final(); out = s.grade()
    expect("settle failure: final.json", (d.get("success"), d.get("graded_by"), d.get("reason") in ("timeout", "agent_exit"), d.get("final_window")),
           (False, "live", True, 90))
    expect("settle failure: reward", (out["success"], out["infra_error"], out["grader_error"]), (0, 0, 0))
    expect("settle failure: 91 + 90 recorded rows", d.get("n_actions"), 181)
    s.stop()

    # 3. a live failure at the cutoff (the goal never held), with a failed video: 0, not infra, the verdict kept
    s = Svc("fail_video", RW_STUB_VIDEO_FAIL=1); svcs.append(s); s.start()
    s.submit(row(0.2))
    expect("live failure: the hook", s.end(), 2)
    d = s.final(); out = s.grade()
    expect("live failure: final.json", (d.get("success"), d.get("graded_by"), d.get("video"), d.get("video_done"), "video_error" in d),
           (False, "live", False, True, True))
    expect("live failure: reward", (out["success"], out["infra_error"], out["video_rendered"]), (0, 0, 0))
    expect("live failure: no replay at all (the video failed before it)", s.replays(), [])
    s.stop()

    # 4. a failed video after a live success keeps the success
    s = Svc("success_video_fail", RW_STUB_VIDEO_FAIL=1); svcs.append(s); s.start()
    s.submit(row(1.5)); s.end()
    out = s.grade()
    expect("video failure: the success stands", (out["success"], out["infra_error"], out["video_rendered"]), (1, 0, 0))
    s.stop()

    # 4b. the rows cannot be exported after the episode ended: the verdict it ended with stands (journal.f64 has the rows)
    s = Svc("record_fail", RW_STUB_RECORD_FAIL=1); svcs.append(s); s.start()
    s.submit(row(1.5)); s.end(); d = s.final(); out = s.grade()
    expect("record failure: the success stands", (d.get("success"), "finalize_error" in d, out["success"], out["infra_error"]), (True, True, 1, 0))
    s.stop()

    # 4c. a restart that finds the verdict on disk while its video was pending: kept, the video marked over, not served
    s = Svc("restart_after_verdict"); svcs.append(s); s.start(); s.submit(row(1.5)); s.end(); s.stop()
    fin = s.final(); fin.update(video_done=False, video_pending=True); json.dump(fin, open(os.path.join(s.data, "final.json"), "w"))
    s.start(serve=False); time.sleep(1.0); d = s.final()
    expect("restart after the verdict", (d.get("success"), d.get("graded_by"), d.get("video_done"), d.get("video_pending")), (True, "live", True, False))
    s.stop()

    # 5. a simulator error from the agent's call: the agent's 0, not infra
    s = Svc("sim_error", RW_STUB_STEP_RAISE=1); svcs.append(s); s.start()
    code, m = s.submit(row(-2.5))
    expect("sim error: the call", code, 500)
    s.end(); d = s.final(); out = s.grade()
    expect("sim error: reward", (d.get("reason"), out["success"], out["sim_error"], out["infra_error"]), ("error", 0, 1, 0))
    s.stop()

    # 6. a frozen instance that does not rebuild: infra, and the agent is never served
    s = Svc("mismatch", RW_STUB_MISMATCH=1); svcs.append(s); s.start(serve=False)
    time.sleep(0.5); d = s.final(); out = s.grade()
    expect("instance mismatch: final.json", (str(d.get("reason", "")).startswith("instance_mismatch"), d.get("gave_up"), d.get("infra_error")), (True, True, 1))
    expect("instance mismatch: reward", (out["success"], out["infra_error"], out["instance_mismatch"]), (0, 1, 1))
    s.stop()

    # 7. give-ups: crashes between calls -> infra; every crash inside the agent's calls -> its 0
    for name, in_call, want_reason, want_infra in (("crashes_between", False, "sim_crashed", 1), ("crashes_in_calls", True, "sim_crashed_on_call", 0)):
        s = Svc(name); svcs.append(s); s.start(); s.submit(row(0.2)); s.stop()
        with open(os.path.join(s.data, "episode.jsonl"), "a") as f:
            for _ in range(2):
                f.write(json.dumps({"ts": time.time(), "ev": "resuming", "crashed_in_call": in_call}) + "\n")
            if in_call:
                f.write(json.dumps({"ts": time.time(), "ev": "call_begin", "id": 999, "path": "/submit"}) + "\n")
        s.start(serve=False); time.sleep(0.5)
        for _ in range(100):
            if s.final().get("gave_up"): break
            time.sleep(0.1)
        d = s.final(); out = s.grade()
        expect(f"{name}: final.json", (d.get("reason"), d.get("gave_up")), (want_reason, True))
        expect(f"{name}: reward", (out["success"], out["infra_error"]), (0, want_infra))
        s.stop()

    # 7b. the simulator dies in the settle window at the end of the agent's phase, every time (compose restarts it; the hook
    # re-sends the signal): the window counts as the agent's last call, so the give-up is sim_crashed_on_call, the agent's 0
    s = Svc("settle_crash", RW_STUB_SETTLE_CRASH=1); svcs.append(s); s.start()
    s.submit(row(0.2))                                   # the goal does not hold: no window inside the call
    for attempt in range(6):
        subprocess.run([sys.executable, os.path.join(SIM, "rcb_limited.py"), "end", s.data, "--timeout", "8"], capture_output=True, timeout=60)
        if s.final().get("gave_up"): break
        s.stop(); s.start(serve=False); time.sleep(0.5)
        for _ in range(100):
            if s.final().get("gave_up") or os.path.exists(os.path.join(s.data, "server.pid")): break
            time.sleep(0.1)
    d = s.final(); out = s.grade()
    expect("settle crash: final.json", (d.get("reason"), d.get("gave_up"), d.get("infra_error")), ("sim_crashed_on_call", True, None))
    expect("settle crash: reward", (out["success"], out["infra_error"]), (0, 0))
    ev = [json.loads(x) for x in open(os.path.join(s.data, "episode.jsonl")) if x.strip()]
    expect("settle crash: every resume saw a crash in a call", [e.get("crashed_in_call") for e in ev if e.get("ev") == "resuming"], [True, True])
    s.stop()

    # 8. the grader alone: no final.json -> infra; an old replay-rule record (no graded_by) is no live verdict
    empty = os.path.join(TMP, "empty"); os.makedirs(empty)
    out = grade(empty)
    expect("no final.json", (out["success"], out["infra_error"], out["missing_log"]), (0, 1, 1))
    old = os.path.join(TMP, "old"); os.makedirs(old)
    json.dump({"success": True, "replay_success": True, "deterministic": True, "finalized": True, "reason": "success"}, open(os.path.join(old, "final.json"), "w"))
    out = grade(old)
    expect("an old replay-rule record", (out["success"], out["infra_error"]), (0, 1))
finally:
    for s in svcs:
        s.stop()
    shutil.rmtree(TMP, ignore_errors=True)
for e in errs: print("FAIL", e)
print(f"{'FAIL' if errs else 'ok'} robowits standard service, live verdict: {n} checks, {len(errs)} failed")
sys.exit(1 if errs else 0)
