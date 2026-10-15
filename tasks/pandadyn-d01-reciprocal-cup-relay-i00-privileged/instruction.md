# Panda Dynamic Scenes · Reciprocal two-cup air relay (D01) — frozen instance i00

You control two simulated **Franka Panda** arms (`panda-0` on the left, `panda-1` on the right; each with its standard hand and the task's tool where it has one) in a simulated scene (ManiSkill 3 / SAPIEN, rigid-body CPU PhysX at 1000 Hz) via Python.
**Task:** A ball is thrown high into the air when the episode starts and comes down near the left Panda. The left arm catches it in its cup and throws it through the air to the right arm, whose cup must have moved from its start to catch it. The right arm carries the ball to a second transfer region and throws it back. The left arm catches it again and delivers it into an open box that slides back and forth along a rail, where the ball must settle while the box is moving.

This is a *fixed scene instance*: everything starts the same way after every reset, and you may reset and retry as many
times as you want. Your deliverable is **one replayable trajectory** of the robot's low-level actions, not a general
policy. Things move by themselves from the first control step on: the scene does not wait for the robot.

## Scene
Two Pandas. panda-0 (left): base at (-0.55, -0.22, 0), yaw 0 (facing +x). panda-1 (right): base at (0.74, 0.22, 0), yaw pi (facing -x). Each hand carries a closed square cup: 0.12 m x 0.12 m inside (2 x `tool_half`), walls 28 mm high (`tool_height`) and 5 mm thick, floor 5 mm thick. The tool frame is the centre of the floor's top surface, z up out of the cup. A fixed adapter bar joins the cup's -x wall (tool frame) to the hand; in the tool frame the hand's TCP is at (-0.12, 0, +0.04). At the start the left cup is level with identity orientation, centre at (0.02, -0.18, 0.22). The right cup is level and turned 180 deg about z (orientation wxyz (0, 0, 0, 1), so its adapter side faces +x, towards its own base), centre at (0.19, 0.18, 0.22). Role labels by phase (panda-0, panda-1): left_initial_catch (catcher, preparing_receiver); left_to_right_flight (donor, moving_receiver); right_catch (clearing_donor, catcher); second_region (preparing_receiver, loaded_carrier); right_to_left_flight (moving_receiver, donor); left_catch_and_deliver (catcher_deliverer, cleared_partner).

A small orange ball (radius 18 mm) is thrown upwards and towards the left arm at t = 0. It rises high and falls back down near the left cup within about the first second. A blue open box (the cart: 0.15 m x 0.15 m inside, 0.06 m deep) is the moving link of a straight rail along the world's y axis, on the left arm's side. It is driven back and forth the whole episode, slowly, and slowest where it turns around. There are no other objects. The table top is the world's z = 0 plane.

Exactly (privileged information, also readable through the tooling): Ball: radius `radius` (0.018 m), mass `object_mass` (0.035 kg), restitution `restitution` (0.1), friction 0.2. At t = 0 it is at (0.03 + `incoming_speed` x `preview`, y0, 0.39) = (0.2575, y0, 0.39) with velocity (-`incoming_speed`, 0, (0.22 + 0.028 + `radius` - 0.39 + 4.905 x `preview`^2) / `preview`) = (-0.35, 0, about 2.998) m/s. It peaks at about z = 0.85 m (t of about 0.31 s) and passes through (0.03, y0, 0.248 + `radius`) = (0.03, y0, 0.266) at t = `preview` (0.65 s). y0 ~ U(-0.11, -0.07) is drawn at reset (first draw). Cart: moving link of a prismatic fixture whose rail origin is (-0.10, -0.29, 0.05), axis +y, limits +-0.5 m. It is an open box (inner half 0.075, walls 0.06 m) whose floor's top surface is the link origin (z = 0.05), mass 0.3 kg. At reset it is placed at q0 ~ U(-0.02, 0.02) (second draw) with velocity `fixture_speed`. It is then driven (PD, kp 80, kd 8, at most 8 N) to the target q0 + 0.20 sin((`fixture_speed`/0.20) t), with target velocity `fixture_speed` cos((`fixture_speed`/0.20) t). That is an oscillation of 0.20 m amplitude with peak speed `fixture_speed` (0.04 m/s) and period 31.4 s. It reverses at t = 7.85 s and t = 23.6 s, and its speed exceeds 0.02 m/s only for t < 5.2 s and 10.5 s < t < 20.9 s within the 25 s horizon (confirmed in an idle run). Cups: `tool_half` 0.06, `tool_height` 0.028, `tool_mass` 0.2 kg, `tool_friction` 0.3, restitution 0.05. Table friction `table_friction` (0.08). The right cup's start position (0.19, 0.18, 0.22) is stored as `right_start` and used by right_catch.

The instance's parameters (`s.params()`, SI units): `horizon` = 25, `object_mass` = 0.035, `tool_mass` = 0.2, `tool_half` = 0.06, `radius` = 0.018, `preview` = 0.65, `incoming_speed` = 0.35, `fixture_speed` = 0.04, `restitution` = 0.1, `table_friction` = 0.08, `tool_friction` = 0.3, `tool_height` = 0.028.

**Goal geometry.** Second transfer region: the point (0.13, 0.15, 0.24) for panda-1's tool frame, radius 0.035 m. Flight heights: ball centre above z = 0.30 m (left to right) and z = 0.31 m (right to left). Right-cup relocation: more than 0.04 m from its start (0.19, 0.18, 0.22) at the right catch. `goal_target` = (0.03, y0, 0.22), the point under the ball's first crossing point, is announced at reset. It reveals the ball's seeded y0, so it is privileged mode only. Further flags (`transfer_a`, `transfer_b`, `left_start`, `right_start`) are stored but not exported as goal_* observations; transfer_a and transfer_b are not used by any predicate.

## Success (the task's own check)
The task has 6 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **left_initial_catch**: panda-0's cup catches the ball. First the ball flies free (touching nothing) for at least 25 ms. It then enters the cup from above: its centre crosses downwards through the plane `tool_height` + `radius` = 0.046 m above the cup floor (cup frame) while within `tool_half` - `radius` = 0.042 m of the cup centre in both x and y of the cup frame. After that entry the ball stays in the cup for 0.18 s without interruption. In the cup frame: |x| and |y| < `tool_half` - 0.45 x `radius` = 0.0519 m; centre between `radius` - 4 mm = 0.014 m and `tool_height` - 0.12 x `radius` = 0.02584 m above the floor; touched by that cup within the last 25 ms; speed relative to the cup < 0.09 m/s.
2. **left_to_right_flight**: The ball has touched nothing for more than 0.045 s (counted within this phase) and its centre is above z = 0.30 m.
3. **right_catch**: panda-1's cup catches the ball by the same test as left_initial_catch (a fresh entry from above after at least 25 ms of free flight, then retention for 0.18 s without interruption). At a step where this catch holds, the right cup's tool frame is more than 0.04 m (3-D distance) from its start position (0.19, 0.18, 0.22).
4. **second_region**: panda-1's tool frame is within 0.035 m of (0.13, 0.15, 0.24) while the ball is retained in the right cup. Retention uses the same test as above but needs no hold time.
5. **right_to_left_flight**: The ball has touched nothing for more than 0.045 s (counted within this phase) and its centre is above z = 0.31 m.
6. **left_catch_and_deliver**: panda-0's cup first catches the ball again (fresh entry from above after at least 25 ms of free flight, then retention for 0.18 s, as in left_initial_catch). After that catch is registered, the ball rests in the cart. In the cart's frame: |x| and |y| < 0.075 - 0.45 x `radius` = 0.0669 m; centre between 0.014 m and 0.06 - 0.12 x `radius` = 0.05784 m above the cart floor; touched by the cart within the last 25 ms; speed relative to the cart < 0.09 m/s. At the same time the ball does not touch the left cup and the cart moves faster than 0.02 m/s, for 0.7 s without interruption. This completes the task.

The episode **ends by itself** at the first control step where the last phase is complete (success; rows after it are
never executed) or where the task has failed. `s.status()` reports the phase you are in and the failure, if any.

**The task fails** (the episode ends, reward 0) as soon as any of these happens:
- the task's own failure conditions: none (only the rules below apply);
- the task's horizon is reached: 25 s of simulated time (`timeout`);
- an object leaves the workspace: its centre falls below z = -0.2 m or gets more than 1.8 m from the world's z axis
  (`out_of_bounds`);
- a forbidden contact or a deep interpenetration (below);
- a safety limit is exceeded (`limit_violation`, below).

**Contacts.** Each cup may touch only the ball. Neither cup may touch the cart, its rail or base, or the table. The two arms must never touch each other: any contact between any parts of panda-0 and panda-1, cups included, is a failure. No other robot part (fingers, hands, links, bases) may touch anything, including the ball. In every task: the two arms (and their tools) never touch each other
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
build. The environment's source, the task included, is in `/opt/pandadyn/panda_dynamics` (`tasks/dual/reciprocal_cup_relay.py`).

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

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
