# AM-Bench · Push Slider — frozen instance i00

You control a simulated **aerial manipulator**: a fully actuated hexarotor (six tilted rotors, so it can hold any attitude
while hovering) carrying a small arm (four joints: three pitch joints and a roll joint) with a two-finger gripper, in
AM-Bench on Isaac Lab / Isaac Sim 5.1 (PhysX), via Python. **Task:** A wall stands in front of the hovering aerial manipulator, with a horizontal slider mounted on its front face: a straight rail about 1 m long and a red knob that slides along it. The knob starts at the rail's left end (as seen from the robot facing the wall) and must be pushed along the rail until it is within 5 cm of the right end of its travel, i.e. at least 0.95 m along its 1 m travel.

This is a *fixed scene instance*: the scene and the robot start the same way after every reset, and you may reset and
retry as many times as you want. Your deliverable is **one replayable trajectory** of the robot's low-level actions, not a
general policy.

## Scene
The ground is the world's z = 0 plane. In front of the robot stands an immovable (kinematic) wall: a slab 0.1 m thick, 2.0 m wide and 2.0 m tall with a concrete-block surface, its front face turned toward the robot. The wall is upright (no tilt in this task); its distance and sideways offset vary between instances. On its front face a slider fixture is mounted horizontally: a fixed rail 1.02 m long and 6 cm tall (a shallow channel standing about 3 cm out from the wall) and a red knob (a 4 x 4 x 6 cm block on a short stem, protruding about 7 cm from the wall surface) that slides along the rail over 1 m of travel. The fixture's height and sideways position on the wall vary between instances. The knob has no spring (it stays where it is left) but its motion is resisted by joint friction and damping. Nothing moves by itself. The robot starts hovering level and motionless, facing the wall, with its arm at its zero joint configuration (end effector a little ahead of and above the airframe) and the gripper closed.

