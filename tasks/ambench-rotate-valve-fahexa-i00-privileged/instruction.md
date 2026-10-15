# AM-Bench · Rotate Valve — frozen instance i00

You control a simulated **aerial manipulator**: a fully actuated hexarotor (six tilted rotors, so it can hold any attitude
while hovering) carrying a small arm (four joints: three pitch joints and a roll joint) with a two-finger gripper, in
AM-Bench on Isaac Lab / Isaac Sim 5.1 (PhysX), via Python. **Task:** A valve is mounted on the front face of a wall in front of the hovering aerial manipulator: a large red wheel disc on a short shaft, with a handle bar sticking out of the disc's face toward the robot. Turn the valve: rotate the wheel clockwise, as seen from the robot's side of the wall, by at least 170 degrees from its starting angle.

This is a *fixed scene instance*: the scene and the robot start the same way after every reset, and you may reset and
retry as many times as you want. Your deliverable is **one replayable trajectory** of the robot's low-level actions, not a
general policy.

## Scene
The ground is the world's z = 0 plane. In front of the robot stands an immovable (kinematic) wall: a slab 0.1 m thick, 2.0 m wide and 2.0 m tall with a concrete-block surface, its front face turned toward the robot. The wall is upright (no tilt in this task); its distance and sideways offset vary between instances. A valve is mounted on the wall's front face with its axis perpendicular to the wall: a dark-blue circular base plate (about 47 cm across) fixed just in front of the wall, a short shaft, and a red disc of the same size that turns with the shaft. On the disc's robot-facing side, off the axis, is a handle bar (square cross-section about 6 cm, 16 cm long, parallel to the axis); at reset it sits directly below the hub (the 6 o'clock position), and it can also spin freely about its own long axis. The valve's height and sideways position on the wall vary between instances. The shaft has no spring and no end stops: it stays at whatever angle it is left, its motion resisted by damping and friction. Nothing moves by itself. The robot starts hovering level and motionless, facing the wall, with its arm at its zero joint configuration (end effector a little ahead of and above the airframe) and the gripper closed.

Exactly (privileged information, also readable through the tooling): One environment; its origin is the world origin. Robot at every reset: base_link at (0, 0, 1.0) m with orientation (1, 0, 0, 0) wxyz (body +x is the world +x direction), zero velocity; arm_link1_pitch_joint = arm_link2_pitch_joint = arm_link3_pitch_joint = arm_link4_roll_joint = 0 rad; arm_lfinger_joint = arm_rfinger_joint = 0.001 m (their lower limit: gripper closed, gripper_width 0.002 m). By the robot's URDF kinematics this puts ee_link at about (0.227, 0, 1.124) m with identity orientation and the tool-tip point (ee_link origin + 0.18 m along the ee_link x axis) at about (0.407, 0, 1.124) m; the end-effector command is initialised to the current ee_link pose. Wall: kinematic cuboid 0.1 (x) x 2.0 (y) x 2.0 (z) m, nominal centre (2.0, 0.0, 1.0) m and orientation identity (front face the plane x = centre_x - 0.05, normal -x, toward the robot); friction 1.0 static / 1.0 dynamic, restitution 0; visual material NVIDIA Concrete_Block.mdl. At each reset (Isaac Lab mdp.reset_root_state_uniform) the centre becomes (2.0 + dx, 0.0 + dy, 1.0) with dx, dy ~ U(-0.2, 0.2) m independently; the configured pitch range is (0, 0), so the wall keeps the identity orientation (upright, front normal -x). Valve: articulation valve.usd with a fixed root body base_link, self-collisions disabled, solver iterations 16 position / 4 velocity, spawned with scale (1.8, 1.0, 1.8) in the asset's own frame (radial dimensions x1.8, axial dimensions unchanged), mass_props mass = 0.05 kg set on each of the valve's rigid links (the USD authors 0.01 kg per link, 0.005 kg for the handle), contact offset 0.005 m, rest offset 0. At each reset, after the wall, base_link is placed at wall_centre + R_wall (-0.06, vy, vz) with vy, vz ~ U(-0.2, 0.2) m independently (the base-plate centre 0.01 m in front of the wall surface) with orientation R_wall composed with (0.5, 0.5, 0.5, 0.5) wxyz, so the shaft axis (base_link local +z) is world +x, pointing into the wall. Along the axis toward the robot, from the base-plate centre: blue base plate radius 0.234 m, thickness 0.015 m, colour (0.018, 0.115, 0.232); shaft radius 0.108 m from 0.0075 to 0.0475 m; red disc radius 0.234 m from 0.048 to 0.058 m (OmniPBR diffuse tint (0.99, 0.01, 0.01)); handle bar (body handle_link, 0.063 x 0.063 m cross-section, 0.16 m long along the axis) on the robot-facing side of the disc, below the hub at reset (the USD authors its centre 0.135 m out along the axis and 0.144 m below it after scaling, but its joint anchor on the disc is authored elsewhere, so the simulated pose follows the joint: read handle_link's position, which is AM-Bench's goal_pos observation). Joints: base_to_shaft, revolute about base_link +z (world +x), no position limits, reset to 0 rad with zero velocity every episode, Isaac Lab implicit actuator stiffness 0, damping 15.0, friction 0.2 (static and dynamic), effort limit 20, velocity limit 5.0 rad/s; shaft_to_disk fixed; disk_to_handle, revolute about the handle's long axis, unlimited, reset to 0, stiffness 0, damping 10.0, friction 0.1, effort limit 20, velocity limit 5.0 rad/s. Physics material on base plate, shaft and disc: static and dynamic friction 10000; the handle uses the scene default (friction 1.0 / 1.0, restitution 0).

## Success (AM-Bench's own check)
Success when the valve has turned clockwise by at least 17/18 pi = 2.96706 rad (170 degrees; valve_target_angle): the unwrapped angle of the revolute joint base_to_shaft, counted from its 0 rad at the reset, is >= 2.96706 rad. Positive is the right-hand rotation about the shaft axis base_link +z, which points into the wall (world +x): clockwise when viewed from the robot's side, so a handle starting straight below the hub first moves toward world +y (the robot's left) and at 170 degrees is 10 degrees short of straight up. The joint has no limits, and PhysX reports its position wrapped into [-pi, pi] (s.objects() shows that raw value): AM-Bench's check compares that raw value, which a counter-clockwise turn of 190 degrees would also bring to +170 degrees, so the tooling (and the grader, with the same tooling) gives the check the unwrapped angle instead, the sum of the joint's per-step changes since the reset, readable as s.valve_angle() (rad). Only a clockwise turn counts; turning the wheel back counter-clockwise subtracts. AM-Bench also reports a subtask criterion valve_engaged (joint position >= 0.05 x 17/18 pi = 0.1484 rad); it is informational only. Evaluated after every control step (decimation 1, so after every 1/120 s physics step) on the simulated state; no hold time is required. The episode terminates at the first step where it holds. Otherwise it is truncated by the time limit: episode_length_s = 20 s, i.e. max_episode_length = 2400 control steps; AM-Bench raises the time-out when episode_length_buf >= max_episode_length - 1, i.e. at the 2399th step.
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

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
