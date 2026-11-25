# DexHand · Install a desktop DDR4 RAM module (privileged)

## Task
Take the memory module out of its foam holder and install it in the motherboard's outer memory slot, the one nearest the
board edge, the right way round; press it in until the latch snaps shut, then let go.

## Goal
Success: in this order, the module is lifted out of its foam holder, held by the thumb and at least one other finger; it
goes straight down into the target socket, fully seated and the right way round; the latch snaps closed; then the hand
is off the module and the latch, and the module stays seated, latched and still for a second. A replay ends as soon as
the task is done; later rows are not run.

Any of these ends the episode at once as a failure, which later actions cannot undo:
- The module touches anything other than the hand, its foam holder or the target socket.
- The module is dropped or falls freely (no drop-and-catch).
- The module drops below the bench top or is pushed into the socket's floor.
- The module leaves the work area.
- The physics becomes unstable.

Deliverable: `/app/output/trajectory.npz` with a finite numeric `actions` array of shape `(T, 28)` for `sharpa` or
`(T, 26)` for `wuji`, at most 3000 rows, plus the `hand` member (`s.save_trajectory` writes both), and
`/app/output/gen.py`, the script that produced it. Save it compressed (`numpy.savez_compressed`; `s.save_trajectory`
does): an archive larger than 64 MB is rejected. Save a valid one early and overwrite it when you have a better one.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed.

Only the robot's actuator targets act on the scene: no object teleports, grasp welds, scripted object motion or applied
forces.

## Robot Interface
One dexterous hand on a six-axis wrist stage (no arm), at a bench (DexHand, MuJoCo). The scene is one fixed instance.
You have the full simulator to develop with; you hand in a trajectory of motor targets.

### Session
`/opt/tools/rcb_dexhand.py`, importable as `rcb_dexhand`:
```python
from rcb_dexhand import Session
s = Session("ram_module_install")               # default hand: DEXHAND_HAND or "sharpa"
s = Session("ram_module_install", hand="wuji")  # explicit hand
s.hand, s.action_dim, s.actuator_names          # selected hand, row width and exact row order
s.hold_action()                                 # current motor targets
s.model.actuator_ctrlrange                      # native target limits
s.model, s.data                                 # privileged MuJoCo model and state
s.features()                                    # module pose in the socket frame, end depths, latch angle, contacts
s.status()                                      # success, done, reason, steps, stage (0..3), total_stages
s.step(row)                                     # ten 2 ms physics substeps; a no-op once the episode is done
s.snapshot(), s.restore(snap)                   # save / restore the full physics and verdict state
s.render_frame("overview")                      # RGB uint8 (480, 640, 3); also "holder", "socket", "socket_side", "wide"
s.reset()                                       # exact frozen reset
s.replay(actions)                               # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
The world frame has z up; lengths are in metres and angles in radians. The bench top is at z = 0.825 m, the motherboard
surface at z = 0.843 m; the target socket body `socket_3` is at (0.576, 0.004, 0.8438) with its slot along world +y (the
key sits 5.6 mm towards +y of the slot centre); the foam holder is centred at `task.json` `holder_xy`.

### Actions
Each row is one 50 Hz control. The first six entries are the wrist-stage targets, identical for both hands:
`wrist_x, wrist_y, wrist_z` (metres, world position of the hand mount) and `wrist_rx, wrist_ry, wrist_rz` (radians,
serial XYZ joints, not a quaternion). The finger targets follow in native actuator order, in radians:

- `sharpa`: 28 values, the six wrist targets and 22 Sharpa Wave finger targets `right_thumb_CMC_FE` ...
  `right_pinky_DIP`.
- `wuji`: 26 values, the same six wrist targets and 20 Wuji Hand 2.2 finger targets `r_wuji_r_THJ0..3`,
  `r_wuji_r_FFJ0..3`, `r_wuji_r_MFJ0..3`, `r_wuji_r_RFJ0..3`, `r_wuji_r_LFJ0..3`.

Every target must lie within `s.model.actuator_ctrlrange`. Both hands start from the same wrist targets (hand above the
bench, fingers pointing down); the frozen finger start pose of each hand is in `task.json` (`initial_targets`).

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both. Choose the hand with `Session(..., hand="wuji")` or the environment variable
`DEXHAND_HAND=wuji` (default `sharpa`). `s.save_trajectory(actions, path)` records the hand in the archive (`hand`
member, `sharpa` when absent); a trajectory whose row width does not match its hand is rejected. Action rows are `28`
wide for `sharpa` and `26` wide for `wuji`; `s.actuator_names` gives the exact order. Both hands hang from the same
six-axis wrist stage, with the same wrist joints, ranges, gains and start targets; the wrist targets are the world
position (m) and serial XYZ angles (rad) of the hand mount.

### Robot
You control one dexterous hand mounted on a six-DoF wrist positioning stage (three prismatic and three serial revolute
joints, no arm). The stage and the fingers are position actuated in the physics engine under native force bounds;
grasping, carrying, inserting and releasing require physical contact. The controller runs at 50 Hz, with ten 2 ms
physics substeps.

The wrist targets `wrist_x, wrist_y, wrist_z` are world positions of the hand mount (metres) and
`wrist_rx, wrist_ry, wrist_rz` serial XYZ joint angles (radians, not a quaternion).

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (the simulator's start-up too). At
  the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 2 CPUs, 7 GiB memory, 2048 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU. Over a cap a process can be killed (the CPU cap only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
