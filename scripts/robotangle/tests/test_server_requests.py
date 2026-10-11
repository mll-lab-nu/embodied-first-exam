"""Synthetic test of the RoboTangle standard sim service (scripts/robotangle/shared/standard/sim/server.py) on the real
eai-standard/2.4 layer, with a stub Session (fake_service.py; needs numpy, no simulator, no GPU; about 20 s):
  1. malformed request fields are a 400 that moves nothing and leaves the episode alive (PROTOCOL §4.6), including JSON
     integers beyond the float range, which were a 500 that ended the episode as an infrastructure error (review
     2026-10-10 R2, M5);
  2. the proprio group `gripper_opening` is the measured pad gap in metres in both gripper spaces, and its /spec text and
     joint_pos's agree with the column (M7): in the native space it repeated the drive coordinate.
  3. one call holds at most /spec max_frames_per_call images (review R3 B-M2): a request that would exceed it for certain
     is a 400 that moves nothing, the largest default request is served, a camera named several times is one camera, and
     rows that take longer than their `dt` (the joint-speed limit) stop adding frames at the budget without being cut short.
usage: python3 scripts/robotangle/tests/test_server_requests.py [repo root]"""
import json, os, shutil, socket, subprocess, sys, tempfile, time, urllib.error, urllib.request
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(ROOT, "scripts/eai_standard"))
import rcb1  # noqa: E402
TMP = tempfile.mkdtemp(prefix="rt_srv_")
SIM = os.path.join(TMP, "sim"); os.makedirs(SIM)       # the sim directory of a task, assembled from the sources
for src in ("scripts/robotangle/shared/standard/sim/server.py", "scripts/robotangle/shared/rcb_topogym.py",
            "scripts/eai_standard/v2_4/rcb_limited.py", "scripts/eai_standard/rcb1.py"):
    shutil.copy(os.path.join(ROOT, src), SIM)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


def get(port, path):
    return json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=30).read())


def post(port, path, meta, actions=None):
    raw = rcb1.encode(meta, [rcb1.array_part("actions", np.asarray(actions, np.float32))]) if actions is not None else json.dumps(meta).encode()
    try:
        r = urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=raw, method="POST"), timeout=60)
        code, body = r.status, r.read()
    except urllib.error.HTTPError as e:
        code, body = e.code, e.read()
    return code, (rcb1.decode(body)[0] if body[:4] == b"RCB1" else json.loads(body))


