# DexHand · Load two punched pages into a ring binder (privileged)

## Task
Open the rings of the ring binder on the desk, thread both punched pages onto them through their holes, close the rings
and let go.

## Goal
Success: in this order, the rings are opened; with the rings open, both pages are threaded on them, each hole on its own
ring, and lie over the back cover with the hand off them; the rings are closed through every hole; then the hand is off
the pages and the binder, and both pages rest still on the binder for a second. A replay ends as soon as the task is
done; later rows are not run.

Any of these ends the episode at once as a failure, which later actions cannot undo:
- A page touches the floor or is dropped.
- A page falls below the desk top or leaves the work area.
- The binder is pushed away or tipped.
- A ring or a finger is pushed through a page (a ring may enter a page only through its hole).
- The physics becomes unstable.

Deliverable: `/app/output/trajectory.npz` with a finite numeric `actions` array of shape `(T, 28)` for `sharpa` or
`(T, 26)` for `wuji`, at most 6000 rows, plus the `hand` member (`s.save_trajectory` writes both), and
`/app/output/gen.py`, the script that produced it. Save it compressed with `numpy.savez_compressed` (`s.save_trajectory`
does this). An archive larger than 64 MB is rejected. Save a valid one early and overwrite it when you have a better
one.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed.

Only the robot's actuator targets act on the scene: no object teleports, grasp welds, scripted object motion or applied
forces.

## Robot Interface
One dexterous hand on a six-axis wrist stage (no arm), at a desk (DexHand, MuJoCo). The scene is one fixed instance. You
have the full simulator to develop with; you hand in a trajectory of motor targets.

### Session
`/opt/tools/rcb_dexhand.py`, importable as `rcb_dexhand`:
```python
from rcb_dexhand import Session
s = Session("binder_page_load")               # default hand: DEXHAND_HAND or "sharpa"
s = Session("binder_page_load", hand="wuji")  # explicit hand
s.hand, s.action_dim, s.actuator_names          # selected hand, row width and exact row order
s.hold_action()                                 # current motor targets
s.model.actuator_ctrlrange                      # native target limits
s.model, s.data                                 # privileged MuJoCo model and state
s.features()                                    # toggle angles, threaded/linked holes, contacts, page poses
s.status()                                      # success, done, reason, steps, stage (0..4), total_stages, hold_steps
s.step(row)                                     # ten 2 ms physics substeps; a no-op once the episode is done
s.render_frame("overview")                      # RGB uint8 (480, 640, 3); also "closeup", "rings", "pages"
s.reset()                                       # exact frozen reset
s.replay(actions)                               # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
The world frame has z up; lengths are in metres and angles in radians. The desk top is at z = 0.70 m, the binder starts
at (0.48, 0.00, 0.705) with its back cover towards +x, and the pages lie flat on the desk with their middle hole centres
at `task.json` `page_xy` (0.71, 0.22) and (0.71, -0.025), z = 0.7004 m (page frame: origin at the middle hole centre, +x
across the sheet away from the holes, +z the printed face); the desk's +x edge is at x = 0.98 m. The wrist-stage targets
are offsets from `task.json` `wrist_base` (0.62, 0.00, 0.70); at zero wrist rotation the fingers point down (-z) and the
palm faces +x.

### Actions
Each row is one 50 Hz control step. The first six entries are the wrist-stage targets, identical for both hands:
`wrist_x, wrist_y, wrist_z` (metres, world-aligned offsets from `wrist_base`) and `wrist_rx, wrist_ry, wrist_rz`
(radians, serial XYZ joints, not a quaternion). The finger targets follow in native actuator order, in radians:

- `sharpa`: 28 values, the six wrist targets and 22 Sharpa Wave finger targets `right_thumb_CMC_FE` ...
  `right_pinky_DIP`.
- `wuji`: 26 values, the same six wrist targets and 20 Wuji Hand 2.2 finger targets `r_wuji_r_THJ0..3`,
  `r_wuji_r_FFJ0..3`, `r_wuji_r_MFJ0..3`, `r_wuji_r_RFJ0..3`, `r_wuji_r_LFJ0..3`.

Every target must lie within `s.model.actuator_ctrlrange`. Both hands start from the same wrist targets; the frozen
finger start pose of each hand is in `task.json` (`initial_targets`).

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both. Choose the hand with `Session(..., hand="wuji")` or the environment variable
`DEXHAND_HAND=wuji` (default `sharpa`). `s.save_trajectory(actions, path)` records the hand in the archive as the `hand`
member; an archive without it counts as `sharpa`. A trajectory whose row width does not match its hand is rejected.
Action rows are `28` wide for `sharpa` and `26` wide for `wuji`; `s.actuator_names` gives the exact order. Both hands
hang from the same six-axis wrist stage, with the same wrist joints, ranges, gains and start targets.

### Robot
You control one dexterous hand mounted on a six-DoF wrist positioning stage (three prismatic and three serial revolute
joints, no arm). The stage and the fingers are position actuated in the physics engine under native force bounds;
grasping, carrying and releasing require physical contact. The controller runs at 50 Hz, with ten 2 ms physics substeps.

The wrist targets `wrist_x, wrist_y, wrist_z` are offsets (metres, along the world axes) from the stage base at (0.62,
0.00, 0.70); `wrist_rx, wrist_ry, wrist_rz` are serial XYZ joint angles (radians); at zero wrist rotation the fingers
point down (-z) and the palm faces +x.

### Scene
The binder is free on the desk: back cover (with the ring mechanism near its spine edge) towards +x, spine and front
cover on passive hinges towards -x. Its two toggle plates carry the three ring halves on each side; an over-centre
housing spring (a passive spatial tendon) holds them either closed (0 rad) or open (0.60 rad), and the plates and the
two booster paddles are coupled by the binder's internal linkage (passive joint couplings, never attached to the hand).
Pressing a booster paddle down opens the rings; pushing the plates back past the over-centre point (for example by
pressing the raised inner edges of the open plates down) closes them.

## Limits
- Time: 3600 s of wall-clock time from the start of your session. Everything counts, including the simulator's start-up.
  At the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). A call into a long-running process can block for its
  whole wait time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, including the simulator's and the benchmark's source.
- Resources: 2 CPUs, 7 GiB memory, 2048 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU. Going over a cap can get a process killed (the CPU cap only slows you down). Usage: `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
