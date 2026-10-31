# TactileLab · nut_thread — STANDARD MODE (robot as a service, eai-standard/2.2)

You control a **dual-arm X-Trainer** whose **right gripper's fingers are two GelSight Mini tactile sensors**, **as if it
were real hardware**: the simulator runs in a service you cannot open. You get one client and one episode.

**Task:** The M16 nut already sits engaged on the top of the fixed bolt: grasp it, turn it down the thread and let go of it.

In the scene: a fixed M16 bolt (thread 25 mm long, pitch 2 mm); an M16 nut (30 g) engaged on its top, about 2 mm into the thread.

**Success.** Checked after every control step, the condition is reached once all of these hold:
- the nut counts as threaded (and stays so) at the first control step where it is at least **3.5 mm** below the thread top (about three quarters of a turn further down than at the start), with lateral offset at most 8 mm and axis angle at most 15°
- the right gripper has made a release that has held for 30 steps
- when the condition is judged (after the 60-step hold), the nut is still on the bolt within the bounds above

## Rules
- **No reset, no privileged state** (docs/protocol/standard_mode.md): you see the cameras, the tactile images and the
  robot's own proprioception; no object poses, no success predicate.
- **Episode.** When the success condition is reached after a control step, the last command is held for 60 more control
  steps (1 s, in the same response) and the task is judged. This task's condition stays reached once reached (it
  latches), so the task is solved unless a part has left its place (the end-of-episode check above) by then. Solved ends
  the episode with score 1; otherwise the episode goes on, and the next control step at which the condition is reached
  starts another hold. After a hold that does not solve the task, the next one starts no earlier than 60 control steps
  later, so your rows keep running between holds. The episode also ends when your time is up (the last command is then
  held for 60 control steps and the task judged once more), on a simulator error (score 0), when the task has failed for
  good (above, if any), or once the episode has run 29,940 control steps, holds included (499 s of simulated time;
  reason `step_guard`; a hold already running finishes first; then held and judged as at the time limit):
  `spec["max_control_steps"]` = 30,060 is the most an episode runs, its final hold included. This task's replays run at
  about 18.2 control steps per second (10.9 on a loaded host); this service is no faster.
- There is nothing to hand in: the service records and grades the episode as it runs. Leave your script at
  `/app/output/gen.py` for the record.
- The service answers one request at a time; a crash is recovered: the same episode resumes after the last completed
  call (`spec["on_service_error"]`, `r.wait_ready()`).

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`)
```python
from rcb_client import Robot
r = Robot()                          # waits while Isaac Sim starts and builds the scene (a few minutes)
spec = r.spec()                      # action type, cameras, proprio layout, robot spec, kinematics, budget
obs = r.get_obs(cameras=["wrist_right", "tactile_right", "tactile_left"], depth=True)
obs.last["wrist_right"]; obs.last_depth["wrist_right"]; obs.meta["proprio"]   # uint8 (H,W,3); float32 metres; layout + now
res = r.submit("ee_pose", A, dt=1/60)   # A: (T, 22) rows; see spec()["action_types"]["ee_pose"]
res.meta["done"], res.meta["reason"]; res.group("tactile")
r.fk(q16); r.ik({"tcp_right": pose7})  # stateless model of the robot (spec()["kinematics"])
```
- Cameras: `wrist_right` and `wrist_left` (640×480 RGB and z-depth, on the wrists), `tactile_right` and `tactile_left`
  (320×240, the image of each gel pad of the right gripper: the gel's deformation against what it touches; not pinhole
  cameras). Per-frame poses: `res.extrinsic_cv[cam]`; mounts, intrinsics and a narrower field of view per call
  (`wrist_right@<hfov_deg>`): `spec["cameras"]`.
- `ee_pose` (22): the right and left wrist targets (x y z, quaternion wxyz, env frame: metres, z up, robot base at
  (-0.5, 0, 1.1) facing +x), the right and left gripper commands (0 open, 1 closed), the right and left finger-gap
  overrides (m; negative = none), and the right fingers' drive settings: velocity limit (m/s, at most 0.2), effort limit
  (N, at most 20), stiffness (N/m, at most 10,000), damping (N s/m, at most 1,000); 0 = unchanged; the stock drive is
  0.2 m/s, 20 N, 200 N/m and 40 N s/m (send these to restore it). In this task they act on the right fingers. An
  all-zero quaternion holds that arm; a target's x, y and z must each lie within +-2 m of the robot base (`spec`
  `limits.position_box_m` around `limits.position_box_center`), else 400. Rows are `dt` apart (a multiple of 1/60 s, at
  most 0.5 s), at most 10 s per call; targets are tracked by a differential IK and joint PD drives, so a far target is
  not reached in one step. The fingertip centre is 0.1777 m along the wrist's +z axis. A malformed request is answered
  400 and executes nothing. One call returns at most 3000 images (`max_frames_per_call`, PROTOCOL §3 "Images per call").

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resources
Your container: **8 CPUs**, **16 GiB of memory**, **1024 processes and threads** and **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. The simulator runs in its own container and does not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
