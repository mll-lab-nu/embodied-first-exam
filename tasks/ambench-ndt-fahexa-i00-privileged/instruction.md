# AM-Bench · NDT Inspection — frozen instance i00

You control a simulated **aerial manipulator**: a fully actuated hexarotor (six tilted rotors, so it can hold any attitude
while hovering) carrying a small arm (four joints: three pitch joints and a roll joint) with a two-finger gripper, in
AM-Bench on Isaac Lab / Isaac Sim 5.1 (PhysX), via Python. **Task:** The hovering aerial manipulator starts outside a large warehouse building, facing one of its long walls, and high up on that wall a small rectangle is marked out with yellow-and-black hazard tape. Carry out a non-destructive-testing style inspection: bring the end effector to the fixed inspection point in front of the marked rectangle (see the goal geometry) and keep it there for 100 consecutive control steps (0.83 s).

This is a *fixed scene instance*: the scene and the robot start the same way after every reset, and you may reset and
retry as many times as you want. Your deliverable is **one replayable trajectory** of the robot's low-level actions, not a
general policy.

## Scene
The ground is the world's z = 0 plane. The scene is NVIDIA's static sample warehouse (shelving racks, pallets, boxes, signs, a forklift and a posed worker figure, none of which moves). The robot hovers a short distance in front of the outer face of one of the building's long walls, which faces it squarely. That wall is a flat, solid panel surface from a few metres above the ground up to the roof; below it the building is open, so at the robot's height the warehouse interior, a pillar on either side and a few signs in the wall's plane are visible. Straight ahead of the robot and well above it, a marked region is taped onto the wall: a rectangle of yellow-and-black hazard-striped reflective tape 3 cm wide, 0.30 m tall and 0.22 m wide outside (0.24 x 0.16 m inside). The tape is visual only (no collision). Far off to the robot's right stands a separate concrete wall slab (0.1 x 2 x 2 m) that plays no part in the task. Nothing moves and nothing varies between instances. The robot starts hovering level and motionless, facing the warehouse wall, with its arm at its zero joint configuration (end effector a little ahead of and above the airframe) and the gripper closed.

Exactly (privileged information, also readable through the tooling): One environment; its origin is the world origin. Robot at every reset: base_link at (0, 0, 1.0) m with orientation (1, 0, 0, 0) wxyz (body +x is the world +x direction), zero velocity; arm_link1_pitch_joint = arm_link2_pitch_joint = arm_link3_pitch_joint = arm_link4_roll_joint = 0 rad; arm_lfinger_joint = arm_rfinger_joint = 0.001 m (their lower limit: gripper closed, gripper_width 0.002 m). By the robot's URDF kinematics this puts ee_link at about (0.227, 0, 1.124) m with identity orientation and the tool-tip point (ee_link origin + 0.18 m along the ee_link x axis) at about (0.407, 0, 1.124) m; the end-effector command is initialised to the current ee_link pose. Warehouse: Isaac Sim's sample scene Samples/Replicator/Benchmark/full_warehouse_worker_benchmark_sdg.usd, loaded from NVIDIA's asset server (Isaac 5.1 asset root) together with the Simple_Warehouse props, materials and textures, the Reallusion worker character and the forklift it references; translated by (28.3, 0, 0) m, unrotated; static colliders only, no rigid bodies. Its wall facing the robot is the plane x = 1.97 m (interior x > 1.97, y from -23.4 to 30.6 m); between pillars at y = -2.4 and 3.6 m (0.55 m wide, front at x = 1.87) it consists of single-quad panels with mesh collision from z = 3 to 9 m; the panels of the band z 0..3 m are authored at 1/100 scale in this asset, so that band is open. Roof at z = 9 m. Marker: marked_region.usda (local wrapper) at (1.962, 0, 7.0) m with orientation (0, 0.7071, 0, 0.7071) wxyz (local x to world +z, local y to world -y, local z to world +x); its visible part is four strips of NVIDIA's ReflectiveTape2M5CM_I01 tape (yellow/black stripes) referenced by URL from NVIDIA's content server, lying at x of about 1.968 just in front of the wall and framing an outer 0.30 m (z) x 0.22 m (y), inner 0.24 x 0.16 m rectangle centred at (y, z) = (0, 7.0); its target_region debug surface has purpose 'guide' (not rendered); no collision. Wall slab: kinematic cuboid 0.1 x 2.0 x 2.0 m, centre (2.0, -10.0, 1.0) m, identity, friction 1.0 / 1.0, visual material NVIDIA Concrete_Block.mdl. Isaac Lab's ground plane (z = 0) overlaps the warehouse floor tiles; besides the dome light the warehouse has its own rect lights. No reset events: every instance is identical. AM-Bench's goal_pos observation is the fixed goal (1.77, 0, 7.0). Scene default physics material: friction 1.0 / 1.0, restitution 0.

