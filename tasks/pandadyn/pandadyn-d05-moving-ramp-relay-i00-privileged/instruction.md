# Panda Dynamic Scenes · Moving ramp relay (D05) — frozen instance i00

You control two simulated **Franka Panda** arms (`panda-0` on the left, `panda-1` on the right; each with its standard hand and the task's tool where it has one) in a simulated scene (ManiSkill 3 / SAPIEN, rigid-body CPU PhysX at 1000 Hz) via Python.
**Task:** An orange ball rests in the left Panda's cup, and the right Panda holds a straight channel that is open at both ends. The left arm must pass the ball into the inlet part of the channel. The ball must then leave the channel by its outlet end and be caught again in free flight by the left cup. The relay is then repeated with the channel held at a clearly different orientation from the first time. After the second catch, the left cup must deliver the ball into a fixed basin, where it must come to rest.

This is a *fixed scene instance*: everything starts the same way after every reset, and you may reset and retry as many
times as you want. Your deliverable is **one replayable trajectory** of the robot's low-level actions, not a general
policy.

## Scene
panda-0 (left): base at (-0.55, -0.22, 0), yaw 0 (facing +x). It carries an open-top square cup, 0.14 m x 0.14 m inside (2 x `tool_half`, `tool_half` = 0.07 m), with four 0.055 m high, 5 mm thick walls and a 5 mm floor, held by an adapter on its tool -x wall. The tool frame is the centre of the cup floor's inner surface, z up. The TCP sits 0.12 m along tool -x and 0.04 m above the tool frame. Start: (-0.04, -0.14, 0.23), orientation identity (upright). panda-1 (right): base at (0.74, 0.22, 0), yaw pi (facing -x). It carries a straight channel, open at both ends and 0.28 m long (2 x `right_tool_half`, `right_tool_half` = 0.14 m). It has a flat floor 72 mm wide and 8 mm thick and two side walls 40 mm high and 8 mm thick. A side adapter holds it at the middle of its tool +y wall. The tool frame is the centre of the floor's top surface: x runs along the channel (the +x end is the outlet, the -x half the inlet side), y across it, z up. The TCP sits 0.12 m along tool -x, 0.12 m along tool +y and 0.04 m above the tool frame. Start: (0.18, 0.10, 0.24), quaternion (0, 0, 0, 1) (yawed 180 deg: level, outlet end toward world -x). Role labels (panda-0 / panda-1) by phase: first_channel_entry donor / channel_operator; first_moving_exit relocating_receiver / moving_outlet; first_catch catcher / channel_support; second_channel_entry donor / changed_channel; second_moving_exit relocating_receiver / moving_outlet; second_catch_and_delivery catcher_deliverer / channel_support.

An orange ball (radius 18 mm) rests at a slightly random spot on the floor of the left arm's cup. A fixed blue open-top basin, 0.15 m x 0.15 m inside and 0.06 m deep, stands on posts above the table. Nothing moves by itself; once the ball is in the channel, it rolls under gravity. The table top is the world's z = 0 plane.

Exactly (privileged information, also readable through the tooling): Ball: radius `radius` = 0.018 m, mass `object_mass` = 0.035 kg, restitution 0.08, friction 0.2. At reset it is placed at rest at the left cup's frame origin + (u_x, u_y, `radius` + 0.0005) in world axes, i.e. 0.5 mm above the cup floor. u_x and u_y are drawn uniformly in [-`ball_offset`, `ball_offset`] = [-0.015, 0.015] m. `ball_roll_speed` = 0, so the ball starts at rest and no heading is drawn. Basin: static container with floor top surface centre at (0.04, -0.24, 0.08); inner half-size 0.075 x 0.075 m; wall height 0.06 m (rim at z = 0.14); friction 0.4; restitution 0.03. Cup: `tool_half` = 0.07, `tool_mass` = 0.2 kg. Channel: `right_tool_half` = 0.14, `right_tool_mass` = 0.25 kg. Both tools have `tool_friction` = 0.3 and restitution 0.05. `outlet_min_speed` = 0 (see static_outlet_exit). Horizon `horizon` = 25 s. The only random draws are u_x and u_y, made at reset.

The instance's parameters (`s.params()`, SI units): `horizon` = 25, `object_mass` = 0.035, `tool_mass` = 0.2, `tool_half` = 0.07, `radius` = 0.018, `preview` = 0.65, `incoming_speed` = 0.35, `fixture_speed` = 0.04, `restitution` = 0.1, `table_friction` = 0.08, `tool_friction` = 0.3, `right_tool_half` = 0.14, `right_tool_mass` = 0.25, `ball_offset` = 0.015, `outlet_min_speed` = 0, `ball_roll_speed` = 0.

**Goal geometry.** All phase geometry is relative to the channel, the cup and the basin. `goal_target` = (0.18, 0.10, 0.24), the channel's start position, is announced at reset, but no phase condition uses it.

## Success (the task's own check)
The task has 6 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **first_channel_entry**: The ball touches the channel (any part of panda-1's tool) while two things hold. Its centre is more than 0.045 m from the channel centre on the inlet side (channel-frame x < -0.045). And at that moment it does not touch the cup. The channel's pose (position and orientation) at that moment is recorded.
2. **first_moving_exit**: The ball's centre is more than 0.13 m from the channel centre on the outlet side (channel-frame x > 0.13, i.e. within 1 cm of the outlet end or past it; y and z are not bounded), while the ball does not touch the channel. At that moment the world speed of the channel's outlet tip must be at least `outlet_min_speed`, which is 0 at this instance.
3. **first_catch**: The ball enters the left cup from above and is retained. The entry: after touching nothing for at least 0.025 s, the ball's centre passes downward through the plane 0.073 m above the cup floor (wall height 0.055 m + radius 0.018 m, in the cup's frame). At that crossing the centre must be within 0.052 m (`tool_half` - radius) of the cup centre along both cup x and cup y. From then on the ball must stay contained in the cup for 0.18 s without interruption. Contained in the cup means all of the following, in the cup's frame: |x| and |y| of the ball centre below 0.0619 m (`tool_half` - 0.45 x radius); height above the cup floor between 0.014 m and 0.0528 m; in contact with the cup within the last 25 ms; moving at less than 0.09 m/s relative to the cup (including the cup's rotation). The free-flight time counts only from the start of this phase.
4. **second_channel_entry**: As in first_channel_entry, the ball touches the channel at channel-frame x < -0.045 while not touching the cup. In addition, the channel's orientation must differ by at least 0.30 rad (about 17.2 deg) from the orientation recorded at the first entry, i.e. |q . q_first| <= cos 0.15 for the unit quaternions. A touch while the orientation is too close to the first one does not count.
5. **second_moving_exit**: As in first_moving_exit: the ball's centre is at channel-frame x > 0.13 while the ball does not touch the channel, and the outlet tip moves at least `outlet_min_speed` (0 here).
6. **second_catch_and_delivery**: First the ball is caught again in the left cup exactly as in first_catch. That is: an entry after at least 0.025 s of free flight (counted from the start of this phase) through the plane 0.073 m above the cup floor within 0.052 m of the centre on both axes, then contained in the cup for 0.18 s without interruption. After that catch, the ball must be contained in the basin and not touch the cup, for 0.7 s without interruption. Contained in the basin means all of the following, in the basin's frame (origin at the centre of its floor's top surface, axes = world axes): |x| and |y| of the ball centre below 0.0669 m (0.075 - 0.45 x radius); height above the basin floor between 0.014 m and 0.0578 m; in contact with the basin within the last 25 ms; speed below 0.09 m/s. This completes the task.

