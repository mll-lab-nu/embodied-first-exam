# AM-Bench · Open Door — frozen instance i00

You control a simulated **aerial manipulator**: a fully actuated hexarotor (six tilted rotors, so it can hold any attitude
while hovering) carrying a small arm (four joints: three pitch joints and a roll joint) with a two-finger gripper, in
AM-Bench on Isaac Lab / Isaac Sim 5.1 (PhysX), via Python. **Task:** A free-standing door stands ahead of the hovering aerial manipulator: an oak door panel in a metal frame, hinged on its left edge (as seen from the robot), with a metal lever handle near its right edge on the robot-facing side. Open the door: swing the panel on its hinge, away from the robot, by more than 20 degrees from closed.

This is a *fixed scene instance*: the scene and the robot start the same way after every reset, and you may reset and
retry as many times as you want. Your deliverable is **one replayable trajectory** of the robot's low-level actions, not a
general policy.

## Scene
The ground is the world's z = 0 plane; there is no wall, only the free-standing door assembly on the ground ahead of the robot. It consists of an immovable metal frame (two posts 2.0 m tall, 8 cm deep and 4 cm wide, about 1.4 m apart, joined at the top by a crossbar) and an oak panel 1.4 m wide, 2.0 m tall and 4 cm thick whose bottom edge is at ground level. The panel is hinged along the left post (as seen from the robot facing the door) about a vertical axis; it starts closed, in the plane of the frame, and can only swing away from the robot, up to 90 degrees open. It has no spring and no latch: it stays at whatever angle it is left, its motion resisted by hinge damping (which varies between instances) and a little joint friction. On the robot-facing side, near the free (right) edge and a little below mid-height, is a metal lever handle (a horizontal bar about 22 cm long standing about 11 cm proud of the panel) with a small round lock plate above it; the handle and the lock plate are visual only: they have no collision geometry. The door assembly's distance, sideways offset and yaw (turned by up to 15 degrees about the vertical) vary between instances. Nothing moves by itself. The robot starts hovering level and motionless, facing the door, with its arm at its zero joint configuration (end effector a little ahead of and above the airframe) and the gripper closed.

Exactly (privileged information, also readable through the tooling): One environment; its origin is the world origin. Robot at every reset: base_link at (0, 0, 1.0) m with orientation (1, 0, 0, 0) wxyz (body +x is the world +x direction), zero velocity; arm_link1_pitch_joint = arm_link2_pitch_joint = arm_link3_pitch_joint = arm_link4_roll_joint = 0 rad; arm_lfinger_joint = arm_rfinger_joint = 0.001 m (their lower limit: gripper closed, gripper_width 0.002 m). By the robot's URDF kinematics this puts ee_link at about (0.227, 0, 1.124) m with identity orientation and the tool-tip point (ee_link origin + 0.18 m along the ee_link x axis) at about (0.407, 0, 1.124) m; the end-effector command is initialised to the current ee_link pose. Door: articulation door.usd with a fixed root body DoorFrame (at the bottom centre of the frame), self-collisions disabled, solver iterations 4 position / 0 velocity; nominal root (1.0, 0.0, 0.0) m, orientation identity. At each reset (Isaac Lab mdp.reset_root_state_uniform) the root becomes (1.0 + dx, 0.0 + dy, 0.0) with dx, dy ~ U(-0.3, 0.3) m independently and orientation quat_from_euler_xyz(0, 0, yaw) with yaw ~ U(-pi/12, pi/12) rad (about the vertical through the root); AM-Bench's door_pos observation is this root position. In the door's frame (x away from the robot at yaw 0, y to the robot's left, z up): posts (convex-hull boxes) 0.08 (x) x 0.04 (y) x 2.0 (z) m centred at y = +0.7 and y = -0.7, z = 1.0; top bar (box) 0.08 x 1.44 x 0.04 m centred at z = 2.02. Panel (body DoorBody, convex-hull box) 0.04 x 1.4 x 2.0 m, closed it spans x -0.02..0.02, y -0.7..0.7, z 0..2.0; mass 1.0 kg (mass_props). Hinge: revolute joint 'Hinge' (DoorFrame to DoorBody) through (0, 0.7, z) in the door frame, axis the door frame's +z; limits [0, 90] degrees = [0, pi/2] rad; positive rotation (right-handed about +z) swings the free edge (y = -0.7) toward +x, away from the robot; reset to 0 rad (closed) with zero velocity every episode. Isaac Lab implicit actuator (replacing the USD drive): stiffness 0, damping 5.0 N m s/rad scaled at every reset by a factor ~ U(0.5, 2.0) (mdp.randomize_actuator_gains, so damping ~ U(2.5, 10)), joint friction 0.2 (static and dynamic), effort limit 20 N m. Handle (visual meshes without collision, attached to the panel; panel frame, closed): lever bar x -0.137..-0.127, y -0.52..-0.30, z 0.93..0.96, post and back plate (about y -0.58..-0.42, z 0.87..1.03) between it and the panel face; lock disc (visual only) about 6 cm across centred near (-0.023, -0.56, 1.15). No physics material is bound to the door: scene default friction 1.0 / 1.0, restitution 0. Web assets: the panel's Oak.mdl and the frame's and handle's stainless-steel textures (Steel_Stainless base colour, normal and ORM PNGs) are loaded from NVIDIA's Omniverse content server.

## Success (AM-Bench's own check)
Success when the revolute joint Hinge has position > 20 degrees = 0.349066 rad (door_opened_threshold_deg; strict inequality). The joint ranges from 0 rad (closed, its value at every reset) to pi/2 rad; positive is the panel's rotation about the vertical hinge axis that swings its free edge away from the robot. Nothing else is checked (the robot need not pass through the doorway). AM-Bench also reports subtask criteria door_engaged (joint position >= 0.05 x 0.349066 = 0.017453 rad) and door_opened (the success condition); they are informational only. Evaluated after every control step (decimation 1, so after every 1/120 s physics step) on the simulated state; no hold time is required. The episode terminates at the first step where it holds. Otherwise it is truncated by the time limit: episode_length_s = 15 s, i.e. max_episode_length = 1800 control steps; AM-Bench raises the time-out when episode_length_buf >= max_episode_length - 1, i.e. at the 1799th step.
The episode **ends by itself** at the first control step where the check holds (success; rows after it are never
executed), or when the task's episode length of **15 s** runs out (a failure: AM-Bench's time-out ends the episode
at control step 1799). Isaac Lab resets the scene inside the step that ends an episode, so after it `s.state()` and
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
  is your only budget; an episode lasts at most 15 s of simulated time.
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
