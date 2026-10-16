# Panda Dynamic Scenes · Load a coasting cart, throw the switch, recover the part (S08) — STANDARD MODE (robot as a service, eai-standard/2.2)

You control one simulated **Franka Panda** arm (7 joints, its standard hand, and the task's tool where it has one) **as if it were real hardware**: the simulator (ManiSkill 3 / SAPIEN, rigid-body physics at
1000 Hz) runs in a service you cannot open. You get one client and one episode.
**Task:** A small cube (the part) rides a powered roller conveyor, and an unpowered cart is already coasting along a straight channel towards a passive hinged switch that splits the track into two diagonal branches. Grasp the part with both fingers while it is still moving and lift it, drop it into the moving cart, then push the switch with a finger so that it will steer the cart into the branch selected for this instance (one of the two sides, drawn per instance and given under Goal geometry) before the cart reaches it. The cart must then be deflected by the switch into that branch. Finally, grasp the part again, lift it out of the cart and hold it up before the cart runs too far down the branch.

## Scene
One Panda, base at (-0.55, 0, 0) facing +x (yaw 0). No tool: the stock Panda hand with its two fingers. The tool frame (the reported tool pose) is the hand's TCP, the point between the fingertips, with its z axis pointing out of the hand along the fingers. At the start the TCP is at (-0.13, -0.13, 0.20) with the gripper pointing straight down (orientation wxyz (0, 1, 0, 0)). The fingers close along world y and start fully open (aperture 0.08 m; the action's last component is the total aperture, 0 to 0.08 m). In this task the finger motion is not time-synchronised with the arm joints, so a finger command does not stretch the arm motion. The finger servo damping is also raised to 8.

The part is an orange cube with 36 mm edges. It sits on a short roller conveyor of 20 thin grey rollers, which spin by themselves and carry it towards the conveyor's open end; past that end it drops to the table. The cart is a small blue open tray, 0.13 m x 0.11 m inside with 12 mm walls. It rides on four free orange ball bearings (radius 18 mm) and has no motor: it is already coasting at t = 0 and keeps rolling straight. It first passes between two parallel static walls (an entry channel, 16 mm thick and 5 cm tall), then meets the switch. The switch is a passive vertical blade (12 mm thick, 0.14 m long, 45 mm tall) on a vertical hinge with joint friction and no spring, and it carries a small knob on top of its free end. At the start the blade points straight back along the cart's path, edge-on to the incoming cart. Beyond the switch there are two diagonal branches, one on each side. Each has a static guide rail (16 mm thick, 0.24 m long, 5 cm tall) and, at its far end, a shallow static open box (dock, 0.14 m x 0.12 m inside, 18 mm walls). The table top is the world's z = 0 plane.

**Goal geometry.** At this instance the selected branch is branch -1: the diagonal branch on the -x side (the side nearer the robot's base). Lines in the world frame used by the predicates: part lift height z = 0.20 m; switch deadline y = 0.105 for the cart's origin; branch reached at y > 0.23 with |x| > 0.08 on the selected side; recovery window ends at |x| = 0.27 or y = 0.43 for the cart's origin.

## Time in this scene
The scene is dynamic: from the first control step on, things move by themselves (as described above), and they do not
wait for the robot. The simulated clock advances **only through your calls**: every row of a `submit` and every second of an
`observe` watch runs control steps (10 ms each); between calls the world is frozen, however long you think. A call that
runs control steps runs them all, whatever happens meanwhile, and returns what the cameras saw. The episode lasts at most
**25 s of simulated time** (the task's horizon, 2500 control steps): when it is reached before the task
is complete, the task has failed. At t = 0 the part is already moving along the conveyor and drops off its end within a few seconds. The cart is already coasting and keeps rolling at constant speed (it has no motor) until something stops it. Nothing in the images marks the selected branch: it is given under Goal geometry.

## Success
The task has 5 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **moving_part_pickup**: Both fingers grip the part (bilateral grip: the left finger or its pad and the right finger or its pad are both in contact with the part at that physics step) at some moment when the part moves faster than 0.025 m/s. After that (same or later step), with the part still gripped, its centre is higher than z = 0.20 m.
2. **load_coasting_cart**: At a step when the part is not gripped by both fingers, the part touches the cart's tray while the cart moves faster than 0.02 m/s.
3. **physical_switch_operation**: During this phase a finger (either finger or finger pad) touches the switch. After that, at some step: the switch angle q (about the vertical hinge, counterclockwise seen from above; q = 0 is the blade pointing from its hinge towards -y) is turned towards the selected branch by more than 0.50 rad, i.e. -branch x q > 0.50 (q < -0.50 rad when branch = +1, the +x side; q > +0.50 rad when branch = -1); the switch turns slower than 0.12 rad/s; and the cart's origin is still at y < 0.105. If, before this, the cart touches the switch or its origin passes y = 0.105, the task fails (missed_switch_deadline).
4. **selected_branch**: During this phase the cart touches the switch and touches the guide rail of the selected branch (`branch_rail_{branch}`), in either order. Then the cart's origin is at y > 0.23 and on the selected side, with branch x x > 0.08 (x > 0.08 for branch +1, x < -0.08 for branch -1).
5. **payload_recovery**: Both fingers grip the part, its centre is more than 0.10 m above the cart's origin (the centre of the cart floor's top surface), and the part does not touch the cart, for 0.5 s without interruption. This completes the task.

The episode **ends by itself** at the first control step where the last phase is complete (success) or where the task has
failed (`meta["done"]`, `meta["reason"]`: `success` or the failure's name).

**The task fails** (the episode ends, reward 0) as soon as any of these happens:
- during physical_switch_operation, the phase's completion condition is not met at a step where the cart touches the switch or the cart's origin is at y > 0.105 (`missed_switch_deadline`);
- during physical_switch_operation or selected_branch, the part's centre drops below z = 0.018 m (it is lying on the table) (`loaded_cart_spill`);
- during payload_recovery, the cart's origin reaches |x| > 0.27 or y > 0.43 (`missed_downstream_recovery_window`);
- the task's horizon is reached: 25 s of simulated time (`timeout`);
- an object leaves the workspace: its centre falls more than 0.2 m below the table top or gets more than 1.8 m from the
  world's z axis (`out_of_bounds`);
- a forbidden contact or a deep interpenetration (below);
- a safety limit is exceeded (`limit_violation`, below).

**Contacts.** No tool is mounted. Only the finger links (fingers and finger pads) may touch anything. They may touch the part, the cart's tray and its bearing balls (all free objects), and the moving blade/knob of the switch (`switch`). The fingers may not touch the conveyor (its rollers or its base), the switch base, the entry walls, branch rails, docks or the table. No other part of the robot (hand, links, base) may touch anything. Finger-to-finger contact is allowed. In every task: the two arms (and their tools) never touch each other
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