The episode **ends by itself** at the first control step where the last phase is complete (success; rows after it are
never executed) or where the task has failed. `s.status()` reports the phase you are in and the failure, if any.

**The task fails** (the episode ends, reward 0) as soon as any of these happens:
- when the ball meets the first_moving_exit or second_moving_exit condition, the world speed of the channel's outlet tip is below `outlet_min_speed`. The outlet tip is the tool-frame point (`right_tool_half`, 0, 0). At this instance `outlet_min_speed` = 0, so this failure cannot occur (`static_outlet_exit`);
- the task's horizon is reached: 25 s of simulated time (`timeout`);
- an object leaves the workspace: its centre falls below z = -0.2 m or gets more than 1.8 m from the world's z axis
  (`out_of_bounds`);
- a forbidden contact or a deep interpenetration (below);
- a safety limit is exceeded (`limit_violation`, below).

**Contacts.** The cup and the channel may touch only the ball. They must not touch each other, the basin or its posts, the table or the robot pedestals. No other robot part, the fingers included, may touch anything. The two arms and their tools must never touch each other, so the ball has to pass between cup and channel without the two tools touching. A tool must not touch its own arm. In every task: the two arms (and their tools) never touch each other
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
build. The environment's source, the task included, is in `/opt/pandadyn/panda_dynamics` (`tasks/dual/moving_ramp_relay.py`).

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
