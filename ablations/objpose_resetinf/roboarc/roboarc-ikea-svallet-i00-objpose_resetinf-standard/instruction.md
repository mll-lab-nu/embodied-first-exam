# IKEA MuJoCo · SVALLET work lamp — STANDARD MODE (robot as a service, eai-standard/2.4)

You control a robot (**two 6-DoF ViperX 300 s arms (MuJoCo Menagerie ALOHA), each with its own parallel gripper**; plain MuJoCo 3.14.0 on the CPU) **as if it were real hardware**: the simulator
runs in a service you cannot open. You get one client and one episode: cameras, proprioception and joint commands.
**Task:** Press the lamp shade's key down into the socket on top of the stand column until the spring jaw snaps over it, then screw the E12 bulb up into the shade's socket until it seats.

## Success requirements

- Both retention joints are connected (shade on the stand, bulb in the shade) and, at the end, each connector is within its gates (axial gap, lateral offset and axis tilt).
- The stand rests on the bench (vertical contact force above 0.1 N) and is within 3 degrees of its upright start orientation.
- No robot contact with any lamp part at the end.

The benchmark's terminal rules, the same in every IKEA MuJoCo task, come on top of these requirements. When your rows end: (1) the requirements above hold; (2) the parts are released: no robot link touches any part; (3) every part is at rest: at most 0.01 m/s and 0.05 rad/s; (4) the simulation never broke down: no non-finite state, no MuJoCo BADQACC / BADQPOS / BADQVEL warning, no contact of a part deeper than 10 mm, at any time. The grader then holds your last row for 1.0 s more and requires (1)-(4) again at its end.

Here the service checks (1)-(4) after every `submit` and every `get_obs(seconds > 0)`. When they all hold, it also checks
them after holding your last row 1.0 s more, on a copy (the robot is not moved): if that settled check passes too, the
episode ends with success (`meta["reason"]` is `success`); if not, the episode goes on and you can still fix it
(`meta["settle_failed"]` counts such checks). A breakdown ends the episode at once (`meta["reason"]` is
`sim_breakdown`), with no success. An episode that ends otherwise (your time is up) is judged as it stands by the same
two checks. The task is scored 1 only if the live episode succeeded; nothing is replayed afterwards.

## Physics and mechanism

- Parts move only through contact with the robot, gravity and the scene's own mechanism. The shade's barb cams a spring jaw (a slide joint with a spring, 1200 N/m) open and it snaps back over the barb. The bulb thread (11.9 mm x 1.5 mm right-hand, convex thread pieces) advances only by turning and seats on the socket stop. Retention welds switch on with the current relative pose when the seating gates hold. The prewired cable is not built.
- Grasps are physical: friction from the finger contacts. Nothing attaches a part to a gripper, and there is no assist.

## Rules (real-robot rules)
- **No reset.** The episode ends on success (above), on a simulator breakdown, when your time is up, or on a simulator
  error. What you do to the scene stays done: plan, observe, then act in small chunks.
- **No privileged state.** You see what the cameras see (RGB, and depth when you ask for it) plus the robot's own state:
  joint positions, velocities and actuator forces, gripper openings, tool-frame poses. Nothing tells you where the parts,
  the table or the work surface are (no poses, positions or heights of the scene). The success check is not exposed; the
  requirements above still apply in full.
- **Your only budget is the time limit (`## Time limit`)**; there is no step budget. The service also ends the episode
  itself (`meta["reason"]` is `timeout`; it is graded as it stands) when its own count of that limit,
  `meta["time_left_s"]`, reaches 0. That count starts at your first request to the service, so it never reaches 0 before
  your time is up.
- There is nothing to hand in: the service records your episode as the trajectory and grades it. Leave the script that
  drove the robot at `/app/output/gen.py`, and save useful frames and scripts under `/app/output/` as you go.

## Client (already installed; `python` from any directory)
```python
from rcb_client import Robot
r = Robot()                                    # finds the service (sim:8000 / localhost:8000), waits until it is ready
spec = r.spec()                                # action layout and limits, cameras (intrinsics, mounts), proprio layout, world frame, budget
obs = r.get_obs()                              # current frames: obs.last[cam] -> uint8 (480, 848, 3)
obs = r.get_obs(depth=True)                    # + obs.last_depth[cam] -> float32 (480, 848) z-depth in metres (0 = no reading)
obs.meta["cameras"][cam]                       # intrinsic_cv, extrinsic_cv (world -> camera, OpenCV axes), cam2world_gl
obs.group("tcp_pose", now=True)                # proprio groups: joint_pos, joint_vel, gripper_opening, tcp_pose, joint_cmd, joint_effort
res = r.submit("joint_position", rows, dt=0.0025, interpolate="linear", cameras=["cam_high"], video="mp4")
res.meta["executed_rows"], res.meta["clipped"], res.meta["done"], res.meta["reason"], res.meta["time_left_s"]
res.video["cam_high"]                          # mp4 bytes of the chunk; video="frames" gives res.frames[cam] (N, H, W, 3)
obs = r.get_obs(seconds=2.0)                   # hold the last command, simulate 2 s and return the video (<= 30 s)
r.fk(q); r.ik({"left_gripper": [x, y, z, qw, qx, qy, qz]})   # stateless kinematics on the robot's model
r.status()                                     # calls, control steps, done, reason, time left
```
A connection error means the service crashed and is resuming the SAME episode: call `r.wait_ready()` and check
`r.status()` before you continue (`spec()["on_service_error"]`).

