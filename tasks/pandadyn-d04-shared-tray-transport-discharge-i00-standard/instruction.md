# Panda Dynamic Scenes · Shared tray transport and discharge (D04) — STANDARD MODE (robot as a service, eai-standard/2.2)

You control two simulated **Franka Panda** arms (`panda-0` on the left, `panda-1` on the right; each with its standard hand and the task's tool where it has one) **as if it were real hardware**: the simulator (ManiSkill 3 / SAPIEN, rigid-body physics at
1000 Hz) runs in a service you cannot open. You get one client and one episode.
**Task:** The two Pandas hold one tray between them. Each arm's small open fork cradles a tab on one end of the tray, and an orange ball lies loose in the tray. Working together, the arms must first hold the tray steadily. They then carry it through two waypoints that make a turn. When the environment pushes the ball, they must bring it back to rest near the tray centre. Next they bring the tray to an exit position beside a fixed basin, and finally they tip the ball out so that it settles in the basin. Both forks must support the tray during the transport phases, the ball must not leave the tray before the discharge, and the tray must never drop low.

## Scene
panda-0 (left): base at (-0.55, -0.22, 0), yaw 0 (facing +x). panda-1 (right): base at (0.74, 0.22, 0), yaw pi (facing -x). Each carries a support fork: a small, shallow square cradle 0.07 m x 0.07 m inside (2 x `tool_half`, `tool_half` = 0.035 m). It has a 5 mm floor and 18 mm high walls on three sides, is open on the tool +x side, and is held by an adapter on its closed tool -x wall. The tool frame is the centre of the cradle floor's top surface, z up. The TCP sits 0.12 m along tool -x and 0.04 m above the tool frame. Left fork start: (-0.075, 0, 0.22), orientation identity (open side toward world +x). Right fork start: (0.215, 0, 0.22), quaternion (0, 0, 0, 1) (yawed 180 deg, open side toward world -x). The two open sides face each other. In this task both arms' servos plan their reference motion with lower acceleration and jerk fractions than usual (0.30 and 0.025, default 0.55 and 0.05). Role labels in every phase: panda-0 left_support, panda-1 right_support.

A blue rigid tray, 0.20 m x 0.24 m inside, has a 9 mm rim and a 5 mm floor. A flat tab (48 mm x 60 mm, 8 mm thick) sticks out at floor level from the middle of each of its two longer sides. At the start each tab rests in one arm's fork, so the tray hangs between the two arms. An orange ball (radius 18 mm) lies loose near the middle of the tray. A fixed blue open-top basin, 0.21 m x 0.20 m inside and 0.08 m deep, stands on posts above the table. Nothing moves by itself, except that the environment gives the ball a brief push along world +x the moment the third phase begins. The table top is the world's z = 0 plane.

**Goal geometry.** Tray waypoints A = (0.12, -0.04, 0.27) and B = (0.02, 0.08, 0.27) apply to the tray's frame origin. The exit point (0.12, 0.18) applies in the horizontal plane and is not announced. The tray's frame origin must always stay at or above z = 0.17 m.

## Time in this scene
The scene is dynamic: from the first control step on, things move by themselves (as described above), and they do not
wait for the robot. The simulated clock advances **only through your calls**: every row of a `submit` and every second of an
`observe` watch runs control steps (10 ms each); between calls the world is frozen, however long you think. A call that
runs control steps runs them all, whatever happens meanwhile, and returns what the cameras saw. The episode lasts at most
**25 s of simulated time** (the task's horizon, 2500 control steps): when it is reached before the task
is complete, the task has failed. Nothing moves at t = 0: the tray rests in both forks and the ball lies still in it. The only scripted motion is the push the ball receives the moment the third phase (disturbance_recovery) starts.

## Success
The task has 5 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **shared_support**: For 0.35 s without interruption, two things hold. The tray is supported by both forks: it has been in contact with the left fork within the last 0.04 s and with the right fork within the last 0.04 s. And the ball is inside the tray, as defined under ball_spill.
2. **transport_turn**: With the tray supported by both forks (as above), the tray's frame origin (the centre of its floor's top surface) comes within 0.025 m of waypoint A = (0.12, -0.04, 0.27). Later, again with both forks supporting it, the origin comes within 0.025 m of waypoint B = (0.02, 0.08, 0.27). The waypoints must be reached in this order.
3. **disturbance_recovery**: When this phase begins, the environment pushes the ball along world +x for 0.03 s with a fixed impulse. The phase completes when all of the following hold for 0.4 s without interruption. Both forks support the tray. The push has been fully applied (at least 95% of it). The ball's centre is within 0.045 m of the tray centre in the tray's x-y plane. The ball moves at less than 0.07 m/s relative to the tray, including the tray's rotation.
4. **exit_alignment**: With both forks supporting the tray, the tray's frame origin is within 0.04 m of (0.12, 0.18), measured horizontally (x and y only).
5. **natural_discharge**: The ball is contained in the basin and does not touch the tray, for 0.7 s without interruption. Contained in the basin means all of the following, in the basin's frame (origin at the centre of its floor's top surface, axes = world axes). |x| and |y| of the ball centre are below 0.0919 m (0.10 - 0.45 x radius; the same bound is used on both axes). Its height above the basin floor is between 0.014 m and 0.0778 m. It has been in contact with the basin within the last 25 ms. Its speed is below 0.09 m/s. Neither fork has to support the tray in this phase, but the tray must still stay above z = 0.17 m. This completes the task.

The episode **ends by itself** at the first control step where the last phase is complete (success) or where the task has
failed (`meta["done"]`, `meta["reason"]`: `success` or the failure's name).

**The task fails** (the episode ends, reward 0) as soon as any of these happens:
- before natural_discharge (in phases shared_support to exit_alignment), the ball leaves the tray region. In the tray's frame that is |x| >= 0.11 m, |y| >= 0.16 m, or a centre at or more than 0.01 m below the tray floor's top surface (`ball_spill`);
- at any time, in every phase including the discharge, the tray's frame origin falls below z = 0.17 m (`shared_support_drop`);
- the task's horizon is reached: 25 s of simulated time (`timeout`);
- an object leaves the workspace: its centre falls more than 0.2 m below the table top or gets more than 1.8 m from the
  world's z axis (`out_of_bounds`);
- a forbidden contact or a deep interpenetration (below);
- a safety limit is exceeded (`limit_violation`, below).

**Contacts.** The forks may touch the tray and the ball, which are free objects, and nothing else: not the basin or its posts, not the table, not the robot pedestals. No other robot part, the fingers included, may touch anything. The two arms and their forks must never touch each other, and a fork must not touch its own arm. The tray and the ball may touch the basin. In every task: the two arms (and their tools) never touch each other
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
  trajectory generator (Ruckig, the joints synchronised to arrive together) within 65 % (speed), 30 % (acceleration) and 2 % (jerk) of the Panda's joint
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
