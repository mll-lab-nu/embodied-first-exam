# IKEA MuJoCo · VARIERA shelf insert — STANDARD MODE (robot as a service, eai-standard/2.4)

You control a robot (**two 7-DoF Franka Panda arms, each with the MuJoCo Menagerie Panda hand (two-finger, tendon-coupled)**; plain MuJoCo 3.14.0 on the CPU) **as if it were real hardware**: the simulator
runs in a service you cannot open. You get one client and one episode: cameras, proprioception and joint commands.
**Task:** Assemble the VARIERA shelf insert: place the two side frames, lower the shelf onto them, and drive the four screws through the shelf holes into the frames' receivers until they seat.

## Success requirements

- Four distinct receivers each hold a screw that was turned relative to that receiver (at least 0.4 measured turns, with a descent matching turns x pitch), its head seated at the shelf hole (axial 0.2 mm, lateral 0.6 mm, axis 1.5 degrees).
- The frames are aligned under the shelf, parts are slower than 0.02 m/s, the assembly stands on the bench on its own, and no robot touches any furniture part.
- All of the above hold for 0.5 s.

The benchmark's terminal rules, the same in every IKEA MuJoCo task, come on top of these requirements. When your rows end: (1) the requirements above hold; (2) the parts are released: no robot link touches any part; (3) every part is at rest: at most 0.01 m/s and 0.05 rad/s; (4) the simulation never broke down: no non-finite state, no MuJoCo BADQACC / BADQPOS / BADQVEL warning, no contact of a part deeper than 10 mm, at any time. The grader then holds your last row for 1.0 s more and requires (1)-(4) again at its end.

Here the service checks (1)-(4) after every `submit` and every `get_obs(seconds > 0)`. When they all hold, it also checks
them after holding your last row 1.0 s more, on a copy (the robot is not moved): if that settled check passes too, the
episode ends with success (`meta["reason"]` is `success`); if not, the episode goes on and you can still fix it
(`meta["settle_failed"]` counts such checks). A breakdown ends the episode at once (`meta["reason"]` is
`sim_breakdown`), with no success. An episode that ends otherwise (your time is up) is judged as it stands by the same
two checks. The task is scored 1 only if the live episode succeeded; nothing is replayed afterwards.

## Physics and mechanism

- Parts move only through contact with the robot, gravity and the scene's own mechanism. Screw threads and receivers are non-convex SDF meshes (0.5 mm pitch, right-hand): a screw advances only by being turned. There are no welds or other non-contact mechanisms.
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
obs = r.get_obs(seconds=2.0)                   # hold the last command, simulate 2 s and return the video (<= 30 s, and
                                               # at most spec()["max_frames_per_call"] frames: cameras x (fps x s + 2),
                                               # x 6 with per-frame depth, x 4 with legacy depth)
r.fk(q); r.ik({"left_tcp": [x, y, z, qw, qx, qy, qz]})   # stateless kinematics on the robot's model
r.status()                                     # calls, control steps, done, reason, time left
```
A connection error means the service crashed and is resuming the SAME episode: call `r.wait_ready()` and check
`r.status()` before you continue (`spec()["on_service_error"]`).

## Robot, actions, observations
- **Action** `joint_position`: rows of 16 values, float32 or float64, layout `spec()["action_types"]["joint_position"]["layout"]`:
  per arm (`left_`, then `right_`): `actuator1`..`actuator7` = joint position targets (rad; joint 7, the wrist, has no joint limit in these scenes, unlike the real Panda), `actuator8` = gripper command (0 = closed, 255 = open; the hand squeezes at its tendon force limit, about 70 N per finger, at any width when commanded 0). One control step is 2.5 ms (400 Hz: the row is applied for 4 physics steps of
  0.625 ms). `dt` must be a multiple of 0.0025 s (at most 0.5 s); `hold` keeps each row for
  its `dt`, `linear` interpolates the arm targets. A chunk covers at most 10 s. Out-of-range values are clipped to the
  actuator's control range and reported in `meta["clipped"]`. Speed rule (the robot's real limits; clamp, not fail): arm joint targets move at most 0.0054375 rad per control step on joints 1-4 (`actuator1`..`actuator4`: 2.175 rad/s) and 0.006525 rad on joints 5-7 (`actuator5`..`actuator7`: 2.61 rad/s), the Franka Panda's joint velocity limits
  (`spec()["robot_spec"]["controller"]`); a row that asks for more takes the control steps it needs, and
  `meta["clipped"]` says so. The gripper command is not limited: it switches at the row. The arms are position servos with the scene's
  gains and force limits; use `obs.group("joint_cmd", now=True)` as the starting row to move smoothly.
- **Cameras** (ALOHA-style, 848 x 480, vertical field of view 58 deg): `cam_high` (static, above the front of the work
  area, looking down), `cam_low` (static, low at the front), `cam_left_wrist` and `cam_right_wrist` (on each hand, looking
  at the fingers; they move, so use the pose that comes with each frame). Intrinsics and mounts in `spec()["cameras"]`,
  the per-frame world -> camera pose in every response; depth on request.
- **Proprioception** (`spec()["proprio_layout"]`, groups in `spec()["proprio_groups"]`): per arm the 7 joint positions
  and velocities, the gripper opening (m), the tool-frame pose (`left_tcp` / `right_tcp` (between the fingertips): x y z + qw qx qy qz, world frame), the
  applied commands and the actuator forces.
- **World frame**: origin at the left arm's base link (`left_link0`) on its mounting, +z up, x along that arm's forward
  direction; metres, quaternions **WXYZ**. The proprio tool-frame poses, the camera extrinsics and mounts and `/kinematics`
  are all in it; no positions of the scene are given. `spec()["robot_spec"]["base"]` gives the right arm's base pose in it
  (the rig's fixed geometry).
- Not available (simulator privilege): part poses, positions of anything in the scene, the scene files, contact forces on
  parts, the success check itself.

## Time per call
One control step takes about 18.8 ms of wall clock here (the simulation runs at about 0.13x real time), so a `submit` of the maximum 10 s chunk takes about 75 s. The client waits long enough for any call; a client timeout or a connection error means the connection or the
service failed (see above), not that the call is still on its way: do not resend it blindly. `r.operation_status()`
(the last call's operation, or `r.operation_status(operation_id)`) asks the service what became of a call.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 10800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
