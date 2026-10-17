# Panda Dynamic Scenes · Supported cube flip relay (D13) — frozen instance i00

You control two simulated **Franka Panda** arms (`panda-0` on the left, `panda-1` on the right; each with its standard hand and the task's tool where it has one) in a simulated scene (ManiSkill 3 / SAPIEN, rigid-body CPU PhysX at 1000 Hz) via Python.
**Task:** The left arm holds a large shallow tray with a cube on it, and the right arm holds a small flat pusher. The left arm must first bring the tray to a presentation point. The right arm must then tip the cube over onto an adjacent face. It does so with a short push that sets the cube rotating and ends before the cube is half-way over, so that the cube completes the tip on its own momentum and settles on the tray. The left arm then moves the cube, on the tray, to a new place, and the pusher tips it a second time in the same way, so that the cube's original bottom face ends up on top. Finally the tray must carry the correctly oriented cube to an output point and hold it there. The cube must never leave the tray.

This is a *fixed scene instance*: everything starts the same way after every reset, and you may reset and retry as many
times as you want. Your deliverable is **one replayable trajectory** of the robot's low-level actions, not a general
policy.

## Scene
Two Pandas facing each other along x. panda-0 (left): base at (-0.55, -0.22, 0), yaw 0 (facing +x). Its tool is a tray with a 5 mm floor, inside 0.24 x 0.24 m (2 x `left_tool_half`, 0.12 at this instance), with walls 12 mm high and 5 mm thick on all four sides. The tool frame is the centre of the inside floor surface, z up, x pointing away from the arm's base. With the tray level the hand points straight down and the floor centre is 0.12 m ahead of the gripper TCP along tool x and 0.04 m below it. The grey adapter enters at the middle of the back (tool -x) wall: a 12 mm wide post protrudes 6 mm inward from the floor up to 35 mm, and a bar protrudes 12 mm inward 29-41 mm above the floor, above the 12 mm wall. Start: floor centre at (0.04, -0.035, 0.23), level, axes aligned with the world. panda-1 (right): base at (0.74, 0.22, 0), yaw pi (facing -x). Its tool is a pusher: a small rigid plate 8 mm thick (along tool x), 50 mm wide (tool y) and 12 mm tall (tool z), with the tool frame at its centre and x normal to its face, pointing away from the arm's base. The pusher centre is 0.12 m ahead of the TCP along tool x and 0.04 m below it. A grey adapter (a horizontal bar from the hand and a short post) ends about 5 cm behind it on the hand side; plate and adapter form one rigid tool link. Start: pusher centre at (0.16, 0.02, 0.268), rotated 180 deg about z (face normal = world -x, toward the tray). Role labels per phase (left, right): support_presentation: tray_support, preparing_pusher; first_inertial_flip: moving_support, impulse_pusher; second_contact_geometry: repositioning_support, cleared_pusher; second_inertial_flip: moving_support, impulse_pusher; oriented_output: oriented_carrier, cleared_pusher.

A plain orange cube (44 mm edge, all faces alike) starts resting flat on the left tray's floor, near the tray centre and a little toward the pusher's side (+x). Its axes start aligned with the world axes. There is nothing else in the scene, and nothing moves by itself. The table top is the world's z = 0 plane.

Exactly (privileged information, also readable through the tooling): Cube: half extent `cube_half` = 0.022 m, mass `object_mass` = 0.05 kg, friction 0.65, restitution 0.25. At reset it is placed at rest, unrotated (its local axes equal the world axes), at (0.06, y0, 0.23 + `cube_half` + 0.0005), with y0 ~ U(-0.038, -0.032) (the only random draw; nothing is drawn later). That is 20 mm toward +x from the tray centre and 0.5 mm above the floor. Tray: mass `left_tool_mass` = 0.22 kg, friction `left_tool_friction` = 0.65. Pusher: mass `tool_mass` = 0.2 kg, friction `tool_friction` = 0.3. Tool restitution 0.05. The `friction` parameter (0.65) is listed in the config, but the cube's friction is hard-coded to the same 0.65. Table friction `table_friction` = 0.08. `radius`, `incoming_speed`, `fixture_speed`, `preview` and `restitution` are not used by this task. Horizon `horizon` = 25 s.

The instance's parameters (`s.params()`, SI units): `horizon` = 25, `object_mass` = 0.05, `tool_mass` = 0.2, `tool_half` = 0.07, `radius` = 0.018, `preview` = 0.65, `incoming_speed` = 0.35, `fixture_speed` = 0.04, `restitution` = 0.1, `table_friction` = 0.08, `tool_friction` = 0.3, `cube_half` = 0.022, `friction` = 0.65, `left_tool_half` = 0.12, `left_tool_mass` = 0.22, `left_tool_friction` = 0.65.

**Goal geometry.** Presentation point (0.08, 0.015, 0.23) for the tray's tool frame (support_presentation), announced at reset as `goal_target`; output point (-0.04, 0.16, 0.25) for the tray's tool frame (oriented_output), announced as `goal_goal`.

## Success (the task's own check)
The task has 5 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **support_presentation**: the cube is on the tray (it has touched the tray's tool link within the last 25 ms) while the tray's tool frame is within 0.025 m of the presentation point (0.08, 0.015, 0.23).
2. **first_inertial_flip**: an inertial flip, judged only from pusher contacts made in this phase. The tilt of a cube axis means the angle between that cube-local axis and world vertical; here the tilted axis is the cube's local z (initially up). (a) The pusher (any part of its tool link) touches the cube; the tilt at the last moment of contact is the release angle. (b) Early release: at some moment more than 0.02 s after the last pusher contact, the cube is untouched by the pusher, the release angle was between 0.03 rad and pi/4 - 0.02 = 0.765 rad (about 1.7 to 43.9 deg), and the cube turns faster than 0.4 rad/s. This is recorded once. (c) Inertial crossing: after the early release, the tilt grows from at most 45 deg (pi/4) at one physics step to more than 45 deg at the next. (d) After that, the final state must hold for 0.25 s without interruption: the cube's local +x axis (the face that initially faced +x, toward the right arm) points up within 0.18 rad (about 10.3 deg), the cube moves slower than 0.05 m/s and turns slower than 0.3 rad/s, and it is on the tray (touched within the last 25 ms). The cube's world position at the moment this phase completes is recorded.
3. **second_contact_geometry**: with the cube on the tray (touched within the last 25 ms) and not touched by the pusher at that moment, the cube's centre is more than 0.025 m (world distance) away from the position recorded at the end of first_inertial_flip.
4. **second_inertial_flip**: the same inertial-flip rule as first_inertial_flip, judged only from pusher contacts made in this phase, with the cube's local x axis (now pointing up) as the tilted axis. That is: a pusher contact, then a release with tilt between 0.03 rad and 0.765 rad followed (more than 0.02 s later, still untouched) by an angular speed above 0.4 rad/s, then the tilt of local x passing 45 deg. The final state is that the cube's local -z axis (its original bottom face) points up within 0.18 rad, with speed < 0.05 m/s, angular speed < 0.3 rad/s and the cube on the tray, for 0.25 s without interruption.
5. **oriented_output**: for 0.5 s without interruption: the cube is on the tray (touched within the last 25 ms) and its local -z axis points up within 0.18 rad; the tray's tool frame is within 0.025 m of the output point (-0.04, 0.16, 0.25); and the cube moves at less than 0.04 m/s relative to the tray. This completes the task.

The episode **ends by itself** at the first control step where the last phase is complete (success; rows after it are
never executed) or where the task has failed. `s.status()` reports the phase you are in and the failure, if any.

**The task fails** (the episode ends, reward 0) as soon as any of these happens:
- at any time, the cube's centre in the tray's tool frame is 0.115 m or more from the floor centre along x or y (|x| or |y| >= 0.115 m), or 0.01 m or more below the floor surface (z <= -0.01 m) (`cube_lost_from_tray`);
- during first_inertial_flip or second_inertial_flip, the pusher touches the cube after an early release has been recorded in that phase but before the 45 deg inertial crossing. An early release that does not lead to a crossing therefore leaves no retry: any further pusher contact in that phase fails the task (`flip_recontact_before_balance`);
- the task's horizon is reached: 25 s of simulated time (`timeout`);
- an object leaves the workspace: its centre falls below z = -0.2 m or gets more than 1.8 m from the world's z axis
  (`out_of_bounds`);
- a forbidden contact or a deep interpenetration (below);
- a safety limit is exceeded (`limit_violation`, below).

**Contacts.** The tray and the pusher (each its whole tool link, adapter included) may touch the cube only, not the table. No other part of either robot, the fingers included, may touch anything. The two arms and their tools may never touch each other, and no arm may touch itself. In every task: the two arms (and their tools) never touch each other
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
build. The environment's source, the task included, is in `/opt/pandadyn/panda_dynamics` (`tasks/dual/supported_cube_flip_relay.py`).

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