**Goal geometry.** The inspection point is fixed, the same in every instance, and not itself marked in the scene: g = (1.77, 0.0, 7.0) m in world coordinates (z up; the robot starts with base_link at (0, 0, 1.0) facing +x). The success region for ee_link's origin is |x - 1.77| < 0.03 m and sqrt(y^2 + (z - 7.0)^2) < 0.08 m. It lies on the robot's side of the taped rectangle, opposite its centre, a little less than 20 cm from it.

## Success (AM-Bench's own check)
With e the position of ee_link's origin (not the tool tip) and g = (1.77, 0.0, 7.0) m (goal_position; environment origin = world origin), a control step is 'in' when |e_x - g_x| < 0.03 m and sqrt((e_y - g_y)^2 + (e_z - g_z)^2) < 0.08 m. A counter increases by 1 at every 'in' step and is reset to 0 at every step that is not; success when it reaches 100 (success_hold_steps), i.e. at the 100th consecutive 'in' step (100/120 s, about 0.83 s). Orientation, velocity and contact are not tested. g is 0.192 m in front of the marker's origin, so with ee_link level and pointing at the wall the tool-tip point is about 2 cm short of the wall surface. AM-Bench reports inspection_target_held (the success itself) as its only criterion. Evaluated after every control step (decimation 1, so after every 1/120 s physics step) on the simulated state; the 100-step hold above is the only hold requirement. The episode terminates at the first step where it holds. Otherwise it is truncated by the time limit: episode_length_s = 20 s, i.e. max_episode_length = 2400 control steps; AM-Bench raises the time-out when episode_length_buf >= max_episode_length - 1, i.e. at the 2399th step.
The episode **ends by itself** at the first control step where the check holds (success; rows after it are never
executed), or when the task's episode length of **20 s** runs out (a failure: AM-Bench's time-out ends the episode
at control step 2399). Isaac Lab resets the scene inside the step that ends an episode, so after it `s.state()` and
`s.objects()` show the start again; `s.status()` keeps the outcome and the end state's hash, and the cameras show the end.

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below). It is replayed
open-loop from the same initial state in two fresh processes and scored 1 if the task succeeds in both replays, else 0
(a trajectory that only just succeeds may not succeed in both: leave a margin). Also leave the script that produced it
at `/app/output/gen.py`. Save a working trajectory as soon as you have one and overwrite it as you improve it: whatever
is in `/app/output/` when the time is up is graded. The file holds `task` and `actions`, a (T, 8) float array of at most
**8,000 rows** (one per control step); anything else (another shape, NaN, more rows, a row whose quaternion
`qw qx qy qz` has zero length, a file that is not such an npz) scores 0.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_ambench import Session
s = Session(instance="/app/instance.json")   # ~2-6 min: launches Isaac Sim, builds the scene, resets to the frozen instance
                                   # Session(..., cameras=True[, depth=True]) to look (see Cameras below)
