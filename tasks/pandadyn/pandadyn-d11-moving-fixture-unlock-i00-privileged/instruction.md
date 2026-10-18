# Panda Dynamic Scenes · Moving fixture unlock (D11) — frozen instance i00

You control two simulated **Franka Panda** arms (`panda-0` on the left, `panda-1` on the right; each with its standard hand and the task's tool where it has one) in a simulated scene (ManiSkill 3 / SAPIEN, rigid-body CPU PhysX at 1000 Hz) via Python.
**Task:** The left gripper starts around the handle of a free, hand-held fixture: a short channel with a ball inside, closed at its front by a spring-loaded latch gate, with a square socket on its side above the latch's push button. The left arm must grip the fixture and move it off its stand. While the fixture is still moving, the right arm must insert its peg into the socket, press the latch button down with the peg until the gate opens, and then pull the peg back out while the left hand keeps holding the fixture. The ball must then leave the fixture, run down a fixed inclined chute and come to rest in a basin at the chute's foot. The fixture must never be dropped.

This is a *fixed scene instance*: everything starts the same way after every reset, and you may reset and retry as many
times as you want. Your deliverable is **one replayable trajectory** of the robot's low-level actions, not a general
policy.

## Scene
Two Pandas facing each other along x. panda-0 (left): base at (-0.55, -0.22, 0), yaw 0 (facing +x), no tool: its tool frame is the gripper TCP (the point between the fingertips). It starts with the TCP at (-0.063, 0, 0.285), pointing straight down (TCP x = world +x, fingers closing along world y). Its fingers start open 0.0175 m each (0.035 m total aperture), straddling the fixture's 34 mm wide handle without gripping it. For this arm the finger servo is stiffer than the default (finger PD gains kp 1875 N/m and kd 8 instead of 300 and 12; the force is still capped at 15 N per finger). Its fingers also follow their own trajectory, not synchronized with the arm joints. panda-1 (right): base at (0.74, 0.22, 0), yaw pi (facing -x). Its tool is a square peg, 16 x 16 mm in section and 70 mm long, hanging straight down from the tool frame: the tool frame is at the peg's top end and the tip is at tool-frame (0, 0, -0.07). A grey adapter (a horizontal bar from the hand and a short post) ends about 5 cm behind the peg on the hand side; peg and adapter form one rigid tool link. With the peg vertical the hand points straight down and the peg's top is 0.12 m ahead of the gripper TCP along tool x and 0.04 m below it. Start: tool frame at (0.12, 0.15, 0.40), peg vertical, rotated 180 deg about z (tool x = world -x), so the tip is at (0.12, 0.15, 0.33). Role labels per phase (left, right): moving_fixture_presentation: fixture_support, tracking_pin; relative_pin_insertion: moving_fixture_support, pin_inserter; mechanical_latch_open: fixture_support, latch_operator; follow_and_withdraw: outlet_operator, withdrawing_pin; gravity_delivery: outlet_support, cleared_pin.

The fixture is a free rigid body, not attached to anything. At the start it rests level on a small orange stand plate carried by two thin grey posts. It is a blue channel running along x: a flat floor between two side walls 56 mm apart and 45 mm high. At its back (-x) end is a small handle block (16 mm along x, 34 mm wide, 28 mm tall). At its front (+x) end the floor stops short of the walls' ends, leaving an exit opening. An orange spring-loaded latch closes this exit with a 20 mm high gate standing just beyond the floor's end. The latch slides along the fixture's own vertical axis by up to 26 mm. Its push button sits right under a square socket (28 mm opening, 30 mm tall, 16 mm walls) that is fixed to the fixture beside the channel's front end on its +y side, above the wall. Pushing the button down lowers the gate below the floor and opens the exit, and a spring pushes the latch back up when released. An orange ball (radius 16 mm) lies loose on the channel floor behind the gate. Fixed in the scene are a grey inclined chute (an open channel, 66 mm wide inside, 22 mm walls) running downhill toward +x, and at its lower end a blue open basin (0.13 m along x by 0.12 m inside, 40 mm deep). Nothing moves by itself. The table top is the world's z = 0 plane.

Exactly (privileged information, also readable through the tooling): Fixture: free-root articulation. Its root link 'fixture' (mass 0.14 kg) is placed at reset at (0.02, 0, 0.26), unrotated, at rest; this start position is the reference for moving_fixture_presentation. In the fixture frame (origin on the channel floor's top surface): floor x in [-0.07, 0.02], |y| <= 0.028, top at z = 0; side walls at y = +-0.034 (12 mm thick, inner faces at +-0.028), x in [-0.068, 0.068], z in [-0.005, 0.045]; handle block x in [-0.091, -0.075], |y| <= 0.017, z in [0.011, 0.039]; socket: square ring with opening x in [0.006, 0.034], y in [0.051, 0.079] (axis at (0.020, 0.065)), z in [0.06, 0.09] (top face at z = 0.09). Latch link 'fixture_latch' (mass 0.025 kg): prismatic along fixture z, q in [-0.026, 0] m (q < 0 means pressed down), joint friction 0.04, damping 0.08. Its spring drive pulls toward q = 0 with stiffness 35 N/m, damping 0.2 and force limit 0.6 N; there is no other drive. Reset q = 0. Latch parts at q = 0, in the fixture frame: gate x in [0.020, 0.030], |y| <= 0.03, z in [0, 0.02]; connecting bar x in [0.017, 0.033], y in [0, 0.07], z in [0, 0.01]; button 22 x 22 x 16 mm centred (0.020, 0.065, 0.049) (top at z = 0.057, 3 mm below the socket). Stand: static plate 60 x 48 x 6 mm centred (0, 0, 0.247) (top at z = 0.25) on two posts at x = +-0.0195. Ball: radius 0.016 m, mass 0.025 kg, restitution 0.05, friction 0.2. At reset it is placed at rest at world (-0.008 + dx, dy, 0.277), with dx ~ U(-0.006, 0.006) drawn first and dy ~ U(-0.004, 0.004) drawn second (the only random draws; nothing is drawn later). That is fixture-local x about -0.028, 1 mm above the floor. Chute: static; its floor's top surface runs along the segment from (0.15, 0.13, 0.205) down to (0.33, 0.13, 0.08); 66 mm wide inside, 22 mm walls, friction 0.12. Basin: static open box, inner floor centre at (0.38, 0.13, 0.02), inside 0.13 (x) x 0.12 (y) m, 40 mm deep, friction 0.4. Announced `goal_target` = (0.06, 0.065, 0.335) (unused by the predicates). Peg tool: `tool_mass` = 0.2 kg, friction `tool_friction` = 0.3, restitution 0.05. Table friction `table_friction` = 0.08. `object_mass`, `radius`, `incoming_speed`, `fixture_speed`, `preview` and `restitution` are not used by this task. Horizon `horizon` = 25 s.

The instance's parameters (`s.params()`, SI units): `horizon` = 25, `object_mass` = 0.035, `tool_mass` = 0.2, `tool_half` = 0.07, `radius` = 0.018, `preview` = 0.65, `incoming_speed` = 0.35, `fixture_speed` = 0.04, `restitution` = 0.1, `table_friction` = 0.08, `tool_friction` = 0.3.

**Goal geometry.** Drop limit: the fixture's frame origin must stay at or above z = 0.18 m. `goal_target` is announced at reset in the state. It is a fixed point, not seed-dependent: where the socket's mid-height centre would be if the fixture were moved 20 mm along +x from its start. No predicate uses it, but it gives away the fixture's location: privileged mode only. The ball's seeded start is not announced.

## Success (the task's own check)
The task has 5 phases. They are checked after every physics step (1 ms) and must be completed **in this order**
(a phase is checked only once the previous one is complete, and a completed phase stays complete):
1. **moving_fixture_presentation**: the left gripper grips the fixture body (both left-arm fingers in contact with it; contact with the latch does not count), while the fixture's frame origin is more than 0.018 m away from where it started and the fixture's centre of mass moves faster than 0.005 m/s.
2. **relative_pin_insertion**: the peg is inserted into the socket while the fixture keeps moving, for 0.06 s without interruption. Measured in the fixture frame, the peg tip (tool-frame point (0, 0, -0.07)) is within 5 mm horizontally of the socket's axis and 10-35 mm below the socket's top face (insertion depth 0.01 m < depth < 0.035 m; the socket itself is 30 mm deep). Meanwhile the left gripper still grips the fixture body and the fixture's centre of mass moves faster than 0.003 m/s.
3. **mechanical_latch_open**: the latch is pressed down by more than 17 mm (latch joint q < -0.017 m) at a moment when the peg tool touches the latch.
4. **follow_and_withdraw**: the peg tip is more than 15 mm above the socket's top face, measured along the fixture's z axis only (depth < -0.015 m, any lateral position). At the same moment the peg tool does not touch the latch and the left gripper still grips the fixture body.
5. **gravity_delivery**: after this phase has begun, the ball touches the chute; a chute contact before this phase does not count. After that, the ball rests in the basin for 0.7 s without interruption. Rests means: in the basin's frame (origin at the inner floor centre) its centre is within 0.0528 m of the centre along both x and y (0.45 x radius inside a 0.06 m half-width square) and between 0.012 m and 0.0381 m above the floor; it has touched the basin within the last 25 ms; and its speed is below 0.09 m/s. This completes the task.

The episode **ends by itself** at the first control step where the last phase is complete (success; rows after it are
never executed) or where the task has failed. `s.status()` reports the phase you are in and the failure, if any.

**The task fails** (the episode ends, reward 0) as soon as any of these happens:
- at any time, the fixture's frame origin (a point on the channel floor's top surface, 20 mm behind the floor's front edge) is below z = 0.18 m (`fixture_grasp_drop`);
- the task's horizon is reached: 25 s of simulated time (`timeout`);
- an object leaves the workspace: its centre falls below z = -0.2 m or gets more than 1.8 m from the world's z axis
  (`out_of_bounds`);
- a forbidden contact or a deep interpenetration (below);
- a safety limit is exceeded (`limit_violation`, below).

**Contacts.** The fingers of either arm may touch the fixture body (channel, handle, socket) and the ball, but not the latch (gate, bar, button). The right peg tool (whole tool link, adapter included) may touch the fixture body, the latch and the ball. Nothing on either robot may touch the stand, the chute, the basin or the table. No other robot part (hand or arm links) may touch anything. The two arms and their tools may never touch each other, and no arm may touch itself. In every task: the two arms (and their tools) never touch each other
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
build. The environment's source, the task included, is in `/opt/pandadyn/panda_dynamics` (`tasks/dual/moving_fixture_unlock.py`).

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
