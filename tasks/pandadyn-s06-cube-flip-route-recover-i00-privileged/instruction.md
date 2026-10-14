# Panda Dynamic Scenes · Inertial cube flip, chute run and pocket recovery (S06) — frozen instance i00

You control one simulated **Franka Panda** arm (7 joints, its standard hand, and the task's tool where it has one) in a simulated scene (ManiSkill 3 / SAPIEN, rigid-body CPU PhysX at 1000 Hz) via Python.
**Task:** A cube rests on a raised launch surface. With a short push from the pusher blade, tip it over so that the face that initially faces the robot (-x) ends up on top, the cube completing the tip by its own momentum after the blade has let go, and let it settle. Then push the flipped cube onto an inclined chute, let it slide down by itself, meet it with the blade on its downhill side near the chute's lower end, and bring it to rest in the pocket at the bottom of the chute with the same face still on top.

This is a *fixed scene instance*: everything starts the same way after every reset, and you may reset and retry as many
times as you want. Your deliverable is **one replayable trajectory** of the robot's low-level actions, not a general
policy. Things move by themselves from the first control step on: the scene does not wait for the robot.

## Scene
One Panda, base at (-0.40, 0, 0), yaw 0 (facing +x). Its hand carries a small blue pusher blade: a box 8 mm thick (tool x) x 50 mm wide (tool y) x 12 mm tall (tool z), centred at the tool frame origin; its pushing faces are normal to the tool x axis. The blade hangs from a rigid side adapter (part of the tool): from the hand a horizontal bar at tool z = 0.035 runs from tool x = -0.12 to 0 at tool y = +0.13, then along y to y = 0.07, ending in a short 12 mm x 12 mm post at (0, 0.07) reaching down from z = 0.036 to z = 0 (the blade's mid-height); the post stands 45 mm beyond the blade's +y end and is not joined to it visibly, but blade, bars and post are one rigid tool. The Panda TCP is at (-0.12, 0.13, 0.04) in the tool frame, so with the blade level the gripper points straight down. At the start the blade is level (tool axes aligned with the world axes, pushing faces normal to world x), its centre at (-0.05, -0.08, 0.179).

An orange cube (44 mm edge) rests at t = 0 on a raised, flat orange launch surface (a slab 0.28 m along x by 0.18 m, on posts), one face toward the robot. The launch surface's far (+x) edge meets the top of a straight inclined grey chute (a trough with a 0.10 m wide floor and 22 mm side walls) that runs downhill in +x; the chute's top edge lies slightly below the launch surface. At the chute's low end sits a blue shallow pocket (an open box 0.12 m x 0.12 m inside with 12 mm walls), open on the side facing the chute, its floor flush with the chute's end. Friction is high enough that a cube at rest on the chute stays put, but a cube already sliding on it keeps sliding and speeds up by itself. Nothing moves at t = 0. The table top is the world's z = 0 plane.

Exactly (privileged information, also readable through the tooling): Cube: half-extent `cube_half` = 0.022 m, mass `object_mass` = 0.05 kg, friction 0.65 (dynamic 0.5525), restitution 0.3. At reset it is at (0.035 + dx, dy, 0.14 + `cube_half` + 0.0005) = (0.035 + dx, dy, 0.1625), identity orientation, at rest; dx ~ U(-`start_jitter_x`, `start_jitter_x`) (= 0 at nominal) and then dy ~ U(-`start_jitter_y`, `start_jitter_y`) = U(-0.004, 0.004) m, both drawn at reset. Launch surface: static box 0.28 x 0.18 x 0.04 m centred at (0.02, 0, 0.12) (top z = 0.14, x -0.12..0.16, y -0.09..0.09), friction 0.65, two support posts. Chute: static channel whose floor top surface runs from (0.16, 0, 0.138) to (0.36, 0, 0.035), length 0.225 m, slope 27.25 deg, floor half-width 0.05 m, walls 8 mm thick and 0.022 m tall, friction `chute_friction` = 0.47; surface normal (0.4579, 0, 0.8890), downhill unit vector (0.8890, 0, -0.4579). Mean cube/chute static friction 0.56 > tan 27.25 deg = 0.515 > mean dynamic friction 0.476. Pocket: static open box, inner half-size 0.06 m, walls 12 mm high and 5 mm thick, open on its -x side, floor top at z = 0.035, centre (0.41, 0); friction 0.4, restitution 0.03. Announced at reset: `goal_goal` = (0.41, 0, 0.035 + `cube_half`) = (0.41, 0, 0.057) (pocket centre at resting height) and the flag `target_face` = (-1, 0, 0) (not in the observation). Phase parameters: `free_slide` = 0.12 m, `incoming_speed` = 0.33 m/s. Along-chute coordinate of the cube: s = (p - (0.16, 0, 0.138)) . (0.8890, 0, -0.4579). Pusher: `tool_mass` = 0.2 kg, `tool_friction` = 0.3, restitution 0.05; `tool_half` = 0.07 sets only the adapter post's offset. Table friction `table_friction` = 0.08.

The instance's parameters (`s.params()`, SI units): `horizon` = 25, `object_mass` = 0.05, `tool_mass` = 0.2, `tool_half` = 0.07, `radius` = 0.018, `incoming_speed` = 0.33, `fixture_speed` = 0.04, `restitution` = 0.1, `table_friction` = 0.08, `tool_friction` = 0.3, `cube_half` = 0.022, `friction` = 0.65, `chute_friction` = 0.47, `free_slide` = 0.12, `start_jitter_x` = 0, `start_jitter_y` = 0.004.

**Goal geometry.** Chute-entry line: cube centre at world x > 0.18 m (oriented_chute_entry). Intercept line: cube centre at world x > 0.32 m (downstream_intercept). The delivery target is the pocket's centre (a physical fixture). `goal_goal` is the pocket's centre, announced at reset (a fixture's position: privileged mode only).

## Success (the task's own check)
The task has 4 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **momentum_face_flip**: let tilt be the angle between the cube's initially vertical axis and world up. The blade's last contact with the cube must end while the tilt is between 0.03 and pi/4 - 0.02 = 0.765 rad (1.7 to 43.9 deg), and at some step more than 20 ms after that last contact the cube must still turn faster than 0.4 rad/s (an early release); the tilt must then pass pi/4 (45 deg) without further blade contact. After that the cube must lie with its original -x face on top (that face's outward normal within 0.18 rad of world +z), moving at less than 0.05 m/s and turning at less than 0.3 rad/s, touching the launch surface, for 0.25 s without interruption. Touching the cube with the blade again after the early release and before the tilt has passed 45 deg fails the task (flip_recontact_before_balance).
2. **oriented_chute_entry**: the cube touches the chute while its centre is at world x > 0.18 m and its original -x face points away from the chute surface (that face's outward normal within 0.35 rad (20.1 deg) of the chute surface's normal). The cube's position along the chute's downhill direction at that moment is recorded as the start of its free slide.
3. **downstream_intercept**: the phase completes at a step where the cube touches the blade and at the same time: the cube's centre is at world x > 0.32 m; the cube touches the chute; the blade's tool-frame origin lies on the downhill side of the cube's centre (positive component along the chute's downhill direction); since the start of its free slide the cube's centre has moved at least `free_slide` = 0.12 m along the chute's downhill direction; and on the previous physics step the cube's velocity component down the chute was at least `incoming_speed` = 0.33 m/s. Any cube-blade contact that does not meet all of these restarts the free slide from the cube's current position.
4. **pocket_delivery**: the cube touches the pocket, its centre is within 0.04 m (horizontal distance) of the pocket's centre, its original -x face is on top (outward normal within 0.18 rad of world +z), it moves at less than 0.04 m/s and turns at less than 0.2 rad/s, for 0.5 s without interruption. This completes the task.

The episode **ends by itself** at the first control step where the last phase is complete (success; rows after it are
never executed) or where the task has failed. `s.status()` reports the phase you are in and the failure, if any.

**The task fails** (the episode ends, reward 0) as soon as any of these happens:
- during momentum_face_flip, the blade touches the cube after an early release has been registered and before the cube's tilt has passed 45 deg (`flip_recontact_before_balance`);
- the task's horizon is reached: 25 s of simulated time (`timeout`);
- an object leaves the workspace: its centre falls below z = -0.2 m or gets more than 1.8 m from the world's z axis
  (`out_of_bounds`);
- a forbidden contact or a deep interpenetration (below);
- a safety limit is exceeded (`limit_violation`, below).

**Contacts.** Only the pusher (blade, adapter bars and post) may touch anything, and it may touch only the cube: touching the launch surface, the chute, the pocket or the table is forbidden. No other part of the robot, the fingers included, may touch anything, the cube included. In every task: the two arms (and their tools) never touch each other
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
build. The environment's source, the task included, is in `/opt/pandadyn/panda_dynamics` (`tasks/single/cube_flip_route_recover.py`).

The grader replays in two fresh processes; each is exactly this CLI (a fresh process, so run it to self-check):
`python /opt/tools/rcb_pandadyn.py replay --instance /app/instance.json --traj /app/output/trajectory.npz`

## Conventions
- World frame: metres, z up, the table top is the plane z = 0; quaternions are **wxyz**. Each arm's base pose is in the robot spec (`arms`).
- Action row (8 values per control step): `[joint1..7, aperture]`. Each arm's 8 values are its 7 absolute joint-position
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
