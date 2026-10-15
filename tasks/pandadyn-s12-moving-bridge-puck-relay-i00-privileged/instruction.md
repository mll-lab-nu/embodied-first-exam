# Panda Dynamic Scenes · Spinning bridge puck relay and goal (S12) — frozen instance i00

You control one simulated **Franka Panda** arm (7 joints, its standard hand, and the task's tool where it has one) in a simulated scene (ManiSkill 3 / SAPIEN, rigid-body CPU PhysX at 1000 Hz) via Python.
**Task:** At the start a square puck is sliding along a raised source lane towards the Panda's paddle. Strike it so that it slides onto a platform (the bridge) that spins continuously about a vertical axis, and from the bridge onto an exit lane. Intercept it there with the paddle, strike it again, and send it along the exit lane past a hinged, partly open gate, across a goal line, without the paddle touching it as it crosses and with the gate still open.

This is a *fixed scene instance*: everything starts the same way after every reset, and you may reset and retry as many
times as you want. Your deliverable is **one replayable trajectory** of the robot's low-level actions, not a general
policy. Things move by themselves from the first control step on: the scene does not wait for the robot.

## Scene
One Panda, base at (-0.55, 0, 0) facing +x (yaw 0). Its hand carries a paddle: a flat rigid plate 12 mm thick, 0.10 m wide (2 x `tool_half`) and 50 mm tall, whose face normal is the tool frame's x axis, attached by a fixed adapter bar. The tool frame is the paddle's centre. In the tool frame the hand's TCP is at (-0.12, 0, +0.04). At the start the paddle is upright with identity orientation (faces along world x, width along world y), centre at (-0.08, -0.15, 0.075).

The puck is an orange square block 44 mm x 44 mm x 24 mm thick, quite bouncy. At t = 0 it is sliding towards the paddle on the source lane, a low, very slippery orange slab. If nothing touches it, it slows and stops on the lane shortly before reaching the paddle's start position. Next to the lane's end, a blue rectangular platform (the bridge, 0.20 m x 0.10 m, 20 mm thick) turns continuously about a vertical axis through its centre at a steady slow rate, counterclockwise seen from above. Its top is 2 mm lower than the source lane. Beyond it lies the exit lane, a second slippery orange slab 2 mm lower again. Near the exit lane's far end a hinged gate stands on one side edge: a vertical amber blade 0.12 m long and 55 mm tall with a small knob on its free end. At the start it is swung partly open and still reaches partway across the lane. A very weak spring pulls it towards closed, but the blade's lower edge rests on the lane surface, so it hardly moves unless pushed. Past the end of the exit lane, on the table, is the goal line, with a static orange wall (the backstop, 0.14 m wide, 8 cm tall) behind it. The table top is the world's z = 0 plane.

Exactly (privileged information, also readable through the tooling): Puck: box with half extents (0.022, 0.022, 0.012), mass `object_mass` (0.035 kg), friction 0.15, restitution 0.5. At reset it is at (0.06, -0.13 + dy, 0.0465) with velocity (-`incoming_speed`, 0, 0) = -0.35 m/s along x; dy ~ U(-0.012, 0.012) is drawn at reset (first draw). In an idle run it stopped at x of about -0.024 after about 0.4 s, with no paddle contact. Source lane `source_lane`: static slab 0.28 x 0.145 x 0.024 m centred at (-0.08, -0.1175, 0.022), top z = 0.034, spanning x -0.22 to 0.06 and y -0.19 to -0.045, friction 0.025. Bridge `bridge`: revolute fixture with a vertical axis through (0.18, -0.05). The platform 0.20 x 0.10 x 0.02 m is centred on the axis, top at z = 0.032, mass 0.20 kg; at q = 0 its long side is along world x. At reset q0 ~ U(-0.15, 0.15) (second draw), with angular velocity 0.35 rad/s. It is then driven at a constant rate: target q0 + 0.35 t rad, target velocity 0.35 rad/s (PD, kp 80, kd 8, at most 0.5 N m); positive is counterclockwise from above, period of about 17.95 s. Exit lane `exit_lane`: static slab 0.32 x 0.11 x 0.028 m centred at (0.25, 0.12, 0.016), top z = 0.030, spanning x 0.09 to 0.41 and y 0.065 to 0.175, friction 0.04. Gate `gate`: hinge at (0.37, 0.18, 0.03) about world z. The blade is 0.012 x 0.12 x 0.055 m, running from the hinge towards -y at q = 0 (closed: right across the lane), bottom edge at z = 0.03, friction 0.2, restitution 0.35. A knob 0.032 x 0.024 x 0.024 m sits over the blade tip at z = 0.10. Limits [0, 1.3] rad; reset to q = 1.1 rad at rest, with the blade tip at about (0.477, 0.126). Its passive spring drive has target 0, kp 0.00012 N m/rad, kd 0.005 N m s/rad and a cap of 0.25 N m; joint friction 0.00008, damping 0.001. The blade rests on the exit lane's top. In an idle run q stayed at 1.10 for the whole 32 s. Backstop `goal_backstop`: static box 0.02 x 0.14 x 0.08 m centred at (0.54, 0.12, 0.04). Table friction `table_friction` (0.015 in this task). Paddle: `tool_half` 0.05, `tool_mass` 0.2 kg, `tool_friction` 0.3. Horizon `horizon` = 32 s. `goal` = (0.48, 0.12, 0.043) (fixed).

The instance's parameters (`s.params()`, SI units): `horizon` = 32, `object_mass` = 0.035, `tool_mass` = 0.2, `tool_half` = 0.05, `radius` = 0.018, `preview` = 0.65, `incoming_speed` = 0.35, `fixture_speed` = 0.04, `restitution` = 0.1, `table_friction` = 0.015, `tool_friction` = 0.3.

**Goal geometry.** Goal line: x = 0.48 (world), crossed towards +x with the puck's centre within 0.045 m of y = 0.12. It is announced at reset as `goal_goal` = (0.48, 0.12, 0.043); the z value is not used. Gate angle threshold: more than 0.20 rad at the crossing.

## Success (the task's own check)
The task has 5 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **incoming_strike**: The paddle touches the puck.
2. **physical_bridge_transfer**: During this phase the puck touches the bridge platform at least once. After that, at some step, the puck touches the exit lane while not touching the bridge.
3. **exit_interception**: The paddle touches the puck.
4. **second_strike**: In this phase the puck first loses contact with the paddle, at time t_s (the first step of the phase without paddle contact; t_s is not reset afterwards). Later the paddle touches the puck again at a time more than 0.035 s after t_s.
5. **closing_gate_goal**: The puck's centre crosses the goal line x = 0.48 (world) moving towards +x between two consecutive physics steps, with its centre within 0.045 m of y = 0.12. At that step the puck does not touch the paddle and the gate's angle is more than 0.20 rad (open). This completes the task. A crossing that fails either check ends the task as a failure.

The episode **ends by itself** at the first control step where the last phase is complete (success; rows after it are
never executed) or where the task has failed. `s.status()` reports the phase you are in and the failure, if any.

**The task fails** (the episode ends, reward 0) as soon as any of these happens:
- in closing_gate_goal, the puck crosses the goal line (as defined there) while touching the paddle or while the gate's angle is 0.20 rad or less (`closed_gate_or_carried_puck`);
- the task's horizon is reached: 32 s of simulated time (`timeout`);
- an object leaves the workspace: its centre falls below z = -0.2 m or gets more than 1.8 m from the world's z axis
  (`out_of_bounds`);
- a forbidden contact or a deep interpenetration (below);
- a safety limit is exceeded (`limit_violation`, below).

**Contacts.** Only the paddle may touch the puck, and the paddle may touch nothing but the puck: not the lanes, the bridge, the gate, the backstop or the table. No other part of the robot (fingers, hand, links, base) may touch anything. In every task: the two arms (and their tools) never touch each other
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
build. The environment's source, the task included, is in `/opt/pandadyn/panda_dynamics` (`tasks/single/moving_bridge_puck_relay.py`).

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
  your only budget. A simulated episode ends at the latest at the task's horizon (32 s, 3200 rows).
- One `Session` per process. Stepping runs at roughly 40-150 control steps per second; rendering happens only when a frame
  is asked for and never moves anything. Do not call `s.close()` before writing every output.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **5 GiB of GPU memory**, **16 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`. GPU memory counts what a process reserves (JAX, for example, reserves most of the card unless told not to). These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. When enforcement is on and GPU memory goes above 1.5 times its limit, the monitor also kills the process holding the most of it at once, to protect the machine; that alone does not fail the trial. CPU is capped at 8 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
