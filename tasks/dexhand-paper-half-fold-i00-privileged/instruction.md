# DexHand: Fold a sheet of paper in half with a permanent crease

Fold the sheet of paper on the table in half: lift its free half over its fixed half, press a permanent crease along the marked center line, take the hand away, and leave the folded sheet lying on the table. The 160 x 100 mm sheet (1.28 g) lies flat on the table top. Its left half is glued to a backing patch next to a dark clamp and cannot move; the right half is free, and its last 25 mm overhang the table edge. Success requires 100 consecutive 50 Hz control samples (2 s) in which no part of the hand touches the paper and all of these hold: fold angle of the free half above 2.6 rad, permanent (plastic) crease on the center line above 2.2 rad on average with at least 90% of its hinges above 2.2 rad, free edge within 18 mm of the fixed edge, stretch below 8%, and the whole sheet over the table top: every paper vertex within the table's extent (x from -0.345 to 0.135 m, y from -0.30 to 0.30 m) and at most 2 mm below the table top (z >= 0.298 m). The episode ends with that success, or fails immediately and permanently if any paper vertex sinks more than 10 mm below the table top (z < 0.29 m, for example bent down over the table edge) or leaves the workspace box (x from -0.03 to 0.19 m, y from -0.09 to 0.09 m, z <= 0.45 m), if the paper stretches by more than 8%, or the simulation becomes unstable. A fold that springs back, a crease that is not permanent, or a hand still touching the paper is not a success. Only the robot's motor targets act on the paper; there are no grasp welds, scripted paper motion or applied forces. The episode allows at most 1500 controls at 50 Hz (30 s).

A dexterous hand on a six-DoF wrist positioning stage is your robot. The wrist stage is position actuated in the
physics engine; folding and creasing need physical contact. Physics runs at 0.5 ms (40 substeps per 20 ms control),
and the controller runs at 50 Hz.

## Scene (world frame, metres, z up)
- Table top at z = 0.30 m, spanning x from -0.345 to 0.135 m (the edge on the hand's side) and y from -0.30 to
  0.30 m. Fail-fast limits on every paper vertex, checked every 0.5 ms: z >= 0.29 m (10 mm below the table top)
  and inside the workspace box x -0.03..0.19 m, y -0.09..0.09 m, z <= 0.45 m. At success every vertex must lie
  within the table's x/y extent and at z >= 0.298 m (2 mm tolerance below the table top).
- The sheet starts flat at z = 0.3012 m, spanning x from 0 to 0.16 m and y from -0.05 to 0.05 m, in a 9 x 5 vertex
  grid (20 mm by 25 mm spacing). Vertices with x <= 0.08 m are the glued half and never move. The fold line is the
  column at x = 0.08 m (an orange guide line marks it). A fold brings the free edge (x = 0.16 m) back over the glued
  edge (x = 0); the target fold rotates the free half by more than 2.6 rad about the fold line, upward and over.
- The paper is a passive elastic/plastic shell: hinges bend elastically up to 0.5 rad beyond their rest angle and
  then yield, so a crease becomes permanent only when the paper is bent well past its current rest shape. The fold
  angle is measured from the fold-line column to the free-edge column; the crease is the mean plastic rest angle of
  the hinges on the fold line. Contact compliance gives the sheet an effective thickness of 0.7 mm.
- Cameras: `overview` and `side`.

## Hands
Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success predicate are the same for both; only one hand is used per episode.
The first six targets of a row drive the wrist stage that carries the hand: `wrist_x`, `wrist_y`, `wrist_z` (metres, world frame) and `wrist_rx`, `wrist_ry`, `wrist_rz` (radians, serial XYZ joints); the finger targets follow in the hand's native actuator order. Sharpa starts in a near-edge pregrasp; Wuji starts at the same six wrist targets with its fingers curled clear of the paper.
Choose the hand with `Session(..., hand="wuji")` or the environment variable `DEXHAND_HAND=wuji` (default `sharpa`). Action rows are `28` wide for `sharpa` and `26` wide for `wuji`; `s.actuator_names` gives the exact order. `s.save_trajectory(actions, path)` records the hand in the archive (`hand` member). The verifier rebuilds the scene with the recorded hand (default `sharpa` when the member is absent) and rejects a trajectory whose width does not match that hand; rows are never padded, truncated or converted between hands.


## Deliverable
Save `/app/output/trajectory.npz` with a finite numeric `actions` array of shape `(T, 28)` for `sharpa` or
`(T, 26)` for `wuji`, at most 1500 rows, plus the `hand` it was made for, and `/app/output/gen.py`, the
script that produced it. Each row is one 50 Hz control: `wrist_x, wrist_y, wrist_z` targets (metres),
`wrist_rx, wrist_ry, wrist_rz` (radians, serial XYZ joints), then the finger targets in `s.actuator_names` order.
Targets must lie within `s.model.actuator_ctrlrange`. The separate verifier starts from its own frozen scene and
replays only these motor targets in two fresh processes; both must succeed with identical final state hashes. The
replay stops at the first success or failure, so rows after it are not executed. Object poses, configuration
overrides, pickled arrays and success claims in the archive are not read. Save a deliverable early and keep
improving it; the file present when the time budget ends is graded.
Save the archive compressed (`numpy.savez_compressed`; `s.save_trajectory` does): an archive file larger than 64 MB is rejected with reward 0.

## Tooling
```python
from rcb_dexhand import Session
s = Session("paper_half_fold")            # hand="wuji" or DEXHAND_HAND=wuji for Wuji Hand 2.2
s.actuator_names, s.action_dim           # row order and width
s.model.actuator_ctrlrange               # native target limits
s.hold_action()                          # current targets (the initial pregrasp after reset)
s.step(row)                              # one 20 ms control (40 physics substeps); returns features()
s.features()                             # fold/crease/alignment/contacts/strain/on-table/stage diagnostics
s.status()                               # success, done, reason, steps, stage (of 4), released_hold_steps, state_sha
s.observe(camera="overview")             # joint positions/velocities/targets, paper vertices and rest angles, RGB
s.snapshot(); s.restore(snap)            # exact save/restore of the episode, paper material memory included
s.render_frame("overview")               # RGB uint8 (480, 640, 3); also "side"
s.reset()                                # exact frozen reset
s.replay(rows)                           # reset, execute rows until done, return status()
s.save_trajectory(rows, "/app/output/trajectory.npz")
s.model, s.data, s.shell                 # privileged MuJoCo model/data and the paper shell
```
Tooling lives in `/opt/tools`. Read `instance.json`, `runtime.py` and `shell.py` for the complete scene, material law
and predicate. Stages (diagnostics): folded (fold angle and edge alignment), creased (permanent crease), released on
the table (no hand contact, sheet over the table, strain), held (100 consecutive samples = success).

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