s.reset()                          # back to the frozen instance (the seeded reset; as often as you like)
s.step(row)                        # one control step (1/120 s): row = 8 values (below); True once the episode is over
s.hold_action()                    # a row that keeps the current end-effector target and gripper command
s.status()                         # {'success', 'done', 'end_reason', 'control_steps', 'sim_time_s', 'episode_length_s', 'state_sha', ...}
s.state()                          # privileged: AM-Bench's own observation of the task (robot, end effector, task objects, goal)
s.objects()                        # every task object and fixture: pose (xyz + quaternion wxyz), velocities, joint state
s.proprio()                        # the robot: base and end-effector poses and velocities, gripper width, arm joints, current command
s.actions()                        # (T, 8) rows executed since the last reset: the trajectory of this episode
s.replay(actions)                  # reset, run the rows open-loop until the episode ends, return status (+ executed_rows)
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_frame("ee_camera")        # cameras=True only: RGB uint8 (384, 384, 3) at the end effector, or "base_camera" (on the airframe, looking forward)
s.render_depth("ee_camera")        # cameras=True, depth=True: float32 z-depth (m), 0 = no reading
s.camera_info()                    # cameras=True: intrinsics, world -> camera extrinsics (OpenCV axes), mounts
s.start_video("/app/output/try.mp4"); ...; s.stop_video()   # cameras=True only: film the steps in between (both cameras side by side)
s.env                              # the Isaac Lab environment itself (AM-Bench's source is in /opt/ambench: read-only reference)
```
The tooling is deliberately thin: the environment's own action, its state and its cameras. Reaching, pressing, pushing,
turning and throwing are yours to build. Isaac Sim runs once per process, and only the first episode of a process is
guaranteed to be bit-identical to a fresh process's: after changes, check your trajectory with the grader's CLI.
**Cameras.** The robot's two onboard cameras come with `Session(..., cameras=True)` (decided once per process): a second
Isaac process then draws them from the physics state (it starts with the Session and takes ~3.5 GB of GPU memory and ~12 GB
of memory), so looking never changes the physics, which stays exactly the grader's.

The grader replays in two fresh processes; each is exactly this CLI (a fresh process, so run it to self-check):
`python /opt/tools/rcb_ambench.py replay --instance /app/instance.json --traj /app/output/trajectory.npz`
(`... film --instance ... --traj ... --video out.mp4` films the same rows through the cameras). A process whose output
shows `PhysX error: GPU ... fail to launch` or `CUDA error: out of memory` ran short of GPU memory and its physics is not
reliable (PhysX steps on without the failed kernels): rerun it with fewer Isaac processes at once. The grader runs such a
replay once more and never scores it.

## Conventions
- World frame: metres, z up, the ground is the plane z = 0; positions are relative to the environment's origin (the
  tooling and the actions use the same origin); quaternions are **wxyz**.
- Action row (8 values per control step), AM-Bench's absolute end-effector pose action: the target position of the
  end-effector link (x, y, z, m) and its target orientation (qw, qx, qy, qz, in AM-Bench's command frame of the end
  effector: `s.proprio()["command"]` and `hold_action()` give the current target in the same convention), then the gripper
  command (-1 = closed .. +1 = open). Every step, AM-Bench's floating-base inverse kinematics turns the target into an
  airframe pose and arm joint targets, its PID controller turns the airframe pose into the six rotor thrusts, and the arm
  joints track their targets.
- Control and physics run at 120 Hz (one physics step per row). There is no step budget: the time limit (`## Time limit`)
  is your only budget; an episode lasts at most 20 s of simulated time.
- One `Session` per process (Isaac Sim launches once, then the scene builds: ~2-6 min, the upper end on a busy host).
  Physics is PhysX on the **GPU** (about 10-15 control steps per second of wall time). A camera-free Session takes ~2 GiB
  of memory and ~1.2 GiB of GPU memory, one with cameras ~14 GiB and ~4.6 GiB (its render worker included): run at most
  two Sessions with cameras at once. Do not call `s.close()` before writing every output.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **16 GiB of GPU memory**, **28 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`. GPU memory counts what a process reserves (JAX, for example, reserves most of the card unless told not to). These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. When enforcement is on and GPU memory goes above 1.5 times its limit, the monitor also kills the process holding the most of it at once, to protect the machine; that alone does not fail the trial. CPU is capped at 8 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
