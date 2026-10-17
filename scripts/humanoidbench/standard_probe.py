"""Checks and times one standard twin's sim service; `gen_tasks.py measure-standard` runs it inside the base image with
a GPU, against a scratch copy of the sidecar directory (argv[1]). Settings come from the environment: RCB_TASK,
RCB_INSTANCE, RCB_ROOM_CAMERA_POSE, RCB_IMAGE_HW, RCB_DATA, RCB_FACTS (that family's facts.json entry, as JSON) and
RCB_IMAGES (where the t=0 images go).

In process, through rcb_service.Service.handle (the HTTP surface without the socket):
  spec        eai-standard/2.1; the actuators in facts.json's order, the episode length
  hardware    every actuator has a range, every joint an axis, every camera a field of view and a pose
  images      every camera at t=0 is neither black nor flat; room_camera stands where spec() says
  proprio     the proprioception row is the robot's joint slice of qpos / qvel, then the IMU
  nop         an all-zero episode, sent in chunks, ends where facts.json says and returns facts.json's nop_return: the
              formula in the sidecar is upstream's
  reset       (the optional capability) back to the frozen start, every camera's image included; a chunk is
              bit-identical to the same rows sent one at a time (one row a control step, and rows two control steps
              apart, interpolated linearly); the servo targets are the rows mapped linearly onto spec()'s ranges
  success     with the pass mark lowered in this process only, the episode ends as a success, the finalize grades
              it live (graded_by "live", no replay) and renders a video that is not black
Then through the real HTTP service and the shipped client: a crash (SIGKILL) and restart that must resume the same
episode, and the cost per control step: one row a call with one head camera, with both, and chunks of 10 rows.
Prints PASS/FAIL lines and a last JSON line for gen_tasks.py.
"""
import json
import os
import signal
import statistics
import subprocess
import sys
import time

import numpy as np

SIM = sys.argv[1]
sys.path.insert(0, SIM)
import server  # noqa: E402  restores the formula, picks the GL backend
import rcb1  # noqa: E402
from PIL import Image  # noqa: E402
from rcb_service import Service  # noqa: E402

env = os.environ.get
task, facts, images_dir, data = env("RCB_TASK"), json.loads(env("RCB_FACTS")), env("RCB_IMAGES"), env("RCB_DATA")
os.makedirs(images_dir, exist_ok=True)
failed = []


def check(name, ok, **kw):
    print(("PASS " if ok else "FAIL ") + name, json.dumps(kw, default=str)[:600], flush=True)
    if not ok:
        failed.append(name)


def call(svc, path, meta=None, rows=None):
    body = rcb1.encode(meta or {}, [rcb1.array_part("actions", np.asarray(rows, np.float64))] if rows is not None else [])
    code, ctype, out = svc.handle("POST", path, body)
    assert ctype == "application/x-rcb1", (code, out[:300])
    return rcb1.decode(out)


def run(svc, rows, **meta):
    """Rows at one per control step, in chunks of at most 10 s; returns the last answer's meta."""
    n = int(round(svc.max_chunk_s / svc.sim.control_dt))
    for i in range(0, len(rows), n):
        m, _ = call(svc, "/submit", {"type": "joint_position", "dt": svc.sim.control_dt, "interpolate": "hold",
                                     "video": "none", "cameras": ["left_eye_camera"], **meta}, rows[i:i + n])
        if m["done"]:
            break
    return m


pose = [float(v) for v in env("RCB_ROOM_CAMERA_POSE", "").split(",") if v.strip()]
sim = server.HumanoidBench(task, env("RCB_INSTANCE"), proprio=True, imu=True, room_camera=True,
                           room_pose=(np.array(pose[:3]), *pose[3:]) if pose else None, task_text="probe",
                           image_hw=int(env("RCB_IMAGE_HW") or 0) or None)
svc = Service(sim, data=f"{data}/inproc", reset_budget=10)
svc.start()
sp, nu = svc.spec, sim.nu
jp = sp["action_types"]["joint_position"]
check("spec", sp["protocol"] == "eai-standard/2.1" and jp["layout"] == facts["actuator_names"]
      and sp["max_control_steps"] == facts["max_steps"], nu=nu, control_dt=sp["control_dt"], cameras=list(sp["cameras"]),
      joints=len(sp["proprio"]["joints"]), gl=sp["gl_backend"], room=sim._room)
