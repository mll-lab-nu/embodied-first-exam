# EmbodiedSWE · drive the seven motherboard bolts with an allen key, Franka (standard)

## Task
A Franka Panda arm with its parallel gripper, under EmbodiedSWE's operational-space (torque) controller. A gaming-PC
case lying on its side on a sturdy table, opening up, its motherboard facing the ceiling. The board carries 7 case-mount
screw holes, each backed by an M8 threaded insert in the case. Beside the case: 7 loose M8 allen (socket-head) bolts
lying in a row, and one long-series L-shaped allen key (its arm is long enough that the swinging handle clears the case
walls). Each bolt head carries a 7 mm hex socket. Every hole already holds its bolt hand-started upright, a few threads
in. Seat the key in a bolt's socket and drive the bolt down (turn clockwise while pressing) until it seats — then move
on to the next hole. A seated bolt locks in place. The robot runs as a service you reach only through its client, as if
it were real hardware: one live episode.

## Goal
Success: all seven bolts are driven down and seated in their holes, standing upright; the bolts move only down their
holes as the key turns them clockwise, and each needs at least five more full turns. The episode ends as soon as the
task is done, at the end of the first call after which it holds (judged on the live simulator).

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
cameras gets `overview`, `wrist` at 4 frames per second, so every call up to `max_chunk_s` / `max_watch_s` fits.

### Actions
The action is `ee_pose` only, 9 values: the world pose of `panda_hand` (`x y z qw qx qy qz`) and the two finger position
targets (m, 0 closed, 0.04 open). Rows are streamed at the 15 Hz control rate with your `dt`;
`spec["action_types"]["ee_pose"]` has the layout, the controller and the joint limits. Coordinates are the simulator's
world frame (metres, z up; `spec["world"]`).

### Observations
Cameras (RGB 640×480, depth on request): `overview` (static) and `wrist` (on the hand).

## Others
- The key holds in a firm pinch: close the fingers across its handle's hex and the grip locks; open wide to release.

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
