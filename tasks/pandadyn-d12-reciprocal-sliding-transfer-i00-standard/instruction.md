# Panda Dynamic Scenes · Reciprocal sliding transfer (D12) — STANDARD MODE (robot as a service, eai-standard/2.2)

You control two simulated **Franka Panda** arms (`panda-0` on the left, `panda-1` on the right; each with its standard hand and the task's tool where it has one) **as if it were real hardware**: the simulator (ManiSkill 3 / SAPIEN, rigid-body physics at
1000 Hz) runs in a service you cannot open. You get one client and one episode.
**Task:** Each arm holds a level scoop, a shallow square tray that is open on the side facing the other arm. A cube on a very slippery surface starts on the left scoop. Without tilting the scoops, the left arm must make the cube slide out over its open edge onto the right scoop, where the cube has to come to rest. The right arm then carries it to a new place and makes it slide back onto the left scoop, where it must come to rest again. Finally the cube must be set down on a fixed output platform and left there at rest. Until that final deposit begins, the scoops may not tilt by more than 2.1 deg, and the cube may never be without scoop contact for more than about a tenth of a second.

## Scene
Two Pandas facing each other along x. panda-0 (left): base at (-0.55, -0.22, 0), yaw 0 (facing +x). panda-1 (right): base at (0.74, 0.22, 0), yaw pi (facing -x). Each hand carries a scoop: a square tray with a 5 mm floor, inside 0.16 x 0.16 m (2 x `tool_half`, 0.08 at this instance). It has 25 mm high, 5 mm thick walls on three sides and no wall on its tool +x side, the side pointing away from the arm's own base. The tool frame is the centre of the inside floor surface, z up, x toward the open side. With the scoop level the hand points straight down and the scoop's floor centre is 0.12 m ahead of the gripper TCP along tool x and 0.04 m below it. The grey adapter enters at the middle of the back (tool -x) wall: a 12 mm wide post protrudes 6 mm inward from floor level up to 35 mm, and a bar protrudes 12 mm inward 29-41 mm above the floor, above the wall top. Start: left floor centre at (-0.015, -0.04, 0.19), level, axes aligned with the world (open side facing +x). Right floor centre at (0.175, -0.04, 0.187), level, rotated 180 deg about z (open side facing -x). The two open edges thus face each other across a gap of about 2 cm, with the right floor 3 mm lower. Role labels per phase (left, right): left_inertial_slip: inertial_donor, matched_receiver; right_receive_and_brake: cleared_donor, braking_receiver; reverse_geometry: preparing_receiver, loaded_carrier; left_receive_and_brake: braking_receiver, inertial_donor; final_support_deposit: deliverer, cleared_partner.

An orange cube (36 mm edge) starts resting flat on the left scoop's floor, off the floor centre toward the open edge. Contact between the cube and the scoops is very slippery. The output platform is a fixed orange slab (0.20 x 0.15 m, 24 mm thick) on two grey posts, standing beside the scoops' working area on the -y side, toward the right arm. Nothing moves by itself. The table top is the world's z = 0 plane.

## Time in this scene
The scene is dynamic: from the first control step on, things move by themselves (as described above), and they do not
wait for the robot. The simulated clock advances **only through your calls**: every row of a `submit` and every second of an
`observe` watch runs control steps (10 ms each); between calls the world is frozen, however long you think. A call that
runs control steps runs them all, whatever happens meanwhile, and returns what the cameras saw. The episode lasts at most
**25 s of simulated time** (the task's horizon, 2500 control steps): when it is reached before the task
is complete, the task has failed. Nothing moves at t = 0 except that the cube settles onto the left scoop. Because the surfaces are so slippery, any change in a scoop's velocity makes the cube slide on it; watch the cube's position on the scoop from frame to frame.

## Success
The task has 5 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **left_inertial_slip**: while the cube is on the left scoop (it has touched that tool link within the last 25 ms), its centre has moved more than 0.028 m toward the open edge from its start offset, measured along the left scoop's tool x axis (left-tool-frame x > 0.040 + 0.028 = 0.068 m).
2. **right_receive_and_brake**: the cube is on the right scoop (touched within the last 25 ms) and not on the left one (no left-scoop contact within the last 25 ms), for 0.3 s without interruption. During that time its centre is within 0.065 m of the right scoop's floor centre along both tool x and tool y (|x|, |y| < 0.065 m in the right tool frame), and it moves at less than 0.05 m/s relative to the right scoop (the scoop's rigid-body velocity at the cube's position). The right tool frame's position at the moment this phase completes is recorded as the receive pose.
3. **reverse_geometry**: with the cube on the right scoop (touched within the last 25 ms), the right tool frame is more than 0.06 m away from the receive pose recorded at the end of right_receive_and_brake.
4. **left_receive_and_brake**: the cube is on the left scoop (touched within the last 25 ms) and not on the right one (no right-scoop contact within the last 25 ms), for 0.3 s without interruption. During that time its centre is within 0.065 m of the left floor centre along both tool x and tool y, and it moves at less than 0.05 m/s relative to the left scoop.
5. **final_support_deposit**: the cube touches the output platform and has touched neither scoop within the last 25 ms, for 0.5 s without interruption. During that time its centre is within 0.065 m horizontally (a circle) of the platform's centre (the platform top is 0.20 x 0.15 m), and it moves slower than 0.04 m/s. This completes the task.

The episode **ends by itself** at the first control step where the last phase is complete (success) or where the task has
failed (`meta["done"]`, `meta["reason"]`: `success` or the failure's name).

**The task fails** (the episode ends, reward 0) as soon as any of these happens:
- before final_support_deposit (during phases left_inertial_slip to left_receive_and_brake), either scoop's tool z axis tilts more than 2.1 deg away from world vertical (`tilt_only_shortcut`);
- before final_support_deposit, the cube stays unsupported for more than 0.09 s at a stretch. Unsupported means it has touched neither scoop within the last 25 ms, so this fires after roughly 0.115 s without any scoop contact (`airborne_transfer_shortcut`);
- the task's horizon is reached: 25 s of simulated time (`timeout`);
- an object leaves the workspace: its centre falls more than 0.2 m below the table top or gets more than 1.8 m from the
  world's z axis (`out_of_bounds`);
- a forbidden contact or a deep interpenetration (below);
- a safety limit is exceeded (`limit_violation`, below).

**Contacts.** Each scoop (whole tool link, adapter included) may touch the cube only: not the output platform, not the table. No other part of either robot, the fingers included, may touch anything. The two arms and their scoops may never touch each other, and no arm may touch itself. In every task: the two arms (and their tools) never touch each other
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