One call returns at most 1000 images (`max_frames_per_call`, PROTOCOL §3 "Images per call").

## Robot, actions, observations
- **Action** `joint_position`: rows of 14 values, float32 or float64, layout `spec()["action_types"]["joint_position"]["layout"]`:
  per arm (`left_`, then `right_`): `waist`, `shoulder`, `elbow`, `forearm_roll`, `wrist_angle`, `wrist_rotate` = joint position targets (rad; `wrist_rotate` unlimited), `gripper` = finger rail position target (0.002 m closed .. 0.037 m open). One control step is 2.5 ms (400 Hz: the row is applied for 4 physics steps of
  0.625 ms). `dt` must be a multiple of 0.0025 s (at most 0.5 s); `hold` keeps each row for
  its `dt`, `linear` interpolates the arm targets. A chunk covers at most 10 s. Out-of-range values are clipped to the
  actuator's control range and reported in `meta["clipped"]`. Speed rule (the robot's real limits; clamp, not fail): arm joint targets move at most 0.00785397 rad per control step on every arm joint (3.14159 rad/s, the ViperX 300 s joint velocity limit)
  (`spec()["robot_spec"]["controller"]`); a row that asks for more takes the control steps it needs, and
  `meta["clipped"]` says so. The gripper command is not limited: it switches at the row. The arms are position servos with the scene's
  gains and force limits; use `obs.group("joint_cmd", now=True)` as the starting row to move smoothly.
- **Cameras** (ALOHA-style, 848 x 480, vertical field of view 58 deg): `cam_high` (static, above the front of the work
  area, looking down), `cam_low` (static, low at the front), `cam_left_wrist` and `cam_right_wrist` (on each hand, looking
  at the fingers; they move, so use the pose that comes with each frame). Intrinsics and mounts in `spec()["cameras"]`,
  the per-frame world -> camera pose in every response; depth on request.
- **Proprioception** (`spec()["proprio_layout"]`, groups in `spec()["proprio_groups"]`): per arm the 6 joint positions
  and velocities, the gripper opening (m), the tool-frame pose (`left_gripper` / `right_gripper` (between the fingertips): x y z + qw qx qy qz, world frame), the
  applied commands and the actuator forces.
- **World frame**: origin at the left arm's base link (`left_base_link`) on its mounting, +z up, x along that arm's forward
  direction; metres, quaternions **WXYZ**. The proprio tool-frame poses, the camera extrinsics and mounts and `/kinematics`
  are all in it; no positions of the scene are given. `spec()["robot_spec"]["base"]` gives the right arm's base pose in it
  (the rig's fixed geometry).
- Not available (simulator privilege): part poses, positions of anything in the scene, the scene files, contact forces on
  parts, the success check itself.

## Time per call
One control step takes about 5.8 ms of wall clock here (the simulation runs at about 0.43x real time), so a `submit` of the maximum 10 s chunk takes about 23 s. The client waits long enough for any call; a client timeout or a connection error means the connection or the
service failed (see above), not that the call is still on its way: do not resend it blindly. `r.operation_status()`
(the last call's operation, or `r.operation_status(operation_id)`) asks the service what became of a call.

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

## This run: unlimited resets, save and load

This run changes the reset budget and adds two calls. This section overrides anything above, and anything in `/spec`,
that says there is no reset, one episode only, or fewer resets.

- You have 1000 resets (`spec()["budget"]["reset"]` is 1000): in practice as many as your time allows.
- `POST /reset` on the same base URL as your other calls (`http://sim:8000` or `http://localhost:8000`), with a JSON body
  such as `{"cameras": []}` (in Python, for example `requests.post(base + "/reset", json={"cameras": []})`; the
  client's `_post("/reset", {"cameras": []}, [], 60)` where it has no `reset()`). It abandons the running episode, or
  follows one that has ended (a failure or a fall included), and starts a new episode from the same starting state.
  The answer carries the new episode's first frames; `meta` and `GET /status` add `episode`, `resets_left`, `saves`,
  `loads` and `control_steps_total`.
- Where `/spec` has `state_ops`, two more calls exist (its text is the full rule):
  - `POST /save_state` with `{}` stores the current state in the service and answers JSON
    `{"handle": "s1", "step": ...}`. The handle is all you get, never the state's contents.
  - `POST /load_state` with `{"handle": "s1", "cameras": []}` restores a state saved earlier in this run and starts a
    new episode there; it answers as `/reset` does. At most 32 handles are kept (the least recently used one is
    dropped). Saves and loads do not use up resets.
  Where `/spec` has no `state_ops`, this task offers resets only.
- Your time keeps running across resets and loads (in standard-realtime the robot's clock pauses after a reset or a
  load until your next command).
- Only the last episode is graded: from the starting state, or for a loaded episode the path that led to the saved
  state followed by what you did after the load. The success rule is checked again from your next command on. A
  success still ends the run: no reset, save or load after it.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resources
Your container: **4 CPUs**, **10 GiB of memory**, **1024 processes and threads** and **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. The simulator runs in its own container and does not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 10800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
