# RoboCasa-GR1 · PnPPotatoToMicrowaveClose — STANDARD MODE (robot as a service)

A **Fourier GR1 humanoid** (arms, waist and two dexterous six-command Fourier hands; fixed base) works at a kitchen counter: RoboCasa's GR1 tabletop `PnPPotatoToMicrowaveClose` task (robosuite, MuJoCo).
**Task: pick up the potato, place it into the microwave and close the microwave.**
The scene is one frozen instance: the initial state of one of the benchmark's official demonstrations.

You control the robot **as if it were real hardware**: the simulator runs in a service you cannot open. You get one
client and one episode.

## Rules (real-robot rules)
- **No reset.** What you knock over stays knocked over.
- **No privileged state.** You see what the robot's cameras see (RGB, optional depth, with each camera's
  calibration) and the robot's own state. No object poses, no scene layout, no success signal.
- Your only budget is the time limit (`## Time limit`; `meta["time_left_s"]` is the service's count of it). There is nothing
  to hand in: the service records the episode as the trajectory and grades it. Leave your script at
  `/app/output/gen.py` for the record.
- Do not use the benchmark's demonstrations, trained policies or any published solution; write your own controller.
- Images come back as arrays in a Python object; what you look at and where you store it is up to your code.

## Scoring
The episode runs until your time is up. The service then applies the environment's own success check for `PnPPotatoToMicrowaveClose` to
the state of the live episode **after the last executed control step**: the episode as the service ran it, nothing is
replayed. A success reached earlier and then lost does not count: end in the state you want graded and stop submitting.

Both of these hold on the graded state (upstream `_check_success`, `tabletop_microwave_pnp.py`):
- the potato's centre (its body origin) is inside the microwave's interior;
- the door is shut: upstream's opening fraction is at most 0.005 (0 = shut, 1 = fully open).

Where the hands end up is not checked.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`)
```python
from rcb_client import Robot
r = Robot()                                   # connects (waits while the service starts: about a minute)
spec = r.spec()                               # control_dt, action layout + limits + kinds, cameras, proprio layout, budget
cams = list(spec["cameras"])                  # robot0_agentview_center, robot0_agentview_left, robot0_agentview_right, egoview, robot0_eye_in_right_hand, robot0_eye_in_left_hand
obs = r.get_obs(cameras=cams, include_depth=True)   # obs.last[cam] -> uint8 (240, 320, 3); obs.depth[cam] -> metres
obs.meta["proprio"]                           # {"layout": [...], "now": [...]}: joints, end effector, last command
obs.meta["cameras"]                           # per camera: intrinsic_cv, cam2world_gl (OpenGL: looks along -z), current
obs = r.get_obs(cameras=cams[:1], seconds=2.0, video="mp4")    # hold still and watch for 2 s (max 30)
res = r.submit("ee_pose", A, cameras=cams[:1], video="mp4")   # A: (T, 24) rows, one per control step
res.meta["done"], res.meta["reason"], res.meta["control_steps"]
res.video[cam]; res.frames[cam]; res.last[cam]; res.proprio; res.save("/app/runs/003")
```
- Action `ee_pose`: the robot's native controller command, applied once per control step (`control_dt` =
  0.05 s; float64). 24 channels, in order: the right then the left hand's grip-site pose target `x, y, z, rx, ry, rz` -- absolute, in the robot's base frame (metres, axis-angle radians), reached by the whole-body inverse-kinematics controller (mink), limits [-10, 10]; then six commands per hand (right, then left) in the finger order `little, ring, middle, index, thumb_flexion, thumb_rotation` -- unscaled Fourier hand commands in [-3, 3], not a binary grip. The GR1 has no mobile base. Values are clipped to the limits. Rows are `dt` apart (default and minimum: `control_dt`; a chunk covers at
  most 10 s).
- `get_obs(seconds=s)` keeps applying the last command (before the first one: both grip sites' current poses and the
  current hand commands) while physics runs for `s` seconds; those control steps are part of the episode. Every
  channel is an absolute target, so the grip sites stay within about a millimetre, but the IK's posture term can still
  move the waist and elbows by a few hundredths of a radian while you watch.
- The cameras are mounted on the robot and move with it: use the calibration that comes with each response.
- The hands: each hand command is the position target, in radians, of that finger's joints (`thumb_flexion` drives
  two thumb joints, `thumb_rotation` one): 0 is the straight, open finger, larger values bend it toward the palm
  (the hand closes), and every finger joint stops at the end of its range (1.22 to 1.74 rad), so values below 0 or
  above about 1.7 change nothing more. The grip site that the pose targets place is the origin of the hand's mounting
  frame (`gripper0_right_grip_site`, `gripper0_left_grip_site`), at the wrist end of the hand, not a point between
  the fingertips. The four small pink spheres beside each hand are part of the robot model (visual markers
  `robot0_<side>_pinch_spheres_0..3`, about 13.5 cm from its grip site, with no collision): they are not objects.
- World frame: metres, z up. In the proprio, `eef_left_*` / `eef_right_*` are the grip sites' positions in the world
  frame; the action's pose targets and the `cmd_*` entries (the last command) are in the robot's base frame.
  The robot's base frame (body `robot0_base`, fixed in the world) has its origin at world (2.65000, -2.17500, 0.97000) m and is turned +90.0 deg about z (quaternion w x y z (0.70711, 0, 0, 0.70711)): `p_world = R @ p_base + t` with R = [[0, -1, 0], [1, 0, 0], [0, 0, 1]].

One call returns at most 3000 images (`max_frames_per_call`, PROTOCOL §3 "Images per call").

## This run: privileged state queries

This run lets you query the simulator's state. This section overrides anything above, and anything in `/spec`, that
says object poses or the scene's state are never given.

- `GET /state/entities` (on the same base URL as your other calls) lists what you can query:
  `{"frame": ..., "quaternion_order": ..., "entities": {name: {"kind": ..., "fields": {field: unit}}}}`. The
  kinds are `robot` (the robot's base or root), `robot_link` (a hand, a foot, an end effector), `object`,
  `articulation` (a door, a drawer, a faucet: its joints) and `scene_feature` (a zone, a line, a hazard, a canvas
  region). The list is fixed for the run.
- `POST /state/query` with `{"names": ["robot", ...], "fields": ["pos", "quat"]}` answers JSON
  `{"state": {name: {field: value}}, "control_steps": ..., "sim_time_s": ..., "state_queries": ...}` with the
  current values. `fields` is optional: without it you get every field of each name. In Python:
  `requests.post(base + "/state/query", json={"names": ["robot"]}).json()["state"]`.
  - The usual fields: `pos` [x, y, z] m, `quat` (in `quaternion_order`), `lin_vel` m/s, `ang_vel` rad/s,
    `height_above_ground` m, `joint_pos` / `joint_vel` {joint: value}, `size` [3] m (full extents), and `bbox`
    [[min x, y, z], [max x, y, z]] m. A task may add its own; each field's unit is in the list.
  - All values are in the world frame that `frame` describes.
  - A field that an entity does not have is left out of its entry.
  - An unknown name or field is a 400 that lists the valid ones.
- A query only reads. It takes no control step, and it does not advance or pause the clock. In standard-realtime it
  answers at the current simulation time while the robot keeps moving. It is served while the episode runs (409 after
  the episode ended). Queries are counted and recorded; they do not change the grading.
- Nothing else changes: the goal, the success rule and its thresholds are not given, and no answer says whether the
  task is done.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resources
Your container: **3 CPUs**, **16 GiB of memory**, **1024 processes and threads** and **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. The simulator runs in its own container and does not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
