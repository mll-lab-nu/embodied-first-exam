# Panda Dynamic Scenes · Spring gate switchyard (D07) — STANDARD MODE (robot as a service, eai-standard/2.2)

You control two simulated **Franka Panda** arms (`panda-0` on the left, `panda-1` on the right; each with its standard hand and the task's tool where it has one) **as if it were real hardware**: the simulator (ManiSkill 3 / SAPIEN, rigid-body physics at
1000 Hz) runs in a service you cannot open. You get one client and one episode.
**Task:** A low-friction puck slides inside a U-shaped pen of bouncy rails that is open toward the right arm, and a spring-loaded swinging gate stands inside the pen. The left Panda has a bare gripper. It must take hold of the gate with both fingers and swing it open one way. The right Panda's paddle must then hit the puck so that it travels deep into the pen. While the puck runs round, the left hand, still gripping, must swing the gate the other way: at the moment the puck hits the upper (+y) rail, the gate must be at that opposite angle. The right paddle then intercepts the puck. Finally the puck must cross a goal line in front of a backstop on the right arm's side while the gate is still deflected well away from its rest position and the paddle is not touching the puck.

## Scene
panda-0 (left): base at (-0.55, -0.22, 0), yaw 0 (facing +x). It has no tool and uses the stock Panda parallel gripper: two fingers with a total opening of up to 0.08 m, fully open (0.04 m per finger) at reset. Its tool frame, reported as `panda-0_tool_pose`, is the gripper TCP between the fingertips. At the start the TCP is at (0.04, -0.10, 0.16), pointing straight down (quaternion (0, 1, 0, 0)), with the fingers closing along world y. panda-1 (right): base at (0.74, 0.22, 0), yaw pi (facing -x). It carries a flat rigid paddle, 0.10 m long (2 x `tool_half`, `tool_half` = 0.05 m), 0.05 m tall and 12 mm thick, on a rigid adapter on its back (tool -x) side. The tool frame is the paddle centre, with x normal to its faces, y along its length and z up. The TCP sits 0.12 m behind the paddle centre and 0.04 m above it. Paddle start: centre (0.30, -0.08, 0.045), quaternion (0, 0, 0, 1) (yawed 180 deg, faces normal to world x); its lower edge is then 0.020 m above the table. Role labels in every phase: panda-0 gate_operator, panda-1 preparing_striker.

An orange square puck (44 mm x 44 mm, 24 mm tall) slides on the table with very little friction. At t = 0 it is already moving toward the right arm. Three fixed, very bouncy orange rails, 60 mm tall, form a U-shaped pen open toward the right arm. The far rail is on the left arm's side, and two long side rails run along it: the upper rail on the +y side and the lower rail on the -y side. Inside the pen stands a swinging gate: an amber leaf 0.13 m long, 55 mm tall and 12 mm thick that turns about a vertical hinge at one end. Its lower edge is just above the table, so the puck cannot pass beneath it. A raised orange-red handle block (32 x 24 x 24 mm) sits on the leaf's free end. A weak torsional spring pulls the gate back toward its rest orientation, in which the leaf runs along the world y axis, and the hinge is nearly frictionless. A short, non-bouncy backstop wall (0.14 m wide, 60 mm tall) stands outside the pen, beyond the goal line on the right arm's side. Only the puck moves at the start; the gate moves when pushed and springs back when let go. The table top is the world's z = 0 plane.

**Goal geometry.** Goal line for the puck's centre: x = 0.43, crossed in +x with |y - 0.15| < 0.055 m. It. Loop line: the puck's centre must get to x < -0.05. Gate angle thresholds: q > 0.5 rad, q < -0.35 rad and |q| > 0.3 rad.

## Time in this scene
The scene is dynamic: from the first control step on, things move by themselves (as described above), and they do not
wait for the robot. The simulated clock advances **only through your calls**: every row of a `submit` and every second of an
`observe` watch runs control steps (10 ms each); between calls the world is frozen, however long you think. A call that
runs control steps runs them all, whatever happens meanwhile, and returns what the cameras saw. The episode lasts at most
**35 s of simulated time** (the task's horizon, 3500 control steps): when it is reached before the task
is complete, the task has failed. The puck is already sliding toward the right paddle at t = 0, before the gate can have been opened. A paddle contact before the gate is open does not count as the first shot. The gate springs back toward its rest orientation whenever it is let go.

## Success
The task has 5 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **left_gate_open**: Two things hold at the same moment. Both fingers of panda-0's gripper (the left finger and the right finger, each counting together with its pad) are in contact with the gate's swinging part (leaf or handle). And the gate angle q exceeds 0.5 rad. q is 0 at the spring's rest orientation and positive when the free end swings toward +x (counter-clockwise seen from above).
2. **right_loop_shot**: The puck touches the right paddle at some moment during this phase; touches before this phase do not count. After that, the puck's centre is at world x < -0.05 while the puck does not touch the right paddle.
3. **gate_reconfiguration**: At one and the same moment, three things hold. Both left fingers touch the gate's swinging part. The gate angle q is below -0.35 rad. And the puck is in contact with the upper rail (the rail on the +y side of the pen).
4. **return_interception**: The puck touches the right paddle.
5. **final_gate_shot**: The puck's centre crosses x = 0.43 moving in +x, with |y - 0.15| < 0.055 m. Moving in +x means x was <= 0.43 on the previous physics step and is > 0.43 now. At that moment the puck must not touch the right paddle, and the gate must be deflected by more than 0.3 rad either way (|q| > 0.3); no grip is required. This completes the task.

The episode **ends by itself** at the first control step where the last phase is complete (success) or where the task has
failed (`meta["done"]`, `meta["reason"]`: `success` or the failure's name).

**The task fails** (the episode ends, reward 0) as soon as any of these happens:
- the task's own failure conditions: none (only the rules below apply);
- the task's horizon is reached: 35 s of simulated time (`timeout`);
- an object leaves the workspace: its centre falls more than 0.2 m below the table top or gets more than 1.8 m from the
  world's z axis (`out_of_bounds`);
- a forbidden contact or a deep interpenetration (below);
- a safety limit is exceeded (`limit_violation`, below).

**Contacts.** The gripper fingers and finger pads of either arm may touch the puck and the gate's swinging part (leaf and handle). They must not touch the gate's base, the rails, the backstop, the table or the robot pedestals. The right paddle, including its adapter, may touch only the puck, not the gate, rails, backstop or table. No other robot part, such as the hand or the arm links, may touch anything. The two arms and the paddle must never touch each other, and the paddle must not touch its own arm. In every task: the two arms (and their tools) never touch each other
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

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
