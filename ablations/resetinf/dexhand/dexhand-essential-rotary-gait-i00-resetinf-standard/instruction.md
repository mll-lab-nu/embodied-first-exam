# DexHand · Multi-turn encoder knob with fixed-wrist finger gait (standard)

## Task
One dexterous hand on a six-axis wrist stage, the wrist locked (no arm), with a rotary encoder knob under its fingers
(DexHand, MuJoCo). Keep the wrist fixed. Rotate the knob to +720 degrees (two turns), then back to +360 degrees and hold
it still, regripping as you go: at least four contact handoffs between finger sets that share a finger.
The robot runs as a service you reach only through its client, as if it were real hardware.

## Goal
Success: the knob has turned two full turns forward, with at least four handoffs between finger sets that share a
finger, then one full turn back, so that it ends one turn from its start, held still by the fingers. The episode ends as
soon as the task is done.

The episode ends at once as a failure if the hand loses contact with the knob, presses it hard, the palm moves, or the
physics becomes unstable. Later actions cannot undo a failure.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at `/app/output/gen.py`.

Real-robot rules:
- Resets: as many as your time allows, with save and load (Robot Interface,
  `### This run: unlimited resets, save and load`); only the last episode is graded.
- No privileged state: you get the robot's camera images (with their calibration) and its own sensor readings; no object
  poses, no scene layout, no score; the episode ends when the task is done, and the service tells you that it ended and
  why.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.

Only the robot's actuator targets act on the scene: no object teleports, grasp welds, scripted object motion or applied
forces.

## Robot Interface
### Client
`/opt/tools/rcb_client.py`:
```python
from rcb_client import Robot
r = Robot()
spec = r.spec()
obs = r.get_obs(cameras=["overview", "inhand_top"], depth=True)
obs.last["overview"]           # RGB uint8 (480, 640, 3)
obs.last_depth["overview"]     # z-depth in metres
obs.meta["proprio"]            # named robot measurements
q = obs.group("joint_pos", now=True)
res = r.submit("joint_position", rows, dt=0.02, interpolate="hold", video="none")
r.fk(q)                       # robot-link forward kinematics; no physics is stepped
r.status()
res = r._post("/reset", {"cameras": ["overview"]}, [], 900)   # POST /reset (this client has no reset())
```
Requests can return RGB frames or mp4, with depth `none`, `last` or `frames`. Each call returns at most 1,000 camera
images, counting per-frame depth; reduce cameras, fps or duration for larger chunks. `get_obs(seconds=...)` holds the
current targets for up to 30 s and records those steps. Calling it without seconds only observes the current state.
Forward kinematics uses only the robot's own links; no IK primitive is supplied. If the service connection fails, call
`r.wait_ready()` and inspect `r.status()` before continuing. Crash recovery resumes the same journaled episode, without
a reset, and the wall-clock budget keeps running.

Resets: `r._post("/reset", ...)` (`POST /reset`) starts a new episode from the same starting state, abandoning the
running one or after one has ended; it takes no simulated time and returns the start's images and proprioception. Once
an episode has ended, `submit` raises `EpisodeOver` until you reset. `meta["episode"]` and `meta["resets_left"]` count
the episodes; `meta["control_steps"]` is the current episode's, `meta["control_steps_total"]` all of them.

### Actions
`rows` is `(T, 28)` (Sharpa) or `(T, 26)` (Wuji) in `spec["action_types"]["joint_position"]["layout"]` order: wrist XYZ
translations (metres), three serial XYZ rotational joints (radians), then the 22 or 20 finger joints (radians). Actuator
targets are clipped to the published joint limits and clipping is reported. `dt` must be a multiple of 0.02 s, between
0.02 and 0.5 s; a chunk covers at most 10 s. Hold interpolation holds each row for `dt`; linear interpolation starts
from the previous target. The robot has no scalar gripper opening.

