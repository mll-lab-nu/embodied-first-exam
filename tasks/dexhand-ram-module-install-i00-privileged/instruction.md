# DexHand: Install a desktop DDR4 RAM module

Install the DDR4 memory module into the outer DIMM socket of the motherboard (socket_3, the slot nearest the board edge). The module stands upright in a slotted anti-static foam holder on the bench, key notch towards +y; the motherboard is fixed in its service tray and the socket's single moving latch starts open. Pick the module up, keep its keyed orientation, insert it straight into the socket and press it home so that the passive latch snaps closed, then let go. The episode succeeds when these stages have happened in order: (1) picked: the module is out of the holder (no holder contact, its lower edge at least 10 mm above the slit top, z >= 0.851 m) and held by the thumb and at least one other finger; (2) seated: both lower module ends 1.5 to 2.6 mm above the socket base (the 2 mm seating datum), lateral offset of both ends at most 0.5 mm, along-slot offset at most 1.0 mm, the module's height axis within 3 degrees of vertical and its length axis within 3 degrees of the socket's keyed direction (a reversed module never counts); (3) latched: while seated, the moving latch hinge is at most 0.08 rad (closed); and then, for 50 consecutive controls (1 s), the module stays seated and latched with no hand contact on the module or the latch, module speed at most 0.01 m/s and angular speed at most 0.2 rad/s. The episode ends with success at that moment; a partial installation never counts. The episode ends immediately with failure, checked after every 2 ms physics substep, when the module touches anything other than the hand, its foam holder or the target socket (the bench, the service tray, the motherboard and its components, the other three sockets, the floor), when the module is unsupported (touches nothing) while its centre of mass falls faster than 0.2 m/s, or has fallen freely more than 5 cm (no drop-and-catch), when any lower module corner drops below the bench top (z < 0.825 m) or a lower module end inside the socket comes closer than 1.2 mm to the socket base (pushed into the 2 mm floor), when the module origin leaves the workspace box x in [0.30, 0.95] m, y in [-0.36, 0.34] m, z in [0.826, 1.25] m, or when the physics becomes unstable; later actions cannot undo a failure. Only robot actuator targets are allowed; no object teleports, grasp welds, scripted object motion or direct module forces. The episode allows at most 3000 controls at 50 Hz; reaching that limit without success is a failure. The socket throat is the source's 1.66 mm (module 1.27 mm).

You control one dexterous hand mounted on a six-DoF wrist positioning stage (three prismatic and three serial revolute
joints, no arm). The stage and the fingers are position actuated in the physics engine under native force bounds;
grasping, carrying, inserting and releasing require physical contact. The controller runs at 50 Hz, with ten 2 ms
physics substeps.

## Hands
Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success predicate are the same for both; only one hand is used per episode.
Both hands hang from the same six-axis wrist stage, with the same wrist joints, ranges, gains and start targets; the wrist targets are the world position (m) and serial XYZ angles (rad) of the hand mount.
Choose the hand with `Session(..., hand="wuji")` or the environment variable `DEXHAND_HAND=wuji` (default `sharpa`). Action rows are `28` wide for `sharpa` and `26` wide for `wuji`; `s.actuator_names` gives the exact order. `s.save_trajectory(actions, path)` records the hand in the archive (`hand` member). The verifier rebuilds the scene with the recorded hand (default `sharpa` when the member is absent) and rejects a trajectory whose width does not match that hand; rows are never padded, truncated or converted between hands.

## Action layout
Each row is one 50 Hz control. The first six entries are the wrist-stage targets, identical for both hands:
`wrist_x, wrist_y, wrist_z` (metres, world position of the hand mount) and `wrist_rx, wrist_ry, wrist_rz` (radians,
serial XYZ joints, not a quaternion). The finger targets follow in native actuator order, in radians:

- `sharpa`: 28 values, the six wrist targets and 22 Sharpa Wave finger targets `right_thumb_CMC_FE` ... `right_pinky_DIP`.
- `wuji`: 26 values, the same six wrist targets and 20 Wuji Hand 2.2 finger targets `r_wuji_r_THJ0..3`,
  `r_wuji_r_FFJ0..3`, `r_wuji_r_MFJ0..3`, `r_wuji_r_RFJ0..3`, `r_wuji_r_LFJ0..3`.

Every target must lie within `s.model.actuator_ctrlrange`. Both hands start from the same wrist targets (hand above
the bench, fingers pointing down); the frozen finger start pose of each hand is in `task.json` (`initial_targets`).

## Deliverable
Save `/app/output/trajectory.npz` with a finite numeric `actions` array of shape `(T, 28)` for `sharpa` or `(T, 26)`
for `wuji`, at most 3000 rows, plus the `hand` member (`s.save_trajectory` writes both), and
`/app/output/gen.py`, the script that produced it. The separate verifier rebuilds the frozen scene with the recorded
hand and replays only these motor targets in two fresh processes; both replays must succeed and end in the identical
state hash. A replay stops at the first success or the first failure; later rows are not executed. Object poses,
configuration overrides, pickled arrays and success claims are not deliverables and are never read.
Save the archive compressed (`numpy.savez_compressed`; `s.save_trajectory` does): an archive file larger than 64 MB is rejected with reward 0.

## Tooling
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
Read `/opt/tools/task.json`, `scene.py`, `checker.py` and `runtime.py` for the complete geometry, failure checks and
predicate. The world frame has z up; lengths are in metres and angles in radians. The bench top is at z = 0.825 m,
the motherboard surface at z = 0.843 m; the target socket body `socket_3` is at (0.576, 0.004, 0.8438) with its slot
along world +y (the key sits 5.6 mm towards +y of the slot centre); the foam holder is centred at `task.json`
`holder_xy`.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
