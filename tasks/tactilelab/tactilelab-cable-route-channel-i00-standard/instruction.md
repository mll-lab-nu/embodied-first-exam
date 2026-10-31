# TactileLab · cable_route_channel — STANDARD MODE (robot as a service, eai-standard/2.2)

You control a **dual-arm X-Trainer** whose **right gripper's fingers are two GelSight Mini tactile sensors**, **as if it
were real hardware**: the simulator runs in a service you cannot open. You get one client and one episode.

**Task:** Starting from its clamped end, press the cable segment by segment down into the shallow slot between two rails, then let go and leave it at rest.

In the scene: a straight 0.40 m slot between two 5 mm high rails (inner width 34 mm); a 0.40 m cable (radius 3.5 mm) pinned at the slot's start, running 3 cm along it before swinging away over a row of 22 mm tall clips and up to a tall post.

**Success.** Judged when the episode ends: the conditions must hold then and have held for the stated number of consecutive control steps before.
- the routed length is at least **0.20 m**: the longest run of cable nodes from the clamped end that each lie within 14.5 mm of the slot centreline and no higher than 5.5 mm above the table
- the gripper has released the cable: the pad gap was below 20 mm at some step and is at least 20 mm now
- no cable node moves faster than **0.01 m/s**
- held for **25** steps

The task fails for good if a gel pad overlaps a rail, a clip or the post by more than 0.2 mm, a cable node drops more than 30 mm below the table top, or a part of it is pushed through the back of a gel pad (two or more of its samples inside the volume up to 40 mm behind a pad for 10 consecutive control steps). The episode then ends (`failed`).

## Rules
- **No reset, no privileged state** (docs/protocol/standard_mode.md): you see the cameras, the tactile images and the
  robot's own proprioception; no object poses, no success predicate.
- **Episode.** When the success condition is reached after a control step, the last command is held for 60 more control
  steps (1 s, in the same response) and the task is judged. The condition is judged again: the task is solved if it
  still holds. Solved ends the episode with score 1; otherwise the episode goes on, and the next control step at which
  the condition is reached starts another hold. After a hold that does not solve the task, the next one starts no
  earlier than 60 control steps later, so your rows keep running between holds. The episode also ends when your time is
  up (the last command is then held for 60 control steps and the task judged once more), on a simulator error (score 0),
  when the task has failed for good (above, if any), or once the episode has run 4,740 control steps, holds included (79
  s of simulated time; reason `step_guard`; a hold already running finishes first; then held and judged as at the time
  limit): `spec["max_control_steps"]` = 4,860 is the most an episode runs, its final hold included. This task's replays
  run at about 3.83 control steps per second (2.5 on a loaded host); this service is no faster.
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
  0.2 m/s, 20 N, 200 N/m and 40 N s/m (send these to restore it). In this task they change nothing (they are checked and
  recorded only). An all-zero quaternion holds that arm; a target's x, y and z must each lie within +-2 m of the robot
  base (`spec` `limits.position_box_m` around `limits.position_box_center`), else 400. Rows are `dt` apart (a multiple
  of 1/60 s, at most 0.5 s), at most 10 s per call; targets are tracked by a differential IK and joint PD drives, so a
  far target is not reached in one step. The fingertip centre is 0.1777 m along the wrist's +z axis. A malformed request
  is answered 400 and executes nothing. One call returns at most 3000 images (`max_frames_per_call`, PROTOCOL §3 "Images
  per call").

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resources
Your container: **8 CPUs**, **16 GiB of memory**, **1024 processes and threads** and **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. The simulator runs in its own container and does not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
