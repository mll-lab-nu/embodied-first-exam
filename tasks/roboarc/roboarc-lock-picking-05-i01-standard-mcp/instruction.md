# RoboARC · lock_picking (standard-mcp)

## Task
A 7-DoF Franka Panda arm with a Robotiq 2F-85 parallel gripper on a fixed base, at a table (RoboARC, MuJoCo). Pick up
the two-tab key from its rest. Insert the tabbed key through all four rotor plates and the final END plate, while
respecting their slots and stops. The key's leading tab is longer than its second tab, which sits one plate spacing
behind it. The robot runs as a service you reach only through the `efe-robot` MCP tools, as if it were real hardware:
one live episode.

## Goal
Success: the key's shaft passes through all four rotor plates and the END plate at once, pointing the way it went in,
pushed in far enough that the leading tab has come out clear past END's outer face (only the shaft's tip reaching END is
not enough); on the way the tabs passed the plates only through their slots, the shaft and tabs were never forced
through solid plate, and no rotor was turned past its stops. The key may still be held. Turning a rotor past one of its
stops ends the episode as a failure. Dropping the key off the table ends the episode as a failure. The episode ends, as
a success, as soon as all of this has held for half a second.

Nothing to hand in: the service records and grades the episode, and the tool server records your calls.

Real-robot rules:
- One episode, no reset: what you knock over stays knocked over.
- No privileged state: you get the robot's camera images (with their calibration), its own sensor readings and the
  safety readings (Robot Interface); no object poses, no scene layout; the episode ends when the task is done.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
