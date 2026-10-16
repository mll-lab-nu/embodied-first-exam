# Panda Dynamic Scenes · Cylinder rescue, guide route and oriented delivery (S11) — STANDARD MODE (robot as a service, eai-standard/2.2)

You control one simulated **Franka Panda** arm (7 joints, its standard hand, and the task's tool where it has one) **as if it were real hardware**: the simulator (ManiSkill 3 / SAPIEN, rigid-body physics at
1000 Hz) runs in a service you cannot open. You get one client and one episode.
**Task:** A short round-ended cylinder is rolling along a raised lane when the episode starts and will run off its end. Intercept it in the open-sided tray the Panda holds. Bring it to rest in the tray with its long axis along the world's y axis. Put it into a gently sloping guide channel near the channel's entry, and let it travel out past the far end without the tray touching it at that moment. Catch it again in the tray at the exit, aligned and settled. Finally, deliver it lying along y into a pocket that slides back and forth on a rail, where it must rest while the pocket is moving.

## Scene
One Panda, base at (-0.55, 0, 0) facing +x (yaw 0). Its hand carries a 'receiver': a square tray 0.14 m x 0.14 m inside (2 x `tool_half`), walls 30 mm high and 5 mm thick, floor 5 mm thick. The wall on the tool frame's -x side is missing (open side). The tool frame is the centre of the floor's top surface, z up out of the tray. The tray is side-mounted: an L-shaped adapter bar runs from the hand to the top of the tray's -y wall. In the tool frame the hand's TCP is at (-0.12, -0.12, +0.04), so the tray sits 12 cm ahead of, 12 cm to the side of and 4 cm below the TCP. At the start the tray is level (identity orientation; open side facing world -x), centre at (0.21, -0.18, 0.13).

The cylinder is orange and round-ended (a capsule), 76 mm long overall and 38 mm in diameter. At t = 0 it is rolling on its side, long axis across its direction of travel, along a raised, low-friction static lane (an orange slab on posts), and it rolls off the lane's open end within about the first second. Elsewhere, at a higher level, a static guide channel is mounted on posts. It is 0.09 m wide inside with 22 mm side walls, open at both ends, and slopes very slightly down from its entry end to its exit end. A short static wall stands just behind its entry end. A blue open box (the pocket: 0.15 m x 0.15 m inside, 0.06 m deep) is the moving link of a straight rail along the world's y axis. It is driven back and forth, slowly, by a force-limited drive. On its first outward stroke it runs into the side of the raised source lane and stays pressed against it until the drive reverses; it then moves back along the rail. The table top is the world's z = 0 plane.

**Goal geometry.** Required orientation: the cylinder's long axis along world y (either sign) within 0.2 rad. Guide test lines: world x = 0.02 (entry contact must occur at x below it) and world x = 0.24 (exit beyond it).

## Time in this scene
The scene is dynamic: from the first control step on, things move by themselves (as described above), and they do not
wait for the robot. The simulated clock advances **only through your calls**: every row of a `submit` and every second of an
`observe` watch runs control steps (10 ms each); between calls the world is frozen, however long you think. A call that
runs control steps runs them all, whatever happens meanwhile, and returns what the cameras saw. The episode lasts at most
**25 s of simulated time** (the task's horizon, 2500 control steps): when it is reached before the task
is complete, the task has failed. The cylinder is already rolling at t = 0 and is off the lane within about one second. The pocket moves from t = 0, then stays stuck against the source lane for a long stretch before moving back. It moves fast enough for the last phase only for a few seconds after it comes free, and before its next turning point.

## Success
The task has 5 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **rolling_interception**: The cylinder is held by the tray and does not touch the source lane. 'Held' means: in contact with the tray within the last 25 ms; in the tray frame its centre has |x| and |y| < `tool_half` = 0.07 m; and its centre is between 0.013 m and 0.07 m above the tray floor.
2. **axial_alignment**: The cylinder is held (as above) and aligned, moving at less than 0.06 m/s relative to the tray (at its centre), for 0.3 s without interruption. Aligned means its long axis is within 0.2 rad of the world y axis, either way round: |y component of the axis| > cos 0.2.
3. **guide_rail_traverse**: During this phase the cylinder touches the guide while its centre is at world x < 0.02. Later, at a step when it does not touch the tray, its centre is at world x > 0.24, past the guide's exit end.
4. **exit_reception**: The cylinder is held by the tray (as above), aligned with world y within 0.2 rad, not touching the guide, and moving at less than 0.06 m/s relative to the tray, for 0.2 s without interruption.
5. **oriented_moving_delivery**: All of the following hold for 0.7 s without interruption. The cylinder touches the pocket and is not held by the tray. It lies inside the pocket: in the pocket's frame, for both x and y, |centre offset| + 0.019 + 0.019 x |axis component| < 0.075, i.e. the whole capsule is inside the inner walls. Its centre is more than 0.016 m above the pocket floor, and its top (centre height + 0.019 + 0.019 x |axis z component|) is below 0.063 m. Its long axis is within 0.2 rad of world y. The pocket moves faster than 0.02 m/s. The cylinder moves at less than 0.06 m/s relative to the pocket. This completes the task.

The episode **ends by itself** at the first control step where the last phase is complete (success) or where the task has
failed (`meta["done"]`, `meta["reason"]`: `success` or the failure's name).

**The task fails** (the episode ends, reward 0) as soon as any of these happens:
- from axial_alignment onwards (after the interception), the cylinder touches the table (`cylinder_left_route_or_receiver`);
- the task's horizon is reached: 25 s of simulated time (`timeout`);
- an object leaves the workspace: its centre falls more than 0.2 m below the table top or gets more than 1.8 m from the
  world's z axis (`out_of_bounds`);
- a forbidden contact or a deep interpenetration (below);
- a safety limit is exceeded (`limit_violation`, below).

**Contacts.** Only the tray may touch the cylinder, and the tray may touch nothing but the cylinder: not the source lane, guide, backstop, pocket or its rail, and not the table. No other part of the robot (fingers, hand, links, base) may touch anything. In every task: the two arms (and their tools) never touch each other
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
