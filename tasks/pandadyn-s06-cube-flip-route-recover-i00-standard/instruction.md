# Panda Dynamic Scenes · Inertial cube flip, chute run and pocket recovery (S06) — STANDARD MODE (robot as a service, eai-standard/2.2)

You control one simulated **Franka Panda** arm (7 joints, its standard hand, and the task's tool where it has one) **as if it were real hardware**: the simulator (ManiSkill 3 / SAPIEN, rigid-body physics at
1000 Hz) runs in a service you cannot open. You get one client and one episode.
**Task:** A cube rests on a raised launch surface. With a short push from the pusher blade, tip it over so that the face that initially faces the robot (-x) ends up on top, the cube completing the tip by its own momentum after the blade has let go, and let it settle. Then push the flipped cube onto an inclined chute, let it slide down by itself, meet it with the blade on its downhill side near the chute's lower end, and bring it to rest in the pocket at the bottom of the chute with the same face still on top.

## Scene
One Panda, base at (-0.40, 0, 0), yaw 0 (facing +x). Its hand carries a small blue pusher blade: a box 8 mm thick (tool x) x 50 mm wide (tool y) x 12 mm tall (tool z), centred at the tool frame origin; its pushing faces are normal to the tool x axis. The blade hangs from a rigid side adapter (part of the tool): from the hand a horizontal bar at tool z = 0.035 runs from tool x = -0.12 to 0 at tool y = +0.13, then along y to y = 0.07, ending in a short 12 mm x 12 mm post at (0, 0.07) reaching down from z = 0.036 to z = 0 (the blade's mid-height); the post stands 45 mm beyond the blade's +y end and is not joined to it visibly, but blade, bars and post are one rigid tool. The Panda TCP is at (-0.12, 0.13, 0.04) in the tool frame, so with the blade level the gripper points straight down. At the start the blade is level (tool axes aligned with the world axes, pushing faces normal to world x), its centre at (-0.05, -0.08, 0.179).

An orange cube (44 mm edge) rests at t = 0 on a raised, flat orange launch surface (a slab 0.28 m along x by 0.18 m, on posts), one face toward the robot. The launch surface's far (+x) edge meets the top of a straight inclined grey chute (a trough with a 0.10 m wide floor and 22 mm side walls) that runs downhill in +x; the chute's top edge lies slightly below the launch surface. At the chute's low end sits a blue shallow pocket (an open box 0.12 m x 0.12 m inside with 12 mm walls), open on the side facing the chute, its floor flush with the chute's end. Friction is high enough that a cube at rest on the chute stays put, but a cube already sliding on it keeps sliding and speeds up by itself. Nothing moves at t = 0. The table top is the world's z = 0 plane.

**Goal geometry.** Chute-entry line: cube centre at world x > 0.18 m (oriented_chute_entry). Intercept line: cube centre at world x > 0.32 m (downstream_intercept). The delivery target is the pocket's centre (a physical fixture).

## Time in this scene
The scene is dynamic: from the first control step on, things move by themselves (as described above), and they do not
wait for the robot. The simulated clock advances **only through your calls**: every row of a `submit` and every second of an
`observe` watch runs control steps (10 ms each); between calls the world is frozen, however long you think. A call that
runs control steps runs them all, whatever happens meanwhile, and returns what the cameras saw. The episode lasts at most
**25 s of simulated time** (the task's horizon, 2500 control steps): when it is reached before the task
is complete, the task has failed. Nothing moves at t = 0: the cube rests on the launch surface with one face toward the robot. Once on the chute the cube slides and speeds up by itself, and a cube entering the pocket fast can tumble onto another face.

## Success
The task has 4 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **momentum_face_flip**: let tilt be the angle between the cube's initially vertical axis and world up. The blade's last contact with the cube must end while the tilt is between 0.03 and pi/4 - 0.02 = 0.765 rad (1.7 to 43.9 deg), and at some step more than 20 ms after that last contact the cube must still turn faster than 0.4 rad/s (an early release); the tilt must then pass pi/4 (45 deg) without further blade contact. After that the cube must lie with its original -x face on top (that face's outward normal within 0.18 rad of world +z), moving at less than 0.05 m/s and turning at less than 0.3 rad/s, touching the launch surface, for 0.25 s without interruption. Touching the cube with the blade again after the early release and before the tilt has passed 45 deg fails the task (flip_recontact_before_balance).
2. **oriented_chute_entry**: the cube touches the chute while its centre is at world x > 0.18 m and its original -x face points away from the chute surface (that face's outward normal within 0.35 rad (20.1 deg) of the chute surface's normal). The cube's position along the chute's downhill direction at that moment is recorded as the start of its free slide.
3. **downstream_intercept**: the phase completes at a step where the cube touches the blade and at the same time: the cube's centre is at world x > 0.32 m; the cube touches the chute; the blade's tool-frame origin lies on the downhill side of the cube's centre (positive component along the chute's downhill direction); since the start of its free slide the cube's centre has moved at least `free_slide` = 0.12 m along the chute's downhill direction; and on the previous physics step the cube's velocity component down the chute was at least 0.33 m/s. Any cube-blade contact that does not meet all of these restarts the free slide from the cube's current position.
4. **pocket_delivery**: the cube touches the pocket, its centre is within 0.04 m (horizontal distance) of the pocket's centre, its original -x face is on top (outward normal within 0.18 rad of world +z), it moves at less than 0.04 m/s and turns at less than 0.2 rad/s, for 0.5 s without interruption. This completes the task.

The episode **ends by itself** at the first control step where the last phase is complete (success) or where the task has
failed (`meta["done"]`, `meta["reason"]`: `success` or the failure's name).

**The task fails** (the episode ends, reward 0) as soon as any of these happens:
- during momentum_face_flip, the blade touches the cube after an early release has been registered and before the cube's tilt has passed 45 deg (`flip_recontact_before_balance`);
- the task's horizon is reached: 25 s of simulated time (`timeout`);
- an object leaves the workspace: its centre falls more than 0.2 m below the table top or gets more than 1.8 m from the
  world's z axis (`out_of_bounds`);
- a forbidden contact or a deep interpenetration (below);
- a safety limit is exceeded (`limit_violation`, below).

**Contacts.** Only the pusher (blade, adapter bars and post) may touch anything, and it may touch only the cube: touching the launch surface, the chute, the pocket or the table is forbidden. No other part of the robot, the fingers included, may touch anything, the cube included. In every task: the two arms (and their tools) never touch each other
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

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
