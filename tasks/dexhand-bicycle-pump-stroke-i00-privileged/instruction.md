# DexHand: Inflate a tire with a portable bicycle pump

Inflate the bicycle tire with the portable bicycle pump. A mini floor pump (Topeak Mini Morph type, 154 g class, barrel 0.25 m tall) stands free on its folding foot on the bench next to a 406 (20 inch) wheel lying on the bench; the pump's hose head is already locked on the wheel's Schrader valve and the tire starts partly inflated at 207.8 kPa gauge. The pump's T handle rests at the top of its 0.20 m travel: the piston is a passive slide whose compressed-air spring pushes the handle back up (about 6 N at the top and 46 N at the bottom of the stroke) with viscous damping and 1 N seal friction. A stroke counts when the handle is pushed down to a piston depth of at least 0.18 m (90 % of the travel) and then returns to a depth of at most 0.04 m (20 %); shallower strokes never count and are not failures. The tire pressure is a checker quantity, not simulated air: every counted stroke adds 380 Pa (the mean rise per stroke of the source gas model). Success requires, in this order: (1) at least 6 counted strokes; (2) tire pressure at least 210.0 kPa gauge; (3) the handle released at the top: piston depth at most 0.01 m, no hand contact with any part of the pump, pump tilt at most 0.0873 rad (5 degrees) from upright, pump centre-of-mass speed at most 0.02 m/s and handle speed at most 0.02 m/s, held continuously for 50 consecutive controls (1 s). The episode ends with success at that moment. The episode ends immediately with failure, checked after every 2 ms physics substep, when the pump tilts more than 0.2618 rad (15 degrees) from upright, when its base moves more than 0.03 m horizontally from its start or rises more than 0.02 m above it, when its centre of mass falls below the bench top (z < 0.70 m) or any pump part touches the floor, or when the physics becomes unstable; later actions cannot undo a failure. The episode allows at most 3000 controls at 50 Hz; reaching that limit without success is a failure. Only robot actuator targets are allowed; no object teleports, grasp welds, scripted object motion or direct object forces. The wheel, valve, locked pump head and hose are static props.

You control one dexterous hand mounted on a six-DoF wrist positioning stage (three prismatic and three serial revolute
joints, no arm). The stage and the fingers are position actuated in the physics engine under native force bounds;
pushing the pump handle requires physical contact. The controller runs at 50 Hz, with ten 2 ms physics substeps.

## Hands
Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success predicate are the same for both; only one hand is used per episode.
Both hands hang palm-down from the same six-axis wrist stage, with the same wrist joints, ranges, gains and start targets; the stage origin is at world (0.6, 0.0, 0.7) and all-zero wrist angles point the palm down with the fingers toward world +y.
Choose the hand with `Session(..., hand="wuji")` or the environment variable `DEXHAND_HAND=wuji` (default `sharpa`). Action rows are `28` wide for `sharpa` and `26` wide for `wuji`; `s.actuator_names` gives the exact order. `s.save_trajectory(actions, path)` records the hand in the archive (`hand` member). The verifier rebuilds the scene with the recorded hand (default `sharpa` when the member is absent) and rejects a trajectory whose width does not match that hand; rows are never padded, truncated or converted between hands.

## Action layout
Each row is one 50 Hz control. The first six entries are the wrist-stage targets, identical for both hands:
`wrist_x, wrist_y, wrist_z` (metres, measured from the stage origin at world (0.6, 0.0, 0.7)) and
`wrist_rx, wrist_ry, wrist_rz` (radians, serial XYZ joints, not a quaternion; all zero = palm facing down, fingers
pointing to world +y, thumb toward world -x). The finger targets follow in native actuator order, in radians:

- `sharpa`: 28 values, the six wrist targets and 22 Sharpa Wave finger targets `right_thumb_CMC_FE` ... `right_pinky_DIP`.
- `wuji`: 26 values, the same six wrist targets and 20 Wuji Hand 2.2 finger targets `r_wuji_r_THJ0..3`,
  `r_wuji_r_FFJ0..3`, `r_wuji_r_MFJ0..3`, `r_wuji_r_RFJ0..3`, `r_wuji_r_LFJ0..3`.

Every target must lie within `s.model.actuator_ctrlrange`. Both hands start from the same wrist targets; the frozen
finger start pose of each hand is in `task.json` (`initial_targets`).

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
s = Session("bicycle_pump_stroke")               # default hand: DEXHAND_HAND or "sharpa"
s = Session("bicycle_pump_stroke", hand="wuji")  # explicit hand
s.hand, s.action_dim, s.actuator_names           # selected hand, row width and exact row order
s.hold_action()                                  # current motor targets
s.model.actuator_ctrlrange                       # native target limits
s.model, s.data                                  # privileged MuJoCo model and state
s.features()                                     # strokes, piston depth, pressure, pump pose/speed, contacts, failure
s.status()                                       # success, done, reason, steps, stage (0-3), total_stages
s.step(row)                                      # ten 2 ms physics substeps; a no-op once the episode is done
s.render_frame("overview")                       # RGB uint8 (480, 640, 3); also "closeup"
s.reset()                                        # exact frozen reset
s.replay(actions)                                # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
`s.features()` and `s.status()` report `strokes`, `piston_depth_m`, `tire_gauge_pa`, `stage` (completed stages:
1 = six strokes, 2 = pressure target, 3 = released hold), `released_hold_steps`, `pump_tilt_rad`,
`pump_displacement_m`, `pump_lift_m`, `pump_speed_m_s`, `handle_speed_m_s`, `hand_pump_contacts` and, after a failure,
`failure` / `failure_detail`. Read `/opt/tools/task.json`, `scene.py`, `checker.py` and `runtime.py` for the complete
geometry, failure checks and predicate. The world frame has z up; lengths are in metres and angles in radians. The bench top is at z = 0.70 m; the
pump body is `pump` (free joint `pump_free`), its piston slide `piston_extension` (0.20 m = handle up, at rest) and the
T handle geom `t_handle`.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