class Service:
    def __init__(self, space: str):
        self.port = free_port(); self.data = tempfile.mkdtemp(prefix="data_", dir=TMP)
        self.log = open(self.data + ".out", "w")
        self.p = subprocess.Popen([sys.executable, os.path.join(HERE, "fake_service.py"), SIM, self.data, str(self.port), space],
                                  stdout=self.log, stderr=subprocess.STDOUT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        for _ in range(150):
            try:
                get(self.port, "/status"); return
            except Exception:  # noqa: BLE001
                if self.p.poll() is not None: break
                time.sleep(0.2)
        raise RuntimeError("the service did not start:\n" + open(self.data + ".out").read()[-3000:])

    def close(self):
        self.p.kill(); self.p.wait(); self.log.close()


errs = []; n = 0
HUGE = 10 ** 400
OK = np.zeros((2, 8)); BASE = {"type": "joint_position", "video": "none"}
BAD = [("dt huge int", "/submit", {**BASE, "dt": HUGE}), ("dt -huge int", "/submit", {**BASE, "dt": -HUGE}),
       ("video_fps huge int", "/submit", {**BASE, "video_fps": HUGE}), ("seconds huge int", "/observe", {"seconds": HUGE, "video": "none"}),
       ("observe video_fps huge int", "/observe", {"video_fps": HUGE}), ("ee_pose dt huge int", "/submit", {**BASE, "type": "ee_pose", "dt": HUGE}),
       ("dt null", "/submit", {**BASE, "dt": None}), ("dt string", "/submit", {**BASE, "dt": "0.025"}), ("dt true", "/submit", {**BASE, "dt": True}),
       ("dt list", "/submit", {**BASE, "dt": [0.025]}), ("dt not a multiple", "/submit", {**BASE, "dt": 0.03}),
       ("video_fps null", "/submit", {**BASE, "video_fps": None}), ("video_fps 0", "/submit", {**BASE, "video_fps": 0}),
       ("video_fps 2.5", "/submit", {**BASE, "video_fps": 2.5}), ("video_fps 41", "/submit", {**BASE, "video_fps": 41}),
       ("seconds null", "/observe", {"seconds": None}), ("seconds string", "/observe", {"seconds": "1"}), ("seconds -1", "/observe", {"seconds": -1}),
       ("seconds 31", "/observe", {"seconds": 31}), ("note int", "/submit", {**BASE, "note": 5}), ("note dict", "/submit", {**BASE, "note": {"a": 1}}),
       ("cameras string", "/submit", {**BASE, "cameras": "agentview"}), ("cameras [1]", "/submit", {**BASE, "cameras": [1]}),
       ("type list", "/submit", {**BASE, "type": ["joint_position"]}), ("interpolate dict", "/submit", {**BASE, "interpolate": {"a": 1}}),
       ("video list", "/submit", {**BASE, "video": ["mp4"]}), ("depth 7", "/submit", {**BASE, "depth": 7})]
svc = Service("native")
try:
    for name, path, meta in BAD:      # one episode for all of them: none may end it or move the robot
        code, body = post(svc.port, path, meta, OK if path == "/submit" else None); st = get(svc.port, "/status"); n += 1
        if code != 400 or st["done"] or st["control_steps"] != 0:
            errs.append(f"{name}: HTTP {code}, status {st} (want 400, the episode alive, 0 control steps): {str(body)[:200]}")
    code, body = post(svc.port, "/submit", {**BASE, "dt": 0.025}, OK); st = get(svc.port, "/status"); n += 1
    if code != 200 or st["done"] or st["control_steps"] != 2:
        errs.append(f"a valid submit after the malformed ones: HTTP {code}, status {st}")
    final = json.load(open(os.path.join(svc.data, "final.json")))
    if final.get("infra_error") or final.get("done"):
        errs.append(f"final.json after the malformed requests: {final}")
finally:
    svc.close()
svc = Service("native")     # a fresh episode: a failure above may have ended the first one
try:
    # M7, native space: joint_pos carries the drive coordinate (rad, 0 = open .. 0.8 = closed), gripper_opening the gap (m)
    spec = get(svc.port, "/spec"); g = spec["proprio_groups"]
    first = g["gripper_opening"][0]; lay = spec["proprio_layout"]
    A = np.zeros((1, 8)); A[0, 7] = 0.8          # the native CLOSED target
    code, m = post(svc.port, "/submit", {**BASE, "dt": 0.025}, A); now = m["proprio"]["now"]; n += 1
    if not (abs(now[7] - 0.8) < 1e-6 and abs(now[first]) < 1e-6 and lay[first] == "arm_gripper_opening_m"):
        errs.append(f"native, closed: joint_pos gripper {now[7]} (want 0.8 rad), {lay[first]} {now[first]} (want 0 m)")
    A[0, 7] = 0.0                                 # the native OPEN target
    code, m = post(svc.port, "/submit", {**BASE, "dt": 0.025}, A); now = m["proprio"]["now"]; n += 1
    if not (abs(now[7]) < 1e-6 and abs(now[first] - 0.085) < 1e-6):
        errs.append(f"native, open: joint_pos gripper {now[7]} (want 0 rad), gripper_opening {now[first]} (want 0.085 m)")
    for name, words in (("joint_pos", ("native drive coordinate", "arm_native_gripper: rad, 0 = open .. 0.8 = closed", "not an opening width")),
                        ("joint_vel", ("native drive coordinate",)), ("gripper_opening", ("gap between the two finger pads", "Always metres"))):
        n += 1
        if not all(w in g[name][2] for w in words): errs.append(f"native /spec proprio_groups.{name}: {g[name][2]!r}")
finally:
    svc.close()
svc = Service("width")
try:
    spec = get(svc.port, "/spec"); g = spec["proprio_groups"]; first = g["gripper_opening"][0]
    A = np.zeros((1, 8)); A[0, 7] = 0.04
    code, m = post(svc.port, "/submit", {**BASE, "dt": 0.025}, A); now = m["proprio"]["now"]; n += 3
    if not (abs(now[7] - 0.04) < 1e-6 and abs(now[first] - 0.04) < 1e-6):
        errs.append(f"width: joint_pos gripper {now[7]}, gripper_opening {now[first]} (want 0.04 m both)")
    if "gripper opening (m)" not in g["joint_pos"][2] or "native" in g["joint_pos"][2] + g["joint_vel"][2] + g["gripper_opening"][2]:
        errs.append(f"width /spec proprio_groups: {g['joint_pos'][2]!r} {g['gripper_opening'][2]!r}")
finally:
    svc.close()
svc = Service("native")     # 3. the call's image budget
try:
    def call(path, meta, actions=None):
        raw = rcb1.encode(meta, [rcb1.array_part("actions", np.asarray(actions, np.float32))]) if actions is not None else json.dumps(meta).encode()
        try:
            r = urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{svc.port}{path}", data=raw, method="POST"), timeout=300)
            return r.status, *rcb1.decode(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read()), {}
    limit = get(svc.port, "/spec").get("max_frames_per_call"); n += 1
    if limit != 2000: errs.append(f"/spec max_frames_per_call: {limit!r} (want 2000)")
    for name, path, meta, acts in (
            ("a 30 s watch at 40 fps with per-frame depth (1202 frames x 4)", "/observe", {"seconds": 30, "video_fps": 40, "depth": "frames"}, None),
            ("the same with include_depth", "/observe", {"seconds": 30, "video_fps": 40, "include_depth": True}, None),
            ("a 10 s chunk at 40 fps with per-frame depth", "/submit", {**BASE, "dt": 0.25, "video_fps": 40, "depth": "frames", "video": "frames"}, np.zeros((40, 8)))):
        code, body, _ = call(path, meta, acts); st = get(svc.port, "/status"); n += 1
        want = 400 if path == "/observe" else 200      # the chunk: 402 frames x 4 = 1608 images, inside the budget
        if code != want or st["done"] or (want == 400 and (st["control_steps"] != 0 or "max_frames_per_call" not in str(body))):
            errs.append(f"{name}: HTTP {code} (want {want}), status {st}: {str(body)[:200]}")
    steps0 = get(svc.port, "/status")["control_steps"]
    code, m, parts = call("/observe", {"seconds": 30, "cameras": ["agentview"] * 7, "video": "frames"}); n += 1   # the default rate, the longest watch
    shape = list(parts.get("frames/agentview", {}).get("data", np.zeros(0)).shape)
    if code != 200 or shape[0] not in (301, 302) or m.get("frames_skipped") or get(svc.port, "/status")["control_steps"] != steps0 + 1200:
        errs.append(f"the longest default watch, its camera named 7 times: HTTP {code}, frames {shape} (want 301 or 302 of one camera), {str(m)[:200]}")
    A = np.zeros((30, 8)); A[::2, :7] = 2.9; A[1::2, :7] = -2.9      # each row takes 145 control steps at 0.04 rad per step, not 1
    code, m, parts = call("/submit", {"type": "joint_position", "dt": 0.025, "video_fps": 40, "depth": "frames", "video": "frames"}, A); n += 1
    shape = list(parts.get("frames/agentview", {}).get("data", np.zeros(0)).shape)
    if not (code == 200 and m["executed_rows"] == 30 and m["control_steps_chunk"] > 4000 and shape[:1] == [500] and m.get("frames_skipped", 0) > 3000
            and len(parts["proprio"]["data"]) == 500):
        errs.append(f"rows stretched by the speed limit: HTTP {code}, frames {shape} (want 500 = 2000 / 4), "
                    f"{ {k: m.get(k) for k in ('executed_rows', 'control_steps_chunk', 'frames_skipped')} }")
finally:
    svc.close()
shutil.rmtree(TMP, ignore_errors=True)
for e in errs: print("FAIL", e)
print(f"{'FAIL' if errs else 'ok'} robotangle standard service: {n} checks, {len(errs)} failed")
sys.exit(1 if errs else 0)
