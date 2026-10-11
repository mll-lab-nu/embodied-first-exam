"""Synthetic test of the RoboWits standard sim service's image budget (scripts/robowits/shared/server.py on the real
eai-standard/2.2 layer, with a stub Session; needs numpy, no simulator, no GPU; a few seconds). One call holds at most
/spec max_frames_per_call images (review R3 B-M2): a request that would exceed it for certain is a 400 that moves nothing,
the largest default request is served, a camera named several times is one camera, and ee_pose rows that take longer than
the 4 control steps they are counted with stop adding frames at the budget without being cut short.
usage: python3 scripts/robowits/tests/test_server_frames.py [repo root]"""
import hashlib, json, os, runpy, shutil, socket, subprocess, sys, tempfile, time, types, urllib.error, urllib.request
import numpy as np
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))


def serve(sim: str, data: str, port: int) -> None:
    """The launcher (a child process): the real server.py with a stub rcb_robowits (16 joint targets, three 4x6 cameras)."""
    sys.path.insert(0, sim)
    os.environ.update(RCB_DATA=data, RCB_SESSION_LOG="", RCB_INSTANCE=os.path.join(data, "instance.json"), RCB_TASK="stack_cubes")
    os.makedirs(data, exist_ok=True); json.dump({}, open(os.environ["RCB_INSTANCE"], "w"))
    import rcb_limited as L
    _serve = L.serve
    L.serve = lambda svc, port=port: _serve(svc, port)

    class Session:
        def __init__(s, task, instance=None):
            s._t = np.zeros(16); s.n_steps = 0; s._recording = None; s.instance_sha = "s0"; s.eval_index = 0
            s.instance_matches = s.instance_exact = True; s.max_steps = 200000; s.spec = {"text": "do it"}; s.robot = types.SimpleNamespace()
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
            a = np.stack(s._recording) if s._recording else np.zeros((0, 16), np.float32); s._recording = None; return a

        def save_trajectory(s, acts, path, meta=None): np.savez(path, actions=acts, task="t", meta=json.dumps(meta or {}))
        def ik(s, arm, pos, q): return np.zeros(7), 0.0, 0.0         # every pose: the joints at 0
        def replay(s, acts): return {"success": False, "state_sha": s.state_sha()}
        def kinematics(s, req): return {"ok": True}
        def start_video(s, path, fps=15): pass
        def stop_video(s): pass

        def step(s, row):
            s._t = np.asarray(row, np.float64).reshape(-1).copy(); s.n_steps += 1
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
TMP = tempfile.mkdtemp(prefix="rw_srv_"); SIM = os.path.join(TMP, "sim"); os.makedirs(SIM)
for src in ("scripts/robowits/shared/server.py", "scripts/eai_standard/rcb_limited.py", "scripts/eai_standard/rcb1.py"):
    shutil.copy(os.path.join(ROOT, src), SIM)
with socket.socket() as k:
    k.bind(("127.0.0.1", 0)); PORT = k.getsockname()[1]
URL = f"http://127.0.0.1:{PORT}"
out = open(os.path.join(TMP, "service.out"), "w")
proc = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--serve", SIM, os.path.join(TMP, "data"), str(PORT)], stdout=out,
                        stderr=subprocess.STDOUT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})


def get(path):
    return json.loads(urllib.request.urlopen(URL + path, timeout=30).read())


def call(path, meta, actions=None):
    raw = rcb1.encode(meta, [rcb1.array_part("actions", np.asarray(actions, np.float32))]) if actions is not None else json.dumps(meta).encode()
    try:
        r = urllib.request.urlopen(urllib.request.Request(URL + path, data=raw, method="POST"), timeout=300)
        return r.status, *rcb1.decode(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read()), {}


