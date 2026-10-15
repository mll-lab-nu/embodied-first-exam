# Panda Dynamic Scenes · Moving grasp handover (D10) — frozen instance i00

You control two simulated **Franka Panda** arms (`panda-0` on the left, `panda-1` on the right; each with its standard hand and the task's tool where it has one) in a simulated scene (ManiSkill 3 / SAPIEN, rigid-body CPU PhysX at 1000 Hz) via Python.
**Task:** A long bar-shaped part is already riding a powered roller conveyor when the episode starts. The left arm must grasp it with its gripper while it is still moving and lift it, then carry it, still moving, through a presentation point. It then hands the part over to the right arm: both grippers hold it at the same time, then the left gripper opens wide and lets go while the right one keeps holding it. Finally the right arm must lay the part into a long open slot that slides back and forth on a rail and let go of it, so that the part lies in the slot while the slot is moving.

This is a *fixed scene instance*: everything starts the same way after every reset, and you may reset and retry as many
times as you want. Your deliverable is **one replayable trajectory** of the robot's low-level actions, not a general
policy. Things move by themselves from the first control step on: the scene does not wait for the robot.

## Scene
Two Pandas with their standard two-finger grippers and no tool. panda-0 (left): base at (-0.55, -0.23, 0), yaw 0 (facing +x). panda-1 (right): base at (0.74, 0.23, 0), yaw pi (facing -x). Each arm's tool frame is its gripper TCP (the point between the fingertips). At the start both TCPs point straight down (TCP z = world -z, and TCP x = world +x for both arms), so the fingers close along world y. Left TCP at (-0.10, -0.10, 0.20); right TCP at (0.19, 0.16, 0.23). Both grippers start partly open at 0.024 m per finger (0.048 m total aperture). The action's last entry is the total aperture in [0, 0.08] m, and each finger moves at most 0.025 m/s. In this task the fingers follow their own trajectory, not synchronized with the arm joints, so an aperture change does not stretch the duration of the arm motion. Role labels per phase (left, right): moving_pickup: moving_grasper, preparing_receiver; moving_presentation: moving_donor, tracking_receiver; overlapping_grips: donor_grip, receiver_grip; donor_release: releasing_donor, sole_support; receiver_slot_delivery: cleared_donor, slot_deliverer.

An orange bar-shaped part (0.22 x 0.034 x 0.036 m, long axis along world x) lies across a short roller conveyor. The conveyor has 20 grey rollers (radius 6 mm, 136 mm long, axes along x, 12.5 mm apart along y) on a pedestal, all motor-driven so that their tops carry the part along +y. The part is longer than the rollers and overhangs them at both ends. At t = 0 the part is already moving along +y with the conveyor. The conveyor keeps running for the whole episode, and nothing stops the part at its end: a part that is not taken is carried off the end and falls. A blue open box, the 'slot' (0.25 m along x by 0.13 m along y inside, 0.06 m deep), rides a straight rail along y. The slot is driven back and forth along the rail in a smooth sinusoidal oscillation by itself for the whole episode: slowly, and slowest where it turns around. The table top is the world's z = 0 plane.

Exactly (privileged information, also readable through the tooling): Conveyor: fixed articulation centred at (-0.08, -0.08, 0.10). Roller axes are at z = 0.108 (roller tops at z = 0.114), roller centres at y = -0.08 + (i - 9.5) x 0.0125 for i = 0..19 (from -0.19875 to +0.03875), each roller spanning x in [-0.148, -0.012]; roller friction 0.9. Each roller has a velocity drive toward -`incoming_speed` / 0.006 rad/s about +x (surface speed `incoming_speed` = 0.08 m/s toward +y at the top), with damping gain 0.012 and torque limit 0.008 N m, and is already spinning at that speed at reset. Part: box with half extents (0.11, 0.017, 0.018) m, mass 0.065 kg (fixed in code; `object_mass` is not used), friction 0.8, restitution 0.05. At reset its centre is at (-0.08, y0, 0.133) with y0 ~ U(-0.15, -0.12) (first draw), unrotated, with velocity (0, `incoming_speed`, 0). Slot: prismatic fixture, rail centre (0.24, 0.03, 0.10), axis +y, limits +-0.5 m; inside 0.25 x 0.13 m, 0.06 m deep, inner floor at the link origin (z = 0.10), moving mass 0.3 kg. A PD drive (kp 80, kd 8, force limit 8 N) tracks q*(t) = q0 + 0.20 sin(w t) with velocity target `fixture_speed` cos(w t), where w = `fixture_speed` / 0.20 = 0.175 rad/s (period about 35.9 s). q0 ~ U(-0.06, -0.02) m is the second draw at reset; the initial velocity is `fixture_speed` = 0.035 m/s along +y. This is an oscillation of 0.20 m amplitude about q0 with peak speed `fixture_speed`. Its target speed exceeds 0.02 m/s only while |cos(w t)| > 0.02 / `fixture_speed` = 0.571: at this instance t < 5.5 s and 12.45 s < t < 23.45 s. Slot world y = 0.03 + q. No other random values; nothing is drawn after reset. Table friction `table_friction` = 0.08. `radius`, `preview`, `restitution` and the `tool_*` parameters are not used by this task. Horizon `horizon` = 25 s.

The instance's parameters (`s.params()`, SI units): `horizon` = 25, `object_mass` = 0.035, `tool_mass` = 0.2, `tool_half` = 0.07, `radius` = 0.018, `preview` = 0.65, `incoming_speed` = 0.08, `fixture_speed` = 0.035, `restitution` = 0.1, `table_friction` = 0.08, `tool_friction` = 0.3.

**Goal geometry.** Presentation point (0.09, 0.05, 0.24) for the part's centre (moving_presentation), announced at reset as `goal_target`. Lift height: part centre above z = 0.21 m (moving_pickup). Drop limit: part centre must stay at or above z = 0.13 m during moving_presentation, overlapping_grips and donor_release.

## Success (the task's own check)
The task has 5 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **moving_pickup**: the left gripper grips the part (both left-arm fingers, finger links or pads, are in contact with it) at a moment when the part moves faster than 0.025 m/s; this is recorded once. After that, with the left grip still holding, the part's centre rises above z = 0.21 m.
2. **moving_presentation**: while the left gripper still grips the part (both fingers in contact), the part's centre comes within 0.07 m of the presentation point (0.09, 0.05, 0.24) at a moment when the part moves faster than 0.015 m/s.
3. **overlapping_grips**: both grippers grip the part at the same time (both fingers of each hand in contact with it) for 0.08 s without interruption.
4. **donor_release**: the right gripper grips the part (both fingers in contact), no left-arm finger touches the part, and the left gripper is open wider than 0.065 m (sum of its two finger positions), all for 0.12 s without interruption.
5. **receiver_slot_delivery**: the part lies in the moving slot, and the slot moves along its rail faster than 0.02 m/s, for 0.7 s without interruption. The part touches the slot, and neither gripper grips it (a single finger may still touch it). In the slot's frame its centre is within 0.014 m of the slot centre along x (the slot's long axis), within 0.045 m along y, and between 0.01 m and 0.06 m above the slot floor. It moves at less than 0.05 m/s relative to the slot. This completes the task.

The episode **ends by itself** at the first control step where the last phase is complete (success; rows after it are
never executed) or where the task has failed. `s.status()` reports the phase you are in and the failure, if any.

**The task fails** (the episode ends, reward 0) as soon as any of these happens:
- during moving_presentation, overlapping_grips or donor_release, the part's centre drops below z = 0.13 m (`handover_drop`);
- the task's horizon is reached: 25 s of simulated time (`timeout`);
- an object leaves the workspace: its centre falls below z = -0.2 m or gets more than 1.8 m from the world's z axis
  (`out_of_bounds`);
- a forbidden contact or a deep interpenetration (below);
- a safety limit is exceeded (`limit_violation`, below).

**Contacts.** There are no tools. The fingers of either gripper (finger links and pads) may touch the part and nothing else: not the conveyor rollers or frame, not the slot or its rail, not the table. No other robot part (hand or arm links) may touch anything, the part included. The two arms may never touch each other, finger to finger included, and no arm may touch itself. In every task: the two arms (and their tools) never touch each other
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
build. The environment's source, the task included, is in `/opt/pandadyn/panda_dynamics` (`tasks/dual/moving_grasp_handover.py`).

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
