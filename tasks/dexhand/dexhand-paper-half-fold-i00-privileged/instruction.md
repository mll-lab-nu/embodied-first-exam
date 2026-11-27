# DexHand · Fold a sheet of paper in half with a permanent crease (privileged)

## Task
Fold the sheet of paper on the table in half: lift its free half over its fixed half, press a permanent crease along the
marked center line, take the hand away, and leave the folded sheet lying on the table.

## Goal
Success: the free half lies folded over onto the fixed half, its edge close to the fixed edge, with a crease along the
center line that stays when let go; the whole sheet is over the table top and not stretched; and the hand has been off
the paper for two seconds. A replay ends as soon as the task is done; later rows are not run.

Any of these ends the episode at once as a failure, which later actions cannot undo:
- Any part of the paper sinks well below the table top, for example bent down over the table edge.
- The paper leaves the work area.
- The paper is stretched.
- The physics becomes unstable.

Deliverable: `/app/output/trajectory.npz` with a finite numeric `actions` array of shape `(T, 28)` for `sharpa` or
`(T, 26)` for `wuji`, at most 1500 rows, plus the `hand` it was made for, and `/app/output/gen.py`, the script that
produced it. Each row is one 50 Hz control: `wrist_x, wrist_y, wrist_z` targets (metres), `wrist_rx, wrist_ry, wrist_rz`
(radians, serial XYZ joints), then the finger targets in `s.actuator_names` order. Targets must lie within
`s.model.actuator_ctrlrange`. Save it compressed with `numpy.savez_compressed` (`s.save_trajectory` does this). An
archive larger than 64 MB is rejected. Save a valid one early and overwrite it when you have a better one.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed.

Only the robot's actuator targets act on the scene: no object teleports, grasp welds, scripted object motion or applied
forces.

## Robot Interface
One dexterous hand on a six-axis wrist stage (no arm), at a table (DexHand, MuJoCo). The scene is one fixed instance.
You have the full simulator to develop with; you hand in a trajectory of motor targets.

### Session
`/opt/tools/rcb_dexhand.py`, importable as `rcb_dexhand`:
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

### Actions
The first six targets of a row drive the wrist stage that carries the hand: `wrist_x`, `wrist_y`, `wrist_z` (metres,
world frame) and `wrist_rx`, `wrist_ry`, `wrist_rz` (radians, serial XYZ joints); the finger targets follow in the
hand's native actuator order.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both. Choose the hand with `Session(..., hand="wuji")` or the environment variable
`DEXHAND_HAND=wuji` (default `sharpa`). `s.save_trajectory(actions, path)` records the hand in the archive as the `hand`
member; an archive without it counts as `sharpa`. A trajectory whose row width does not match its hand is rejected.
Action rows are `28` wide for `sharpa` and `26` wide for `wuji`; `s.actuator_names` gives the exact order. Sharpa starts
in a near-edge pregrasp; Wuji starts at the same six wrist targets with its fingers curled clear of the paper.

### Robot
A dexterous hand on a six-DoF wrist positioning stage is your robot. The wrist stage is position actuated in the physics
engine; folding and creasing need physical contact. Physics runs at 0.5 ms (40 substeps per 20 ms control), and the
controller runs at 50 Hz.

The wrist targets `wrist_x, wrist_y, wrist_z` are world positions of the hand mount (metres) and
`wrist_rx, wrist_ry, wrist_rz` serial XYZ joint angles (radians, not a quaternion).

### Scene
World frame, metres, z up.

- Table top at z = 0.30 m, spanning x from -0.345 to 0.135 m (the edge on the hand's side) and y from -0.30 to 0.30 m.
- The sheet starts flat at z = 0.3012 m, spanning x from 0 to 0.16 m and y from -0.05 to 0.05 m, in a 9 x 5 vertex grid
  (20 mm by 25 mm spacing). Vertices with x <= 0.08 m are the glued half and never move. The fold line is the column at
  x = 0.08 m (an orange guide line marks it). A fold brings the free edge (x = 0.16 m) back over the glued edge (x = 0),
  turning the free half upward and over about the fold line.
- The paper is a passive elastic/plastic shell: hinges bend elastically up to 0.5 rad beyond their rest angle and then
  yield, so a crease becomes permanent only when the paper is bent well past its current rest shape. The fold angle is
  measured from the fold-line column to the free-edge column; the crease is the mean plastic rest angle of the hinges on
  the fold line. Contact compliance gives the sheet an effective thickness of 0.7 mm.
- Cameras: `overview` and `side`.

## Limits
- Time: 3600 s of wall-clock time from the start of your session. Everything counts, including the simulator's start-up.
  At the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). A call into a long-running process can block for its
  whole wait time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, including the simulator's and the benchmark's source.
- Resources: 2 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU. Going over a cap can get a process killed (the CPU cap only slows you down). Usage: `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
