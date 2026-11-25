# EmbodiedSWE · deliver the fruit to the plate, Unitree G1 (standard)

## Task
Put every fruit on the table onto the clay plate on the far side of the table; nothing else goes on the plate.

## Goal
Success: the lemon, the only fruit, rests on the clay plate, well inside its rim and still, and nothing that is not
fruit is on the plate. The episode ends as soon as the task is done, at the end of the first call after which it holds
(judged on the live simulator).

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- One episode, no reset: what you knock over stays knocked over.
- You get only the cameras and the robot's own sensor readings: no object poses, no scene layout; the episode ends when
  the task is done.

## Robot Interface
A Unitree G1 humanoid with three-finger hands, walking under EmbodiedSWE's frozen locomotion policy, its arms and waist
under its Pink IK. The robot runs as a service you reach only through its client, as if it were real hardware: one live
episode.

### Client
`/opt/tools/rcb_client.py`: its docstring is its manual; `r.spec()` gives the numbers. The service answers one request
at a time: while a long call runs, every other request waits, so a client-side timeout means "busy", not "crashed".
Simulated time advances only inside your calls. One call returns at most 240 images (cameras × the frames captured: the
first, one every round(60 / `video_fps`) control steps and the last; a per-frame depth one more image; `video="none"`
captures only the first and the last); a larger request is refused (400) before anything runs. A call that names no
cameras gets `overview`, `head` at 3 frames per second, so every call up to `max_chunk_s` / `max_watch_s` fits.

### Actions
The action is `ee_pose` only, 32 values: the world poses of the left and right `wrist_yaw_link` (`x y z qw qx qy qz`
each), 14 hand joint targets (rad), then the base command `vx vy wz hip_height` (`[0, 0, 0, 0.72]` stands still; the
wrist poses are in the world frame, so move them with the robot while it walks). Rows are streamed at the 60 Hz control
rate with your `dt`; `spec["action_types"]["ee_pose"]` has the layout, the controller and the joint limits. Coordinates
are the simulator's world frame (metres, z up; `spec["world"]`).

### Observations
Cameras (RGB 640×480, depth on request): `overview` (static) and `head` (on the torso, where the real G1 carries its
depth camera).

## Limits
- Time: 14400 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 8 CPUs, 24 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Steps: at most 400,000 control steps (1.9 h of simulated time, reason `step_guard`); then the episode ends and is
  graded as it stands.