errs = []; n = 0
try:
    for _ in range(150):
        try:
            get("/status"); break
        except Exception:  # noqa: BLE001
            if proc.poll() is not None: break
            time.sleep(0.2)
    else:
        proc.kill()
    if proc.poll() is not None:
        raise RuntimeError("the service did not start:\n" + open(os.path.join(TMP, "service.out")).read()[-3000:])
    limit = get("/spec").get("max_frames_per_call"); n += 1
    if limit != 1500: errs.append(f"/spec max_frames_per_call: {limit!r} (want 1500)")
    for name, meta in (("a 30 s watch at 30 fps, three cameras (902 frames x 3)", {"seconds": 30, "video_fps": 30}),
                       ("a 30 s watch with per-frame depth (302 frames x 3 x 4)", {"seconds": 30, "depth": "frames"}),
                       ("the same with include_depth", {"seconds": 30, "include_depth": True})):
        code, body, _ = call("/observe", meta); st = get("/status"); n += 1
        if code != 400 or st["done"] or st["control_steps"] != 0 or "max_frames_per_call" not in str(body):
            errs.append(f"{name}: HTTP {code} (want 400), status {st}: {str(body)[:200]}")
    code, body, _ = call("/submit", {"type": "joint_position", "dt": 1 / 30, "video_fps": 30, "depth": "frames"}, np.zeros((300, 16))); n += 1
    if code != 400 or get("/status")["control_steps"] != 0:
        errs.append(f"a 10 s chunk at 30 fps with per-frame depth (302 frames x 3 x 4): HTTP {code} (want 400): {str(body)[:200]}")
    code, m, parts = call("/observe", {"seconds": 30, "video": "frames"}); n += 1                     # the default rate and cameras, the longest watch
    shapes = {c: list(parts[f"frames/{c}"]["data"].shape[:1]) for c in ("ego", "wrist_right", "wrist_left") if f"frames/{c}" in parts}
    if code != 200 or shapes != {"ego": [302], "wrist_right": [302], "wrist_left": [302]} or m.get("frames_skipped") or get("/status")["control_steps"] != 900:
        errs.append(f"the longest default watch (906 images): HTTP {code}, frames {shapes}, {str(m)[:200]}")
    code, m, parts = call("/observe", {"seconds": 30, "video_fps": 30, "cameras": ["ego"] * 9, "video": "frames"}); n += 1
    shape = list(parts.get("frames/ego", {}).get("data", np.zeros(0)).shape[:1])
    if code != 200 or shape != [902] or len([p for p in parts if p.startswith("frames/")]) != 1:
        errs.append(f"one camera named 9 times at 30 fps: HTTP {code}, frames {shape} (want 902 of one camera)")
    A = np.zeros((1, 16)); A[0, :7] = 2.0; call("/submit", {"type": "joint_position", "video": "none"}, A)   # the right arm at 2 rad
    P = np.tile(np.array([0.3, 0, 0.3, 1, 0, 0, 0, 0.05] * 2, np.float64), (20, 1))   # the stub's IK: back to 0, 50 control steps for row 0, 4 for the rest
    code, m, parts = call("/submit", {"type": "ee_pose", "video_fps": 30, "depth": "frames", "video": "frames"}, P); n += 1
    shape = list(parts.get("frames/ego", {}).get("data", np.zeros(0)).shape[:1])
    if not (code == 200 and m["executed_rows"] == 20 and m["control_steps_chunk"] == 126 and shape == [125] and m.get("frames_skipped") == 3
            and len(parts["proprio"]["data"]) == 125):
        errs.append(f"ee_pose rows longer than counted: HTTP {code}, frames {shape} (want 125 = 1500 / (3 x 4)), "
                    f"{ {k: m.get(k) for k in ('executed_rows', 'control_steps_chunk', 'frames_skipped')} if code == 200 else m}")
finally:
    proc.kill(); proc.wait(); out.close(); shutil.rmtree(TMP, ignore_errors=True)
for e in errs: print("FAIL", e)
print(f"{'FAIL' if errs else 'ok'} robowits standard service, image budget: {n} checks, {len(errs)} failed")
sys.exit(1 if errs else 0)
