# ABC Sim · multi-drawer search -- frozen instance

You control a bimanual robot -- two I2RT YAM arms (6 revolute joints and a parallel two-finger gripper each) side by side at the near edge of a table, facing +x (the left arm is the one at +y) -- via Python (ABC Sim, `abc_sim` on MuJoCo 3.6.0).
**Task:** Find the measuring cup, then the dish brush and put each in the bin, in that order. Each target counts when its centre is inside the bin (within 0.056 m x 0.052 m of the bin's centre along the bin's horizontal axes and at most 0.26 m above its floor) while it is the current target: first the measuring cup, then the dish brush. Success: every target has counted (a counted target may leave the bin again). Distractors in the bin do not matter. The goal must hold for 30 consecutive control steps (1.02 s); the episode then ends in success.

A stack of three closed drawers stands on the table; kitchen tools are hidden in its drawers (some drawers hold more than one, one is empty). A small bin stands on the table on the right. The task's directive, as the scene states it: "find the measuring cup".

This is a *fixed scene instance*: the start state, the objects and the goal never change between resets. You may reset
and retry as many times as you want. Your deliverable is **one replayable trajectory**, not a general policy.

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below): `(T, 14)` rows,
one per control step, at most 20,000 rows. It is replayed open-loop from the same initial state in two fresh processes and
scored 1 if both episodes end in success in the same state, else 0. Also leave the script that produced it at
`/app/output/gen.py`.

Save a trajectory as soon as you have one that works, improve it while time remains, and do not stop early.

## Tooling (already installed; run `python` from any directory)
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
s.replay(actions)                  # resets, replays open-loop until the episode ends, returns status -> self-check
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_frame("top"); s.render_depth("top"); s.camera_info("top")   # RGB (480, 640, 3), z-depth (m), calibration
s.render_video(actions, "/app/output/check.mp4")
s.kinematics({"op": "fk", "q": q14}); s.kinematics({"op": "ik", "targets": {"left_tcp": [x, y, z, qw, qx, qy, qz]}})
```
Bodies: the hidden objects are `drawer_search_distractor_NN` (labels, drawers and the target sequence: `s.state()['randomization']`); objects parked far below the table are unused. Tool frames: `left_tcp` / `right_tcp` (each arm's tool centre point) and `left_grasp` /
`right_grasp` (the point between the finger pads); `s.kinematics` solves IK for them with each arm's own six joints.
Cameras: `top` (above and behind the arms, looking down at the table), `left` and `right` (wrist cameras on the arms), `overhead`, `left_side`, `right_side`. There are no motion primitives: every skill is yours to build from joint targets.

CLI equivalent of the grader:
`python /opt/abc-tools/rcb_abc.py replay --instance /app/instance.npz --traj /app/output/trajectory.npz --repeat 2`

## Conventions
- World frame: the table's; x forward (away from the arms' bases), y to the left as the arms face the table, z up;
  metres, radians, quaternions `wxyz`. Directions are as the arms face the table: left = +y, right = -y, behind = +x (farther from the arms), in front = -x (nearer to them).
- Action: 14 numbers per control step: `[left_joint1..6, left_gripper, right_joint1..6, right_gripper]` -- each arm's six joint position targets (rad) and its gripper opening (0 = closed, 1 = open, each finger 0.0475 m from closed; up to 1.042). The joints and grippers are position servos that track the targets (MuJoCo position actuators with damping and force limits); a target outside a joint's range is clamped to it, and the simulator rounds every command to float32. One control step = 17 physics steps of 2 ms = 0.034 s (29.4 Hz).
- There is no step budget: your wall-clock time is the limit. An episode ends at success;
  `s.step` then refuses further rows until `s.reset()`. Rendering runs on the GPU (EGL) when one is available.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **5 GiB of GPU memory**, **12 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`. GPU memory counts what a process reserves (JAX, for example, reserves most of the card unless told not to). These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. When enforcement is on and GPU memory goes above 1.5 times its limit, the monitor also kills the process holding the most of it at once, to protect the machine; that alone does not fail the trial. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