check("hardware", len(jp["range_rad"]) == nu and len(sp["proprio"]["axis"]) == len(sp["proprio"]["joints"])
      and all(abs(np.linalg.norm(a) - 1) < 1e-2 for a in sp["proprio"]["axis"]) and bool(sp["imu"]["frame"])
      and all({"fovy_deg", "pose", "hw"} <= set(v) for v in sp["cameras"].values()),
      cameras={c: v["pose"] for c, v in sp["cameras"].items()})
start = sim.state_sha()

meta, parts = call(svc, "/observe", {"video": "frames"})
t0 = {c: parts[f"last/{c}"]["data"] for c in sim.cameras}
stats = {}
for cam, img in t0.items():
    Image.fromarray(img).save(f"{images_dir}/t0_{cam}.png")
    stats[cam] = [list(img.shape), round(float(img.mean()), 1), round(float(img.std()), 1)]
check("images", all(v[1] > 5 and v[2] > 2 for v in stats.values()), stats=stats)
# room_camera was rendered last: the viewer's own camera must sit where spec() says, read back into the world
gl, cpose = sim.s.low.mujoco_renderer.viewer.scn.camera, sp["cameras"]["room_camera"]["pose"]
pel = sim.s.model.body("pelvis").id
x0, yaw = sim.s.data.xpos[pel], np.arctan2(sim.s.data.xmat[pel][3], sim.s.data.xmat[pel][0])
Y = np.array([[np.cos(yaw), -np.sin(yaw), 0], [np.sin(yaw), np.cos(yaw), 0], [0, 0, 1]])
seen = (np.array(gl[0].pos) + np.array(gl[1].pos)) / 2, np.array(gl[0].forward)
said = Y @ cpose["position_m"] + [x0[0], x0[1], 0], Y @ cpose["forward"]
check("room_camera pose", np.allclose(seen[0], said[0], atol=5e-3) and np.allclose(seen[1], said[1], atol=5e-3),
      seen=[v.round(3).tolist() for v in seen], said=[v.round(3).tolist() for v in said])
dof, nj = sim.robot.dof, len(sp["proprio"]["joints"])
now = np.array(meta["proprio"]["now"])
check("proprio", len(now) == len(sp["proprio_layout"]) == 2 * nj + 6 and nj == dof - 7
      and np.allclose(now[:nj], sim.s.data.qpos[7:dof], atol=1e-5)
      and np.allclose(now[nj:2 * nj], sim.s.data.qvel[6:dof - 1], atol=1e-4), n=len(now), dof=dof)

m = run(svc, np.zeros((facts["max_steps"], nu)))
ret = sim.s._ret
check("nop", m["control_steps"] == facts["nop_steps"] and round(ret, 2) == facts["nop_return"] and m["done"]
      and m["reason"] == "failed", control_steps=m["control_steps"], nop_steps=facts["nop_steps"], ret=round(ret, 4),
      nop_return=facts["nop_return"], reason=m["reason"])

meta, parts = call(svc, "/reset", {"video": "frames"})
ok_start = sim.state_sha() == start
drift = {c: int((np.abs(parts[f"last/{c}"]["data"].astype(int) - img.astype(int)).sum(-1) > 12).sum())
         for c, img in t0.items()}                                   # the same start, so the same pictures (goal marker too)
A = np.clip(np.random.default_rng(0).normal(0, 0.1, (min(40, facts["nop_steps"] - 1), nu)), -1, 1)
for a in A:
    run(svc, a[None])
