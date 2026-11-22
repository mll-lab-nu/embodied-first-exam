# EmbodiedSWE · draw and dose liquid with a syringe, two Frankas (standard-mcp-shell)

## Task
Two Franka Panda arms with parallel grippers, each under EmbodiedSWE's operational-space (torque) controller. On the top
shelf of a medical cart: a large syringe LYING FLAT (a scanned model — translucent barrel with graduation marks and
finger flanges, a plunger with a thumb plate, travel 0.12 m = its full capacity, and a luer nozzle at the tip), a rack
of three GLASS TEST TUBES, and a wide RESERVOIR beaker of water (its blue level visibly drops as liquid is drawn). The
cart's lower shelf holds packaged syringes and a basin — scenery only. Draw a full load (>= 95% of capacity, tip seated
in the reservoir), dispense between 23% and 43% of capacity into EACH of the three tubes, then lay the syringe back down
at its spot on the shelf. The robot runs as a service you reach through the `efe-robot` MCP tools, their Python client
`efe_robot` or the service's own client, as if it were real hardware: one live episode.

## Goal
Success: you drew a full load from the reservoir (tip seated on it), dosed each of the three tubes with 23% to 43% of
the capacity (tip seated on its mouth), and the syringe now lies back at its starting spot on the shelf, roughly flat
and at rest. The episode ends as soon as the task is done, at the end of the first call after which it holds (judged on
the live simulator).

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at
`/app/output/gen.py`.

Real-robot rules:
- One episode, no reset: what you knock over stays knocked over.
- No privileged state: you get the robot's camera images (with their calibration) and its own sensor readings; no object
  poses, no scene layout; the episode ends when the task is done.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
- One route at a time: the tools, `efe_robot` and the service's client all drive the one robot.

## Robot Interface
### Tools
The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__move_robot`), also as Python functions:
`import efe_robot` (`/opt/tools/efe_robot.py`, on `PYTHONPATH`; each function has the tool's name, arguments and result,
its docstring the tool's description) or `python3 /opt/tools/efe_robot.py <tool> '<JSON arguments>'` from the shell.
They and the service's client (`### Client`) all drive the one robot. Their conventions (all but space `native`): the
robot base frame is midway between the two arm bases (panda_link0) at their height (world (0, 0.42, 0.71)), facing where
both arms face: +X forward (world -y), +Y left (world +x), +Z up. Both arms face +X; the arm the scene calls left stands
at Y = -0.28 (on this frame's right side), the arm it calls right at Y = +0.28; metres, radians, quaternions `wxyz`,
gripper 0 open .. 1 closed. Parts: left (arm: 2 joints, end-effector pose); right (arm: 2 joints, end-effector pose).
Cameras: `overview`, `left_wrist`, `right_wrist`.

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
- One call at a time (the Python functions wait for a pending call themselves). A call still running after 45 s returns
  `{"pending": true, "operation": id}`: collect it with `wait(operation=id)`. `"episode_over": true` means the episode
  has ended.

This robot: Each arm takes end-effector poses only, tracked by EmbodiedSWE's operational-space (torque) controller; the
arm joints take no direct command. Both arms can move in one move_robot call (one goal per arm). The end-effector pose
of an arm is its panda_hand frame, not the fingertips: the point midway between the fingertips is 0.1034 m along the
hand's own +Z (approach) axis from it. An arm's two joint_positions are its finger position targets (finger_1, finger_2,
metres each: 0 = closed, 0.04 = open): send both together, e.g. [0.04, 0.04] to open and [0.0, 0.0] to close; a closed
target on an object squeezes it. gripper_opening_m is the measured distance between that hand's finger pads (about 0.08
fully open). The measured joint angles are in observe's proprio_now (its layout: describe_robot's spec_file,
proprio_layout). One episode, no reset; it ends by itself once the task is complete.

### Client
`/opt/tools/rcb_client.py`: its docstring is its manual; `r.spec()` gives the numbers. The service answers one request
at a time: while a long call runs, every other request waits, so a client-side timeout means "busy", not "crashed".
Simulated time advances only inside your calls. One call returns at most 240 images (cameras × the frames captured: the
first, one every round(15 / `video_fps`) control steps and the last; a per-frame depth one more image; `video="none"`
captures only the first and the last); a larger request is refused (400) before anything runs. A call that names no
cameras gets `overview`, `left_wrist`, `right_wrist` at 2 frames per second, so every call up to `max_chunk_s` /
`max_watch_s` fits.

### Actions
The action is `ee_pose` only, 18 values: left arm then right arm, each the world pose of its `panda_hand`
(`x y z qw qx qy qz`) and its two finger position targets (m, 0 closed, 0.04 open). Rows are streamed at the 15 Hz
control rate with your `dt`; `spec["action_types"]["ee_pose"]` has the layout, the controller and the joint limits.
Coordinates are the simulator's world frame (metres, z up; `spec["world"]`).

### Observations
Cameras (RGB 640×480, depth on request): `overview` (static), `left_wrist` (on the left hand), and `right_wrist` (on the
right hand).

## Others
- Liquid moves with the plunger, but ONLY while the syringe is roughly upright with the nozzle tip seated on a mouth:
  hovering within 6 mm laterally and 12 mm above the rim. Pulling the plunger while seated on the reservoir draws
  liquid; pushing it dispenses into whichever tube the tip is seated on — anywhere else the liquid is WASTED. Tubes
  never un-fill: a tube pushed past its band is ruined for the episode (the reservoir can be re-drawn from, but
  over-dispensing cannot be undone). The water is VISIBLE: a blue column inside the translucent barrel shows the drawn
  liquid, and each tube fills with a blue column as it receives its dose. The plunger has deliberate friction: push/pull
  it slowly and steadily.

## Limits
- Time: 14400 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 8 CPUs, 24 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Steps: at most 400,000 control steps (7.4 h of simulated time, reason `step_guard`); then the episode ends and is
  graded as it stands.
