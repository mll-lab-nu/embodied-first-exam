# AM-Bench · Press Button — frozen instance i00

You control a simulated **aerial manipulator**: a fully actuated hexarotor (six tilted rotors, so it can hold any attitude
while hovering) carrying a small arm (four joints: three pitch joints and a roll joint) with a two-finger gripper, in
AM-Bench on Isaac Lab / Isaac Sim 5.1 (PhysX), via Python. **Task:** A wall stands in front of the hovering aerial manipulator, and a push button is mounted flat on the wall's front face, facing the robot: a red circular plunger in a dark-grey circular housing. Press the button, i.e. push its spring-loaded plunger into the housing, along the wall's normal, until it is depressed by at least 4 mm (40 % of its 10 mm travel).

This is a *fixed scene instance*: the scene and the robot start the same way after every reset, and you may reset and
retry as many times as you want. Your deliverable is **one replayable trajectory** of the robot's low-level actions, not a
general policy.

## Scene
The ground is the world's z = 0 plane. In front of the robot stands an immovable (kinematic) wall: a slab 0.1 m thick, 2.0 m wide and 2.0 m tall with a concrete-block surface, its front face turned toward the robot. Its distance, its sideways offset and a small tilt (the top leaning toward or away from the robot) vary between instances. On the wall's front face sits a push button: a dark-grey circular housing, 12 mm thick, fixed flush to the wall, and in front of it a red circular plunger, 10 mm thick, whose face stands about 2 cm proud of the wall surface. The plunger is the only moving part: it slides along the wall's normal into the housing (10 mm of travel) and is spring-loaded, returning to its rest position when not pushed. Where the button sits on the central part of the wall varies between instances, and so does its face size (plunger diameter between 6 and 12 cm, housing proportionally 1.2 times wider). Nothing moves by itself. The robot starts hovering level and motionless, facing the wall, with its arm at its zero joint configuration (end effector a little ahead of and above the airframe) and the gripper closed.

Exactly (privileged information, also readable through the tooling): One environment; its origin is the world origin. Robot at every reset: base_link at (0, 0, 1.0) m with orientation (1, 0, 0, 0) wxyz (body +x is the world +x direction), zero velocity; arm_link1_pitch_joint = arm_link2_pitch_joint = arm_link3_pitch_joint = arm_link4_roll_joint = 0 rad; arm_lfinger_joint = arm_rfinger_joint = 0.001 m (their lower limit: gripper closed, gripper_width 0.002 m). By the robot's URDF kinematics this puts ee_link at about (0.227, 0, 1.124) m with identity orientation and the tool-tip point (ee_link origin + 0.18 m along the ee_link x axis) at about (0.407, 0, 1.124) m; the end-effector command is initialised to the current ee_link pose. Wall: kinematic cuboid 0.1 (x) x 2.0 (y) x 2.0 (z) m, nominal centre (2.0, 0.0, 1.0) m and orientation identity (front face the plane x = centre_x - 0.05, normal -x, toward the robot); friction 1.0 static / 1.0 dynamic, restitution 0; visual material NVIDIA Concrete_Block.mdl. At each reset (Isaac Lab mdp.reset_root_state_uniform) the centre becomes (2.0 + dx, 0.0 + dy, 1.0) with dx, dy ~ U(-0.2, 0.2) m independently, and the orientation becomes quat_from_euler_xyz(0, pitch, 0) with pitch ~ U(-0.2, 0.2) rad (a rotation about the world y axis through the wall centre; positive pitch tilts the top of the wall away from the robot, the front normal turning upward). Button: articulation push_button.usd with a fixed root (housing) and self-collisions disabled. At each reset, after the wall, its root is placed at wall_centre + R_wall (-0.05, by, bz) with by, bz ~ U(-0.3, 0.3) m independently (a point on the wall's front face, offset in the wall's own y-z plane) and given the wall's orientation, so the button's local +x is the wall normal pointing into the wall. Housing: cylinder along local x, radius 0.072 s, thickness 0.012 m (local x from -0.012 to 0), mass 0.5 kg, colour (0.1, 0.1, 0.1). Plunger (body 'plunger'; AM-Bench's goal_pos observation is its position): cylinder radius 0.06 s, thickness 0.01 m, authored at local x = -0.015 (its face about 2 cm in front of the wall surface), mass 0.02 kg, colour (0.9, 0.1, 0.1). Button physics material: static friction 0.6, dynamic 0.5, restitution 0.1. Prismatic joint PlungerSlideJoint along the button's local +x (positive = plunger pushed toward the wall), limits [0, 0.01] m, reset to 0 m with zero velocity every episode; Isaac Lab implicit actuator with stiffness 1000 N/m and damping 80 N s/m toward the target 0 m, effort limit 20 N, velocity limit 5 m/s. Scale s (applied to the button's local y and z only: face radius changes, thickness does not) ~ U(0.5, 1.0), drawn once when the environment is created (a prestartup event), not at each reset. Scene default physics material: friction 1.0 / 1.0, restitution 0.

## Success (AM-Bench's own check)
Success when the button's prismatic joint PlungerSlideJoint has position >= 0.004 m (button_pressed_threshold; the joint ranges from 0 m, unpressed, to 0.01 m, fully pressed; positive = plunger pushed into the housing toward the wall). Evaluated after every control step (decimation 1, so after every 1/120 s physics step) on the simulated state; no hold time is required. The episode terminates at the first step where it holds. Otherwise it is truncated by the time limit: episode_length_s = 20 s, i.e. max_episode_length = 2400 control steps; AM-Bench raises the time-out when episode_length_buf >= max_episode_length - 1, i.e. at the 2399th step.
The episode **ends by itself** at the first control step where the check holds (success; rows after it are never
executed), or when the task's episode length of **20 s** runs out (a failure: AM-Bench's time-out ends the episode
at control step 2399). Isaac Lab resets the scene inside the step that ends an episode, so after it `s.state()`,
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
  is your only budget; an episode lasts at most 20 s of simulated time.
- One `Session` per process (Isaac Sim launches once, then the scene builds: ~2-6 min, the upper end on a busy host).
  Physics is PhysX on the **GPU** (about 10-15 control steps per second of wall time). One Isaac process takes up to
  ~13 GiB of memory and ~6.5 GiB of GPU memory: run at most two at once. Do not call `s.close()` before writing every
  output.

## External material
You may install packages you need (pip, apt). Please solve the task yourself: do not look up or download a solution to it, such as this benchmark's own source code, published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **16 GiB of GPU memory**, **28 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`. GPU memory counts what a process reserves (JAX, for example, reserves most of the card unless told not to). These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. When enforcement is on and GPU memory goes above 1.5 times its limit, the monitor also kills the process holding the most of it at once, to protect the machine; that alone does not fail the trial. CPU is capped at 8 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