Sharpa rows: the six wrist targets, then
`right_thumb_CMC_FE, right_thumb_CMC_AA, right_thumb_MCP_FE, right_thumb_MCP_AA, right_thumb_IP`,
`right_<index|middle|ring>_MCP_FE, _MCP_AA, _PIP, _DIP` and `right_pinky_CMC, _MCP_FE, _MCP_AA, _PIP, _DIP`. Wuji rows:
the same six wrist targets, then `r_wuji_r_THJ0..3` (thumb CMC flexion, CMC abduction, MCP, IP) and `r_wuji_r_FFJ0..3`,
`MFJ0..3`, `RFJ0..3`, `LFJ0..3` (index, middle, ring, pinky: MCP flexion, MCP abduction, PIP, DIP).

### Observations
You receive camera RGB, optional calibrated depth, and the robot's own joint positions, velocities, actuator efforts,
wrist pose and current targets. Quaternions in measured poses use WXYZ; world z is up. Cameras are overview, side, palm
(behind the hand), and two close-ups of the held object, `inhand_top` (from above the palm) and `inhand_side` (from the
thumb side), at 640 x 480; the default is overview and inhand_top. No object state is published: the close-ups (with
depth and their calibration) are how you see the object in the hand.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both, and one hand is used per episode. The service runs the hand that
`DEXHAND_HAND` names on the sim service (default `sharpa`); you cannot switch it during an episode. The hand in use is
`spec()["hand"]`; `spec()["action_types"]["joint_position"]` gives the row width (`28` for `sharpa`, `26` for `wuji`)
and the exact order. Both hands are mounted in the same wrist frame. Each hand starts from its own finger pose (Wuji:
`wuji_reset.json`), with the object held as at the Sharpa start.

### Robot
You control one dexterous hand on a six-DoF wrist positioning stage: a Sharpa Wave hand with 22 independently actuated
finger joints (the default) or a Wuji Hand 2.2 with 20 (see Hands). The wrist stage is position actuated in the physics
engine; grasping and manipulating require physical contact. The five fingers are thumb, index, middle, ring and pinky.
The controller runs at 50 Hz, with ten 2 ms physics substeps.

This is a fixed-wrist essential dexterity task. Native equality constraints lock all six wrist joints. The first six
entries of every action must remain [-0.08, 0, 0.29, 0, 0, 0]. Float32 wire-format rounding is accepted and normalized
to those exact fixed targets before physics runs. Use the declared target values rather than copying measured wrist
joint positions. Only the finger targets may change. Objects have no actuators, scripted motion or grasp attachments;
they move through contact and normal gravity.

### This run: unlimited resets, save and load
This run changes the reset budget and adds two calls.

- You have 1000 resets (`spec()["budget"]["reset"]` is 1000): in practice as many as your time allows.
- `POST /reset` on the same base URL as your other calls (`http://sim:8000` or `http://localhost:8000`), with a JSON
  body such as `{"cameras": []}` (in Python, for example `requests.post(base + "/reset", json={"cameras": []})`; the
  client's `_post("/reset", {"cameras": []}, [], 60)` where it has no `reset()`). It abandons the running episode, or
  follows one that has ended (a failure or a fall included), and starts a new episode from the same starting state. The
  answer carries the new episode's first frames; `meta` and `GET /status` add `episode`, `resets_left`, `saves`, `loads`
  and `control_steps_total`.
- Where `/spec` has `state_ops`, two more calls exist (its text is the full rule):
  - `POST /save_state` with `{}` stores the current state in the service and answers JSON
    `{"handle": "s1", "step": ...}`. The handle is all you get, never the state's contents.
  - `POST /load_state` with `{"handle": "s1", "cameras": []}` restores a state saved earlier in this run and starts a
    new episode there; it answers as `/reset` does. At most 32 handles are kept (the least recently used one is
    dropped). Saves and loads do not use up resets. Where `/spec` has no `state_ops`, this task offers resets only.
- Your time keeps running across resets and loads (in standard-realtime the robot's clock pauses after a reset or a load
  until your next command).
- Only the last episode is graded: from the starting state, or for a loaded episode the path that led to the saved state
  followed by what you did after the load. The success rule is checked again from your next command on. A success still
  ends the run: no reset, save or load after it.

## Others
- The knob is a real encoder cap with its rounded outer profile, normal surface friction and bearing resistance on a
  passive hinge that turns without limit; nothing turns it but the fingers.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 2 CPUs, 10 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 1000 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
