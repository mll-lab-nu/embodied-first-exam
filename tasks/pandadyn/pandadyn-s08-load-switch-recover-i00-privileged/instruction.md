# Panda Dynamic Scenes · Load a coasting cart, throw the switch, recover the part (S08) — frozen instance i00

You control one simulated **Franka Panda** arm (7 joints, its standard hand, and the task's tool where it has one) in a simulated scene (ManiSkill 3 / SAPIEN, rigid-body CPU PhysX at 1000 Hz) via Python.
**Task:** A small cube (the part) rides a powered roller conveyor, and an unpowered cart is already coasting along a straight channel towards a passive hinged switch that splits the track into two diagonal branches. Grasp the part with both fingers while it is still moving and lift it, drop it into the moving cart without stopping the cart, which must keep coasting until the switch is set, then push the switch with a finger so that it will steer the cart into the branch selected for this instance (one of the two sides, drawn per instance and given under Goal geometry) before the cart reaches it. The cart must then be deflected by the switch into that branch. Finally, grasp the part again, lift it out of the cart and hold it up before the cart runs too far down the branch.

This is a *fixed scene instance*: everything starts the same way after every reset, and you may reset and retry as many
times as you want. Your deliverable is **one replayable trajectory** of the robot's low-level actions, not a general
policy. Things move by themselves from the first control step on: the scene does not wait for the robot.

## Scene
One Panda, base at (-0.55, 0, 0) facing +x (yaw 0). No tool: the stock Panda hand with its two fingers. The tool frame (the reported tool pose) is the hand's TCP, the point between the fingertips, with its z axis pointing out of the hand along the fingers. At the start the TCP is at (-0.13, -0.13, 0.20) with the gripper pointing straight down (orientation wxyz (0, 1, 0, 0)). The fingers close along world y and start fully open (aperture 0.08 m; the action's last component is the total aperture, 0 to 0.08 m). In this task the finger motion is not time-synchronised with the arm joints, so a finger command does not stretch the arm motion. The finger servo damping is also raised to 8.

The part is an orange cube with 36 mm edges. It sits on a short roller conveyor of 20 thin grey rollers, which spin by themselves and carry it towards the conveyor's open end; past that end it drops to the table. The cart is a small blue open tray, 0.13 m x 0.11 m inside with 12 mm walls. It rides on four free orange ball bearings (radius 18 mm) and has no motor: it is already coasting at t = 0 and keeps rolling straight. It first passes between two parallel static walls (an entry channel, 16 mm thick and 5 cm tall), then meets the switch. The switch is a passive vertical blade (12 mm thick, 0.14 m long, 45 mm tall) on a vertical hinge with joint friction and no spring, and it carries a small knob on top of its free end. At the start the blade points straight back along the cart's path, edge-on to the incoming cart. Beyond the switch there are two diagonal branches, one on each side. Each has a static guide rail (16 mm thick, 0.24 m long, 5 cm tall) and, at its far end, a shallow static open box (dock, 0.14 m x 0.12 m inside, 18 mm walls). The table top is the world's z = 0 plane.

