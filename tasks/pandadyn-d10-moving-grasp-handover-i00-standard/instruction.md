# Panda Dynamic Scenes · Moving grasp handover (D10) — STANDARD MODE (robot as a service, eai-standard/2.2)

You control two simulated **Franka Panda** arms (`panda-0` on the left, `panda-1` on the right; each with its standard hand and the task's tool where it has one) **as if it were real hardware**: the simulator (ManiSkill 3 / SAPIEN, rigid-body physics at
1000 Hz) runs in a service you cannot open. You get one client and one episode.
**Task:** A long bar-shaped part is already riding a powered roller conveyor when the episode starts. The left arm must grasp it with its gripper while it is still moving and lift it, then carry it, still moving, through a presentation point. It then hands the part over to the right arm: both grippers hold it at the same time, then the left gripper opens wide and lets go while the right one keeps holding it. Finally the right arm must lay the part into a long open slot that slides back and forth on a rail and let go of it, so that the part lies in the slot while the slot is moving.

## Scene
Two Pandas with their standard two-finger grippers and no tool. panda-0 (left): base at (-0.55, -0.23, 0), yaw 0 (facing +x). panda-1 (right): base at (0.74, 0.23, 0), yaw pi (facing -x). Each arm's tool frame is its gripper TCP (the point between the fingertips). At the start both TCPs point straight down (TCP z = world -z, and TCP x = world +x for both arms), so the fingers close along world y. Left TCP at (-0.10, -0.10, 0.20); right TCP at (0.19, 0.16, 0.23). Both grippers start partly open at 0.024 m per finger (0.048 m total aperture). The action's last entry is the total aperture in [0, 0.08] m, and each finger moves at most 0.025 m/s. In this task the fingers follow their own trajectory, not synchronized with the arm joints, so an aperture change does not stretch the duration of the arm motion. Role labels per phase (left, right): moving_pickup: moving_grasper, preparing_receiver; moving_presentation: moving_donor, tracking_receiver; overlapping_grips: donor_grip, receiver_grip; donor_release: releasing_donor, sole_support; receiver_slot_delivery: cleared_donor, slot_deliverer.

An orange bar-shaped part (0.22 x 0.034 x 0.036 m, long axis along world x) lies across a short roller conveyor. The conveyor has 20 grey rollers (radius 6 mm, 136 mm long, axes along x, 12.5 mm apart along y) on a pedestal, all motor-driven so that their tops carry the part along +y. The part is longer than the rollers and overhangs them at both ends. At t = 0 the part is already moving along +y with the conveyor. The conveyor keeps running for the whole episode, and nothing stops the part at its end: a part that is not taken is carried off the end and falls. A blue open box, the 'slot' (0.25 m along x by 0.13 m along y inside, 0.06 m deep), rides a straight rail along y. The slot is driven back and forth along the rail in a smooth sinusoidal oscillation by itself for the whole episode: slowly, and slowest where it turns around. The table top is the world's z = 0 plane.

**Goal geometry.** Presentation point (0.09, 0.05, 0.24) for the part's centre (moving_presentation). Lift height: part centre above z = 0.21 m (moving_pickup). Drop limit: part centre must stay at or above z = 0.13 m during moving_presentation, overlapping_grips and donor_release.

## Time in this scene
The scene is dynamic: from the first control step on, things move by themselves (as described above), and they do not
wait for the robot. The simulated clock advances **only through your calls**: every row of a `submit` and every second of an
`observe` watch runs control steps (10 ms each); between calls the world is frozen, however long you think. A call that
runs control steps runs them all, whatever happens meanwhile, and returns what the cameras saw. The episode lasts at most
**25 s of simulated time** (the task's horizon, 2500 control steps): when it is reached before the task
is complete, the task has failed. At t = 0 the part is already riding the conveyor toward its end and the slot is already moving; both keep going without any action, and the rollers spin for the whole episode. If the part is not grasped in time, it falls off the conveyor's end. The slot is too slow for the last phase near its turning points, so when the delivery can succeed depends on how long the earlier phases took.

## Success
The task has 5 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **moving_pickup**: the left gripper grips the part (both left-arm fingers, finger links or pads, are in contact with it) at a moment when the part moves faster than 0.025 m/s; this is recorded once. After that, with the left grip still holding, the part's centre rises above z = 0.21 m.
2. **moving_presentation**: while the left gripper still grips the part (both fingers in contact), the part's centre comes within 0.07 m of the presentation point (0.09, 0.05, 0.24) at a moment when the part moves faster than 0.015 m/s.
3. **overlapping_grips**: both grippers grip the part at the same time (both fingers of each hand in contact with it) for 0.08 s without interruption.
4. **donor_release**: the right gripper grips the part (both fingers in contact), no left-arm finger touches the part, and the left gripper is open wider than 0.065 m (sum of its two finger positions), all for 0.12 s without interruption.
5. **receiver_slot_delivery**: the part lies in the moving slot, and the slot moves along its rail faster than 0.02 m/s, for 0.7 s without interruption. The part touches the slot, and neither gripper grips it (a single finger may still touch it). In the slot's frame its centre is within 0.014 m of the slot centre along x (the slot's long axis), within 0.045 m along y, and between 0.01 m and 0.06 m above the slot floor. It moves at less than 0.05 m/s relative to the slot. This completes the task.

The episode **ends by itself** at the first control step where the last phase is complete (success) or where the task has
failed (`meta["done"]`, `meta["reason"]`: `success` or the failure's name).

**The task fails** (the episode ends, reward 0) as soon as any of these happens:
- during moving_presentation, overlapping_grips or donor_release, the part's centre drops below z = 0.13 m (`handover_drop`);
- the task's horizon is reached: 25 s of simulated time (`timeout`);
- an object leaves the workspace: its centre falls more than 0.2 m below the table top or gets more than 1.8 m from the
  world's z axis (`out_of_bounds`);
- a forbidden contact or a deep interpenetration (below);
- a safety limit is exceeded (`limit_violation`, below).

**Contacts.** There are no tools. The fingers of either gripper (finger links and pads) may touch the part and nothing else: not the conveyor rollers or frame, not the slot or its rail, not the table. No other robot part (hand or arm links) may touch anything, the part included. The two arms may never touch each other, finger to finger included, and no arm may touch itself. In every task: the two arms (and their tools) never touch each other
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
