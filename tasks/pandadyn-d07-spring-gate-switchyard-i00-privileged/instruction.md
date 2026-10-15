# Panda Dynamic Scenes · Spring gate switchyard (D07) — frozen instance i00

You control two simulated **Franka Panda** arms (`panda-0` on the left, `panda-1` on the right; each with its standard hand and the task's tool where it has one) in a simulated scene (ManiSkill 3 / SAPIEN, rigid-body CPU PhysX at 1000 Hz) via Python.
**Task:** A low-friction puck slides inside a U-shaped pen of bouncy rails that is open toward the right arm, and a spring-loaded swinging gate stands inside the pen. The left Panda has a bare gripper. It must take hold of the gate with both fingers and swing it open one way. The right Panda's paddle must then hit the puck so that it travels deep into the pen. While the puck runs round, the left hand, still gripping, must swing the gate the other way: at the moment the puck hits the upper (+y) rail, the gate must be at that opposite angle. The right paddle then intercepts the puck. Finally the puck must cross a goal line in front of a backstop on the right arm's side while the gate is still deflected well away from its rest position and the paddle is not touching the puck.

This is a *fixed scene instance*: everything starts the same way after every reset, and you may reset and retry as many
times as you want. Your deliverable is **one replayable trajectory** of the robot's low-level actions, not a general
policy. Things move by themselves from the first control step on: the scene does not wait for the robot.

## Scene
panda-0 (left): base at (-0.55, -0.22, 0), yaw 0 (facing +x). It has no tool and uses the stock Panda parallel gripper: two fingers with a total opening of up to 0.08 m, fully open (0.04 m per finger) at reset. Its tool frame, reported as `panda-0_tool_pose`, is the gripper TCP between the fingertips. At the start the TCP is at (0.04, -0.10, 0.16), pointing straight down (quaternion (0, 1, 0, 0)), with the fingers closing along world y. panda-1 (right): base at (0.74, 0.22, 0), yaw pi (facing -x). It carries a flat rigid paddle, 0.10 m long (2 x `tool_half`, `tool_half` = 0.05 m), 0.05 m tall and 12 mm thick, on a rigid adapter on its back (tool -x) side. The tool frame is the paddle centre, with x normal to its faces, y along its length and z up. The TCP sits 0.12 m behind the paddle centre and 0.04 m above it. Paddle start: centre (0.30, -0.08, 0.045), quaternion (0, 0, 0, 1) (yawed 180 deg, faces normal to world x); its lower edge is then 0.020 m above the table. Role labels in every phase: panda-0 gate_operator, panda-1 preparing_striker.

An orange square puck (44 mm x 44 mm, 24 mm tall) slides on the table with very little friction. At t = 0 it is already moving toward the right arm. Three fixed, very bouncy orange rails, 60 mm tall, form a U-shaped pen open toward the right arm. The far rail is on the left arm's side, and two long side rails run along it: the upper rail on the +y side and the lower rail on the -y side. Inside the pen stands a swinging gate: an amber leaf 0.13 m long, 55 mm tall and 12 mm thick that turns about a vertical hinge at one end. Its lower edge is just above the table, so the puck cannot pass beneath it. A raised orange-red handle block (32 x 24 x 24 mm) sits on the leaf's free end. A weak torsional spring pulls the gate back toward its rest orientation, in which the leaf runs along the world y axis, and the hinge is nearly frictionless. A short, non-bouncy backstop wall (0.14 m wide, 60 mm tall) stands outside the pen, beyond the goal line on the right arm's side. Only the puck moves at the start; the gate moves when pushed and springs back when let go. The table top is the world's z = 0 plane.

Exactly (privileged information, also readable through the tooling): Puck: box 0.044 x 0.044 x 0.024 m, mass `object_mass` = 0.035 kg, friction 0.01, restitution 0.65. At reset it is placed at (0.20, -0.06 + u, 0.0125), with u drawn uniformly in [-0.008, 0.008] m, and velocity (+`incoming_speed`, 0, 0) = (0.35, 0, 0) m/s. Table friction `table_friction` = 0.015. Gate (fixture `gate`; hinge state reported as `gate_state` = [q, dq/dt]): fixed hinge at (0.10, 0.05, 0.015), revolute about world +z, limits [-1.5, 1.5] rad, joint friction 0.0002, joint damping 0.001. A spring drive pulls it toward q = 0 with stiffness 0.015 N m/rad, damping 0.005 N m s/rad and a torque limit of 0.25 N m. At q = 0 the leaf (12 mm x 0.13 m x 55 mm, friction 0.2, restitution 0.35) runs from the hinge toward -y. It spans y from 0.05 to -0.08 at x = 0.10, and z from 0.015 to 0.07. The handle block is centred at (0.10, -0.08, 0.085). Positive q swings the free end toward +x (counter-clockwise seen from above). Reset: q = 0, at rest. Rails (static, friction 0.3, restitution 0.75, 60 mm tall): far_rail is 0.016 x 0.36 m, centred at (-0.12, 0.05, 0.03), spanning y from -0.13 to 0.23. upper_rail is 0.40 x 0.016 m, centred at (0.08, 0.23, 0.03), spanning x from -0.12 to 0.28. lower_rail is 0.40 x 0.016 m, centred at (0.08, -0.15, 0.03). backstop (static, restitution 0.05): 0.02 x 0.14 x 0.06 m, centred at (0.48, 0.15, 0.03). Paddle: `tool_half` = 0.05, `tool_mass` = 0.2 kg, `tool_friction` = 0.3, restitution 0.05. The table top spans x in [-0.54, 0.70] and y in [-0.48, 0.48]. Horizon `horizon` = 35 s. The only random draw is u, made at reset.

The instance's parameters (`s.params()`, SI units): `horizon` = 35, `object_mass` = 0.035, `tool_mass` = 0.2, `tool_half` = 0.05, `radius` = 0.018, `preview` = 0.65, `incoming_speed` = 0.35, `fixture_speed` = 0.04, `restitution` = 0.1, `table_friction` = 0.015, `tool_friction` = 0.3.

**Goal geometry.** Goal line for the puck's centre: x = 0.43, crossed in +x with |y - 0.15| < 0.055 m. It is announced at reset as `goal_goal` = (0.43, 0.15, 0.012). Loop line: the puck's centre must get to x < -0.05. Gate angle thresholds: q > 0.5 rad, q < -0.35 rad and |q| > 0.3 rad.

## Success (the task's own check)
The task has 5 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **left_gate_open**: Two things hold at the same moment. Both fingers of panda-0's gripper (the left finger and the right finger, each counting together with its pad) are in contact with the gate's swinging part (leaf or handle). And the gate angle q exceeds 0.5 rad. q is 0 at the spring's rest orientation and positive when the free end swings toward +x (counter-clockwise seen from above).
2. **right_loop_shot**: The puck touches the right paddle at some moment during this phase; touches before this phase do not count. After that, the puck's centre is at world x < -0.05 while the puck does not touch the right paddle.
3. **gate_reconfiguration**: At one and the same moment, three things hold. Both left fingers touch the gate's swinging part. The gate angle q is below -0.35 rad. And the puck is in contact with the upper rail (the rail on the +y side of the pen).
4. **return_interception**: The puck touches the right paddle.
5. **final_gate_shot**: The puck's centre crosses x = 0.43 moving in +x, with |y - 0.15| < 0.055 m. Moving in +x means x was <= 0.43 on the previous physics step and is > 0.43 now. At that moment the puck must not touch the right paddle, and the gate must be deflected by more than 0.3 rad either way (|q| > 0.3); no grip is required. This completes the task.

The episode **ends by itself** at the first control step where the last phase is complete (success; rows after it are
never executed) or where the task has failed. `s.status()` reports the phase you are in and the failure, if any.

**The task fails** (the episode ends, reward 0) as soon as any of these happens:
- the task's own failure conditions: none (only the rules below apply);
- the task's horizon is reached: 35 s of simulated time (`timeout`);
- an object leaves the workspace: its centre falls below z = -0.2 m or gets more than 1.8 m from the world's z axis
  (`out_of_bounds`);
- a forbidden contact or a deep interpenetration (below);
- a safety limit is exceeded (`limit_violation`, below).

**Contacts.** The gripper fingers and finger pads of either arm may touch the puck and the gate's swinging part (leaf and handle). They must not touch the gate's base, the rails, the backstop, the table or the robot pedestals. The right paddle, including its adapter, may touch only the puck, not the gate, rails, backstop or table. No other robot part, such as the hand or the arm links, may touch anything. The two arms and the paddle must never touch each other, and the paddle must not touch its own arm. In every task: the two arms (and their tools) never touch each other
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
build. The environment's source, the task included, is in `/opt/pandadyn/panda_dynamics` (`tasks/dual/spring_gate_switchyard.py`).

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
  your only budget. A simulated episode ends at the latest at the task's horizon (35 s, 3500 rows).
- One `Session` per process. Stepping runs at roughly 40-150 control steps per second; rendering happens only when a frame
  is asked for and never moves anything. Do not call `s.close()` before writing every output.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **5 GiB of GPU memory**, **16 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`. GPU memory counts what a process reserves (JAX, for example, reserves most of the card unless told not to). These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. When enforcement is on and GPU memory goes above 1.5 times its limit, the monitor also kills the process holding the most of it at once, to protect the machine; that alone does not fail the trial. CPU is capped at 8 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
