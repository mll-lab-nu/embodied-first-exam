# Panda Dynamic Scenes · Lever launch, catch and reload (D09) — frozen instance i00

You control two simulated **Franka Panda** arms (`panda-0` on the left, `panda-1` on the right; each with its standard hand and the task's tool where it has one) in a simulated scene (ManiSkill 3 / SAPIEN, rigid-body CPU PhysX at 1000 Hz) via Python.
**Task:** A ball starts in the right arm's cup. The right arm must load it into the small basket of a passive see-saw launcher and move its cup away. The left arm, holding a mallet, must strike the lever so that the ball is flung up into free flight, and the right arm must catch it in its cup. The right arm then loads the ball into the basket a second time and clears away, and the left arm launches it again. In the end the ball must come to rest inside an open box that slides back and forth on a rail, while the box is moving. The left arm's mallet must never touch the ball.

This is a *fixed scene instance*: everything starts the same way after every reset, and you may reset and retry as many
times as you want. Your deliverable is **one replayable trajectory** of the robot's low-level actions, not a general
policy. Things move by themselves from the first control step on: the scene does not wait for the robot.

## Scene
Two Pandas facing each other along x. panda-0 (left): base at (-0.44, -0.23, 0), yaw 0 (facing +x). Its tool is a mallet: a solid block 50 x 50 x 30 mm (along tool x, y, z), with the tool frame at its centre and axes parallel to the hand's when the hand points straight down (x forward, z up). The mallet is carried on an L-shaped side adapter of 12 mm square bars that runs forward from beside the hand, then sideways, then down onto the mallet's top near its -y edge. The mallet centre is 0.12 m ahead of the gripper TCP along tool x, 0.13 m to its tool +y side and 0.075 m below it. Start: mallet centre at (0.16, -0.11, 0.28), tool axes aligned with the world. panda-1 (right): base at (0.74, 0.23, 0), yaw pi (facing -x). Its tool is an open-top square cup: inside 0.14 x 0.14 m (2 x `tool_half`, 0.07 at this instance), walls 55 mm high and 5 mm thick on all four sides, 5 mm floor. The tool frame is the centre of the inside floor surface, z up, x pointing away from the arm's own base. With the cup level the hand points straight down and the cup's floor centre is 0.12 m ahead of the TCP along tool x and 0.04 m below it. The grey adapter enters at the middle of the cup's back (tool -x) wall: a 12 mm wide post protrudes 6 mm into the cup from the floor up to 35 mm, and a bar protrudes 12 mm into the cup between 29 and 41 mm above the floor. Start: cup floor centre at (0.12, 0.17, 0.26), level, rotated 180 deg about z (tool x = world -x). Wrist joints 5-7 of both arms use higher damping gains (24, 20, 14 instead of the default 12, 10, 7). Role labels per phase (left, right): physical_loading: cleared_striker, loader; first_launch: striker, preparing_catcher; right_catch: cleared_striker, catcher; reload_and_clear: cleared_striker, reloader; second_launch: striker, cleared_loader; moving_receptacle_retention: cleared_striker, cleared_loader.

A small orange ball (radius 18 mm) starts at rest on the floor of the right arm's cup. A passive see-saw launcher stands in the middle of the table on an orange square post (the same orange as the ball). The launcher is blue: a lever on a horizontal hinge parallel to world y. At the lever's end on the left arm's side (-x) sits a small square basket (54 mm inside, 12 mm walls). On the other side of the hinge a side arm reaches toward -y to a strike pad (36 x 50 mm), which is held a few centimetres above the lever on a spring and can be pushed down by up to 30 mm. Pushing or striking the pad side down rotates the lever and swings the basket end upward along an arc around the hinge; stops limit the lever's travel. At rest the lever lies horizontal on its lower stop, because the basket side is heavier and a weak return spring also pulls it back to that position. Beyond the launcher, on the right arm's side, a blue open box (0.15 x 0.15 m inside, 0.06 m deep) rides a straight rail along y. The box is driven back and forth along the rail in a smooth sinusoidal oscillation by itself for the whole episode: slowly, and slowest where it turns around. The table top is the world's z = 0 plane.

Exactly (privileged information, also readable through the tooling): Ball: radius `radius` = 0.018 m, mass `object_mass` = 0.035 kg, restitution 0.1, friction 0.2. At reset it is placed at rest at the right tool frame's actual position + (0, 0, `radius` + 0.0005), i.e. on the centre of the cup floor (about (0.12, 0.17, 0.2785)). Launcher: a static pedestal 52 x 52 x 80 mm centred at (0.12, 0, 0.04), and on top of it the fixed lever base block (40 x 40 x 30 mm, centred (0.12, 0, 0.095)). Lever hinge at (0.12, 0, 0.13), axis world +y, limits q in [0, 1.2] rad; positive q lowers the +x (pad) side and raises the -x (basket) side. Reset at q = 0 with zero velocity. Lever link 'lever' (mass 0.07 kg), in its frame (origin on the hinge, x along the beam): beam 0.18 x 0.05 x 0.016 m spanning x in [-0.12, 0.06]; basket (54 x 54 mm inside, 12 mm walls) centred at (-0.12, 0) with its floor top at local z = 0.012, i.e. at world (0, 0, 0.142) when q = 0 (this is the announced `goal_target`); a 36 mm wide side arm at x = 0.04 running to y = -0.075 (`pad_offset` = -0.075). Pad link 'lever_pad' (36 x 50 x 12 mm, 8 g) sits on a prismatic joint along lever-local z at lever-local (0.04, -0.075, 0.045) (world about (0.16, -0.075, 0.175) at q = 0), with travel [-0.030, +0.002] m and a spring drive toward 0 (stiffness 80 N/m, damping 0.2, force limit 3 N). Lever return spring: hinge drive toward q = 0 with stiffness 0.008, damping 0.002 and effort limit 0.12; there is no other drive. Box ('cart'): prismatic fixture, rail centre (0.28, -0.03, 0.025), axis +y, limits +-0.5 m; inside 0.15 x 0.15 m, 0.06 m deep, inner floor at the link origin (z = 0.025 at the rail centre), moving mass 0.3 kg. A PD drive (kp 80, kd 8, force limit 8 N) tracks q*(t) = offset + 0.20 sin(w (t + shift)) with velocity target `fixture_speed` cos(w (t + shift)), where w = `fixture_speed` / 0.20 = 0.2 rad/s (period about 31.4 s). At reset: offset ~ U(-`fixture_offset`, +`fixture_offset`) = U(-0.025, 0.025) m is the first draw. Only if `fixture_phase` > 0 is a phase phi ~ U(-`fixture_phase`, +`fixture_phase`) drawn second, with shift = phi / w; at nominal `fixture_phase` = 0, so there is no draw and phi = shift = 0. The box starts at q = offset + 0.20 sin(phi) with dq/dt = `fixture_speed` cos(phi): at nominal q = offset, moving +y at `fixture_speed` = 0.04 m/s. This is an oscillation of 0.20 m amplitude about the offset with peak speed `fixture_speed`. Its target speed exceeds 0.02 m/s only while |cos(w (t + shift))| > 0.5: at this instance t < 5.2 s and 10.5 s < t < 20.9 s (the next window starts at 26.2 s, after the horizon). Box world y = -0.03 + q. No other random values; nothing is drawn after reset. Tools: `tool_mass` = 0.2 kg each, friction `tool_friction` = 0.3, restitution 0.05. Table friction `table_friction` = 0.08. `incoming_speed`, `preview` and `restitution` are not used by this task. Horizon `horizon` = 25 s.

The instance's parameters (`s.params()`, SI units): `horizon` = 25, `object_mass` = 0.035, `tool_mass` = 0.2, `tool_half` = 0.07, `radius` = 0.018, `preview` = 0.65, `incoming_speed` = 0.35, `fixture_speed` = 0.04, `fixture_offset` = 0.025, `fixture_phase` = 0, `restitution` = 0.1, `table_friction` = 0.08, `tool_friction` = 0.3.

**Goal geometry.** Clearance point (0, 0, 0.18): in physical_loading and reload_and_clear the right cup's tool frame must finally be more than 0.16 m from it. Launch height: in first_launch and second_launch the ball centre must be above z = 0.20 m. `goal_target`, the centre of the basket floor with the lever at rest, is announced at reset in the state. It does not depend on the seed but gives away the launcher's location: privileged mode only. The box's seeded rail offset (and phase, when `fixture_phase` > 0) is not announced.

## Success (the task's own check)
The task has 6 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **physical_loading**: the ball rests in the launcher's basket for 0.1 s without interruption. During that time the ball touches the lever (the lever link, basket included) and does not touch the right cup, and the lever is near horizontal (|q| < 0.12 rad). In the lever's frame (origin on the hinge axis, x along the beam toward the pad side, z normal to the beam), the ball centre is within 0.021 m horizontally of the basket centre (x, y) = (-0.12, 0) and between 0.024 m and 0.044 m above the hinge plane (the basket floor is at 0.012 m, so a resting ball sits at 0.030 m). The ball also moves at less than 0.08 m/s relative to the lever's centre-of-mass velocity. This is recorded once. After that, the right cup's tool frame must be more than 0.16 m away from the clearance point (0, 0, 0.18) (the ball need not still be in the basket at that moment).
2. **first_launch**: the left mallet (any part of panda-0's tool link) touches the lever or its pad; the first such contact in this phase is recorded. After that, the ball has touched nothing for more than 0.04 s while its centre is higher than z = 0.20 m.
3. **right_catch**: the ball drops into the right cup from free flight and stays there. Measured in the cup's tool frame, its centre crosses downward through the plane 0.073 m above the cup floor (wall height 0.055 m + radius), within 0.052 m (half width - radius) of the cup centre along both x and y, after the ball has touched nothing for at least 0.025 s. After that crossing the ball must stay retained in the cup for 0.18 s without interruption. Retained means: its centre is at least 0.45 x radius inside the inner walls (|x|, |y| < 0.0619 m in the tool frame) and between 0.014 m and 0.0528 m above the cup floor; it has touched the cup within the last 25 ms; and it moves at less than 0.09 m/s relative to the cup (the cup's rigid-body velocity at the ball's position).
4. **reload_and_clear**: the same as physical_loading, counted again only within this phase. The ball rests in the basket for 0.1 s without interruption: it touches the lever and not the right cup, |q| < 0.12 rad, its centre is within 0.021 m of the basket centre and 0.024-0.044 m above the hinge plane in the lever frame, and its speed relative to the lever is < 0.08 m/s. After that, the right cup's tool frame must be more than 0.16 m from (0, 0, 0.18).
5. **second_launch**: the same as first_launch, counted again only within this phase: the left mallet touches the lever or its pad, and after that the ball has touched nothing for more than 0.04 s while its centre is higher than z = 0.20 m.
6. **moving_receptacle_retention**: the ball is inside the moving box, and the box moves along its rail faster than 0.02 m/s, for 0.7 s without interruption. Inside means: in the box's frame the ball centre is at least 0.45 x radius inside the inner walls (|x|, |y| < 0.0669 m from the box centre) and between 0.014 m and 0.0578 m above the box floor; the ball has touched the box within the last 25 ms; and it moves at less than 0.09 m/s relative to the box. This completes the task.

The episode **ends by itself** at the first control step where the last phase is complete (success; rows after it are
never executed) or where the task has failed. `s.status()` reports the phase you are in and the failure, if any.

**The task fails** (the episode ends, reward 0) as soon as any of these happens:
- at any time, the ball touches the left arm's mallet tool (any part of its tool link, adapter included) (`direct_ball_hit`);
- the task's horizon is reached: 25 s of simulated time (`timeout`);
- an object leaves the workspace: its centre falls below z = -0.2 m or gets more than 1.8 m from the world's z axis
  (`out_of_bounds`);
- a forbidden contact or a deep interpenetration (below);
- a safety limit is exceeded (`limit_violation`, below).

**Contacts.** The right cup (whole tool link) may touch the ball, the lever and the strike pad. The left mallet (whole tool link) may touch the lever and the pad, and by this task's rule never the ball (direct_ball_hit). Neither tool may touch the lever's base block, the orange pedestal, the moving box or its rail and base, or the table. No other robot part, the fingers included, may touch anything. The two arms and their tools may never touch each other, and no arm may touch itself. In every task: the two arms (and their tools) never touch each other
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
build. The environment's source, the task included, is in `/opt/pandadyn/panda_dynamics` (`tasks/dual/lever_launch_catch_reload.py`).

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
