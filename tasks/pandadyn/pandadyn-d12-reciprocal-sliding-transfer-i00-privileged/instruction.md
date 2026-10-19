# Panda Dynamic Scenes · Reciprocal sliding transfer (D12) — frozen instance i00

You control two simulated **Franka Panda** arms (`panda-0` on the left, `panda-1` on the right; each with its standard hand and the task's tool where it has one) in a simulated scene (ManiSkill 3 / SAPIEN, rigid-body CPU PhysX at 1000 Hz) via Python.
**Task:** Each arm holds a level scoop, a shallow square tray that is open on the side facing the other arm. A cube on a very slippery surface starts on the left scoop. Without tilting the scoops, the left arm must make the cube slide out over its open edge onto the right scoop, where the cube has to come to rest. The right arm then carries it to a new place and makes it slide back onto the left scoop, where it must come to rest again. Finally the cube must be set down on a fixed output platform and left there at rest. Until that final deposit begins, the scoops may not tilt by more than 2.1 deg, and the cube may never be without scoop contact for more than about a tenth of a second.

This is a *fixed scene instance*: everything starts the same way after every reset, and you may reset and retry as many
times as you want. Your deliverable is **one replayable trajectory** of the robot's low-level actions, not a general
policy.

## Scene
Two Pandas facing each other along x. panda-0 (left): base at (-0.55, -0.22, 0), yaw 0 (facing +x). panda-1 (right): base at (0.74, 0.22, 0), yaw pi (facing -x). Each hand carries a scoop: a square tray with a 5 mm floor, inside 0.16 x 0.16 m (2 x `tool_half`, 0.08 at this instance). It has 25 mm high, 5 mm thick walls on three sides and no wall on its tool +x side, the side pointing away from the arm's own base. The tool frame is the centre of the inside floor surface, z up, x toward the open side. With the scoop level the hand points straight down and the scoop's floor centre is 0.12 m ahead of the gripper TCP along tool x and 0.04 m below it. The grey adapter enters at the middle of the back (tool -x) wall: a 12 mm wide post protrudes 6 mm inward from floor level up to 35 mm, and a bar protrudes 12 mm inward 29-41 mm above the floor, above the wall top. Start: left floor centre at (-0.015, -0.04, 0.19), level, axes aligned with the world (open side facing +x). Right floor centre at (0.175, -0.04, 0.187), level, rotated 180 deg about z (open side facing -x). The two open edges thus face each other across a gap of about 2 cm, with the right floor 3 mm lower. Role labels per phase (left, right): left_inertial_slip: inertial_donor, matched_receiver; right_receive_and_brake: cleared_donor, braking_receiver; reverse_geometry: preparing_receiver, loaded_carrier; left_receive_and_brake: braking_receiver, inertial_donor; final_support_deposit: deliverer, cleared_partner.

An orange cube (36 mm edge) starts resting flat on the left scoop's floor, off the floor centre toward the open edge. Contact between the cube and the scoops is very slippery. The output platform is a fixed orange slab (0.20 x 0.15 m, 24 mm thick) on two grey posts, standing beside the scoops' working area on the -y side, toward the right arm. Nothing moves by itself. The table top is the world's z = 0 plane.

Exactly (privileged information, also readable through the tooling): Cube: half extent 0.018 m, mass `object_mass` = 0.035 kg, friction `friction` = 0.05, restitution 0.05. At reset it is placed at rest, unrotated, at the left tool frame's actual position + (0.040, dy, 0.0185) (a world-frame offset), with dy ~ U(-0.004, 0.004) (the only random draw; nothing is drawn later). It thus starts 0.5 mm above the floor, 40 mm from the floor centre toward the open edge. The local start offset (0.040, dy, 0.0185) is kept for left_inertial_slip. Scoops: friction `tool_friction` = 0.05, mass `tool_mass` = 0.2 kg, restitution 0.05. Output platform: static box 'output' with half extents (0.10, 0.075, 0.012) centred at (0.18, -0.22, 0.118) (top surface at z = 0.13), friction 0.4, restitution 0.05, two support posts underneath. Table friction `table_friction` = 0.08. `radius`, `incoming_speed`, `fixture_speed`, `preview`, `restitution`, `target_offset` and `target_tolerance` are not used by this task. Horizon `horizon` = 25 s.

The instance's parameters (`s.params()`, SI units): `horizon` = 25, `object_mass` = 0.035, `tool_mass` = 0.2, `tool_half` = 0.08, `radius` = 0.018, `preview` = 0.65, `incoming_speed` = 0.35, `fixture_speed` = 0.04, `restitution` = 0.1, `table_friction` = 0.08, `tool_friction` = 0.05, `friction` = 0.05, `target_offset` = 0.035, `target_tolerance` = 0.014.

## Success (the task's own check)
The task has 5 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **left_inertial_slip**: while the cube is on the left scoop (it has touched that tool link within the last 25 ms), its centre has moved more than 0.028 m toward the open edge from its start offset, measured along the left scoop's tool x axis (left-tool-frame x > 0.040 + 0.028 = 0.068 m).
2. **right_receive_and_brake**: the cube is on the right scoop (touched within the last 25 ms) and not on the left one (no left-scoop contact within the last 25 ms), for 0.3 s without interruption. During that time its centre is within 0.065 m of the right scoop's floor centre along both tool x and tool y (|x|, |y| < 0.065 m in the right tool frame), and it moves at less than 0.05 m/s relative to the right scoop (the scoop's rigid-body velocity at the cube's position). The right tool frame's position at the moment this phase completes is recorded as the receive pose.
3. **reverse_geometry**: with the cube on the right scoop (touched within the last 25 ms), the right tool frame is more than 0.06 m away from the receive pose recorded at the end of right_receive_and_brake.
4. **left_receive_and_brake**: the cube is on the left scoop (touched within the last 25 ms) and not on the right one (no right-scoop contact within the last 25 ms), for 0.3 s without interruption. During that time its centre is within 0.065 m of the left floor centre along both tool x and tool y, and it moves at less than 0.05 m/s relative to the left scoop.
5. **final_support_deposit**: the cube touches the output platform and has touched neither scoop within the last 25 ms, for 0.5 s without interruption. During that time its centre is within 0.065 m horizontally (a circle) of the platform's centre (the platform top is 0.20 x 0.15 m), and it moves slower than 0.04 m/s. This completes the task.

The episode **ends by itself** at the first control step where the last phase is complete (success; rows after it are
never executed) or where the task has failed. `s.status()` reports the phase you are in and the failure, if any.

**The task fails** (the episode ends, reward 0) as soon as any of these happens:
- before final_support_deposit (during phases left_inertial_slip to left_receive_and_brake), either scoop's tool z axis tilts more than 2.1 deg away from world vertical (`tilt_only_shortcut`);
- before final_support_deposit, the cube stays unsupported for more than 0.09 s at a stretch. Unsupported means it has touched neither scoop within the last 25 ms, so this fires after roughly 0.115 s without any scoop contact (`airborne_transfer_shortcut`);
- the task's horizon is reached: 25 s of simulated time (`timeout`);
- an object leaves the workspace: its centre falls below z = -0.2 m or gets more than 1.8 m from the world's z axis
  (`out_of_bounds`);
- a forbidden contact or a deep interpenetration (below);
- a safety limit is exceeded (`limit_violation`, below).

**Contacts.** Each scoop (whole tool link, adapter included) may touch the cube only: not the output platform, not the table. No other part of either robot, the fingers included, may touch anything. The two arms and their scoops may never touch each other, and no arm may touch itself. In every task: the two arms (and their tools) never touch each other
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
build. The environment's source, the task included, is in `/opt/pandadyn/panda_dynamics` (`tasks/dual/reciprocal_sliding_transfer.py`).

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
