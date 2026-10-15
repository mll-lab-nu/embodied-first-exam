# Panda Dynamic Scenes · Supported cube flip relay (D13) — STANDARD MODE (robot as a service, eai-standard/2.2)

You control two simulated **Franka Panda** arms (`panda-0` on the left, `panda-1` on the right; each with its standard hand and the task's tool where it has one) **as if it were real hardware**: the simulator (ManiSkill 3 / SAPIEN, rigid-body physics at
1000 Hz) runs in a service you cannot open. You get one client and one episode.
**Task:** The left arm holds a large shallow tray with a cube on it, and the right arm holds a small flat pusher. The left arm must first bring the tray to a presentation point. The right arm must then tip the cube over onto an adjacent face. It does so with a short push that sets the cube rotating and ends before the cube is half-way over, so that the cube completes the tip on its own momentum and settles on the tray. The left arm then moves the cube, on the tray, to a new place, and the pusher tips it a second time in the same way, so that the cube's original bottom face ends up on top. Finally the tray must carry the correctly oriented cube to an output point and hold it there. The cube must never leave the tray.

## Scene
Two Pandas facing each other along x. panda-0 (left): base at (-0.55, -0.22, 0), yaw 0 (facing +x). Its tool is a tray with a 5 mm floor, inside 0.24 x 0.24 m (2 x `left_tool_half`, 0.12 at this instance), with walls 12 mm high and 5 mm thick on all four sides. The tool frame is the centre of the inside floor surface, z up, x pointing away from the arm's base. With the tray level the hand points straight down and the floor centre is 0.12 m ahead of the gripper TCP along tool x and 0.04 m below it. The grey adapter enters at the middle of the back (tool -x) wall: a 12 mm wide post protrudes 6 mm inward from the floor up to 35 mm, and a bar protrudes 12 mm inward 29-41 mm above the floor, above the 12 mm wall. Start: floor centre at (0.04, -0.035, 0.23), level, axes aligned with the world. panda-1 (right): base at (0.74, 0.22, 0), yaw pi (facing -x). Its tool is a pusher: a small rigid plate 8 mm thick (along tool x), 50 mm wide (tool y) and 12 mm tall (tool z), with the tool frame at its centre and x normal to its face, pointing away from the arm's base. The pusher centre is 0.12 m ahead of the TCP along tool x and 0.04 m below it. A grey adapter (a horizontal bar from the hand and a short post) ends about 5 cm behind it on the hand side; plate and adapter form one rigid tool link. Start: pusher centre at (0.16, 0.02, 0.268), rotated 180 deg about z (face normal = world -x, toward the tray). Role labels per phase (left, right): support_presentation: tray_support, preparing_pusher; first_inertial_flip: moving_support, impulse_pusher; second_contact_geometry: repositioning_support, cleared_pusher; second_inertial_flip: moving_support, impulse_pusher; oriented_output: oriented_carrier, cleared_pusher.

A plain orange cube (44 mm edge, all faces alike) starts resting flat on the left tray's floor, near the tray centre and a little toward the pusher's side (+x). Its axes start aligned with the world axes. There is nothing else in the scene, and nothing moves by itself. The table top is the world's z = 0 plane.

**Goal geometry.** Presentation point (0.08, 0.015, 0.23) for the tray's tool frame (support_presentation); output point (-0.04, 0.16, 0.25) for the tray's tool frame (oriented_output).

