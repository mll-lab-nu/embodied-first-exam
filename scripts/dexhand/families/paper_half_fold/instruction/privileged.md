# DexHand: {{TITLE}}

{{TASK_TEXT}}

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

{{HANDS}}

## Deliverable
Save `/app/output/trajectory.npz` with a finite numeric `actions` array of shape `(T, 28)` for `sharpa` or
`(T, 26)` for `wuji`, at most {{MAX_ROWS}} rows, plus the `hand` it was made for, and `/app/output/gen.py`, the
script that produced it. Each row is one 50 Hz control: `wrist_x, wrist_y, wrist_z` targets (metres),
`wrist_rx, wrist_ry, wrist_rz` (radians, serial XYZ joints), then the finger targets in `s.actuator_names` order.
Targets must lie within `s.model.actuator_ctrlrange`. The separate verifier starts from its own frozen scene and
replays only these motor targets in two fresh processes; both must succeed with identical final state hashes. The
replay stops at the first success or failure, so rows after it are not executed. Object poses, configuration
overrides, pickled arrays and success claims in the archive are not read. Save a deliverable early and keep
improving it; the file present when the time budget ends is graded.

## Tooling
```python
from rcb_dexhand import Session
s = Session("{{FAMILY}}")            # hand="wuji" or DEXHAND_HAND=wuji for Wuji Hand 2.2
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
