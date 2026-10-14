# Panda Dynamic Scenes · Pendulum energy relay (D08) — frozen instance i00

You control two simulated **Franka Panda** arms (`panda-0` on the left, `panda-1` on the right; each with its standard hand and the task's tool where it has one) in a simulated scene (ManiSkill 3 / SAPIEN, rigid-body CPU PhysX at 1000 Hz) via Python.
**Task:** A passive pendulum (a rod with a ball-shaped bob) hangs between the two arms, each of which holds a flat paddle. The left arm must actively push the pendulum so that it swings out toward the right arm. The right arm must meet it and brake it, then actively drive it back so that it swings out toward the left arm, no longer touching it. The left arm must then touch it again, and the pendulum must end up hanging almost straight down and almost still, and stay that way for one second.

This is a *fixed scene instance*: everything starts the same way after every reset, and you may reset and retry as many
times as you want. Your deliverable is **one replayable trajectory** of the robot's low-level actions, not a general
policy. Things move by themselves from the first control step on: the scene does not wait for the robot.

## Scene
Two Pandas facing each other along x. panda-0 (left): base at (-0.55, -0.22, 0), yaw 0 (facing +x). panda-1 (right): base at (0.74, 0.22, 0), yaw pi (facing -x). Each hand carries the same rigid 'fork' paddle: one flat vertical blade, 12 mm thick, 0.14 m wide (2 x `tool_half`, 0.07 at this instance) and 50 mm tall. A grey adapter (a horizontal bar from the hand and a short post) ends about 5 cm behind the blade on the hand side; blade and adapter form one rigid tool link. The tool frame is the centre of the blade: x is the blade normal (pointing away from the arm's own base), y runs along the blade's width, z is up. With the tool level the hand points straight down and the blade centre is 0.12 m ahead of the gripper TCP along tool x and 0.04 m below it. Start: left tool frame at (-0.04, -0.02, 0.21), axes aligned with the world (blade normal +x); right tool frame at (0.28, 0.02, 0.21), rotated 180 deg about z (blade normal -x, facing the left arm). Both arms use a slower motion profile than the default: the joint trajectory generator is limited to 20 % of the Panda's acceleration limits and 1 % of its jerk limits (default 55 % and 5 %), and wrist joints 5-7 use higher damping gains (24, 20, 14 instead of 12, 10, 7). Role labels per phase (left, right): left_excitation: exciter, preparing_brake; right_braking: cleared_exciter, brake; right_return_impulse: preparing_receiver, return_driver; left_recovery: brake, cleared_driver; low_energy_hold: damping_support, cleared_partner.

A passive pendulum hangs between the two arms from a grey stand: a blue rod (18 mm square cross-section, 0.22 m from the hinge to the bob centre) ending in an orange ball-shaped bob (radius 26 mm). Its hinge axis is horizontal and parallel to world y, so it swings in the vertical x-z plane, toward one arm or the other. The hinge has no motor, no friction and no damping, so once set swinging the pendulum keeps swinging until something takes the energy out. The stand (a horizontal bearing arm reaching to the hinge and an upright post down to the table, plus a small blue block just under the hinge) lies on the +y side of the swing plane, leaving the swing plane open. At t = 0 the pendulum hangs almost straight down and almost at rest. There is nothing else in the scene. The table top is the world's z = 0 plane.

Exactly (privileged information, also readable through the tooling): Pendulum: articulation with a fixed base; hinge (pivot) at (0.12, 0, 0.43), revolute axis world +y, joint limits [-1.45, 1.45] rad, no friction, damping or drive. Rod length `length` = 0.22 m, bob radius 0.026 m (friction 0.5, restitution 0.05); the swinging link's total mass (rod + bob) is `object_mass` = 0.075 kg. Sign convention: with hinge angle q the bob centre is at pivot + (-`length` sin q, 0, -`length` cos q), so q < 0 swings the bob toward +x (the right arm) and q > 0 toward -x (the left arm); at q = 0 the bob centre is at (0.12, 0, 0.21) (this is the announced `goal_target`). At reset two values are drawn from the instance's random stream, in this order: q0 ~ U(-`initial_angle_range`, +`initial_angle_range`) = U(-0.015, 0.015) rad and q0_dot ~ U(-`initial_angular_speed_range`, +`initial_angular_speed_range`) = 0 rad/s at nominal; nothing else is random and nothing is drawn later. Stand: grey upright post (24 mm square) at (0.12, 0.16) from z = 0.43 down to the table, a horizontal bearing arm (24 mm square) at z = 0.43 from the post to the pivot, and a 40 x 40 x 30 mm block centred 35 mm below the pivot. Thresholds: `minimum_excursion` = 0.18 rad, `return_excursion` = 0.12 rad. Paddles: mass `tool_mass` = 0.2 kg each, friction `tool_friction` = 0.3, restitution 0.05. Horizon `horizon` = 25 s.

The instance's parameters (`s.params()`, SI units): `horizon` = 25, `object_mass` = 0.075, `tool_mass` = 0.2, `tool_half` = 0.07, `restitution` = 0.1, `table_friction` = 0.08, `tool_friction` = 0.3, `length` = 0.22, `initial_angle_range` = 0.015, `initial_angular_speed_range` = 0, `minimum_excursion` = 0.18, `return_excursion` = 0.12.

**Goal geometry.** `goal_target`, the bob centre's hanging-rest point, is announced at reset in the state. It does not depend on the seed, but it gives away the pendulum's location: privileged mode only. The predicates use only the hinge angle and the angular speed, not this point. The seeded initial angle is not announced.

## Success (the task's own check)
The task has 5 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **left_excitation**: the left paddle (any part of panda-0's tool link) touches the pendulum while that tool's centre-of-mass speed is above 0.03 m/s (an active push, recorded once); after that, the pendulum swings out toward the right arm beyond `minimum_excursion` = 0.18 rad (about 10.3 deg) from straight down, i.e. hinge angle q < -0.18 rad, bob displaced toward +x. The paddle may or may not still be touching the pendulum at that moment.
2. **right_braking**: the right paddle (any part of panda-1's tool link) touches the pendulum at a moment when the pendulum's angular speed about its hinge is below 0.45 rad/s.
3. **right_return_impulse**: the right paddle touches the pendulum while that tool's centre-of-mass speed is above 0.03 m/s (an active push, recorded once in this phase); after that, at a moment when the right paddle is not touching the pendulum, the pendulum is beyond `return_excursion` = 0.12 rad (about 6.9 deg) toward the left arm (q > 0.12 rad, bob displaced toward -x) and is still swinging further toward the left arm at more than 0.25 rad/s (dq/dt > +0.25 rad/s).
4. **left_recovery**: the left paddle touches the pendulum (any contact).
5. **low_energy_hold**: the pendulum is within 0.055 rad (about 3.2 deg) of hanging straight down (|q| < 0.055 rad) and its angular speed is below 0.12 rad/s, for 1.0 s without interruption. Paddle contact with the pendulum is allowed during the hold. This completes the task.

The episode **ends by itself** at the first control step where the last phase is complete (success; rows after it are
never executed) or where the task has failed. `s.status()` reports the phase you are in and the failure, if any.

**The task fails** (the episode ends, reward 0) as soon as any of these happens:
- the task's own failure conditions: none (only the rules below apply);
- the task's horizon is reached: 25 s of simulated time (`timeout`);
- an object leaves the workspace: its centre falls below z = -0.2 m or gets more than 1.8 m from the world's z axis
  (`out_of_bounds`);
- a forbidden contact or a deep interpenetration (below);
- a safety limit is exceeded (`limit_violation`, below).

**Contacts.** Each paddle (blade and adapter, one rigid tool link) may touch only the swinging part of the pendulum (rod and bob). Neither paddle may touch the pendulum's stand (bearing arm, post, block under the hinge), the table or anything else. No other part of either robot, the fingers included, may touch anything. The two arms and their paddles may never touch each other, and no arm may touch itself. In every task: the two arms (and their tools) never touch each other
(`arm_arm_or_tool_collision`), an arm never touches itself (`self_collision`), no robot part touches the table or the floor
(`forbidden_collision`, `tool_table_collision`), a robot link other than an allowed one touches no object or fixture
(`forbidden_arm_object_contact`, `forbidden_arm_scene_contact`, `forbidden_arm_fixture_contact`), a tool touches only the
task's objects and the fixtures the task allows (`forbidden_tool_fixture_contact`), and no contact penetrates deeper than
4 mm (`excessive_penetration`).

**Safety limits** (the Franka Panda's own limits, checked every 1 ms on each arm; `s.robot_spec()["safety_limits"]`):
measured joint positions within the joint limits (+0.002 rad); measured joint speeds at most 1.01 x (2.175, 2.175, 2.175,
2.175, 2.61, 2.61, 2.61) rad/s; finger speeds at most 0.051 m/s; the hand's TCP at most 1.01 x 1.7 m/s and 1.01 x
2.5 rad/s; joint accelerations (measured over every 20 ms window) at most 1.05 x (15, 7.5, 10, 12.5, 15, 20, 20) rad/s²
and jerks at most 1.05 x (7500, 3750, 5000, 6250, 7500, 10000, 10000) rad/s³; the TCP's acceleration (20 ms windows) at
most 1.05 x 13 m/s² and 1.05 x 25 rad/s²; motor torques at most (87, 87, 87, 87, 12, 12, 12) N m, changing at most
1000 N m/s. The servo's own reference motion is checked against the same speed, acceleration and jerk limits. A contact
(a catch, a strike) moves the arm too: what is measured counts, whatever was commanded.

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below). It is replayed
open-loop from the same initial state in two fresh processes and scored 1 if the task succeeds in both replays and both
end in the same state, else 0. Also leave the script that produced it at `/app/output/gen.py`. Save a working trajectory
as soon as you have one and overwrite it as you improve it: whatever is in `/app/output/` when the time is up is graded.
The file holds `task` and `actions`, a (T, 16) float array of at most **4,500 rows** (one per control step);
anything else (another shape, NaN, more rows, a file that is not such an npz) scores 0.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_pandadyn import Session
s = Session(instance="/app/instance.json")   # ~5-15 s: builds the scene and resets it to the frozen instance
s.reset()                          # back to the frozen initial state (exact; as often as you like)
s.step(row)                        # one control step (10 ms = 10 physics steps): row = 16 values; True once the episode is over
s.hold_action()                    # a row that commands every arm to stay where it is
s.status()                         # {'success', 'done', 'end_reason', 'phase', 'phase_name', 'phases', 'sim_time_s', 'control_steps', 'events', 'state_sha', ...}
s.state()                          # privileged: every object's pose (xyz + quaternion wxyz) and velocities, fixtures, tool poses, phase, announced goals
s.objects(); s.fixtures(); s.params()                # object poses / velocities, fixture joint positions / velocities, the instance's parameters
s.proprio()                        # per arm: joints q (9) and qd (9), hand TCP and tool poses, motor torques, current target row, aperture
s.snapshot(); s.restore(snap)      # exact save / restore of the whole episode (a restore replays its rows: it takes a moment)
s.actions()                        # (T, 16) rows executed since the last reset: the trajectory of this episode
s.replay(actions)                  # reset, run the rows open-loop until the episode ends, return status (+ executed_rows)
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.fk(q7, "panda-0"); s.ik(pose7, "panda-0", frame="tool")   # stateless kinematics: hand TCP / tool world poses <-> 7 joint angles
s.robot_spec()                     # arm bases, tools and mounts, joint limits, servo limits and gains, safety limits
s.render_frame("overview")         # RGB uint8 (480, 640, 3) of "overview" (the whole workspace) or "closeup" (the working area)
s.camera_info()                    # per camera: intrinsic_cv, extrinsic_cv (world -> camera, OpenCV axes), cam2world_gl
s.render_video(actions, "/app/output/check.mp4")   # replays from the frozen state while filming the overview camera
s.u                                # the ManiSkill environment itself (`panda_dynamics` in /opt/pandadyn: read-only reference)
```
The tooling is deliberately thin: joint targets, kinematics and state. Catching, striking, carrying and timing are yours to
build. The environment's source, the task included, is in `/opt/pandadyn/panda_dynamics` (`tasks/dual/pendulum_energy_relay.py`).

The grader replays in two fresh processes; each is exactly this CLI (a fresh process, so run it to self-check):
`python /opt/tools/rcb_pandadyn.py replay --instance /app/instance.json --traj /app/output/trajectory.npz`

## Conventions
- World frame: metres, z up, the table top is the plane z = 0; quaternions are **wxyz**. Each arm's base pose is in the robot spec (`arms`).
- Action row (16 values per control step): `[panda-0 joint1..7, panda-0 aperture, panda-1 joint1..7, panda-1 aperture]`. Each arm's 8 values are its 7 absolute joint-position
  targets (rad, `panda_joint1..7`) and its total gripper aperture target (m, 0 = closed .. 0.08 = open; each finger moves at
  most 0.025 m/s). Values outside the joint limits (`s.robot_spec()`) are clipped to them before they are executed, and the
  trajectory records the clipped row.
- The servo: every control step, each arm's latest target is turned into a smooth reference motion by a jerk-limited
  trajectory generator (Ruckig, the joints synchronised to arrive together) within 65 % (speed), 20 % (acceleration) and 1 % (jerk) of the Panda's joint
  speed, acceleration and jerk limits, and the arm tracks that reference with torque control (PD + inverse dynamics, the
  Panda's torque and torque-rate limits). A new target replans from the current reference motion, so a target far away is
  reached smoothly, not in one step. `s.robot_spec()["servo"]` has the exact limits and gains.
- Control runs at 100 Hz (10 ms per row), physics at 1000 Hz. There is no step budget: the time limit (`## Time limit`) is
  your only budget. A simulated episode ends at the latest at the task's horizon (25 s, 2500 rows).
- One `Session` per process. Stepping runs at roughly 40-150 control steps per second; rendering happens only when a frame
  is asked for and never moves anything. Do not call `s.close()` before writing every output.

## External material
You may install packages you need (pip, apt). Please solve the task yourself: do not look up or download a solution to it, such as this benchmark's own source code, published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **5 GiB of GPU memory**, **16 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`. GPU memory counts what a process reserves (JAX, for example, reserves most of the card unless told not to). These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. When enforcement is on and GPU memory goes above 1.5 times its limit, the monitor also kills the process holding the most of it at once, to protect the machine; that alone does not fail the trial. CPU is capped at 8 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