- Tools only: you may write and run code to compute, but every robot command and observation is an `efe-robot` tool call
  you make yourself; no script starts or calls the tool server, and code must not contact the simulator (the service's
  request log is checked against the server's).

## Robot Interface
### Tools
The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__move_robot`). Their conventions (all but space
`native`): the robot base frame: the arm's root link (the origin of the service's frame), +X forward from the arm base,
+Y left, +Z up; metres, radians, quaternions `wxyz`, gripper 0 open .. 1 closed. Parts: arm (arm: 7 joints, end-effector
pose, gripper). Cameras: `agentview`, `front_oblique`, `wrist`.

- `describe_robot()`: call it first: parts and limits, cameras, control period, action types, the time left; the full
  spec as a JSON file (`spec_file`).
- `observe(cameras?, depth?, seconds?, inline_cameras?)`: JPEG images under `/app/obs/` (depth `.npy`, float32 metres;
  with `seconds` > 0 an `.mp4` too, the robot held still meanwhile); the result has their paths, each camera's `K` and
  pose in the base frame, each part's joints, gripper and end-effector pose, and `proprio_now` (the robot's own
  proprioception row; its layout is in the spec file).
- `locate(camera, u, v | pixels, window_px?)`: the 3-D point in the base frame a depth camera sees at pixel (u, v) of
  its full-size image (u the column, v the row); no time passes.
- `move_robot(goals, duration_s?)`: one goal per part,
  `{target, position?, quaternion_wxyz?, joint_positions?, gripper?}`; the parts move together and the call returns when
  the motion is done, with `reached` (the error per goal), a `failure` category if a goal was not reached, the state and
  a frame per camera.
- `execute_trajectory(space, rows | native_rows | rows_file, dt?, interpolate?)`: dense rows `dt` seconds apart; long
  arrays as `rows_file`, a file under `/app` (`.npy` or `.csv` of native rows for space `native` with `action_type`, or
  a `.json` list).
- `wait(seconds?, operation?)`: let time pass holding the current command, or collect a pending call.
- `signal(kind, note)`: `done` records that you are finished (the episode itself ends as Goal says).
- One call at a time. A call still running after 45 s returns `{"pending": true, "operation": id}`: collect it with
  `wait(operation=id)`. `"episode_over": true` means the episode has ended.

This robot: The episode ends by itself at the first success (all of the task's final conditions holding for its
confirmation time: after the last move let simulated time pass with wait or observe seconds), when the task's own
failure predicate fires (reason task_failed) or when your time is up; there is no step budget and nothing to signal.
End-effector goals are solved by the service's inverse kinematics (no collision checking) and driven to in joint space;
a solution more than 0.5 rad from the current joints on any joint is refused for that arm (it holds), so long
end-effector moves go in steps of a few cm and degrees. Arm joint targets move at most 0.04 rad per control step; a
faster request takes the steps it needs. No gripper target goes lower than 15 mm below the tabletop. Grasping is
assisted (spec robot_spec.grippers states the rule): closing on a graspable part inside its grasp region takes hold of
it, and any command that opens the gripper by more than 0.2 % of its travel lets it go. The gripper value in the state
is the command in force; gripper_opening_m is the measured gap between the finger pads. Joint efforts (proprio_now,
*_effort) rise when an arm pushes on something.

### Observations
- Cameras: `agentview` (static); `front_oblique` (static); `wrist` (on the robot link `hand`; it moves, so use the pose
  that comes with each frame). Resolution 848×480. The spec's `["cameras"][cam]` gives the intrinsics and the mounting:
  a static pose, or the parent link and the fixed offset (world_T_cam = FK(link) · `link_T_cam_cv`). A point (X, Y, Z)
  in a camera's OpenCV frame (x right, y down, z forward) appears at u = fx·X/Z + cx, v = fy·Y/Z + cy; depth is that Z.
  the spec's `["robot_spec"]` lists the joints with their position, velocity and effort limits, the grippers, the PD
  gains and the tool frames; the spec's `["world"]` the frame conventions (the world frame: origin at the robot's root
  link on its mounting, +z up; no positions of the scene are given).
- The safety readings (the tool result's `safety`, in every response) report, since the previous call, forcing (the
  arms' pressing loads and forcing events), the deepest task contact, the longest time above its sustained limit and the
  review events (rigid families), the lowest rope / cord volume ratio (soft families) and the table-guard stops, each
  next to its limit.

### Grasping
- Assisted grasping: a gripper whose command moves towards closed takes hold of a graspable part (lock_key) once both
  fingers touch the same part inside its grasp region, the tool frame within 6 cm of it and the penetration at most 2
  mm, for 0.05 s; the part then follows the gripper rigidly. Any command that opens the gripper (by more than 0.2 % of
  its travel) lets it go. A hold that breaks (the fingers open more than 15 %, the part drifts 1 cm / 0.15 rad from its
  held pose, the hold has to push or pull its part with more than 65 N averaged over 20 ms, or no finger has touched the
  part for 0.2 s) is lost, and the gripper must open before it can take hold again; that force is reached when, for
  example, two held parts that hook into each other are pulled apart, or a held part is pressed into another object. Two
  grippers never hold the same part; other objects are grasped physically (friction).
- Grasp regions (one sphere per graspable part): lock_key: radius 32 mm, on the key's handle. Both finger contacts must
  lie inside the part's sphere; a part touched elsewhere is grasped physically.

## Others
- Objects here (the names the safety readings use): `lock_base`, `lock_disc_0`, `lock_frame_0`, `lock_disc_1`,
  `lock_frame_1`, `lock_disc_2`, `lock_frame_2`, `lock_disc_3`, `lock_frame_3`, `key_tray`, `key_tray_post_0`,
  `key_cradle_0_0`, `key_cradle_0_1`, `key_tray_post_1`, `key_cradle_1_0`, `key_cradle_1_1`, `lock_goal_post`,
  `lock_goal`, `lock_key`.
- The fingertips reach about 6 mm beyond the tool frame (TCP) along its approach axis when open and about 19 mm when
  closed (the Robotiq fingertips move forward as they close). Arm drive torques are capped (the effort limits in
  robot_spec), so an arm pushing against an obstacle stalls at that torque. An arm with any part more than 5 mm deep in
  a fixed object (a fixture, the table) is stopped where it is: its joint targets become its measured joints for that
  control step, so it stops pushing (the response does not report these stops).
- Forcing (an arm drive near its torque cap while its gripper, or a part it holds, presses hard on something) is
  recorded as evidence (the tool result's `safety`) and shown to the reviewer when a success is reviewed; it does not
  end the episode or change the grade by itself. A simulator breakdown ends the episode: as an infrastructure error, or
  as your failure if an arm was forcing just before it.
- The shaft fits the plates' bores closely (bores 15 mm across, the shaft 13.5 mm thick), so the key has to go in
  straight and centred; the rotor plates are 10 mm thick and the plates 120 mm apart.
- The shaft runs from 545 mm behind the leading tab to 15 mm in front of it.
- The leading tab is long and passes a plate only through one of its deep slots; the second tab, 120 mm behind it, is
  shorter and also passes the shallow slots.
- Each rotor turns only between its stops, measured from its start angle, seen from the side the key enters, looking
  along the key toward END (rotor 1 is the plate the key reaches first): rotor 1 2 degrees counterclockwise and 32
  degrees clockwise; rotor 2 32 degrees counterclockwise and 2 degrees clockwise; rotor 3 2 degrees counterclockwise and
  32 degrees clockwise; rotor 4 152 degrees counterclockwise and 2 degrees clockwise.

## Limits
- Time: 10800 s of wall-clock time from the start of your session; everything counts (the time the tools take too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); every tool result has the service's `time_left_s`, which
  starts at your first tool call, so the file is the one to trust. Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the files the tools write included. Do not search for or download a ready-made
  solution (published or reference solutions, recorded demonstrations, trained policies); trials are reviewed.
- Resources: 4 CPUs, 16 GiB memory, 4096 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Steps: no step budget; a technical cap ends the episode after 200,000 control steps, watches included, graded as it
  stands.
