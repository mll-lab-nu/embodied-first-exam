# Panda Dynamic Scenes · Moving bank relay (D06) — frozen instance i00

You control two simulated **Franka Panda** arms (`panda-0` on the left, `panda-1` on the right; each with its standard hand and the task's tool where it has one) in a simulated scene (ManiSkill 3 / SAPIEN, rigid-body CPU PhysX at 1000 Hz) via Python.
**Task:** A low-friction puck is already sliding toward the right arm at the start, through the first of two gaps in a row of posts across the table. The right Panda's paddle must strike it. The puck must then come back through that same gap and hit the left Panda's paddle, which acts as a rebound board. The right paddle strikes the puck a second time. The puck must then come back through the second gap and hit the left board again, with the board at a clearly different position and angle from the first rebound. Finally the puck must cross a goal line in front of a backstop wall on the right arm's side, without the right paddle touching it as it crosses.

This is a *fixed scene instance*: everything starts the same way after every reset, and you may reset and retry as many
times as you want. Your deliverable is **one replayable trajectory** of the robot's low-level actions, not a general
policy. Things move by themselves from the first control step on: the scene does not wait for the robot.

## Scene
panda-0 (left): base at (-0.55, -0.22, 0), yaw 0 (facing +x). panda-1 (right): base at (0.74, 0.22, 0), yaw pi (facing -x). Each carries a flat rigid paddle, 0.10 m long (2 x `tool_half`, `tool_half` = 0.05 m for both arms), 0.05 m tall and 12 mm thick, on a rigid adapter on its back (tool -x) side. The tool frame is the paddle centre, with x normal to its faces, y along its length and z up. The TCP sits 0.12 m behind the paddle centre (tool -x) and 0.04 m above it. Left paddle (the rebound board) start: centre (-0.015, 0.08, 0.045), orientation identity (faces normal to world x, length along world y). Right paddle start: centre (0.27, -0.11, 0.045), quaternion (0, 0, 0, 1) (yawed 180 deg). At the start height each paddle's lower edge is 0.020 m above the table. Role labels (panda-0 / panda-1) by phase: right_first_strike preparing_board / striker; left_first_rebound rebound_operator / preparing_receiver; right_recovery_strike changing_board / striker; left_changed_rebound rebound_operator / cleared_striker; terminal_goal board_support / cleared_striker.

A small orange square puck (44 mm x 44 mm, 24 mm tall) slides on the table with very little friction. At t = 0 it is already moving toward the right arm. Four short orange posts (24 mm x 50 mm, 60 mm tall) stand in a row across the table between the arms. The middle two overlap into a single block, so the row leaves two equal gaps, and the puck starts in line with the first gap. The posts are not bouncy. A long, very bouncy rail (70 mm tall) runs along the +y side of the course. A short backstop wall (0.14 m wide, 70 mm tall, not bouncy) stands behind the goal line on the right arm's side. All of these are fixed, and only the puck moves by itself. The table top is the world's z = 0 plane.

Exactly (privileged information, also readable through the tooling): Puck: box 0.044 x 0.044 x 0.024 m, mass `object_mass` = 0.035 kg, friction 0.012, restitution 0.65. At reset it is placed at (0.12, u, 0.0125), with u drawn uniformly in [-0.03, 0.01] m. Its initial velocity is (+`incoming_speed`, 0, 0) = (0.35, 0, 0) m/s, heading +x through gap 0. Table friction `table_friction` = 0.015. Route posts route_0_-1, route_0_1, route_1_-1 and route_1_1 are static (friction 0.3, restitution 0.05). Each is 0.024 (x) x 0.050 (y) x 0.060 m, centred at x = 0.16 and z = 0.03. Gap 0 is formed by the posts at y = -0.085 and 0.065: y in [-0.06, 0.04], centre -0.01. Gap 1 is formed by the posts at y = 0.085 and 0.235: y in [0.11, 0.21], centre 0.16. The posts at 0.065 and 0.085 overlap. return_rail (static, restitution 0.7): 0.48 x 0.016 x 0.070 m, centred at (0.15, 0.29, 0.035), running along x from -0.09 to 0.39. backstop (static, restitution 0.05): 0.02 x 0.14 x 0.07 m, centred at (0.48, 0.16, 0.035). Paddles: `tool_half` = 0.05, `tool_mass` = 0.2 kg, `tool_friction` = 0.3, restitution 0.05. The left arm's setup lists 0.075 m and 0.22 kg, but these are overridden by `tool_half` and `tool_mass`. The table top spans x in [-0.54, 0.70] and y in [-0.48, 0.48]. A puck sliding off it falls below z = -0.2 (generic out_of_bounds). Horizon `horizon` = 25 s. The only random draw is u, made at reset.

The instance's parameters (`s.params()`, SI units): `horizon` = 25, `object_mass` = 0.035, `tool_mass` = 0.2, `tool_half` = 0.05, `radius` = 0.018, `preview` = 0.65, `incoming_speed` = 0.35, `fixture_speed` = 0.04, `restitution` = 0.1, `table_friction` = 0.015, `tool_friction` = 0.3.

**Goal geometry.** Crossing lines for the puck's centre. Gap 0 line: x = 0.16 with |y + 0.01| < 0.048 m, crossed in -x. Gap 1 line: x = 0.16 with |y - 0.16| < 0.048 m, crossed in -x. Goal line: x = 0.42 with |y - 0.16| < 0.055 m, crossed in +x; it is announced at reset as `goal_goal` = (0.42, 0.16, 0.012).

## Success (the task's own check)
The task has 5 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **right_first_strike**: The puck touches the right paddle. Any contact counts; there is no speed condition.
2. **left_first_rebound**: During this phase the puck's centre crosses the line x = 0.16 moving in -x, with |y - (-0.01)| < 0.048 m, i.e. back through gap 0. Moving in -x means x was >= 0.16 on the previous physics step and is < 0.16 now. After that crossing, the puck touches the left paddle. The left paddle's tool-frame pose (position and orientation) at that contact is recorded.
3. **right_recovery_strike**: The puck touches the right paddle more than 0.06 s after this phase began.
4. **left_changed_rebound**: During this phase the puck's centre crosses x = 0.16 moving in -x, with |y - 0.16| < 0.048 m, i.e. through gap 1. After that crossing, the puck touches the left paddle while two pose conditions hold. The paddle's tool-frame origin is more than 0.035 m from the recorded first-rebound position. And its orientation is rotated by more than 0.24 rad (about 13.8 deg) from the recorded orientation, i.e. |q . q_first| < cos 0.12. Contacts that do not meet the pose condition do not count, but they do not fail the task either.
5. **terminal_goal**: The puck's centre crosses x = 0.42 moving in +x, with |y - 0.16| < 0.055 m, while the puck is not touching the right paddle. This completes the task.

The episode **ends by itself** at the first control step where the last phase is complete (success; rows after it are
never executed) or where the task has failed. `s.status()` reports the phase you are in and the failure, if any.

**The task fails** (the episode ends, reward 0) as soon as any of these happens:
- the task's own failure conditions: none (only the rules below apply);
- the task's horizon is reached: 25 s of simulated time (`timeout`);
- an object leaves the workspace: its centre falls below z = -0.2 m or gets more than 1.8 m from the world's z axis
  (`out_of_bounds`);
- a forbidden contact or a deep interpenetration (below);
- a safety limit is exceeded (`limit_violation`, below).

**Contacts.** Each paddle may touch only the puck. The paddles must not touch the posts, the rail, the backstop, the table or the robot pedestals. No other robot part, the fingers included, may touch anything. The two arms and their paddles must never touch each other, and a paddle must not touch its own arm. In every task: the two arms (and their tools) never touch each other
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
build. The environment's source, the task included, is in `/opt/pandadyn/panda_dynamics` (`tasks/dual/moving_bank_relay.py`).

The grader replays in two fresh processes; each is exactly this CLI (a fresh process, so run it to self-check):
`python /opt/tools/rcb_pandadyn.py replay --instance /app/instance.json --traj /app/output/trajectory.npz`

## Conventions
- World frame: metres, z up, the table top is the plane z = 0; quaternions are **wxyz**. Each arm's base pose is in the robot spec (`arms`).
- Action row (16 values per control step): `[panda-0 joint1..7, panda-0 aperture, panda-1 joint1..7, panda-1 aperture]`. Each arm's 8 values are its 7 absolute joint-position
  targets (rad, `panda_joint1..7`) and its total gripper aperture target (m, 0 = closed .. 0.08 = open; each finger moves at
  most 0.025 m/s). Values outside the joint limits (`s.robot_spec()`) are clipped to them before they are executed, and the
  trajectory records the clipped row.
- The servo: every control step, each arm's latest target is turned into a smooth reference motion by a jerk-limited
  trajectory generator (Ruckig, the joints synchronised to arrive together) within 65 % (speed), 55 % (acceleration) and 5 % (jerk) of the Panda's joint
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
