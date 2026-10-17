# Panda Dynamic Scenes · Shared tray transport and discharge (D04) — frozen instance i00

You control two simulated **Franka Panda** arms (`panda-0` on the left, `panda-1` on the right; each with its standard hand and the task's tool where it has one) in a simulated scene (ManiSkill 3 / SAPIEN, rigid-body CPU PhysX at 1000 Hz) via Python.
**Task:** The two Pandas hold one tray between them. Each arm's small open fork cradles a tab on one end of the tray, and an orange ball lies loose in the tray. Working together, the arms must first hold the tray steadily. They then carry it through two waypoints that make a turn. When the environment pushes the ball, they must bring it back to rest near the tray centre. Next they bring the tray to an exit position beside a fixed basin, and finally they tip the ball out so that it settles in the basin. Both forks must support the tray during the transport phases, the ball must not leave the tray before the discharge, and the tray must never drop low.

This is a *fixed scene instance*: everything starts the same way after every reset, and you may reset and retry as many
times as you want. Your deliverable is **one replayable trajectory** of the robot's low-level actions, not a general
policy. Things move by themselves from the first control step on: the scene does not wait for the robot.

## Scene
panda-0 (left): base at (-0.55, -0.22, 0), yaw 0 (facing +x). panda-1 (right): base at (0.74, 0.22, 0), yaw pi (facing -x). Each carries a support fork: a small, shallow square cradle 0.07 m x 0.07 m inside (2 x `tool_half`, `tool_half` = 0.035 m). It has a 5 mm floor and 18 mm high walls on three sides, is open on the tool +x side, and is held by an adapter on its closed tool -x wall. The tool frame is the centre of the cradle floor's top surface, z up. The TCP sits 0.12 m along tool -x and 0.04 m above the tool frame. Left fork start: (-0.075, 0, 0.22), orientation identity (open side toward world +x). Right fork start: (0.215, 0, 0.22), quaternion (0, 0, 0, 1) (yawed 180 deg, open side toward world -x). The two open sides face each other. In this task both arms' servos plan their reference motion with lower acceleration and jerk fractions than usual (0.30 and 0.025, default 0.55 and 0.05). Role labels in every phase: panda-0 left_support, panda-1 right_support.

A blue rigid tray, 0.20 m x 0.24 m inside, has a 9 mm rim and a 5 mm floor. A flat tab (48 mm x 60 mm, 8 mm thick) sticks out at floor level from the middle of each of its two longer sides. At the start each tab rests in one arm's fork, so the tray hangs between the two arms. An orange ball (radius 18 mm) lies loose near the middle of the tray. A fixed blue open-top basin, 0.21 m x 0.20 m inside and 0.08 m deep, stands on posts above the table. Nothing moves by itself, except that the environment gives the ball a brief push along world +x the moment the third phase begins. The table top is the world's z = 0 plane.

Exactly (privileged information, also readable through the tooling): Tray: free rigid body, mass 0.25 kg, friction 0.3, restitution 0.05. Its frame origin is the centre of its floor's top surface. Inner half-size is 0.10 (x) x 0.12 (y) m, the rim is 9 mm high, and the walls and floor are 5 mm thick. The tabs are 0.048 x 0.060 x 0.008 m, centred at tray-frame (+-0.125, 0, 0), so they span |x| from 0.101 to 0.149 m. At reset the tray is at (0.07, 0, 0.225), identity orientation, at rest. The tab undersides are then 1 mm above the fork floors; the left tab spans world x in [-0.079, -0.031] and the right tab x in [0.171, 0.219]. Ball: radius `radius` = 0.018 m, mass `object_mass` = 0.035 kg, restitution 0.05, friction 0.2. At reset it is at rest at (0.07 + u, 0, 0.244), 1 mm above the tray floor, with u drawn uniformly in [-0.006, 0.006] m. Push: for the first 0.03 s after phase disturbance_recovery begins, a constant force of `disturbance_impulse` / 0.03 = 0.233 N acts along world +x at the ball's centre. The total impulse is `disturbance_impulse` = 0.007 N s. Basin: static container with floor top surface centre at (0.30, 0.18, 0.08); inner half-size 0.105 (x) x 0.10 (y) m; wall height 0.08 m (rim at z = 0.16); friction 0.4; restitution 0.03. Forks: `tool_half` = 0.035, `tool_mass` = 0.12 kg, `tool_friction` = 0.3, restitution 0.05. Horizon `horizon` = 25 s. The only random draw is u, made at reset.

The instance's parameters (`s.params()`, SI units): `horizon` = 25, `object_mass` = 0.035, `tool_mass` = 0.12, `tool_half` = 0.035, `radius` = 0.018, `preview` = 0.65, `incoming_speed` = 0.35, `fixture_speed` = 0.04, `restitution` = 0.1, `table_friction` = 0.08, `tool_friction` = 0.3, `disturbance_impulse` = 0.007.

**Goal geometry.** Tray waypoints A = (0.12, -0.04, 0.27) and B = (0.02, 0.08, 0.27) apply to the tray's frame origin and are announced at reset as `goal_waypoints`. The exit point (0.12, 0.18) applies in the horizontal plane and is not announced. The tray's frame origin must always stay at or above z = 0.17 m.

## Success (the task's own check)
The task has 5 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **shared_support**: For 0.35 s without interruption, two things hold. The tray is supported by both forks: it has been in contact with the left fork within the last 0.04 s and with the right fork within the last 0.04 s. And the ball is inside the tray, as defined under ball_spill.
2. **transport_turn**: With the tray supported by both forks (as above), the tray's frame origin (the centre of its floor's top surface) comes within 0.025 m of waypoint A = (0.12, -0.04, 0.27). Later, again with both forks supporting it, the origin comes within 0.025 m of waypoint B = (0.02, 0.08, 0.27). The waypoints must be reached in this order.
3. **disturbance_recovery**: When this phase begins, the environment pushes the ball along world +x for 0.03 s with a fixed impulse (`disturbance_impulse`). The phase completes when all of the following hold for 0.4 s without interruption. Both forks support the tray. The push has been fully applied (at least 95% of `disturbance_impulse`). The ball's centre is within 0.045 m of the tray centre in the tray's x-y plane. The ball moves at less than 0.07 m/s relative to the tray, including the tray's rotation.
4. **exit_alignment**: With both forks supporting the tray, the tray's frame origin is within 0.04 m of (0.12, 0.18), measured horizontally (x and y only).
5. **natural_discharge**: The ball is contained in the basin and does not touch the tray, for 0.7 s without interruption. Contained in the basin means all of the following, in the basin's frame (origin at the centre of its floor's top surface, axes = world axes). |x| and |y| of the ball centre are below 0.0919 m (0.10 - 0.45 x radius; the same bound is used on both axes). Its height above the basin floor is between 0.014 m and 0.0778 m. It has been in contact with the basin within the last 25 ms. Its speed is below 0.09 m/s. Neither fork has to support the tray in this phase, but the tray must still stay above z = 0.17 m. This completes the task.

