# Panda Dynamic Scenes · Strike, catch and merge two balls (D02) — frozen instance i00

You control two simulated **Franka Panda** arms (`panda-0` on the left, `panda-1` on the right; each with its standard hand and the task's tool where it has one) in a simulated scene (ManiSkill 3 / SAPIEN, rigid-body CPU PhysX at 1000 Hz) via Python.
**Task:** Two small balls wait behind closed shutters near the top of two parallel inclined lanes. The shutters open by themselves, the first shortly after the start and the second a few seconds later, and each released ball rolls down its lane and flies off the open lower end. The left Panda's paddle must touch each ball after the ball has flown free. The right Panda's cup must catch the first ball and carry it away from the catch point without losing it. The cup must then catch the second ball while still holding the first, and finally put both balls into a fixed basin, where they must come to rest with the cup no longer touching them.

This is a *fixed scene instance*: everything starts the same way after every reset, and you may reset and retry as many
times as you want. Your deliverable is **one replayable trajectory** of the robot's low-level actions, not a general
policy. Things move by themselves from the first control step on: the scene does not wait for the robot.

## Scene
panda-0 (left): base at (-0.55, -0.22, 0), yaw 0 (facing +x). It carries a flat rigid paddle, 0.14 m long (2 x `tool_half`, `tool_half` = 0.07 m), 0.05 m tall and 12 mm thick. A side adapter runs forward from the hand and then sideways to the paddle's -y end. The tool frame is the paddle's centre, with x normal to its faces, y along its length and z up. The hand's TCP sits 0.12 m behind the paddle centre (tool -x), 0.14 m to the tool -y side and 0.04 m above it. Start: paddle centre at (0.10, -0.21, 0.22), orientation identity (faces normal to world x, length along world y). panda-1 (right): base at (0.74, 0.22, 0), yaw pi (facing -x). It carries an open-top square cup, 0.14 m x 0.14 m inside (2 x `tool_half`), with four 0.055 m high, 5 mm thick walls and a 5 mm floor, held by an adapter on its tool -x wall. The tool frame is the centre of the cup floor's inner surface, z up out of the cup. The TCP sits 0.12 m along tool -x and 0.04 m above the tool frame. Start: cup frame at (0.19, 0.17, 0.18), quaternion (0, 0, 0, 1) (yawed 180 deg: tool x = world -x, tool y = world -y, cup upright). Role labels (panda-0 / panda-1) by phase: first_redirect striker / receiver; first_catch cleared_striker / catcher; loaded_cup_relocation preparing_striker / loaded_carrier; second_redirect striker / loaded_receiver; second_catch cleared_striker / two_ball_catcher; both_delivery cleared_partner / deliverer.

Two identical small orange balls (radius 16 mm) start at rest: ball1 in the lane on the -y side, ball2 in the lane on the +y side. Each lane is a straight grey gravity channel with a 70 mm wide, low-friction floor and 22 mm side walls. The lanes are open at both ends, stand on posts above the table and slope down toward +x. Near the upper end of each lane an amber shutter blocks the ball, and a small fixed housing block stands beside each shutter. The shutters are motor-driven and lift by themselves: ball1's shutter opens shortly after the start and ball2's a few seconds later (the exact time varies from instance to instance). Each released ball rolls down its lane and leaves the lower end in free flight. A fixed blue open-top basin, 0.16 m x 0.16 m inside and 0.075 m deep, stands on posts above the table. Nothing else moves by itself. The table top is the world's z = 0 plane.

Exactly (privileged information, also readable through the tooling): Balls ball1 and ball2: radius 0.016 m, mass 0.025 kg (hard-coded; `object_mass` is not used), restitution 0.1, friction 0.2. At reset both are placed at rest at (-0.19, y, 0.377), y = -0.09 for ball1 and y = +0.09 for ball2, on the lane floor just upstream of the shutter. Lanes lane0 (y = -0.09) and lane1 (y = +0.09) are static gravity channels. Each floor's top surface runs from (-0.22, y, 0.37) down to (0.06, y, `lane_end_z`) = (0.06, y, 0.28), a slope of about 17.8 deg. Floor half-width 0.035 m; side walls 8 mm thick and 0.022 m high, centred at +-0.039 m from the lane axis; friction 0.1; both ends open. `lane_end_jitter` = 0, so no lane draw is made. Release gates gate0 and gate1 are prismatic shutters, 10 mm (x) x 58 mm (y) x 50 mm (z), with their lower edge at (-0.16, y, 0.358). They lift along world +z with 0 to 0.06 m of travel. Each gate's fixed housing block (36 x 28 x 70 mm) sits 0.09 m to the +y side of its shutter. Gate drive: PD with kp 60, kd 6 and a 3 N force limit. Each gate is held closed (target 0) until its release time t_i. After that its target rises as 0.22 x (t - t_i) m (velocity target 0.22 m/s) until the 0.06 m limit. Release times: t_1 = `first_release` = 0.25 s (`first_release_jitter` = 0, no draw). t_2 = `second_release` + U(-`second_release_jitter`, +`second_release_jitter`) = 3.8 + U(-0.12, 0.12) s, drawn at reset (stored in flag `release_times`, not in the observation). Basin: static container with floor top surface centre at (0.20, 0.32, 0.08); inner half-size 0.08 x 0.08 m; wall height 0.075 m (rim at z = 0.155); 5 mm walls; friction 0.4; restitution 0.03. Tools: `tool_half` = 0.07 for both, `tool_mass` = 0.2 kg, `tool_friction` = 0.3, tool restitution 0.05. `table_friction` = 0.08. Horizon `horizon` = 25 s. `radius` = 0.016 is the radius used by the predicates. Unused here: `incoming_speed`, `fixture_speed`, `preview`, `restitution`, `object_mass`. The only random draw is the t_2 offset.

The instance's parameters (`s.params()`, SI units): `horizon` = 25, `object_mass` = 0.035, `tool_mass` = 0.2, `tool_half` = 0.07, `radius` = 0.016, `preview` = 0.65, `incoming_speed` = 0.35, `fixture_speed` = 0.04, `restitution` = 0.1, `table_friction` = 0.08, `tool_friction` = 0.3, `first_release` = 0.25, `first_release_jitter` = 0, `second_release` = 3.8, `second_release_jitter` = 0.12, `lane_end_z` = 0.28, `lane_end_jitter` = 0.

**Goal geometry.** All goal geometry is relative to the cup, the paddle or the basin. `goal_target` = (0.22, 0.02, 0.18) is announced at reset in the observation, but no phase condition uses it.

## Success (the task's own check)
The task has 6 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **first_redirect**: At some moment during this phase, ball1 has flown free (touching nothing at all) for more than 0.025 s. After that, it touches the left paddle (panda-0's tool). Where the ball goes after the touch is not checked.
2. **first_catch**: ball1 enters the right cup (panda-1's tool) from above and is retained. The entry: after touching nothing for at least 0.025 s, the ball's centre passes downward through the plane 0.071 m above the cup floor (wall height 0.055 m + radius 0.016 m, in the cup's frame). At that crossing the centre must be within 0.054 m (`tool_half` - radius) of the cup centre along both cup x and cup y. From then on the ball must stay contained in the cup for 0.18 s without interruption. Contained in the cup means all of the following, in the cup's frame: |x| and |y| of the ball centre below 0.0628 m (`tool_half` - 0.45 x radius); height above the cup floor between 0.012 m and 0.0531 m; in contact with the cup within the last 25 ms; moving at less than 0.09 m/s relative to the cup (including the cup's rotation). The free-flight time counts only from the start of this phase. The cup's position when this phase completes is recorded as the catch position.
3. **loaded_cup_relocation**: With ball1 contained in the right cup (as defined in first_catch), the cup's tool-frame origin is more than 0.06 m from the recorded catch position.
4. **second_redirect**: At some moment during this phase, ball2 has flown free (touching nothing) for more than 0.025 s; only free flight while this phase is active counts. After that, ball2 touches the left paddle. Where the ball goes after the touch is not checked.
5. **second_catch**: ball2 enters the right cup from above and is retained exactly as in first_catch. That is: an entry after at least 0.025 s of free flight (counted from the start of this phase), crossing downward through the plane 0.071 m above the cup floor within 0.054 m of the cup centre on both axes, then contained in the cup for 0.18 s without interruption. At that moment ball1 must also be contained in the cup.
6. **both_delivery**: Both balls are contained in the basin and neither touches the cup, for 0.7 s without interruption. Contained in the basin means all of the following, in the basin's frame (origin at the centre of its floor's top surface, axes = world axes): |x| and |y| of the ball centre below 0.0728 m (0.08 - 0.45 x radius); height above the basin floor between 0.012 m and 0.0731 m; in contact with the basin within the last 25 ms; speed below 0.09 m/s. This completes the task.

The episode **ends by itself** at the first control step where the last phase is complete (success; rows after it are
never executed) or where the task has failed. `s.status()` reports the phase you are in and the failure, if any.

**The task fails** (the episode ends, reward 0) as soon as any of these happens:
- during loaded_cup_relocation, second_redirect and second_catch, ball1's centre leaves the cup's interior footprint or drops low. In the right cup's frame, that is |x| or |y| greater than 0.07 m (`tool_half`), or more than 0.01 m below the cup floor surface (`first_ball_spill`);
- the task's horizon is reached: 25 s of simulated time (`timeout`);
- an object leaves the workspace: its centre falls below z = -0.2 m or gets more than 1.8 m from the world's z axis
  (`out_of_bounds`);
- a forbidden contact or a deep interpenetration (below);
- a safety limit is exceeded (`limit_violation`, below).

**Contacts.** The paddle and the cup may touch only the two balls. Neither tool may touch the lanes or their support posts, the shutters or their housing blocks, the basin or its posts, the table, or the robot pedestals. No other robot part, the fingers included, may touch anything. The two arms and their tools must never touch each other, and a tool must not touch its own arm. In every task: the two arms (and their tools) never touch each other
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
build. The environment's source, the task included, is in `/opt/pandadyn/panda_dynamics` (`tasks/dual/strike_catch_merge.py`).

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
You may install packages you need (pip, apt). Please solve the task yourself: do not look up or download a solution to it, such as this benchmark's own source code, published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **5 GiB of GPU memory**, **16 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`. GPU memory counts what a process reserves (JAX, for example, reserves most of the card unless told not to). These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. When enforcement is on and GPU memory goes above 1.5 times its limit, the monitor also kills the process holding the most of it at once, to protect the machine; that alone does not fail the trial. CPU is capped at 8 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