Exactly (privileged information, also readable through the tooling): One environment; its origin is the world origin. Robot at every reset: base_link at (0, 0, 1.0) m with orientation (1, 0, 0, 0) wxyz (body +x is the world +x direction), zero velocity; arm_link1_pitch_joint = arm_link2_pitch_joint = arm_link3_pitch_joint = arm_link4_roll_joint = 0 rad; arm_lfinger_joint = arm_rfinger_joint = 0.001 m (their lower limit: gripper closed, gripper_width 0.002 m). By the robot's URDF kinematics this puts ee_link at about (0.227, 0, 1.124) m with identity orientation and the tool-tip point (ee_link origin + 0.18 m along the ee_link x axis) at about (0.407, 0, 1.124) m; the end-effector command is initialised to the current ee_link pose. Wall: kinematic cuboid 0.1 (x) x 2.0 (y) x 2.0 (z) m, nominal centre (2.0, 0.0, 1.0) m and orientation identity (front face the plane x = centre_x - 0.05, normal -x, toward the robot); friction 1.0 static / 1.0 dynamic, restitution 0; visual material NVIDIA Concrete_Block.mdl. At each reset (Isaac Lab mdp.reset_root_state_uniform) the centre becomes (2.0 + dx, 0.0 + dy, 1.0) with dx, dy ~ U(-0.2, 0.2) m independently; the configured pitch range is (-0, 0), so the wall keeps the identity orientation (upright, front normal -x). Slider: articulation slider_with_rail.usd with a fixed root body 'Rail' and self-collisions disabled. At each reset, after the wall, its root is placed at wall_centre + R_wall (-0.05, sy, sz) with sy, sz ~ U(-0.3, 0.3) m independently (on the wall's front face) and given the orientation R_wall composed with a 180 degree rotation about z, so the rail's local +x points toward the robot (world -x) and its local +y is world -y. Rail (rail frame, scaled 1.02 along y): base box 0.02 (x) x 1.02 (y) x 0.06 (z) m centred on the wall surface (half of it inside the wall), upper and lower edges 0.02 x 1.02 x 0.01 m at x = 0.02, z = +-0.025, edge covers 0.01 x 1.02 x 0.02 m at x = 0.025, z = +-0.018; mass 1 kg; no visual material bound. Knob (body 'Slider', gravity disabled, mass not authored so PhysX derives it from the collision shapes, colour (1, 0, 0)): a base plate 0.005 x 0.02 x 0.03 m at x = 0.017, a short connector cylinder, and a handle box 0.04 (x) x 0.04 (y) x 0.06 (z) m centred 0.052 m in front of the rail plane. Prismatic joint SliderJoint along the rail's local +y (world -y), limits [-0.5, 0.5] m, reset to -0.5 m with zero velocity every episode (knob at world y = root_y + 0.5, the robot's left end); positive motion moves the knob toward world -y. Isaac Lab implicit actuator (overriding the USD drive): stiffness 0, damping 5.0, joint friction 4.0 (static and dynamic), effort limit 1000, velocity limit 2.0 m/s. Scene default physics material: friction 1.0 / 1.0, restitution 0.

## Success (AM-Bench's own check)
Success when the slider's prismatic joint SliderJoint has position >= 0.45 m (slider_pushed_threshold; the joint ranges from -0.5 m to 0.5 m and starts at -0.5 m), i.e. the knob has travelled at least 0.95 m from its start toward world -y (the robot's right). AM-Bench also reports a subtask criterion slider_engaged (joint position - start >= 0.05 x (0.45 - (-0.5)) = 0.0475 m); it is informational only. Evaluated after every control step (decimation 1, so after every 1/120 s physics step) on the simulated state; no hold time is required. The episode terminates at the first step where it holds. Otherwise it is truncated by the time limit: episode_length_s = 26 s, i.e. max_episode_length = 3120 control steps; AM-Bench raises the time-out when episode_length_buf >= max_episode_length - 1, i.e. at the 3119th step.
The episode **ends by itself** at the first control step where the check holds (success; rows after it are never
executed), or when the task's episode length of **26 s** runs out (a failure: AM-Bench's time-out ends the episode
at control step 3119). Isaac Lab resets the scene inside the step that ends an episode, so after it `s.state()`,
`s.objects()` and the cameras show the start again; `s.status()` keeps the outcome and the end state's hash.

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below). It is replayed
open-loop from the same initial state in two fresh processes and scored 1 if the task succeeds in both replays and both
end in the same state, else 0. Also leave the script that produced it at `/app/output/gen.py`. Save a working trajectory
as soon as you have one and overwrite it as you improve it: whatever is in `/app/output/` when the time is up is graded.
The file holds `task` and `actions`, a (T, 8) float array of at most **8,000 rows** (one per control step); anything else
(another shape, NaN, more rows, a file that is not such an npz) scores 0.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_ambench import Session
s = Session(instance="/app/instance.json")   # ~2-6 min: launches Isaac Sim, builds the scene, resets to the frozen instance
                                   # (no cameras, as the grader; Session(..., cameras=True) to look: see below)
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
s.start_video("/app/output/try.mp4"); ...; s.stop_video()   # cameras=True only: film the steps in between (both cameras side by side)
s.env                              # the Isaac Lab environment itself (AM-Bench's source is in /opt/ambench: read-only reference)
```
The tooling is deliberately thin: the environment's own action, its state and its cameras. Reaching, pressing, pushing,
turning and throwing are yours to build. Isaac Sim runs once per process, and only the first episode of a process is
guaranteed to be bit-identical to a fresh process's: after changes, check your trajectory with the grader's CLI.
**Cameras.** The robot's two onboard cameras exist only in a `Session(..., cameras=True)` (decided once per process). With
them, Isaac renders every step and that makes PhysX's results depend on timing: two runs of the same rows can part after a
few hundred steps. The grader replays without cameras, where a fresh process reproduces a trajectory bit for bit, so use
the cameras to look and check every trajectory with the CLI below.

The grader replays in two fresh processes; each is exactly this CLI (a fresh process, so run it to self-check):
`python /opt/tools/rcb_ambench.py replay --instance /app/instance.json --traj /app/output/trajectory.npz`
(`... film --instance ... --traj ... --video out.mp4` films the rows with the cameras on: an illustration, not a verdict).

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
  is your only budget; an episode lasts at most 26 s of simulated time.
- One `Session` per process (Isaac Sim launches once, then the scene builds: ~2-6 min, the upper end on a busy host).
  Physics is PhysX on the **GPU** (about 10-15 control steps per second of wall time). One Isaac process takes up to
  ~13 GiB of memory and ~6.5 GiB of GPU memory: run at most two at once. Do not call `s.close()` before writing every
  output.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **16 GiB of GPU memory**, **28 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`. GPU memory counts what a process reserves (JAX, for example, reserves most of the card unless told not to). These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. When enforcement is on and GPU memory goes above 1.5 times its limit, the monitor also kills the process holding the most of it at once, to protect the machine; that alone does not fail the trial. CPU is capped at 8 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
