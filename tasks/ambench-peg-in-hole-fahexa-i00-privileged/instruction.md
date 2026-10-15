# AM-Bench · Peg In Hole — frozen instance i00

You control a simulated **aerial manipulator**: a fully actuated hexarotor (six tilted rotors, so it can hold any attitude
while hovering) carrying a small arm (four joints: three pitch joints and a roll joint) with a two-finger gripper, in
AM-Bench on Isaac Lab / Isaac Sim 5.1 (PhysX), via Python. **Task:** The hovering aerial manipulator starts holding a metal peg (a cylinder 15 cm long and 4 cm in diameter) in its gripper, pointing straight ahead. A wall stands ahead with a blue square socket mounted on its front face: a square frame whose square opening faces the robot and is closed at the back by a red plate. Insert the peg: the centre of the peg's front end (the end pointing ahead at the start) must be inside the square opening and more than 2 cm deep into it (the opening is 3 cm deep up to the red plate).

This is a *fixed scene instance*: the scene and the robot start the same way after every reset, and you may reset and
retry as many times as you want. Your deliverable is **one replayable trajectory** of the robot's low-level actions, not a
general policy.

## Scene
The ground is the world's z = 0 plane. In front of the robot stands an immovable (kinematic) wall: a slab 0.1 m thick, 2.0 m wide and 2.0 m tall with a concrete-block surface, its front face turned toward the robot. Its distance, its sideways offset and its tilt (the top leaning toward or away from the robot by up to 30 degrees) vary between instances. On the wall's front face sits an immovable socket: a blue plastic square frame 4 cm thick, mounted flat on the wall, around a square opening perpendicular to the wall face; a red plate (1 cm thick, flush with the wall) closes the opening 3 cm behind the frame's front face. Nominally the frame's outer side is 10 cm and the opening 6 cm; both are scaled by one factor between 0.75 and 1.5 (opening 4.5 to 9 cm square), the depth unchanged. Where the socket sits on the central part of the wall varies between instances. The iron-coloured peg is a free rigid body (it falls if let go); at every reset it is placed between the gripper's fingers, centred at the gripper's tool point with its axis along the tool's forward axis, and the gripper is commanded closed, so the robot starts holding it. Nothing else moves by itself. The robot starts hovering level and motionless, facing the wall, with its arm at its zero joint configuration (end effector a little ahead of and above the airframe) and the gripper closed on the peg.

Exactly (privileged information, also readable through the tooling): One environment; its origin is the world origin. Robot at every reset: base_link at (0, 0, 1.0) m with orientation (1, 0, 0, 0) wxyz (body +x is the world +x direction), zero velocity; arm_link1_pitch_joint = arm_link2_pitch_joint = arm_link3_pitch_joint = arm_link4_roll_joint = 0 rad; arm_lfinger_joint = arm_rfinger_joint = 0.001 m (their lower limit: gripper closed, gripper_width 0.002 m). By the robot's URDF kinematics this puts ee_link at about (0.227, 0, 1.124) m with identity orientation and the tool-tip point (ee_link origin + 0.18 m along the ee_link x axis) at about (0.407, 0, 1.124) m; the end-effector command is initialised to the current ee_link pose. Wall: kinematic cuboid 0.1 (x) x 2.0 (y) x 2.0 (z) m, nominal centre (2.0, 0.0, 1.0) m and orientation identity (front face the plane x = centre_x - 0.05, normal -x, toward the robot); friction 1.0 static / 1.0 dynamic, restitution 0; visual material NVIDIA Concrete_Block.mdl (loaded from NVIDIA's Omniverse content server). At each reset (Isaac Lab mdp.reset_root_state_uniform) the centre becomes (2.0 + dx, 0.0 + dy, 1.0) with dx, dy ~ U(-0.2, 0.2) m independently, and the orientation becomes quat_from_euler_xyz(0, pitch, 0) with pitch ~ U(-pi/6, pi/6) rad (a rotation about the world y axis through the wall centre; positive pitch tilts the top of the wall away from the robot, the front normal turning upward). Socket: kinematic rigid body hole.usd (gravity disabled). At each reset, after the wall, its root is placed at wall_centre + R_wall (-0.07, hy, hz) with hy, hz ~ U(-0.3, 0.3) m independently and given the wall's orientation, so its local +x is the wall normal pointing into the wall and the root (the socket's centre) is 0.02 m in front of the wall surface; AM-Bench's goal_pos observation is this root position. Local geometry before scaling: four boxes 0.04 m deep (x from -0.02 to 0.02) forming a square frame of outer side 0.10 m around the opening |y|, |z| < 0.03 m; a red box GoalRegion 0.01 x 0.06 x 0.06 m with collision at x from 0.01 to 0.02 closing the opening; frame material Polycarbonate_Opaque.mdl 'Polycarbonate_Blue' (from NVIDIA's Omniverse content server); physics material static friction 0.8, dynamic 0.6, restitution 0. Scale (1, s, s) (local y and z only) with s ~ U(0.75, 1.5), drawn once when the environment is created (a prestartup event), not at each reset. Peg: rigid body peg.usd, cylinder along its local x, length 0.15 m, radius 0.02 m, root at its centre, mass 0.01 kg, gravity on, physics material static friction 2.0, dynamic 1.5, restitution 0, visual material Iron.mdl (from NVIDIA's Omniverse content server). At each reset, after the robot, the peg is placed at the tool-tip point (ee_link origin + R(ee_link) (0.18, 0, 0)) with the ee_link orientation and zero velocity: centre at about (0.407, 0, 1.124) m, axis along world x, tip (+0.075 m along its local x) at about (0.482, 0, 1.124) m. The gripper target is set to closed (-1, the finger joints' lower limit 0.001 m); the FA-Hexa defines no object-width converter, so the finger joints are not preset to the peg's 0.04 m diameter. Scene default physics material: friction 1.0 / 1.0, restitution 0.

## Success (AM-Bench's own check)
Success at a control step when the peg tip p = peg root position + R(peg) (0.075, 0, 0) (the centre of the end face that points ahead at reset), expressed in the socket's frame as q = R(socket)^T (p - socket root position), satisfies q.x > 0 (peg_insertion_depth_min = 0: past the socket's mid-plane, i.e. more than 0.02 m behind its front face; the red plate's surface is at q.x = 0.01), |q.y| < 0.03 s and |q.z| < 0.03 s (half the scaled opening side 0.06 s); all inequalities strict. Only this point is tested: the peg's orientation, whether it is still held and contacts are not checked. AM-Bench reports no subtask criteria for this task. Evaluated after every control step (decimation 1, so after every 1/120 s physics step) on the simulated state; no hold time is required. The episode terminates at the first step where it holds. Otherwise it is truncated by the time limit: episode_length_s = 20 s, i.e. max_episode_length = 2400 control steps; AM-Bench raises the time-out when episode_length_buf >= max_episode_length - 1, i.e. at the 2399th step.
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
