# Panda Dynamic Scenes · Impact release, interception and passage relay (S04) — frozen instance i00

You control one simulated **Franka Panda** arm (7 joints, its standard hand, and the task's tool where it has one) in a simulated scene (ManiSkill 3 / SAPIEN, rigid-body CPU PhysX at 1000 Hz) via Python.
**Task:** A small block (the cue) slides along a raised deck toward the robot side at the start. Strike it with the paddle so that it hits a spring-held gate latch and swings the gate open, releasing a ball (the payload) that waits behind the gate on an inclined chute; within 1 s of the cue's impact the ball must be past the gate and rolling down the chute. Intercept the ball with the paddle after it has left the chute, send it through a narrow passage between two walls, then touch it again and bring it to rest in a target zone on the table beyond the passage.

This is a *fixed scene instance*: everything starts the same way after every reset, and you may reset and retry as many
times as you want. Your deliverable is **one replayable trajectory** of the robot's low-level actions, not a general
policy. Things move by themselves from the first control step on: the scene does not wait for the robot.

## Scene
One Panda, base at (-0.45, 0, 0), yaw 0 (facing +x). Its hand carries a blue upright paddle: a box 12 mm thick (tool x) x 0.10 m wide (tool y, 2 x `tool_half`, `tool_half` = 0.05 m) x 50 mm tall (tool z), centred at the tool frame origin; its striking faces are normal to the tool x axis. The paddle hangs from a rigid side adapter (part of the tool): from the hand a horizontal bar at tool z = 0.035 runs from tool x = -0.12 to 0 at tool y = -0.13, then along y to y = -0.05, then a short post goes down onto the paddle's top edge at its -y end. The Panda TCP is at (-0.12, -0.13, 0.04) in the tool frame, so with the paddle upright the gripper points straight down, offset to the paddle's -y side. At the start the paddle is upright, rotated 0.35 rad (20.1 deg) about world z (tool x axis along (cos 0.35, sin 0.35, 0)), its centre at (0.236, 0.266, 0.197). The tool's adapter runs between the gripper's fingertips: closing the gripper to less than about 12 mm of aperture makes the fingers touch the adapter, which ends the episode as `self_collision` (the gripper starts fully open, at 0.08 m).

A raised, low-friction blue deck runs along the world x axis on posts, with 4 mm high curbs along its -x end and its +y edge. An orange block, the cue (40 mm x 40 mm, 24 mm tall), slides along the deck toward -x from t = 0. Beside the deck an inclined grey chute (a trough 0.06 m wide with 12 mm side walls) runs downhill toward +x and ends above the table. An orange ball, the payload (radius 18 mm), lies on the chute held back by a gate. The gate is an amber plate on a vertical hinge whose blade lies across the chute (with a small darker block at the blade's tip); the same rigid piece continues past the hinge as a thin trigger tail reaching over the deck at the cue's height. A weak torsion spring holds the gate closed; pushing the tail toward -x or the blade toward +x turns the whole piece open about its hinge. On the table beyond the chute's low end two short orange walls (0.13 m long, 60 mm tall, 0.09 m apart inside) form a straight passage leading away toward -y and +x; the target zone is an unmarked spot on the table beyond the passage exit (see world goals). The table top is the world's z = 0 plane.

Exactly (privileged information, also readable through the tooling): Cue: box half-extents (0.02, 0.02, 0.012) m, mass 0.045 kg, friction 0.01, restitution 0.45. At t = 0 it is at (0.10 + `incoming_speed` x `preview`, 0.15 + dy, 0.1775) = (0.3275, 0.15 + dy, 0.1775) with velocity (-`incoming_speed`, 0, 0) = (-0.35, 0, 0) m/s (unimpeded it would reach x = 0.10 at t = `preview` = 0.65 s); dy ~ U(-0.006, 0.006) m drawn at reset (the only random draw). Deck ('cue_lane', static): slab top at z = 0.165 spanning x -0.33..0.45, y 0.02..0.21, friction 0.01; curbs 4 mm high: one 12 mm wide at the -x end (x -0.33..-0.318), one 6 mm wide along the +y edge (y 0.204..0.21), friction 0.3; two support posts. Chute ('payload_chute', static): floor top surface line from (-0.30, -0.06, 0.205) to (0.05, -0.06, 0.045), length 0.385 m, slope 24.6 deg, downhill unit vector (0.9095, 0, -0.4158), floor half-width 0.03 m, walls 8 mm thick and 0.012 m tall, friction 0.12. Latch: vertical hinge at (-0.185, 0, 0.17); blade 12 mm thick, 0.125 m long from the hinge toward -y, z 0.17..0.215; tip block 32 x 24 x 24 mm at the blade's end; trigger tail 6 mm thick, 0.13 m long from the hinge toward +y, z 0.171..0.195; density 220 kg/m^3, friction 0.2, restitution 0.35; hinge limits +-1.5 rad, joint friction `latch_friction` = 0.012, damping 0.001; torsion spring drive: stiffness `latch_spring` = 0.02 N m/rad, damping 0.001, torque limit 0.08 N m, equilibrium q = 0 (closed); a -x push on the tail or a +x push on the blade turns it toward positive q. Payload ball: radius `radius` = 0.018 m, mass `object_mass` = 0.035 kg, restitution 0.12, friction 0.2, at rest at reset at (-0.233, -0.06, 0.193), on the chute just uphill of the gate. Passage walls: two static boxes 0.02 x 0.13 x 0.06 m, yaw 0.583 rad, centred at (0.2749, -0.2475, 0.03) and (0.3667, -0.1870, 0.03); in passage coordinates (see world goals) they span along 0..0.13 m at across +-0.055 m (inner faces at +-0.045 m). Also announced at reset (fixed, not used by any predicate): `goal_target` = (-0.185, -0.06, 0.17), where the gate crosses the chute centreline. Paddle: `tool_mass` = 0.2 kg, `tool_friction` = 0.3, restitution 0.05. Table friction `table_friction` = 0.015.

The instance's parameters (`s.params()`, SI units): `horizon` = 25, `object_mass` = 0.035, `tool_mass` = 0.2, `tool_half` = 0.05, `radius` = 0.018, `preview` = 0.65, `incoming_speed` = 0.35, `table_friction` = 0.015, `tool_friction` = 0.3, `latch_friction` = 0.012, `latch_spring` = 0.02.

**Goal geometry.** Interception line: ball centre at world x > 0.10 m (payload_interception). Passage coordinates, horizontal: entry point E = (0.285, -0.163), travel direction u = (sin 0.583, -cos 0.583) = (0.5505, -0.8348), lateral direction w = (cos 0.583, sin 0.583) = (0.8348, 0.5505); along = (p_xy - E) . u, across = (p_xy - E) . w; the passage_redirection region is |across| < 0.045 m and along > 0.105 m. Zone centre Z = E + 0.215 u - 0.005 w = (0.3992, -0.3452) at z = 0.018, radius 0.05 m (horizontal), announced as `goal_zone`.

## Success (the task's own check)
The task has 5 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **cue_strike**: the cue touches the paddle.
2. **mechanical_unlatch**: the cue hits the latch (contact of the cue with the gate's moving piece: blade, tip block or tail) during this phase; call the time of the first such contact T. The gate counts as open once, after that impact, its angle about the hinge exceeds 0.45 rad (25.8 deg) in either direction while the ball's centre is more than 0.02 m past the hinge in +x. The phase completes when, after the gate has counted as open and no later than T + 1.0 s, the ball's centre is past the blade's tip at the gate's current angle q, i.e. more than 0.125 sin|q| + radius + 0.006 m (0.125 m is the blade length) beyond the hinge in +x, and the ball's velocity component along the chute's downhill direction is at least 0.4 m/s. If this has not happened by T + 1.0 s the task fails (payload_not_released).
3. **payload_interception**: the ball touches the chute at some point during this phase, and then the paddle touches the ball while the ball's centre is at world x > 0.10 m.
4. **passage_redirection**: the ball's centre is in the far part of the passage corridor: in passage coordinates across is within +-0.045 m and along is greater than 0.105 m, while the ball is not touching the paddle.
5. **payload_braking**: the paddle touches the ball at least once during this phase; afterwards the ball's centre is within 0.05 m (horizontal distance) of the zone centre, the ball moves at less than 0.035 m/s and touches the table, for 0.5 s without interruption. This completes the task.

The episode **ends by itself** at the first control step where the last phase is complete (success; rows after it are
never executed) or where the task has failed. `s.status()` reports the phase you are in and the failure, if any.

**The task fails** (the episode ends, reward 0) as soon as any of these happens:
- at any time, the paddle touches the latch's moving piece (blade, tip block or trigger tail) (`direct_latch_shortcut`);
- during mechanical_unlatch, more than 1.0 s has passed since the cue first hit the latch and the release condition (gate open, ball past the blade tip, at least 0.4 m/s down the chute) has not been met (`payload_not_released`);
- the task's horizon is reached: 25 s of simulated time (`timeout`);
- an object leaves the workspace: its centre falls below z = -0.2 m or gets more than 1.8 m from the world's z axis
  (`out_of_bounds`);
- a forbidden contact or a deep interpenetration (below);
- a safety limit is exceeded (`limit_violation`, below).

**Contacts.** Only the paddle (including its side adapter) may touch anything, and it may touch only the cue and the ball: touching the latch (which also fails the task as direct_latch_shortcut), the deck, the chute, the passage walls or the table is forbidden. No other part of the robot, the fingers included, may touch anything. In every task: the two arms (and their tools) never touch each other
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
The file holds `task` and `actions`, a (T, 8) float array of at most **4,500 rows** (one per control step);
anything else (another shape, NaN, more rows, a file that is not such an npz) scores 0.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_pandadyn import Session
s = Session(instance="/app/instance.json")   # ~5-15 s: builds the scene and resets it to the frozen instance
s.reset()                          # back to the frozen initial state (exact; as often as you like)
s.step(row)                        # one control step (10 ms = 10 physics steps): row = 8 values; True once the episode is over
s.hold_action()                    # a row that commands every arm to stay where it is
s.status()                         # {'success', 'done', 'end_reason', 'phase', 'phase_name', 'phases', 'sim_time_s', 'control_steps', 'events', 'state_sha', ...}
s.state()                          # privileged: every object's pose (xyz + quaternion wxyz) and velocities, fixtures, tool poses, phase, announced goals
s.objects(); s.fixtures(); s.params()                # object poses / velocities, fixture joint positions / velocities, the instance's parameters
s.proprio()                        # per arm: joints q (9) and qd (9), hand TCP and tool poses, motor torques, current target row, aperture
s.snapshot(); s.restore(snap)      # exact save / restore of the whole episode (a restore replays its rows: it takes a moment)
s.actions()                        # (T, 8) rows executed since the last reset: the trajectory of this episode
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
build. The environment's source, the task included, is in `/opt/pandadyn/panda_dynamics` (`tasks/single/impact_release_relay.py`).

The grader replays in two fresh processes; each is exactly this CLI (a fresh process, so run it to self-check):
`python /opt/tools/rcb_pandadyn.py replay --instance /app/instance.json --traj /app/output/trajectory.npz`

## Conventions
- World frame: metres, z up, the table top is the plane z = 0; quaternions are **wxyz**. Each arm's base pose is in the robot spec (`arms`).
- Action row (8 values per control step): `[joint1..7, aperture]`. Each arm's 8 values are its 7 absolute joint-position
  targets (rad, `panda_joint1..7`) and its total gripper aperture target (m, 0 = closed .. 0.08 = open; each finger moves at
  most 0.025 m/s). Values outside the joint limits (`s.robot_spec()`) are clipped to them before they are executed, and the
  trajectory records the clipped row.
- The servo: every control step, each arm's latest target is turned into a smooth reference motion by a jerk-limited
  trajectory generator (Ruckig, the joints synchronised to arrive together) within 65 % (speed), 55 % (acceleration) and 3 % (jerk) of the Panda's joint
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
