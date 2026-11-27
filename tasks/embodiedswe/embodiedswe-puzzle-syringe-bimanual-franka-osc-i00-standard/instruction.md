# EmbodiedSWE · draw and dose liquid with a syringe, two Frankas (standard)

## Task
Fill the syringe from the beaker, put about a third of a syringe into each of the three test tubes, then lay the syringe
back down where it was on the shelf.

## Goal
Success: the syringe was filled nearly full from the beaker; each of the three tubes got between about a quarter and two
fifths of a full syringe; and the syringe now lies back at its starting spot on the shelf, roughly flat and at rest.

Filling the syringe and dosing the tubes count as they happen.

When you are done, send `/finish` to end the episode and get it graded. Everything else is judged on the state at that
point.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- One episode, no reset: what you knock over stays knocked over.
- You get only the cameras and the robot's own sensor readings: no object poses, no scene layout, no success signal.

## Robot Interface
Two Franka Panda arms with parallel grippers, each under EmbodiedSWE's operational-space (torque) controller. The robot
runs as a service you reach through its client or its MCP tools, as if it were real hardware: one live episode.

`POST /finish` (MCP tool `finish`): ends the episode; it is graded right away.

### Client
`/opt/tools/rcb_client.py`: its docstring is its manual; `r.spec()` gives the numbers. The service answers one request
at a time: while a long call runs, every other request waits, so a client-side timeout means "busy", not "crashed".
Simulated time advances only inside your calls. One call returns at most 240 images; a larger request is refused (400)
before anything runs. The count is cameras × frames captured, where the frames are the first, one every round(15 /
`video_fps`) control steps, and the last. Each depth frame counts as one more image. `video="none"` captures only the
first and the last frame. A call that names no cameras gets `overview`, `left_wrist`, `right_wrist` at 2 frames per
second, so every call up to `max_chunk_s` fits.

### MCP tools
- The same service is also an MCP server, `efe-robot` (in your tool list), with one tool per endpoint: `spec`,
  `observe`, `submit`, `kinematics`, `finish`. A tool takes its endpoint's request fields (any other field in `fields`)
  and returns the service's reply `meta` unchanged; images, arrays and video are written as files under `/app/obs/`
  (`.png`, `.npy`, `.mp4`) and the result lists them. Long action chunks can be passed as a file (`actions_file`).
- `observe` returns at once with what is already recorded: the current frame, or the last `last_s` seconds. Time passes
  only through `submit`, which answers when its rows have run; a `submit` with `interpolate` "hold", `seconds` and no
  rows lets time pass with the robot holding still.
- A call still running after 45 s returns `pending` with an `operation` id; `observe(operation=id)` collects its reply.
- The client and the tools drive the same robot in the same episode; use either, or both.

### Actions
The action is `ee_pose` only, 18 values: left arm then right arm, each the world pose of its `panda_hand`
(`x y z qw qx qy qz`) and its two finger position targets (m, 0 closed, 0.04 open). Rows are streamed at the 15 Hz
control rate with your `dt`; `spec["action_types"]["ee_pose"]` has the layout, the controller and the joint limits.
Coordinates are the simulator's world frame (metres, z up; `spec["world"]`).

### Observations
Cameras (RGB 640×480, depth on request): `overview` (static), `left_wrist` (on the left hand), and `right_wrist` (on the
right hand).

## Others
- Liquid moves only while the syringe is held upright, plunger end up, with its tip right at a mouth: pulling the
  plunger on the beaker draws, pushing it on a tube fills that tube; anywhere else the liquid is wasted.
- A tube never empties again: overfilling one cannot be undone.
- The plunger is stiff: move it slowly and steadily.

## Limits
- Time: 14400 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning. Time left: `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the
  service's `time_left_s` (in every reply) starts at your first request, so the file is the one to trust. Calls into a
  long-running process can block for their whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 8 CPUs, 24 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Steps: at most 400,000 control steps (7.4 h of simulated time, reason `step_guard`); then the episode ends.
- Finish: if you never send `/finish`, the episode is graded when the step limit is reached or your session ends.
