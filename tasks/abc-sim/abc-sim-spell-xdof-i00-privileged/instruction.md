# ABC Sim · spell xdof (privileged)

## Task
Spell XDOF with the letter blocks: lay X, D, O and F side by side in a straight row on the table, each with a letter
face up or down, reading from left to right as the arms face the table.

## Goal
Success: the blocks X, D, O and F lie flat on the table side by side in a straight row, close together, in that order
from left to right as the arms face the table, each with a letter face up or down. The replay ends as soon as the task
is done.

Deliverable: `/app/output/trajectory.npz`, written with `s.save_trajectory(actions, path)`: `(T, 14)` rows, one per
control step, at most 20,000 rows. It is replayed open-loop from the same initial state and scores 1 if its episode ends
in success. Leave the script that produced it at `/app/output/gen.py`. Save a valid one early and overwrite it when you
have a better one.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed.

## Robot Interface
A bimanual robot in ABC Sim (MuJoCo): two I2RT YAM arms (6 revolute joints and a parallel two-finger gripper each) side
by side at the near edge of a table, facing +x (the left arm is the one at +y). The scene is one fixed instance. You
have the full simulator to develop with; you hand in a trajectory of robot actions.

### Session
`rcb_abc` (installed; run `python` from any directory):
```python
from rcb_abc import Session
s = Session(instance="/app/instance.npz")   # a few seconds
s.prompt                           # the directive
s.reset()                          # back to the frozen initial state (unlimited)
s.state()                          # privileged: robot joints, tool frames, every free body's pose, the task's
                                   # evaluator and runtime state, the scene's randomization record
s.objects()                        # every free body: [x, y, z, qw, qx, qy, qz] in the world frame
s.robot_q(); s.hold_action()       # the 14 action coordinates now (holding them keeps the robot still)
s.model, s.data, s.env             # MuJoCo model / data and the abc_sim env: read them; only the rows you record are replayed
s.step(a)                          # one control step (14 numbers); False once the episode is over
s.status()                         # {'success', 'done', 'reason', 'steps', 'success_run', 'state_sha', 'info', ...}
snap = s.snapshot(); s.restore(snap)   # save / restore a mid-episode state exactly (search, planning)
s.record_start(); ...; actions = s.record_stop()   # (T, 14) rows, one per control step
s.replay(actions)                  # resets, replays open-loop until the episode ends, returns status
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_frame("top"); s.render_depth("top"); s.camera_info("top")   # RGB (480, 640, 3), z-depth (m), calibration
s.render_video(actions, "/app/output/check.mp4")
s.kinematics({"op": "fk", "q": q14}); s.kinematics({"op": "ik", "targets": {"left_tcp": [x, y, z, qw, qx, qy, qz]}})
```
There are no motion primitives: every skill is yours to build from joint targets. There is no step budget: your
wall-clock time is the limit. An episode ends at success; `s.step` then refuses further rows until `s.reset()`.
Rendering runs on the GPU (EGL) when one is available.

### Actions
An action has 14 numbers per control step: `[left_joint1..6, left_gripper, right_joint1..6, right_gripper]` -- each
arm's six joint position targets (rad) and its gripper opening (0 = closed, 1 = open, each finger 0.0475 m from closed;
up to 1.042). The joints and grippers are position servos that track the targets (MuJoCo position actuators with damping
and force limits). A target outside a joint's range is clamped to that range. The simulator rounds every command to
float32. One control step = 17 physics steps of 2 ms = 0.034 s (29.4 Hz).

### Observations
Bodies: the letter blocks are `block_A` ... `block_Z`. Tool frames: `left_tcp` / `right_tcp` (each arm's tool centre
point) and `left_grasp` / `right_grasp` (the point between the finger pads); `s.kinematics` solves IK for them with each
arm's own six joints. Cameras: `top` (above and behind the arms, looking down at the table), `left` and `right` (wrist
cameras on the arms), `overhead`, `left_side`, `right_side`.

### World frame
The table's frame: x forward (away from the arms' bases), y to the left as the arms face the table, z up; metres,
radians, quaternions `wxyz`. Directions are as the arms face the table: left = +y, right = -y, behind = +x (farther from
the arms), in front = -x (nearer to them).

## Others
- To check a trajectory the way it is graded, replay it from the command line:
  `python /opt/abc-tools/rcb_abc.py replay --instance /app/instance.npz --traj /app/output/trajectory.npz`.

## Limits
- Time: 3600 s of wall-clock time from the start of your session. Everything counts, including the simulator's start-up.
  At the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). A call into a long-running process can block for its
  whole wait time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, including the simulator's and the benchmark's source.
- Resources: 4 CPUs, 16 GiB memory, 8192 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  one GPU (5 GiB of its memory). Going over a cap can get a process killed (the CPU cap only slows you down). Usage:
  `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