Exactly (privileged information, also readable through the tooling): Conveyor: 20 rollers (radius 6 mm, 0.136 m long along x) with axes spaced 12.5 mm along y, centred on (-0.16, -0.13); roller axes at z = 0.108, so the roller tops are at z = 0.114. Their axes run from y = -0.24875 to y = -0.01125. Each roller is velocity-driven at -`incoming_speed`/0.006 rad/s about x, so its top surface moves along +y at `incoming_speed` (0.08 m/s). The rollers start already spinning; the motor damping is 0.012 N m s/rad with a 0.008 N m torque cap. Part: cube with 0.018 m half-size, mass `object_mass` (0.035 kg), friction 0.65. At reset its centre is at (-0.16 + dx, -0.18, 0.133) with velocity (0, `incoming_speed`, 0); dx ~ U(-0.004, 0.004) is drawn at reset. With the robot idle it rides off the conveyor's +y end at about t = 2.3 s and lands on the table. Cart: chassis (named `cart`) is an open tray (half 0.065 x 0.055, walls 0.012 m, floor 5 mm) of mass 0.16 kg, friction 0.4. Its origin is the centre of the floor's top surface, at reset (0, `cart_start_y` + dy, 0.045) = (0, -0.41 + dy, 0.045), with dy ~ U(-`cart_phase`, `cart_phase`) = U(-0.01, 0.01) drawn at reset (drawn before dx; `part_phase` = 0, so the part's start along the belt is not drawn). The coasting check (cart_stalled_before_switch) uses `coast_min_ratio` x `fixture_speed` = 0.75 x 0.04 = 0.03 m/s. Initial velocity is (0, `fixture_speed`, 0) = 0.04 m/s. Four bearing balls (`cart_bearing_0..3`: radius 0.018, mass 0.008 kg, friction 0.65, restitution 0.02) sit at chassis offsets (+-0.05, +-0.04, -0.026). Each is held by a joint that locks translation but leaves rotation free, and each starts with spin (-`fixture_speed`/0.018, 0, 0) rad/s (rolling). There is no motor; with the robot idle the cart coasts at about 0.04 m/s and stops at y = 0.10 against the tip of the unturned switch (around t = 13 s). Entry walls: static boxes 0.016 x 0.20 x 0.05 m centred at (+-0.083, -0.22, 0.025). Switch (`switch` link on `switch_base`): hinge at (0, 0.30, 0.01) about the world z axis; q > 0 is counterclockwise seen from above, limits +-1.5 rad, joint friction 0.08, damping 0.001, no drive. The blade is 0.012 x 0.14 x 0.045 m and runs from the hinge towards -y at q = 0 (tip at y = 0.16), covering z 0.01 to 0.055. A knob 0.032 x 0.024 x 0.024 m is centred over the blade tip at z = 0.08. The switch is reset to q = 0 at rest. Branch rails `branch_rail_1` / `branch_rail_-1`: static boxes 0.016 x 0.24 x 0.05 m centred at (+0.16, 0.43, 0.025) / (-0.16, 0.43, 0.025), yawed by -0.55 / +0.55 rad. The +x rail runs from about (0.097, 0.328) to (0.223, 0.532). Docks: static open boxes (half 0.07 x 0.06, walls 0.018) with floor top at z = 0.003, centred at (+-0.16, 0.46). Table friction `table_friction` (0.08). Seeded draws at reset, in this order: dy, dx, then `branch` = rng.choice([-1, +1]). `target` = (0.0, 0.30, 0.08), a point above the switch hinge that no predicate uses.

The instance's parameters (`s.params()`, SI units): `horizon` = 25, `object_mass` = 0.035, `incoming_speed` = 0.08, `fixture_speed` = 0.04, `table_friction` = 0.08, `cart_start_y` = -0.41, `cart_phase` = 0.01, `part_phase` = 0, `coast_min_ratio` = 0.75.

**Goal geometry.** At this instance the selected branch is branch -1: the diagonal branch on the -x side (the side nearer the robot's base). Lines in the world frame used by the predicates: part lift height z = 0.20 m; switch deadline y = 0.105 for the cart's origin; branch reached at y > 0.23 with |x| > 0.08 on the selected side; recovery window ends at |x| = 0.27 or y = 0.43 for the cart's origin. `branch` (+1 = +x side, -1 = -x side) is drawn at reset from the instance's random stream. It is stored in the task's flags but is NOT among the exported goal_* observations, and nothing in the scene shows it. `goal_target` is announced at reset. It is not seeded, but it marks the switch hinge position (raised), so it is privileged mode only; no predicate uses it.

## Success (the task's own check)
The task has 5 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **moving_part_pickup**: Both fingers grip the part (bilateral grip: the left finger or its pad and the right finger or its pad are both in contact with the part at that physics step) at some moment when the part moves faster than 0.025 m/s. After that (same or later step), with the part still gripped, its centre is higher than z = 0.20 m.
2. **load_coasting_cart**: At a step when the part is not gripped by both fingers, the part touches the cart's tray while the cart moves faster than 0.02 m/s.
3. **physical_switch_operation**: During this phase a finger (either finger or finger pad) touches the switch. After that, at some step: the switch angle q (about the vertical hinge, counterclockwise seen from above; q = 0 is the blade pointing from its hinge towards -y) is turned towards the selected branch by more than 0.50 rad, i.e. -branch x q > 0.50 (q < -0.50 rad when branch = +1, the +x side; q > +0.50 rad when branch = -1); the switch turns slower than 0.12 rad/s; and the cart's origin is still at y < 0.105. If, before this, the cart touches the switch or its origin passes y = 0.105, the task fails (missed_switch_deadline).
4. **selected_branch**: During this phase the cart touches the switch and touches the guide rail of the selected branch (`branch_rail_{branch}`), in either order. Then the cart's origin is at y > 0.23 and on the selected side, with branch x x > 0.08 (x > 0.08 for branch +1, x < -0.08 for branch -1).
5. **payload_recovery**: Both fingers grip the part, its centre is more than 0.10 m above the cart's origin (the centre of the cart floor's top surface), and the part does not touch the cart, for 0.5 s without interruption. This completes the task.

The episode **ends by itself** at the first control step where the last phase is complete (success; rows after it are
never executed) or where the task has failed. `s.status()` reports the phase you are in and the failure, if any.

**The task fails** (the episode ends, reward 0) as soon as any of these happens:
- during physical_switch_operation, the phase's completion condition is not met at a step where the cart touches the switch or the cart's origin is at y > 0.105 (`missed_switch_deadline`);
- during physical_switch_operation or selected_branch, the part's centre drops below z = 0.018 m (it is lying on the table) (`loaded_cart_spill`);
- during payload_recovery, the cart's origin reaches |x| > 0.27 or y > 0.43 (`missed_downstream_recovery_window`);
- during moving_part_pickup, load_coasting_cart or physical_switch_operation, the cart's horizontal speed stays below 0.03 m/s for 0.1 s without interruption: the cart must keep coasting until the switch is set (an undisturbed cart keeps at least 98 % of its launch speed; a dip shorter than 0.1 s, as when the part lands, does not count) (`cart_stalled_before_switch`);
- the task's horizon is reached: 25 s of simulated time (`timeout`);
- an object leaves the workspace: its centre falls below z = -0.2 m or gets more than 1.8 m from the world's z axis
  (`out_of_bounds`);
- a forbidden contact or a deep interpenetration (below);
- a safety limit is exceeded (`limit_violation`, below).

**Contacts.** No tool is mounted. Only the finger links (fingers and finger pads) may touch anything. They may touch the part, the cart's tray and its bearing balls (all free objects), and the moving blade/knob of the switch (`switch`). The fingers may not touch the conveyor (its rollers or its base), the switch base, the entry walls, branch rails, docks or the table. No other part of the robot (hand, links, base) may touch anything. Finger-to-finger contact is allowed. In every task: the two arms (and their tools) never touch each other
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
build. The environment's source, the task included, is in `/opt/pandadyn/panda_dynamics` (`tasks/single/load_switch_recover.py`).

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
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **5 GiB of GPU memory**, **16 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`. GPU memory counts what a process reserves (JAX, for example, reserves most of the card unless told not to). These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. When enforcement is on and GPU memory goes above 1.5 times its limit, the monitor also kills the process holding the most of it at once, to protect the machine; that alone does not fail the trial. CPU is capped at 8 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
