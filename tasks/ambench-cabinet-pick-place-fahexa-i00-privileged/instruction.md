# AM-Bench · Cabinet Pick and Place — frozen instance i00

You control a simulated **aerial manipulator**: a fully actuated hexarotor (six tilted rotors, so it can hold any attitude
while hovering) carrying a small arm (four joints: three pitch joints and a roll joint) with a two-finger gripper, in
AM-Bench on Isaac Lab / Isaac Sim 5.1 (PhysX), via Python. **Task:** A tall wooden cabinet stands ahead of the hovering aerial manipulator, and a small soda can stands inside one of its shelf compartments, behind a closed sliding door. Get the can onto the top of the cabinet: AM-Bench counts success when the can's centre is less than 5 cm above a fixed height just below the cabinet's top surface (there is no horizontal condition) while the can moves slower than 0.1 m/s.

This is a *fixed scene instance*: the scene and the robot start the same way after every reset, and you may reset and
retry as many times as you want. Your deliverable is **one replayable trajectory** of the robot's low-level actions, not a
general policy.

## Scene
The ground is the world's z = 0 plane; there is no wall. Ahead of the robot stands an immovable cabinet with light-wood panels and metal handles, about 1.2 m wide, 0.6 m deep and 1.68 m tall, its front facing the robot and its top a flat board. From the bottom up: a solid base; a drawer with a horizontal bar handle; a compartment closed by two hinged doors with vertical handles, which are locked; the can's compartment, about 27 cm tall, whose right half (as seen from the robot) is closed by a fixed panel and whose left half is closed by a sliding door with a vertical bar handle; and a top compartment closed by a front panel with a horizontal bar handle. The sliding door slides sideways to the robot's right, in front of the fixed panel, over 0.6 m of travel; it has no spring (it stays where it is left) and its motion is resisted by damping and friction. The bottom drawer and the top front panel are not jointed: they are loose parts held in place only by gravity and contact. The can (4 cm in diameter, 6.4 cm tall, 5 g, with a soda label) stands upright on the floor of the sliding-door compartment, a little in from the front and hidden behind the closed sliding door; its exact spot varies by a few centimetres between instances, and nothing else varies. Nothing moves by itself. The robot starts hovering level and motionless, facing the cabinet, with its arm at its zero joint configuration (end effector a little ahead of and above the airframe) and the gripper closed.

Exactly (privileged information, also readable through the tooling): One environment; its origin is the world origin. Robot at every reset: base_link at (0, 0, 1.0) m with orientation (1, 0, 0, 0) wxyz (body +x is the world +x direction), zero velocity; arm_link1_pitch_joint = arm_link2_pitch_joint = arm_link3_pitch_joint = arm_link4_roll_joint = 0 rad; arm_lfinger_joint = arm_rfinger_joint = 0.001 m (their lower limit: gripper closed, gripper_width 0.002 m). By the robot's URDF kinematics this puts ee_link at about (0.227, 0, 1.124) m with identity orientation and the tool-tip point (ee_link origin + 0.18 m along the ee_link x axis) at about (0.407, 0, 1.124) m; the end-effector command is initialised to the current ee_link pose. Cabinet: cabinet.usd (a MuJoCo-converted asset; panel texture light-wood.png and handle texture metal.png, both local), asset origin at (1.5, 0, 0) m, unrotated. Isaac Lab drives the sub-articulation rooted at pulling_cabinet/pulling_cabinet (fixed to the world; AM-Bench's pulling_door_pos observation is this root, at (2.4, 0, 1.08)); every other part keeps its USD physics. World-frame collision geometry: kinematic carcass of base block x 2.10..2.70, |y| <= 0.60, z 0..0.50, side panels at |y| 0.58..0.60 and back panel x 2.70..2.72, both up to z 1.68; bottom drawer box x 2.10..2.70, |y| <= 0.58, z 0.51..0.79, handle bar reaching x 2.00 (its slide joint has physics:jointEnabled = 0, so it is an unjointed body); middle compartment floor z 0.80..0.82 and two hinged doors (front x 2.10..2.12, handles reaching x 2.00) with hinge limits [0, 0]; the can's compartment: floor z 1.09..1.11, back x 2.68..2.70, ceiling z 1.38, fixed front panel x 2.10..2.12, y -0.57..-0.01, z 1.11..1.37; sliding door (body pulling_door) x 2.07..2.09, y 0.01..0.57, z 1.11..1.37 when closed, its handle a vertical bar x 1.97..1.99, y 0.48..0.50, z 1.14..1.32 on two horizontal standoffs; top compartment floor z 1.38..1.40, front panel x 2.10..2.12, |y| <= 0.58, z 1.405..1.655 (hinge also disabled), handle bar x 2.00..2.02, |y| <= 0.20, z 1.44..1.46; top board z 1.66..1.68 over x 2.12..2.70, |y| <= 0.58, so the top surface is z = 1.68 m. Joint pull_door_slide: prismatic along world +y, limits [-0.6, 0] m, closed at 0 and reset to 0 with zero velocity every episode, so opening moves the door toward world -y (at -0.6 it spans y -0.59..-0.03); Isaac Lab implicit actuator stiffness 0, damping 10, friction 2.0 static and dynamic, effort limit 50. Cabinet masses are not authored (density 0: PhysX derives them from the collision shapes). Can: rigid body can.usd (local, soda.png label), convex-hull collider 0.04 m in diameter and 0.064 m tall, body origin at its centre, mass 0.005 kg, gravity on, no physics material bound. At each reset (mdp.reset_root_state_uniform) its root is set to (2.26 + dx, 0.30 + dy, 1.17) m with dx ~ U(-0.02, 0.02), dy ~ U(-0.05, 0.05) m, identity orientation, zero velocity (AM-Bench's can_pos observation): upright, centre 0.14 to 0.18 m behind the front plane, bottom 2.8 cm above the compartment floor, onto which it drops at the start. Neither the cabinet nor the can is loaded from the web. Scene default physics material: friction 1.0 / 1.0, restitution 0.

## Success (AM-Bench's own check)
Success at a control step when both hold: (1) the can's root position (its body origin, the can's centre) satisfies 0 <= z - 1.67 < 0.05 m (drawer_top_z = 1.67 m above the environment origin, which is the world origin; i.e. 1.67 <= z < 1.72 m); (2) the norm of the can's linear velocity is < 0.1 m/s (can_place_velocity_threshold). Nothing else is tested: no horizontal (x, y) condition, no orientation, the can need not be released, and the door's position does not matter. AM-Bench also reports subtask criteria pulling_door_opened (|pull_door_slide - 0| >= 0.2 m), can_lifted (can z > its z at reset + 0.05 m) and can_placed_on_drawer (the success itself); they are informational only. Evaluated after every control step (decimation 1, so after every 1/120 s physics step) on the simulated state; no hold time is required. The episode terminates at the first step where it holds. Otherwise it is truncated by the time limit: episode_length_s = 60 s, i.e. max_episode_length = 7200 control steps; AM-Bench raises the time-out when episode_length_buf >= max_episode_length - 1, i.e. at the 7199th step.
The episode **ends by itself** at the first control step where the check holds (success; rows after it are never
executed), or when the task's episode length of **60 s** runs out (a failure: AM-Bench's time-out ends the episode
at control step 7199). Isaac Lab resets the scene inside the step that ends an episode, so after it `s.state()` and
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
  is your only budget; an episode lasts at most 60 s of simulated time.
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