The episode **ends by itself** at the first control step where the last phase is complete (success; rows after it are
never executed) or where the task has failed. `s.status()` reports the phase you are in and the failure, if any.

**The task fails** (the episode ends, reward 0) as soon as any of these happens:
- before natural_discharge (in phases shared_support to exit_alignment), the ball leaves the tray region. In the tray's frame that is |x| >= 0.11 m, |y| >= 0.16 m, or a centre at or more than 0.01 m below the tray floor's top surface (`ball_spill`);
- at any time, in every phase including the discharge, the tray's frame origin falls below z = 0.17 m (`shared_support_drop`);
- the task's horizon is reached: 25 s of simulated time (`timeout`);
- an object leaves the workspace: its centre falls below z = -0.2 m or gets more than 1.8 m from the world's z axis
  (`out_of_bounds`);
- a forbidden contact or a deep interpenetration (below);
- a safety limit is exceeded (`limit_violation`, below).

**Contacts.** The forks may touch the tray and the ball, which are free objects, and nothing else: not the basin or its posts, not the table, not the robot pedestals. No other robot part, the fingers included, may touch anything. The two arms and their forks must never touch each other, and a fork must not touch its own arm. The tray and the ball may touch the basin. In every task: the two arms (and their tools) never touch each other
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
build. The environment's source, the task included, is in `/opt/pandadyn/panda_dynamics` (`tasks/dual/shared_tray_transport_discharge.py`).

The grader replays in two fresh processes; each is exactly this CLI (a fresh process, so run it to self-check):
`python /opt/tools/rcb_pandadyn.py replay --instance /app/instance.json --traj /app/output/trajectory.npz`

## Conventions
- World frame: metres, z up, the table top is the plane z = 0; quaternions are **wxyz**. Each arm's base pose is in the robot spec (`arms`).
- Action row (16 values per control step): `[panda-0 joint1..7, panda-0 aperture, panda-1 joint1..7, panda-1 aperture]`. Each arm's 8 values are its 7 absolute joint-position
  targets (rad, `panda_joint1..7`) and its total gripper aperture target (m, 0 = closed .. 0.08 = open; each finger moves at
  most 0.025 m/s). Values outside the joint limits (`s.robot_spec()`) are clipped to them before they are executed, and the
  trajectory records the clipped row.
- The servo: every control step, each arm's latest target is turned into a smooth reference motion by a jerk-limited
  trajectory generator (Ruckig, the joints synchronised to arrive together) within 65 % (speed), 30 % (acceleration) and 2 % (jerk) of the Panda's joint
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
