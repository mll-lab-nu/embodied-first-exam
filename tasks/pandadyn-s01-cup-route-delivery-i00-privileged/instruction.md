# Panda Dynamic Scenes · Cup catch, route pour, rebound recatch and cart delivery (S01) — frozen instance i00

You control one simulated **Franka Panda** arm (7 joints, its standard hand, and the task's tool where it has one) in a simulated scene (ManiSkill 3 / SAPIEN, rigid-body CPU PhysX at 1000 Hz) via Python.
**Task:** An orange ball is thrown upward at the start and comes back down near the robot. Catch it in the open cup the Panda holds, pour it into the designated one of two raised gravity channels, let it roll down that channel by itself, drop off its end and bounce off the tilted rebound plate below it, catch it in the cup again while it flies, and finally put it into a cart that slides back and forth on a rail, where it must rest while the cart is still moving.

This is a *fixed scene instance*: everything starts the same way after every reset, and you may reset and retry as many
times as you want. Your deliverable is **one replayable trajectory** of the robot's low-level actions, not a general
policy. Things move by themselves from the first control step on: the scene does not wait for the robot.

## Scene
One Panda, base at (-0.55, 0, 0), yaw 0 (facing +x). Its hand carries a blue square cup closed on all four sides: inner 0.14 m x 0.14 m (2 x `tool_half`, `tool_half` = 0.07 m), walls 0.028 m high (`tool_height`) and 5 mm thick, floor 5 mm thick. The tool frame is the centre of the cup's inner floor (top surface of the bottom plate), z up out of the opening, x and y along the walls. A rigid dark-grey adapter on the cup's -x side joins it to the hand: a horizontal bar 0.035 m above the floor (tool-frame x from -0.152 to -0.058) and a short vertical post at the middle of the -x wall (rising 7 mm above the rim and protruding 6 mm into the cup); both are part of the tool. The Panda TCP is at (-0.12, 0, 0.04) in the tool frame, so with the cup level the gripper points straight down just behind the cup's -x wall. At the start the cup is level (tool axes aligned with the world axes), its frame origin at (-0.16, -0.32, 0.23).

A small orange ball (radius 18 mm) is thrown upward at t = 0 and falls back down within the first second. Two identical, parallel gravity channels are raised on posts above the table: open-topped grey troughs 0.35 m long with a 0.12 m wide floor between 55 mm high side walls, both running in the -y direction and very nearly level. Route 0 is the channel nearer the robot base, route 1 the farther one. Each channel's upstream (+y) end is closed by an orange end stop; beyond its downstream (-y) end, a little lower, sits an orange rebound plate (0.11 m x 0.13 m, 16 mm thick), tilted so that a ball dropping onto it bounces onward in -y into open space; the plates are very bouncy. A blue open box (the cart, 0.15 m x 0.15 m inside, 0.06 m deep) rides on a straight rail along the world x axis and moves slowly back and forth along it for the whole episode, slowing to a stop at each end of its stroke. The table top is the world's z = 0 plane.

Exactly (privileged information, also readable through the tooling): Ball: radius `radius` = 0.018 m, mass `object_mass` = 0.035 kg, restitution `restitution` = 0.1, friction 0.2. At t = 0 it is at (-0.10 + `incoming_speed` x `preview`, y0, 0.38) = (0.1275, y0, 0.38) with velocity (-`incoming_speed`, 0, (0.23 + `tool_height` + `radius` - 0.38 + 4.905 x `preview`^2) / `preview`) = (-0.35, 0, 3.028) m/s, so its ballistic flight passes (-0.10, y0, 0.276), one radius above the start-height cup's rim plane, at t = `preview` = 0.65 s (apex about z = 0.847 m at t = 0.31 s). Random draws at reset, in this order: `route_index` = rng.integers(2) (the designated route), y0 ~ U(-0.34, -0.30) m, cart start offset q0 ~ U(-0.05, 0) m. Route i (i = 0, 1) lies at x = -0.12 (route 0) and x = 0.08 (route 1): static gravity channel whose floor top surface runs from (x, 0.23, `track_height`) to (x, -0.12, `track_height` - `track_drop`) = from z 0.34 to 0.339 m, floor half-width 0.06 m, walls 8 mm thick and 0.055 m tall, friction 0.12; the channel actor includes its support posts. End stop i: static box 0.128 x 0.012 x 0.07 m centred at (x, 0.244, `track_height` + 0.035), restitution 0.05. Rebound plate i: static box 0.11 x 0.13 x 0.016 m centred at (x, -0.165, `rebound_height` = 0.26), rotated +0.35 rad about world x (surface normal (0, -sin 0.35, cos 0.35)), restitution 0.90, friction 0.3. Announced at reset: `goal_goal` = (x of the designated route, 0.23, `track_height`) and `goal_target` = (-0.10, y0, 0.23); `route_index` itself is a flag that is not in the observation. Cart: prismatic fixture, rail centre (-0.25, -0.33, 0.08), axis +x, limits +-0.5 m, moving link mass 0.3 kg, container inner half-size 0.075 m, depth 0.06 m, floor top at the link origin. Drive law (oscillating): target q(t) = q0 + 0.20 sin((`fixture_speed`/0.20) t) = q0 + 0.20 sin(0.2 t) m, velocity target `fixture_speed` cos(0.2 t) (peak `fixture_speed` = 0.04 m/s), PD stiffness 80 N/m, damping 8 N s/m, force limit 8 N; at reset q = q0 and velocity = `fixture_speed`. Period 31.4 s; the commanded speed exceeds 0.02 m/s only for t < 5.24 s and 10.47 s < t < 20.94 s within the 25 s `horizon`. Cup: `tool_mass` = 0.2 kg, `tool_friction` = 0.3, restitution 0.05. Table friction `table_friction` = 0.08.

The instance's parameters (`s.params()`, SI units): `horizon` = 25, `object_mass` = 0.035, `tool_mass` = 0.2, `tool_half` = 0.07, `radius` = 0.018, `preview` = 0.65, `incoming_speed` = 0.35, `fixture_speed` = 0.04, `restitution` = 0.1, `table_friction` = 0.08, `tool_friction` = 0.3, `tool_height` = 0.028, `track_height` = 0.34, `rebound_height` = 0.26, `track_drop` = 0.001.

**Goal geometry.** At this instance the designated route is route 1: of the two parallel channels, the one farther from the robot's base (the +x one). Touching the other channel during selected_route_entry fails the task (`wrong_route`). Route-entry line: ball centre at world y > 0.10 m (selected_route_entry). Rebound check: ball centre at world y < -0.12 m and z > 0.255 m (track_and_rebound). `goal_goal` (the upstream end point of the designated channel, on its centreline at track height; it reveals which route was drawn) and `goal_target` (the catch point at the cup's start height, at the ball's seeded lateral coordinate y0) are announced at reset: privileged mode only. The route choice itself (`route_index`) is drawn at reset.

## Success (the task's own check)
The task has 5 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **incoming_catch**: the ball, after at least 25 ms of free flight (touching nothing), passes downward through the plane 0.046 m above the cup floor (`tool_height` + radius, one radius above the rim) while its centre is within 0.052 m (`tool_half` - radius) of the cup centre in both tool-frame x and y; after that entry it must stay retained in the cup for 0.18 s without interruption. Retained means: in the cup's frame the ball's centre is within 0.0619 m of the centre in x and y (`tool_half` - 0.45 x radius) and between 0.014 m and 0.0258 m above the floor (radius - 4 mm to `tool_height` - 0.12 x radius), the ball touched the cup within the last 25 ms, and it moves at less than 0.09 m/s relative to the cup.
2. **selected_route_entry**: the ball touches the designated channel (route 0, the channel nearer the robot's base, or route 1, the farther one, drawn per instance and given under Goal geometry; the channel trough and its supports count, the separate end stop does not) while its centre is at world y > 0.10 m and it is not touching the cup. Touching the other channel at any time during this phase fails the task (wrong_route).
3. **track_and_rebound**: without the ball touching the cup or the table (either fails the task), it touches the rebound plate of the designated route while its centre is at world y < -0.12 m and z > `rebound_height` - 0.005 = 0.255 m.
4. **downstream_catch**: the ball is caught in the cup again with the same test as the first catch: at least 25 ms of free flight (counted within this phase), a downward pass through the plane 0.046 m above the cup floor while within 0.052 m of the cup centre in tool-frame x and y, then retained in the cup (same retention conditions) for 0.18 s without interruption.
5. **moving_cart_delivery**: the ball rests in the cart: in the cart's frame its centre is within 0.0669 m of the cart centre in x and y (0.075 - 0.45 x radius) and between 0.014 m and 0.0578 m above the cart floor (radius - 4 mm to 0.06 - 0.12 x radius), it touched the cart within the last 25 ms, and it moves at less than 0.09 m/s relative to the cart; it does not touch the cup; and the cart moves along its rail at more than 0.02 m/s (half of `fixture_speed`); all for 0.7 s without interruption. This completes the task.

The episode **ends by itself** at the first control step where the last phase is complete (success; rows after it are
never executed) or where the task has failed. `s.status()` reports the phase you are in and the failure, if any.

**The task fails** (the episode ends, reward 0) as soon as any of these happens:
- during selected_route_entry, the ball touches the channel that was not designated (`wrong_route`);
- during track_and_rebound, the ball touches the table (`missed_gravity_route`);
- during track_and_rebound, the ball touches the cup (`caught_before_required_rebound`);
- the task's horizon is reached: 25 s of simulated time (`timeout`);
- an object leaves the workspace: its centre falls below z = -0.2 m or gets more than 1.8 m from the world's z axis
  (`out_of_bounds`);
- a forbidden contact or a deep interpenetration (below);
- a safety limit is exceeded (`limit_violation`, below).

**Contacts.** Only the cup (including its adapter) may touch anything, and it may touch only the ball: touching the channels, end stops, rebound plates, the cart or its rail, or the table is forbidden. No other part of the robot, the fingers included, may touch anything, the ball included. In every task: the two arms (and their tools) never touch each other
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
build. The environment's source, the task included, is in `/opt/pandadyn/panda_dynamics` (`tasks/single/cup_route_delivery.py`).

The grader replays in two fresh processes; each is exactly this CLI (a fresh process, so run it to self-check):
`python /opt/tools/rcb_pandadyn.py replay --instance /app/instance.json --traj /app/output/trajectory.npz`

## Conventions
- World frame: metres, z up, the table top is the plane z = 0; quaternions are **wxyz**. Each arm's base pose is in the robot spec (`arms`).
- Action row (8 values per control step): `[joint1..7, aperture]`. Each arm's 8 values are its 7 absolute joint-position
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

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
