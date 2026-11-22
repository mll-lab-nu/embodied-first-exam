# RoboPaint · acrylic stroke copy · The Large Blue Horses (after Marc) (standard-mcp)

## Task
A simulated Franka Panda arm holding a round acrylic brush. Task (笔触临摹, stroke copy): copy the painting shown in the
picture `/app/target.png` (a small acrylic painting after Franz Marc's The Large Blue Horses, 1911) onto the main sheet,
in at most 390 strokes. The robot runs as a service you reach only through the `efe-robot` MCP tools, as if it were real
hardware: one live episode.

## Goal
Success: your painting on the main sheet matches the picture: the same colours in the same places, the same lights and
darks and the same edges, with paint where the picture has paint and only there, in at most 390 strokes; a small offset
of the whole painting (a few millimetres) is forgiven. The process rules below must hold as well. The episode runs until
your time is up (or a simulator error): there is no early end, and the main sheet is scored as your episode left it.

You get no score while you work: the grader scores the main sheet afterwards from the service's own record of your
episode. The score (`final_reward`, 0 to 1) is higher the closer your colours are to the picture's; it is scaled down
above the stroke cap and when a process rule fails.

Process rules: paint with brush strokes, the way a person paints: each stroke is one sweep of the loaded brush, pressed
for the width you want. Colouring in or filling areas with a thin line, zigzag or serpentine fills, and contour-offset
fills (paths that circle round and round inside an area) are not allowed and fail the task, even when the sheet matches
the picture. The grader checks this on the episode with two numbers you can check yourself; only painted strokes on the
main sheet count (the practice sheet is free):
- Paint path budget: `path_mm` ≤ 35900 mm. `path_mm` is the total length of the brush tip's path while it presses on the
  main sheet with paint (all strokes together, sampled at every physics step).
- Strokes are sweeps: `scribble_share` ≤ 0.1. A stroke's scribble ratio is its length divided by the diagonal of its
  bounding box on the sheet (taken as at least 10 mm): about 1 for a straight or curved sweep, 2 for a sweep out and
  back along the same line, more for a zigzag, a back-and-forth fill, a spiral or a loop. `scribble_share` is the share
  of `path_mm` in strokes whose ratio is above 2.5.

Breaking a process rule fails the task.

Nothing to hand in: the service records and grades the episode, and the tool server records your calls.

Real-robot rules:
- One episode, no reset: paint is permanent; every stroke you make stays on the paper.
- No privileged state: you see what the cameras see and feel the robot's own joint positions, velocities and efforts and
  its brush-tip pose; no sheet readout, no brush state, no score.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
- Tools only: you may write and run code to compute, but every robot command and observation is an `efe-robot` tool call
  you make yourself; no script starts or calls the tool server, and code must not contact the simulator (the service's
  request log is checked against the server's).

## Robot Interface
### Tools
The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__move_robot`). Their conventions (all but space
`native`): the robot base frame: the arm's base link panda_link0, +X away from the base over the table and the sheets,
+Y to the robot's left (where the paint or ink is), +Z up; metres, radians, quaternions `wxyz`, gripper 0 open .. 1
closed. Parts: arm (arm: 7 joints, end-effector pose). Cameras: `canvas_cam`, `practice_cam`, `scene_cam`, `side_cam`.

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

This robot: Paints: spec_file static.wells.wells (name, colour, radius 12 mm), in wells on a plate on the robot's left
(+Y): the tip inside a well's circle and below the paint surface loads that paint (the brush starts dry; a new paint
replaces the previous one). The main sheet (scored, under canvas_cam) and the practice sheet beside it (free for tests)
are described in spec_file static.sheets; positions in the world are not given: find the sheets and the paint wells on
the cameras (side_cam shows the brush's height above the paper). One continuous contact of the loaded tip with the main
sheet is one stroke, and pressing deeper gives a wider mark (the handle touches the paper 15 mm below its surface). A
stroke is best sent as one execute_trajectory space ee call: a few rows (above the start, press down, sweep along the
stroke, lift), dt 0.1 to 0.5 s apart; the service moves the tip on a straight line between consecutive rows. Hold the
brush vertical, tuft down (the start orientation). The arm is position-controlled at 20 Hz and lags a moving target. The
episode ends only when your time is up.

### Observations
- Cameras (all static): `canvas_cam` (1024×1024, straight above the main sheet; image top = the sheet's far edge, image
  left = the robot's left; the arm hides the sheet when it is above it), `practice_cam` (512×1024 portrait, above the
  practice sheet, same orientation), `scene_cam` (640×480, across the table facing the robot) and `side_cam` (640×360,
  low on the robot's right, a grazing view along the sheets that shows the brush's height).
- Depth on request: float32 (H,W) z-depth in metres, pixel-aligned with the image (0 = no reading). Depth is geometry
  only: paint on the paper never shows in it.
- Proprioception: the robot's own joint positions, velocities and efforts and its brush-tip pose.

### The brush, the paints and the sheets
- The brush is a rigid handle with a 15 mm soft tuft (no collision; the handle hits the paper 15 mm below its surface);
  the proprio "tip" pose is the tuft's tip. Hold it vertical (as at the start).
- Paints (every colour the painting needs, premixed): 10 wells on a rigid plate on the robot's left (+y), in two rows,
  radius 12 mm; the spec's `["static"]["wells"]["wells"]` gives each well's name, colour and radius. Dipping = the tip
  inside a well's circle and below the paint surface: the brush is then loaded with that paint (the previous paint is
  gone; no mixing on the palette, it never runs dry). The brush starts dry. The robot does not report which paint it
  carries; the tuft shows the colour on the cameras.
- Sheets: the main sheet, a 227.18 mm square in front of the robot, is scored; the practice sheet, 227.18 × 99.41 mm, on
  the robot's right of the main sheet, is not.
- Wherever the loaded tip is below a sheet's surface the brush paints an opaque acrylic mark; what the mark looks like
  depends on how you press, move and turn the brush (the practice sheet is there to find out), and later strokes cover
  earlier ones. One continuous contact of the loaded brush with the main sheet is one stroke. The arm is
  position-controlled (PD, 20 Hz targets): a moving target is followed with a lag.

### The target picture
`/app/target.png` (1024 × 1024 px, RGB) shows the exemplar at its true size and place on the main sheet: the image
covers the main sheet exactly, 0.2219 mm per pixel. Pixel (column u, row v), counted from 0 at the image's top-left, has
its centre at sheet millimetres X = (u + 0.5) · 227.18 / 1024, Y = (v + 0.5) · 227.18 / 1024 (X to the robot's right, Y
towards the robot, origin = the sheet's far-left corner as seen from the robot's base). Image top = the sheet's far edge
(+x), image left = the robot's left (+y): the same orientation as `canvas_cam`.

## Others
- A practice sheet lies beside the main sheet: test the brush there as much as you like; it is never scored or counted.
- The exemplar is this robot's painting after Franz Marc, *The Large Blue Horses* (1911), a public-domain work
  (Wikimedia Commons `File:Franz Marc - Die großen blauen Pferde 1911.jpg`, Public domain); the exemplar picture is CC0.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (the time the tools take too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); every tool result has the service's `time_left_s`, which
  starts at your first tool call, so the file is the one to trust. Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the files the tools write included. Do not search for or download a ready-made
  solution (published or reference solutions, recorded demonstrations, trained policies); trials are reviewed.
- Resources: 8 CPUs, 5 GiB memory, 2048 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Steps: no step budget; actions and simulated time are reported as cost; a runaway guard stops the robot after 72000
  control steps (1 h of simulated time; watching with `seconds > 0` also advances it).
