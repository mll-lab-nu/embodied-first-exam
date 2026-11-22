# EmbodiedSWE · assemble the SO101 arm's elbow: servo, four tab screws, forearm, eight horn screws, two Frankas (standard)

## Task
Two Franka Panda arms with parallel grippers, each under EmbodiedSWE's operational-space (torque) controller. The lower
half of an SO101 robot arm (base + shoulder + upper arm), a bare elbow servo, four identical loose M2x6 screws, eight
loose M3 horn screws, a compact power screwdriver with a magnetic bit, and the not-yet-attached distal half
(forearm..gripper) all rest free on a workbench. The upper arm has four M2 screw holes over the elbow servo's pocket
(joint 3): a countersunk pair in the near outer wall and the mirrored pair through the far wall. The distal half's
forearm fork clips over the seated servo — its cup onto the output horn — and carries four M3 screw holes around the
elbow axis on each side (near: into the horn, reached through the skin's access channels; far: into the servo's case
back). Seat the servo into the pocket and drive the four M2 tab screws (any tab screw fits any tab hole), then clip the
forearm onto the horn and drive the M3s home (any M3 fits any horn-line hole). The screwdriver is torque-activated: it
runs by itself while a screw it carries is seated in a free hole. A driven screw locks in place; the servo is fastened
by the tab screws, the forearm by the horn screws. The robot runs as a service you reach only through its client, as if
it were real hardware: one live episode.

## Goal
Success: all twelve screws are driven home and locked, filling every hole (the four M2 screws in the tab holes over the
servo pocket, the eight M3 screws around the elbow axis); the servo sits in the upper arm's pocket, and the forearm sits
on the servo's output horn (at any elbow angle). The episode ends as soon as the task is done, at the end of the first
call after which it holds (judged on the live simulator).

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at
`/app/output/gen.py`.

Real-robot rules:
- One episode, no reset: what you knock over stays knocked over.
- No privileged state: you get the robot's camera images (with their calibration) and its own sensor readings; no object
  poses, no scene layout; the episode ends when the task is done.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.

## Robot Interface
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
