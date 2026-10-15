# Panda Dynamic Scenes · Cup catch, route pour, rebound recatch and cart delivery (S01) — STANDARD MODE (robot as a service, eai-standard/2.2)

You control one simulated **Franka Panda** arm (7 joints, its standard hand, and the task's tool where it has one) **as if it were real hardware**: the simulator (ManiSkill 3 / SAPIEN, rigid-body physics at
1000 Hz) runs in a service you cannot open. You get one client and one episode.
**Task:** An orange ball is thrown upward at the start and comes back down near the robot. Catch it in the open cup the Panda holds, pour it into the designated one of two raised gravity channels, let it roll down that channel by itself, drop off its end and bounce off the tilted rebound plate below it, catch it in the cup again while it flies, and finally put it into a cart that slides back and forth on a rail, where it must rest while the cart is still moving.

## Scene
One Panda, base at (-0.55, 0, 0), yaw 0 (facing +x). Its hand carries a blue square cup closed on all four sides: inner 0.14 m x 0.14 m (2 x `tool_half`, `tool_half` = 0.07 m), walls 0.028 m high (`tool_height`) and 5 mm thick, floor 5 mm thick. The tool frame is the centre of the cup's inner floor (top surface of the bottom plate), z up out of the opening, x and y along the walls. A rigid dark-grey adapter on the cup's -x side joins it to the hand: a horizontal bar 0.035 m above the floor (tool-frame x from -0.152 to -0.058) and a short vertical post at the middle of the -x wall (rising 7 mm above the rim and protruding 6 mm into the cup); both are part of the tool. The Panda TCP is at (-0.12, 0, 0.04) in the tool frame, so with the cup level the gripper points straight down just behind the cup's -x wall. At the start the cup is level (tool axes aligned with the world axes), its frame origin at (-0.16, -0.32, 0.23).

A small orange ball (radius 18 mm) is thrown upward at t = 0 and falls back down within the first second. Two identical, parallel gravity channels are raised on posts above the table: open-topped grey troughs 0.35 m long with a 0.12 m wide floor between 55 mm high side walls, both running in the -y direction and very nearly level. Route 0 is the channel nearer the robot base, route 1 the farther one. Each channel's upstream (+y) end is closed by an orange end stop; beyond its downstream (-y) end, a little lower, sits an orange rebound plate (0.11 m x 0.13 m, 16 mm thick), tilted so that a ball dropping onto it bounces onward in -y into open space; the plates are very bouncy. A blue open box (the cart, 0.15 m x 0.15 m inside, 0.06 m deep) rides on a straight rail along the world x axis and moves slowly back and forth along it for the whole episode, slowing to a stop at each end of its stroke. The table top is the world's z = 0 plane.

**Goal geometry.** At this instance the designated route is route 1: of the two parallel channels, the one farther from the robot's base (the +x one). Touching the other channel during selected_route_entry fails the task (`wrong_route`). Route-entry line: ball centre at world y > 0.10 m (selected_route_entry). Rebound check: ball centre at world y < -0.12 m and z > 0.255 m (track_and_rebound).

## Time in this scene
The scene is dynamic: from the first control step on, things move by themselves (as described above), and they do not
wait for the robot. The simulated clock advances **only through your calls**: every row of a `submit` and every second of an
`observe` watch runs control steps (10 ms each); between calls the world is frozen, however long you think. A call that
runs control steps runs them all, whatever happens meanwhile, and returns what the cameras saw. The episode lasts at most
**25 s of simulated time** (the task's horizon, 2500 control steps): when it is reached before the task
is complete, the task has failed. The ball is already flying upward at t = 0 and lands in under a second, so watch the first frames in short steps. The cart keeps moving back and forth for the whole episode and slows to a stop at the ends of its stroke. The two channels look the same and nothing marks the designated one: it is given under Goal geometry.

## Success
The task has 5 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **incoming_catch**: the ball, after at least 25 ms of free flight (touching nothing), passes downward through the plane 0.046 m above the cup floor (`tool_height` + radius, one radius above the rim) while its centre is within 0.052 m (`tool_half` - radius) of the cup centre in both tool-frame x and y; after that entry it must stay retained in the cup for 0.18 s without interruption. Retained means: in the cup's frame the ball's centre is within 0.0619 m of the centre in x and y (`tool_half` - 0.45 x radius) and between 0.014 m and 0.0258 m above the floor (radius - 4 mm to `tool_height` - 0.12 x radius), the ball touched the cup within the last 25 ms, and it moves at less than 0.09 m/s relative to the cup.
2. **selected_route_entry**: the ball touches the designated channel (route 0, the channel nearer the robot's base, or route 1, the farther one, drawn per instance and given under Goal geometry; the channel trough and its supports count, the separate end stop does not) while its centre is at world y > 0.10 m and it is not touching the cup. Touching the other channel at any time during this phase fails the task (wrong_route).
3. **track_and_rebound**: without the ball touching the cup or the table (either fails the task), it touches the rebound plate of the designated route while its centre is at world y < -0.12 m and z > `rebound_height` - 0.005 = 0.255 m.
4. **downstream_catch**: the ball is caught in the cup again with the same test as the first catch: at least 25 ms of free flight (counted within this phase), a downward pass through the plane 0.046 m above the cup floor while within 0.052 m of the cup centre in tool-frame x and y, then retained in the cup (same retention conditions) for 0.18 s without interruption.
5. **moving_cart_delivery**: the ball rests in the cart: in the cart's frame its centre is within 0.0669 m of the cart centre in x and y (0.075 - 0.45 x radius) and between 0.014 m and 0.0578 m above the cart floor (radius - 4 mm to 0.06 - 0.12 x radius), it touched the cart within the last 25 ms, and it moves at less than 0.09 m/s relative to the cart; it does not touch the cup; and the cart moves along its rail at more than 0.02 m/s; all for 0.7 s without interruption. This completes the task.

The episode **ends by itself** at the first control step where the last phase is complete (success) or where the task has
failed (`meta["done"]`, `meta["reason"]`: `success` or the failure's name).

**The task fails** (the episode ends, reward 0) as soon as any of these happens:
- during selected_route_entry, the ball touches the channel that was not designated (`wrong_route`);
- during track_and_rebound, the ball touches the table (`missed_gravity_route`);
- during track_and_rebound, the ball touches the cup (`caught_before_required_rebound`);
- the task's horizon is reached: 25 s of simulated time (`timeout`);
- an object leaves the workspace: its centre falls more than 0.2 m below the table top or gets more than 1.8 m from the
  world's z axis (`out_of_bounds`);
- a forbidden contact or a deep interpenetration (below);
- a safety limit is exceeded (`limit_violation`, below).

**Contacts.** Only the cup (including its adapter) may touch anything, and it may touch only the ball: touching the channels, end stops, rebound plates, the cart or its rail, or the table is forbidden. No other part of the robot, the fingers included, may touch anything, the ball included. In every task: the two arms (and their tools) never touch each other
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

res = r.submit("joint_position", A, dt=0.01)  # A: (T, 8) rows dt seconds apart, executed at 100 Hz (hold or linear between rows)
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
- `joint_position` (8 per row): `[joint1..7, aperture]`. Each arm's 8 values are its 7 absolute joint-position targets
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

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