one_by_one = sim.state_sha()
lo, hi = np.array(jp["range_rad"]).T
check("range", np.allclose(sim.s.data.ctrl[:nu], lo + (A[-1].astype(np.float32) + 1) / 2 * (hi - lo), atol=1e-3))
call(svc, "/reset", {"video": "none"})
run(svc, A)
check("reset", ok_start and not any(drift.values()) and sim.state_sha() == one_by_one, steps=len(A), pixels_changed=drift)
# Each row of B is 2 control steps, so B must end well inside the episode. Random rows can end it sooner than the
# all-zero trajectory does: balance_hard's (46 steps) ended before half of nop_steps; a third leaves room.
B, lin = A[:min(20, (facts["nop_steps"] - 1) // 3)], {"dt": 2 * sim.control_dt, "interpolate": "linear"}
call(svc, "/reset", {"video": "none"})
for b in B:
    run(svc, b[None], **lin)
one_by_one = sim.state_sha()
call(svc, "/reset", {"video": "none"})
run(svc, B, **lin)
check("chunk = rows, linear", sim.state_sha() == one_by_one, rows=len(B), dt=lin["dt"])

call(svc, "/reset", {"video": "none"})
bar = type(sim.s.low.task).success_bar                     # lowered for the live episode (and the video's pass)
type(sim.s.low.task).success_bar = facts["nop_return"] / 2 if facts["nop_return"] > 0 else -1e9
sim.s.success_bar = type(sim.s.low.task).success_bar
m = run(svc, np.zeros((facts["max_steps"], nu)))
svc.on_sigusr1()
svc.poll()                                                  # the collect hook's signal, then the HTTP loop: finalize
fin = json.load(open(f"{data}/inproc/final.json"))
vid = False
if fin.get("video"):
    import imageio.v2 as imageio
    frames = imageio.mimread(f"{data}/inproc/replay.mp4", memtest=False)
    vid = len(frames) > 1 and float(np.mean(frames[len(frames) // 2])) > 5
check("success", m["reason"] == "success" and fin.get("success") and fin.get("graded_by") == "live" and vid,
      control_steps=m["control_steps"], final={k: fin.get(k) for k in ("live_success", "success", "graded_by", "video")})
type(sim.s.low.task).success_bar = sim.s.success_bar = bar
del svc, sim

# Through HTTP, as the agent pays it: a crash it must survive, then the cost per control step.
hdata = f"{data}/http"
server_env = {**os.environ, "RCB_DATA": hdata, "RCB_RESET_BUDGET": "100000"}


def start_server():
    return subprocess.Popen([sys.executable, f"{SIM}/server.py"], env=server_env, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)


srv = start_server()
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "shared", "standard"))
try:
    from rcb_client import Robot
    r = Robot("http://localhost:8000")
    B = np.clip(np.random.default_rng(1).normal(0, 0.1, (25, nu)), -1, 1)
    r.submit("joint_position", B, interpolate="hold", cameras=["left_eye_camera"], video="none")
    before = r.status()["control_steps"], r.get_obs(cameras=["left_eye_camera"], video="none").meta["proprio"]["now"]
    srv.kill()                                              # a crash; compose would restart it: the same episode must come back
    srv.wait()
    srv = start_server()
    r = Robot("http://localhost:8000")
    after = r.status()["control_steps"], r.get_obs(cameras=["left_eye_camera"], video="none").meta["proprio"]["now"]
    check("resume", after == before, control_steps=after[0])
    r.reset(cameras=["left_eye_camera"])                    # the random rows may have ended the episode (a fall)

    def cost(n, cameras, rows):
        spent, done = 0.0, 0
        while done < n:
            t = time.perf_counter()
            res = r.submit("joint_position", np.zeros((rows, nu)), interpolate="hold", cameras=cameras, video="none")
            spent += time.perf_counter() - t
            done += res.meta["executed_rows"]
            if res.done:
                r.reset(cameras=["left_eye_camera"])
        return spent / done * 1e3
    runs = {"single": [], "images": [], "batch": []}
    for _ in range(5):
        runs["single"].append(cost(50, ["left_eye_camera"], 1))
        runs["images"].append(cost(30, ["left_eye_camera", "right_eye_camera"], 1))
        runs["batch"].append(cost(100, ["left_eye_camera"], 10))
    r.reset(cameras=["left_eye_camera"])
    r.submit("joint_position", B, interpolate="hold", cameras=["left_eye_camera"], video="none")
    srv.send_signal(signal.SIGUSR1)                         # what the verifier's collect hook does
    for _ in range(120):
        fin = json.load(open(f"{hdata}/final.json"))
        if fin.get("finalized") and not fin.get("video_pending"):   # the verdict, then the video
            break
        time.sleep(1)
    check("finalize", fin.get("graded_by") == "live" and fin.get("sim_startups") == 2, final=fin)
finally:
    srv.terminate()
step_ms = {k: round(statistics.median(v), 2) for k, v in runs.items()}
print("PASS cost", json.dumps(step_ms))
print(json.dumps({"failed": failed, "facts": {
    "control_hz": round(1 / sp["control_dt"]), "image_hw": sp["cameras"]["left_eye_camera"]["hw"],
    "joints": sp["proprio"]["joints"], "step_ms": step_ms}}))
