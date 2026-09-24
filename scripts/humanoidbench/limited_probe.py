"""Checks and times one limited twin's sim service; `gen_tasks.py measure-limited` runs it inside the base image
with a GPU, against a scratch copy of the sidecar directory (argv[1]). Settings come from the environment:
RCB_TASK, RCB_INSTANCE, RCB_ROOM_CAMERA_POSE, RCB_DATA, RCB_FACTS (that family's facts.json entry, as JSON) and
RCB_IMAGES (where the t=0 images go).

In process, through rcb_service.Service (no HTTP):
  spec        the actuators in facts.json's order, the episode length
  images      every camera at t=0 is neither black nor flat
  proprio     obs["proprio"] is the robot's joint slice of qpos / qvel
  nop         the all-zero episode ends where facts.json says and returns facts.json's nop_return: the formula in
              the sidecar is upstream's
  reset       back to the frozen start; a batch is bit-identical to the same actions one at a time
  success     with the bar lowered in this process only, the episode ends as a success and finalize saves,
              replays (success, deterministic) and renders a video that is not black
Then through the real HTTP service and the shipped client: ms per control step one at a time, one at a time with
both head-camera images, and in batches of 10. Prints PASS/FAIL lines and a last JSON line for gen_tasks.py.
"""
import base64
import io
import json
import os
import statistics
import subprocess
import sys
import time

import numpy as np

SIM = sys.argv[1]
sys.path.insert(0, SIM)
import server  # noqa: E402  restores the formula, picks the GL backend
from PIL import Image  # noqa: E402
from rcb_service import Service  # noqa: E402

env = os.environ.get
task, facts, images_dir = env("RCB_TASK"), json.loads(env("RCB_FACTS")), env("RCB_IMAGES")
os.makedirs(images_dir, exist_ok=True)
failed = []


def check(name, ok, **kw):
    print(("PASS " if ok else "FAIL ") + name, json.dumps(kw, default=str)[:600], flush=True)
    if not ok:
        failed.append(name)


def png(b64):
    return np.asarray(Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB"))


pose = [float(v) for v in env("RCB_ROOM_CAMERA_POSE", "").split(",") if v.strip()]
sim = server.HumanoidBench(task, env("RCB_INSTANCE"), proprio=True, imu=True, room_camera=True,
                           room_pose=(np.array(pose[:3]), *pose[3:]) if pose else None, task_text="probe")
svc = Service(sim, reset_budget=10)
sp, nu = svc.spec, sim.s.nu
check("spec", sp["qpos"]["layout"] == facts["actuator_names"] and sp["max_episode_steps"] == facts["max_steps"],
      nu=nu, control_hz=sp["control_hz"], max_steps=sp["max_episode_steps"], cameras=list(sp["cameras"]),
      joints=len(sp["proprio"]["joints"]), gl=sp["gl_backend"], camera_name=sim.s.low.camera_name, room=sim._room)
start = sim.state_sha()

obs = svc.observation(list(sim.cameras))
stats = {}
for cam, b in obs["images"].items():
    img = png(b)
    Image.fromarray(img).save(f"{images_dir}/t0_{cam}.png")
    stats[cam] = [list(img.shape), round(float(img.mean()), 1), round(float(img.std()), 1)]
check("images", all(v[1] > 5 and v[2] > 2 for v in stats.values()), stats=stats)
dof = sim.robot.dof
jp, jv = np.array(obs["proprio"]["joint_pos"]), np.array(obs["proprio"]["joint_vel"])
check("proprio", len(jp) == len(sp["proprio"]["joints"]) == dof - 7 and np.allclose(jp, sim.s.data.qpos[7:dof])
      and np.allclose(jv, sim.s.data.qvel[6:dof - 1]), n=len(jp), dof=dof)

code, o = svc.do_step({"type": "qpos", "actions": np.zeros((facts["max_steps"], nu)).tolist(), "images": False})
ret = sim.s._ret
check("nop", code == 200 and o["executed"] == facts["nop_steps"] and round(ret, 2) == facts["nop_return"]
      and o["done"] and o["reason"] == "failed", executed=o["executed"], nop_steps=facts["nop_steps"],
      ret=round(ret, 4), nop_return=facts["nop_return"], reason=o["reason"])

svc.do_reset({"images": False})
ok_start = sim.state_sha() == start
A = np.clip(np.random.default_rng(0).normal(0, 0.1, (min(40, facts["nop_steps"] - 1), nu)), -1, 1)
for a in A:
    svc.do_step({"type": "qpos", "action": a.tolist(), "images": False})
one_by_one = sim.state_sha()
svc.do_reset({"images": False})
svc.do_step({"type": "qpos", "actions": A.tolist(), "images": False})
check("reset", ok_start and sim.state_sha() == one_by_one, steps=len(A))

svc.do_reset({"images": False})
bar, sim.s.success_bar = sim.s.success_bar, (facts["nop_return"] / 2 if facts["nop_return"] > 0 else -1e9)
code, o = svc.do_step({"type": "qpos", "actions": np.zeros((facts["max_steps"], nu)).tolist(), "images": False})
svc.between_requests()                          # what the HTTP loop does: finalize on the main thread
fin = json.load(open(f"{env('RCB_DATA')}/final.json"))
vid = False
if fin.get("video"):
    import imageio.v2 as imageio
    frames = imageio.mimread(f"{env('RCB_DATA')}/replay.mp4", memtest=False)
    vid = len(frames) > 1 and float(np.mean(frames[len(frames) // 2])) > 5
check("success", o["reason"] == "success" and fin.get("replay_success") and fin.get("deterministic") and vid,
      executed=o["executed"], final={k: fin.get(k) for k in ("success", "replay_success", "deterministic", "video")})
sim.s.success_bar = bar
del svc, sim

# Per-step cost through HTTP, as the agent pays it. A step that ends the episode is followed by an untimed reset,
# which also renders the cameras once: the first frame after a reset sets the renderer up again (~2 s).
data = f"{env('RCB_DATA')}-http"
srv = subprocess.Popen([sys.executable, f"{SIM}/server.py"], env={**os.environ, "RCB_DATA": data,
                       "RCB_RESET_BUDGET": "100000"}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "shared", "limited"))
try:
    from rcb_client import Robot
    r = Robot("http://localhost:8000")

    def cost(n, images, batch):
        spent, done = 0.0, 0
        if images:
            r.observe(images=images)
        while done < n:
            a = np.zeros((batch, nu)) if batch else np.zeros(nu)
            t0 = time.perf_counter(); o = r.step("qpos", a, images=images); spent += time.perf_counter() - t0
            done += o.get("executed", 1)
            if o["done"]:
                r.reset(images=images)
        return spent / done * 1e3
    runs = {"single": [], "images": [], "batch": []}
    for _ in range(5):
        runs["single"].append(cost(50, False, 0))
        runs["images"].append(cost(30, ["left_eye_camera", "right_eye_camera"], 0))
        runs["batch"].append(cost(100, False, 10))
finally:
    srv.terminate()
step_ms = {k: round(statistics.median(v), 2) for k, v in runs.items()}
print("PASS cost", json.dumps(step_ms))
print(json.dumps({"failed": failed, "facts": {
    "control_hz": sp["control_hz"], "image_hw": sp["cameras"]["left_eye_camera"]["hw"],
    "joints": sp["proprio"]["joints"], "step_ms": step_ms}}))
