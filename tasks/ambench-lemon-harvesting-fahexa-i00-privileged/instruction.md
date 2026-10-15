# AM-Bench · Lemon Harvesting — frozen instance i00

You control a simulated **aerial manipulator**: a fully actuated hexarotor (six tilted rotors, so it can hold any attitude
while hovering) carrying a small arm (four joints: three pitch joints and a roll joint) with a two-finger gripper, in
AM-Bench on Isaac Lab / Isaac Sim 5.1 (PhysX), via Python. **Task:** One lemon and six limes are fixed to the front face of a wall in front of the hovering aerial manipulator, and a grey storage tote sits on a small table against the wall to the robot's left. Harvest the lemon: free it from the wall and get it into the tote. Success needs the lemon's reference point (the base of the fruit) inside the tote's nominal box while the gripper is fully open.

This is a *fixed scene instance*: the scene and the robot start the same way after every reset, and you may reset and
retry as many times as you want. Your deliverable is **one replayable trajectory** of the robot's low-level actions, not a
general policy.

## Scene
The ground is the world's z = 0 plane. In front of the robot stands an immovable (kinematic) wall: a slab 0.1 m thick, 2.0 m wide and 2.0 m tall with a concrete-block surface, its front face turned toward the robot. The wall is the same in every instance. Seven fruits sit on its front face, each with its long axis pointing at the robot: one yellow lemon (about 7.6 x 5 x 5 cm, 50 g) and six green limes (about 7.6 x 6 x 6 cm). The limes are fixed in place and cannot be moved. The lemon is a free rigid body held to the wall by a breakable fixed joint: it stays put until the joint has to carry more than 10 N of force or 10 N m of torque, after which it is loose and falls under gravity. Where the fruits sit varies between instances: anywhere in a band 1 m wide and 0.4 m tall, centred sideways on the wall in its upper half, at least 15 cm apart. To the robot's left, against the wall, stands a small table (white top, about 0.45 x 0.48 m and 0.66 m tall) carrying an open-top grey plastic tote, 40 x 30 x 17 cm; table and tote are immovable and the same in every instance. Nothing moves by itself. The robot starts hovering level and motionless, facing the wall, with its arm at its zero joint configuration (end effector a little ahead of and above the airframe) and the gripper closed.

Exactly (privileged information, also readable through the tooling): One environment; its origin is the world origin. Robot at every reset: base_link at (0, 0, 1.0) m with orientation (1, 0, 0, 0) wxyz (body +x is the world +x direction), zero velocity; arm_link1_pitch_joint = arm_link2_pitch_joint = arm_link3_pitch_joint = arm_link4_roll_joint = 0 rad; arm_lfinger_joint = arm_rfinger_joint = 0.001 m (their lower limit: gripper closed, gripper_width 0.002 m). By the robot's URDF kinematics this puts ee_link at about (0.227, 0, 1.124) m with identity orientation and the tool-tip point (ee_link origin + 0.18 m along the ee_link x axis) at about (0.407, 0, 1.124) m; the end-effector command is initialised to the current ee_link pose. Wall: kinematic cuboid 0.1 (x) x 2.0 (y) x 2.0 (z) m, centre (2.0, 0.0, 1.0) m, orientation identity (front face x = 1.95, normal -x), not randomized; friction 1.0 / 1.0, restitution 0; visual material NVIDIA Concrete_Block.mdl. At each reset AM-Bench's randomize_wall_fruit_attachments puts the lemon's root at (1.92, y, z) with y ~ U(-0.5, 0.5) m, z ~ U(1.1, 1.5) m, then draws each of the six limes from the same distribution, rejecting draws closer than 0.15 m in (y, z) to the lemon or an earlier lime (up to 200 tries, else an error); identity orientations, zero velocity. A fruit's root is its body origin at the bottom of the fruit as authored: the lemon collider spans x +-0.038, y +-0.025, z 0.001..0.052 m about it, a lime x +-0.038, y -0.028..0.033, z 0..0.060, so every fruit occupies x 1.882..1.958, its far end 8 mm inside the wall. Lemon: lemon.usd, whose geometry is a payload (NVIDIA SimReady prop lemon_01, 'RigidBody' variant, convex-decomposition collider, SimReady 'organic' physics material: static friction 5.0, dynamic 0.9, restitution 0.001) referenced from NVIDIA's omniverse-content-staging server; dynamic, gravity on, mass 0.05 kg (mass_props). It hangs on a UsdPhysics fixed joint lemon_wall_fixed_joint (body0 the wall, localPos0 (0, 0, 0); body1 the lemon, localPos1 = the wall centre in the lemon frame, (0.08, -y, 1 - z); break force 10 N, break torque 10 N m), redefined at every reset. Limes: lime.usd, payload SimReady lime01 from the same server, same physics material, kinematic (mass 0.02 kg, no effect). Table: cline.usd, payload SimReady 'cline' table from the same server (white top, grey underside, wood legs, metal feet; convex-decomposition colliders with wood / metal physics materials), kinematic, scale (0.4, 0.2, 0.8), body placed at (1.72, 0.5, 0.0) at each reset: it occupies x 1.497..1.944, y 0.258..0.741, z 0..0.656. Container: container.usd, whose geometry is a payload (NVIDIA warehouse asset Container_B06_40x30x17cm, 'Gray' variant, convex decomposition) from NVIDIA's content server, kinematic, scale (1, 1, 1), root (the tote's bottom centre) at (1.72, 0.5, 0.65) at each reset, identity: the tote spans x 1.52..1.92, y 0.35..0.65, z 0.65..0.82. AM-Bench's lemon_pos and container_pos observations are these roots. Scene default physics material: friction 1.0 / 1.0, restitution 0.

## Success (AM-Bench's own check)
Success at a control step when both hold: (1) the lemon's root position (its body origin, at the bottom of the fruit in the lemon's own frame) is inside, bounds inclusive, the world-axis-aligned box container_root + [(-0.20, -0.15, 0), (0.20, 0.15, 0.17)] m, i.e. the tote's nominal 0.40 x 0.30 x 0.17 m size above its bottom-centre root; (2) the gripper width, arm_lfinger_joint + arm_rfinger_joint (each limited to [0.001, 0.045] m, so 0.002 to 0.09 m in total), is > 0.0898 m (gripper_open_threshold): both fingers essentially at their open limit. The lemon need not be at rest and its orientation is not tested; being inside the box at one step is enough. AM-Bench also reports lemon_grasped_and_detached (latched once lemon and tool tip have moved together >= 0.02 m with the gripper closed below 0.05 m and the lemon within 0.12 m of the tool tip) and lemon_delivered_released (the success itself); they are informational only. Evaluated after every control step (decimation 1, so after every 1/120 s physics step) on the simulated state; no hold time is required. The episode terminates at the first step where it holds. Otherwise it is truncated by the time limit: episode_length_s = 30 s, i.e. max_episode_length = 3600 control steps; AM-Bench raises the time-out when episode_length_buf >= max_episode_length - 1, i.e. at the 3599th step.
The episode **ends by itself** at the first control step where the check holds (success; rows after it are never
executed), or when the task's episode length of **30 s** runs out (a failure: AM-Bench's time-out ends the episode
at control step 3599). Isaac Lab resets the scene inside the step that ends an episode, so after it `s.state()` and
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
  is your only budget; an episode lasts at most 30 s of simulated time.
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