## Time in this scene
The scene is dynamic: from the first control step on, things move by themselves (as described above), and they do not
wait for the robot. The simulated clock advances **only through your calls**: every row of a `submit` and every second of an
`observe` watch runs control steps (10 ms each); between calls the world is frozen, however long you think. A call that
runs control steps runs them all, whatever happens meanwhile, and returns what the cameras saw. The episode lasts at most
**25 s of simulated time** (the task's horizon, 2500 control steps): when it is reached before the task
is complete, the task has failed. Nothing moves at t = 0 (the cube just settles onto the tray). All faces of the cube look the same, so its orientation (which face is up) can only be followed by tracking its rotation from frame to frame.

## Success
The task has 5 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **support_presentation**: the cube is on the tray (it has touched the tray's tool link within the last 25 ms) while the tray's tool frame is within 0.025 m of the presentation point (0.08, 0.015, 0.23).
2. **first_inertial_flip**: an inertial flip, judged only from pusher contacts made in this phase. The tilt of a cube axis means the angle between that cube-local axis and world vertical; here the tilted axis is the cube's local z (initially up). (a) The pusher (any part of its tool link) touches the cube; the tilt at the last moment of contact is the release angle. (b) Early release: at some moment more than 0.02 s after the last pusher contact, the cube is untouched by the pusher, the release angle was between 0.03 rad and pi/4 - 0.02 = 0.765 rad (about 1.7 to 43.9 deg), and the cube turns faster than 0.4 rad/s. This is recorded once. (c) Inertial crossing: after the early release, the tilt grows from at most 45 deg (pi/4) at one physics step to more than 45 deg at the next. (d) After that, the final state must hold for 0.25 s without interruption: the cube's local +x axis (the face that initially faced +x, toward the right arm) points up within 0.18 rad (about 10.3 deg), the cube moves slower than 0.05 m/s and turns slower than 0.3 rad/s, and it is on the tray (touched within the last 25 ms). The cube's world position at the moment this phase completes is recorded.
3. **second_contact_geometry**: with the cube on the tray (touched within the last 25 ms) and not touched by the pusher at that moment, the cube's centre is more than 0.025 m (world distance) away from the position recorded at the end of first_inertial_flip.
4. **second_inertial_flip**: the same inertial-flip rule as first_inertial_flip, judged only from pusher contacts made in this phase, with the cube's local x axis (now pointing up) as the tilted axis. That is: a pusher contact, then a release with tilt between 0.03 rad and 0.765 rad followed (more than 0.02 s later, still untouched) by an angular speed above 0.4 rad/s, then the tilt of local x passing 45 deg. The final state is that the cube's local -z axis (its original bottom face) points up within 0.18 rad, with speed < 0.05 m/s, angular speed < 0.3 rad/s and the cube on the tray, for 0.25 s without interruption.
5. **oriented_output**: for 0.5 s without interruption: the cube is on the tray (touched within the last 25 ms) and its local -z axis points up within 0.18 rad; the tray's tool frame is within 0.025 m of the output point (-0.04, 0.16, 0.25); and the cube moves at less than 0.04 m/s relative to the tray. This completes the task.

The episode **ends by itself** at the first control step where the last phase is complete (success) or where the task has
failed (`meta["done"]`, `meta["reason"]`: `success` or the failure's name).

**The task fails** (the episode ends, reward 0) as soon as any of these happens:
- at any time, the cube's centre in the tray's tool frame is 0.115 m or more from the floor centre along x or y (|x| or |y| >= 0.115 m), or 0.01 m or more below the floor surface (z <= -0.01 m) (`cube_lost_from_tray`);
- during first_inertial_flip or second_inertial_flip, the pusher touches the cube after an early release has been recorded in that phase but before the 45 deg inertial crossing. An early release that does not lead to a crossing therefore leaves no retry: any further pusher contact in that phase fails the task (`flip_recontact_before_balance`);
- the task's horizon is reached: 25 s of simulated time (`timeout`);
- an object leaves the workspace: its centre falls more than 0.2 m below the table top or gets more than 1.8 m from the
  world's z axis (`out_of_bounds`);
- a forbidden contact or a deep interpenetration (below);
- a safety limit is exceeded (`limit_violation`, below).

**Contacts.** The tray and the pusher (each its whole tool link, adapter included) may touch the cube only, not the table. No other part of either robot, the fingers included, may touch anything. The two arms and their tools may never touch each other, and no arm may touch itself. In every task: the two arms (and their tools) never touch each other
(`arm_arm_or_tool_collision`), an arm never touches itself (`self_collision`), no robot part touches the table or the floor
(`forbidden_collision`, `tool_table_collision`), a robot link other than an allowed one touches no object or fixture
(`forbidden_arm_object_contact`, `forbidden_arm_scene_contact`, `forbidden_arm_fixture_contact`), a tool touches only the
task's objects and the fixtures the task allows (`forbidden_tool_fixture_contact`), and no contact penetrates deeper than
4 mm (`excessive_penetration`).

**Safety limits** (the Franka Panda's own limits, checked every 1 ms on each arm; `spec["robot_spec"]["controller"]["safety_limits"]`):
measured joint positions within the joint limits (+0.002 rad); measured joint speeds at most 1.01 x (2.175, 2.175, 2.175,
2.175, 2.61, 2.61, 2.61) rad/s; finger speeds at most 0.051 m/s; the hand's TCP at most 1.01 x 1.7 m/s and 1.01 x
2.5 rad/s; joint accelerations (measured over every 20 ms window) at most 1.05 x (15, 7.5, 10, 12.5, 15, 20, 20) rad/s²
and jerks at most 1.05 x (7500, 3750, 5000, 6250, 7500, 10000, 10000) rad/s³; the TCP's acceleration (20 ms windows) at
most 1.05 x 13 m/s² and 1.05 x 25 rad/s²; motor torques at most (87, 87, 87, 87, 12, 12, 12) N m, changing at most
1000 N m/s. The servo's own reference motion is checked against the same speed, acceleration and jerk limits. A contact
(a catch, a strike) moves the arm too: what is measured counts, whatever was commanded.

## Rules (real-robot rules)
- **No reset.** The episode starts when the service comes up and ends on success, on a failure, when your time is up, or
  on a simulator error. A dropped object stays dropped.
- **No privileged state.** You see what the cameras see (RGB, and depth if you ask) plus the robot's own proprioception
  (joints, fingers, hand TCP and tool poses, velocities, motor torques, the current targets). No object poses, no success
  signal before the end.
- There is no step budget: the time limit (`## Time limit`) is your only budget (`meta["time_left_s"]`). Actions and simulated
  time are reported as cost.
- There is nothing to hand in: the service records your episode as the trajectory and grades it. Leave your script at
  `/app/output/gen.py` for the record. The episode is graded as it stands when your time is up.
- **If the service crashes**, a call fails with a connection error: the simulator restarts and resumes the SAME episode
  (never a reset) in the state after the last call it completed, which you may not have received. `r.wait_ready()` waits
  until it answers again, then check `r.status()["control_steps"]` before you continue (`spec["on_service_error"]`).
- **Nothing is put into your context automatically.** Images and videos come back as arrays/bytes in a Python object;
  what you look at and where you store it is your code's decision.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`)
```python
from rcb_client import Robot
r = Robot()                                   # connects (the service builds the scene in a few seconds)
spec = r.spec()                               # action type, layout, joint limits, cameras, budget, robot spec, servo and safety limits

obs = r.get_obs()                             # current frames: obs.last["overview"], obs.last["closeup"] -> uint8 (480, 640, 3); no time passes
obs.meta["proprio"]                           # {"layout": [...], "now": [...]}: joints, fingers, TCP / tool poses, velocities, torques, targets
obs.meta["cameras"]                           # per camera: intrinsic_cv / extrinsic_cv / cam2world_gl (static cameras)
obs = r.get_obs(seconds=0.2, video="frames", video_fps=50)   # hold the current targets and watch 0.2 s (at most 10 s): obs.frames[cam]

res = r.submit("joint_position", A, dt=0.01)  # A: (T, 16) rows dt seconds apart, executed at 100 Hz (hold or linear between rows)
res.meta["done"], res.meta["reason"], res.meta["clipped"], res.meta["control_steps_chunk"], res.meta["sim_time_s"]
res.frames["overview"]                        # uint8 (N, H, W, 3) at video_fps, if video="frames" | "both"; res.video[cam]: mp4 bytes
res.last["closeup"]; res.proprio              # last frame per camera; float32 (N, D) proprio at each frame; res.frame_time_s
res.save("/app/runs/003")                     # meta.json, <cam>.mp4, frames/<cam>/NNN.jpg, last/<cam>.jpg, proprio.npy
r.fk(q); r.ik({"panda-0_tool": pose7}, seed=q) # stateless kinematics of the arms' own models (no physics, no simulated time)
```
Cameras (640×480 RGB, static): `overview` (the whole workspace) and `closeup` (the task's working area); z-depth on
request (`r.get_obs(depth=True)` -> `obs.last_depth[cam]` metres; `r.submit(..., depth="frames")`). `video_fps` (1..50,
default 10) sets how many frames a call returns; a call may return at most `spec["max_frames_per_call"]` images.

### Action type
- `joint_position` (16 per row): `[panda-0 joint1..7, panda-0 aperture, panda-1 joint1..7, panda-1 aperture]`. Each arm's 8 values are its 7 absolute joint-position targets
  (rad, `panda_joint1..7`) and its total gripper aperture target (m, 0 = closed .. 0.08 = open; each finger moves at most
  0.025 m/s). Rows are `dt` apart (`0.01 ≤ dt ≤ 0.5` s, a multiple of the 0.01 s control period; any other `dt` is
  rejected, never rounded); `interpolate="linear"` (default) or `"hold"`; a chunk may cover at most 10 s; out-of-limit
  values are clipped and listed in `meta["clipped"]` (limits in the spec). The service executes the rows as float64;
  `r.submit` sends them as float32 (a float64 `actions` array part is taken as it is). `observe` with
  `seconds > 0` keeps the last targets in force.
- The servo: every control step, each arm's latest target is turned into a smooth reference motion by a jerk-limited
  trajectory generator (Ruckig, the joints synchronised to arrive together) within 65 % (speed), 55 % (acceleration) and 5 % (jerk) of the Panda's joint
  speed, acceleration and jerk limits, and the arm tracks that reference with torque control (PD + inverse dynamics, the
  Panda's torque and torque-rate limits). A new target replans from the current reference motion, so a target far away is
  reached smoothly, not in one step. `spec["robot_spec"]["controller"]` has the exact limits and gains.
- A malformed request (a wrong type, a value out of range) is answered 400 with the reason and executes nothing.

## Conventions
- World frame: metres, z up, the table top is the plane z = 0; quaternions are **wxyz**. Each arm's base pose is in the robot spec (`arms`).
- `spec["proprio_groups"]` names the proprio columns: `joint_pos` (per arm joint1..7, finger_left, finger_right), `tcp_pose`
  (the hand TCP, between the fingertips), `joint_vel`, `gripper_opening`, `joint_effort` (motor torques), `tool_pose` (the
  task tool's frame), `target` (the targets in force). The arms are listed panda-0 first.
- Control runs at 100 Hz (10 ms per row), physics at 1000 Hz.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
