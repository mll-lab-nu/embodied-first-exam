# Panda Dynamic Scenes · Cooperative puck course (D03) — frozen instance i00

You control two simulated **Franka Panda** arms (`panda-0` on the left, `panda-1` on the right; each with its standard hand and the task's tool where it has one) in a simulated scene (ManiSkill 3 / SAPIEN, rigid-body CPU PhysX at 1000 Hz) via Python.
**Task:** A low-friction puck is already sliding across the table toward the left arm when the episode starts. The two Pandas each hold a paddle and must hit the same puck in turn: left, right, left, right. After each of the first three hits the puck must pass through a different gap in a row of posts standing across the table between the arms. First it goes toward the right arm through the gap at the -y end. Then it goes back toward the left arm through the gap at the +y end, next to a side rail. Then it goes toward the right arm again through the middle gap. The right arm's final hit must send the puck across a goal line in front of a backstop wall on the right arm's side.

This is a *fixed scene instance*: everything starts the same way after every reset, and you may reset and retry as many
times as you want. Your deliverable is **one replayable trajectory** of the robot's low-level actions, not a general
policy. Things move by themselves from the first control step on: the scene does not wait for the robot.

## Scene
panda-0 (left): base at (-0.55, -0.22, 0), yaw 0 (facing +x). panda-1 (right): base at (0.74, 0.22, 0), yaw pi (facing -x). Each carries a flat rigid paddle, 0.10 m long (2 x `tool_half`, `tool_half` = 0.05 m), 0.05 m tall and 12 mm thick, on a rigid adapter on its back (tool -x) side. The tool frame is the paddle centre, with x normal to its faces, y along its length and z up. The TCP sits 0.12 m behind the paddle centre (tool -x) and 0.04 m above it. Left paddle start: centre (-0.05, -0.18, 0.048), orientation identity (faces normal to world x, length along world y). Right paddle start: centre (0.28, 0.12, 0.048), quaternion (0, 0, 0, 1) (yawed 180 deg). At the start height each paddle's lower edge is 0.023 m above the table. In this task the servo damping on joints 5-7 is raised to (24, 20, 14) from the default (12, 10, 7). Role labels (panda-0 / panda-1) by phase: left_first_pass striker / preparing_receiver; right_return_route preparing_receiver / striker; left_diagonal_pass striker / preparing_receiver; right_terminal_shot cleared_partner / goal_striker.

A small orange square puck (44 mm x 44 mm, 24 mm tall) slides on the table with very little friction, so it slows down only slowly. At t = 0 it is already moving toward the left arm. A row of four short orange posts stands across the table between the two arms; each post is 32 mm x 50 mm and 70 mm tall. The posts leave three gaps, and they are very bouncy. A long rail, 70 mm tall and also very bouncy, runs along the +y side of the course. A short backstop wall, 0.13 m wide and 70 mm tall and not bouncy, stands behind the goal line on the right arm's side. All of these are fixed, and only the puck moves by itself. The table top is the world's z = 0 plane.

Exactly (privileged information, also readable through the tooling): Puck: box 0.044 x 0.044 x 0.024 m, mass `object_mass` = 0.035 kg, friction 0.015, restitution 0.55. At reset it is placed at (0.23, -0.13 + u, 0.0125), with u drawn uniformly in [-0.014, 0.014] m. Its initial velocity is (-`incoming_speed`, 0, 0) = (-0.35, 0, 0) m/s, heading -x through the gap between posts 0 and 1. Table friction `table_friction` = 0.015. Route posts route_post_0..3 are static (friction 0.3, restitution 0.7). Each is 0.032 (x) x 0.050 (y) x 0.070 m, centred at x = 0.12, z = 0.035 and y = -0.22, -0.045, 0.095, 0.26. The resulting gaps are y in [-0.195, -0.07], [-0.02, 0.07] and [0.12, 0.235]. return_rail (static, restitution 0.7): 0.52 x 0.016 x 0.070 m, centred at (0.14, 0.31, 0.035), running along x from -0.12 to 0.40. goal_backstop (static, restitution 0.05): 0.02 x 0.13 x 0.07 m, centred at (0.53, -0.02, 0.035). Paddles: `tool_half` = 0.05, `tool_mass` = 0.2 kg, `tool_friction` = 0.3, restitution 0.05. The table top spans x in [-0.54, 0.70] and y in [-0.48, 0.48]. A puck sliding off it falls below z = -0.2 (generic out_of_bounds). Horizon `horizon` = 25 s. The only random draw is u, made at reset.

The instance's parameters (`s.params()`, SI units): `horizon` = 25, `object_mass` = 0.035, `tool_mass` = 0.2, `tool_half` = 0.05, `radius` = 0.018, `preview` = 0.65, `incoming_speed` = 0.35, `fixture_speed` = 0.04, `restitution` = 0.1, `table_friction` = 0.015, `tool_friction` = 0.3.

**Goal geometry.** The puck's centre must cross three passage lines, given in flag `passages` (not announced in the observation). P0 = (0.12, -0.13), P1 = (0.12, 0.19) and P2 = (0.12, 0.025); each is a crossing of x = 0.12 with |y - y_P| < 0.055 m. The goal line, announced at reset as `goal_goal` = (0.46, -0.02, 0.012), is a crossing of x = 0.46 in +x with |y + 0.02| < 0.05 m.

## Success (the task's own check)
The task has 4 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **left_first_pass**: First, a strike by the left paddle is registered: the first moment in this phase when the puck touches the left paddle while the paddle body moves faster than 0.035 m/s, more than 0.06 s after the previous registered strike. Only that first qualifying contact counts as the strike; later touches are allowed but do not register again. Then, more than 0.035 s after the strike and while the puck is not touching the left paddle, the puck's centre crosses the line x = 0.12 moving in +x, with |y - (-0.13)| < 0.055 m. Moving in +x means x was <= 0.12 on the previous physics step and is > 0.12 now. This line passes through the gap between the first and second posts from the -y side.
2. **right_return_route**: A strike by the right paddle is registered under the same rule: the puck touches the right paddle while that paddle moves faster than 0.035 m/s, more than 0.06 s after the previous registered strike. Then, more than 0.035 s after it and while the puck is not touching the right paddle, the puck's centre crosses x = 0.12 moving in -x, with |y - 0.19| < 0.055 m. This is the gap between the third and fourth posts, next to the side rail.
3. **left_diagonal_pass**: A strike by the left paddle is registered (same rule). Then, more than 0.035 s after it and while the puck is not touching the left paddle, the puck's centre crosses x = 0.12 moving in +x, with |y - 0.025| < 0.055 m. This is the middle gap, between the second and third posts.
4. **right_terminal_shot**: A strike by the right paddle is registered (same rule). Then, more than 0.035 s after it and while the puck is not touching the right paddle, the puck's centre crosses x = 0.46 moving in +x, with |y - (-0.02)| < 0.05 m. This is the goal line in front of the backstop. This completes the task.

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
build. The environment's source, the task included, is in `/opt/pandadyn/panda_dynamics` (`tasks/dual/cooperative_puck_course.py`).

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
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **5 GiB of GPU memory**, **16 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`. GPU memory counts what a process reserves (JAX, for example, reserves most of the card unless told not to). These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. When enforcement is on and GPU memory goes above 1.5 times its limit, the monitor also kills the process holding the most of it at once, to protect the machine; that alone does not fail the trial. CPU is capped at 8 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
