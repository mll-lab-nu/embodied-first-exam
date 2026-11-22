# EmbodiedSWE · carry the box from the shelf to the bin, Unitree G1 (standard)

## Task
A Unitree G1 humanoid with three-finger hands, walking under EmbodiedSWE's frozen locomotion policy, its arms and waist
under its Pink IK. A steel shelving unit stands with its face 0.46 m ahead of the start pose, boards at 0.41, 0.76 and
1.49 m. On the middle board sits a brown cardboard box, 20 cm on a side and about 0.1 kg, its center 0.86 m up, nearly
flush with the shelf's front edge and with 0.69 m of clear air above it. To the right, about 1.4 m away, a low table
(top 0.53 m) carries an open blue sorting bin: interior about 48 x 72 cm around (1.81, -0.24), floor at 0.53 m, walls
just 0.05 m tall — a shallow tray the box drops into, not a deep basket. Pick the box up off the shelf, carry it to the
table, and leave it resting inside the bin. The robot runs as a service you reach only through its client, as if it were
real hardware: one live episode.

## Goal
Success: the box rests inside the bin's walls, let go of and at rest (not still held, not across the rim), having been
taken off the shelf and carried over to the bin. The episode ends as soon as the task is done, at the end of the first
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
first, one every round(60 / `video_fps`) control steps and the last; a per-frame depth one more image; `video="none"`
captures only the first and the last); a larger request is refused (400) before anything runs. A call that names no
cameras gets `wide`, `head` at 3 frames per second, so every call up to `max_chunk_s` / `max_watch_s` fits.

### Actions
The action is `ee_pose` only, 32 values: the world poses of the left and right `wrist_yaw_link` (`x y z qw qx qy qz`
each), 14 hand joint targets (rad), then the base command `vx vy wz hip_height` (`[0, 0, 0, 0.72]` stands still; the
wrist poses are in the world frame, so move them with the robot while it walks). Rows are streamed at the 60 Hz control
rate with your `dt`; `spec["action_types"]["ee_pose"]` has the layout, the controller and the joint limits. Coordinates
are the simulator's world frame (metres, z up; `spec["world"]`).

### Observations
Cameras (RGB 640×480, depth on request): `wide`, `pick`, `place`, `overview` (static) and `head` (on the torso, where
the real G1 carries its depth camera).

## Others
- The bin is further away than any arm reaches, so the box can only get there if the robot itself does — and the table
  stands off the shelf's axis, so the route turns.

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
- Steps: at most 400,000 control steps (1.9 h of simulated time, reason `step_guard`); then the episode ends and is
  graded as it stands.
