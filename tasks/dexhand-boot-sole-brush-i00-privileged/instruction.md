# DexHand: Brush the debris off a boot sole

Brush all six soil clods off the upward-facing sole of the boot into the collection tray. The boot stands sole-up on a fixed boot-rack peg inside the tray (its sole plane is at z = 1.292 m); six small dry soil clods are lodged in its tread, held there by gravity and friction only (no glue or cohesive bond is simulated, so a clod moves as soon as something pushes it). The shoe brush lies bristles-down on the counter: pick it up with the hand and sweep the sole with the bristles. Success requires, in order: (1) the brush's bristle field touches the boot while the hand touches the brush and the brush does not touch the counter, for at least 10 controls in total; (2) every clod has been touched by the brush's bristle field (contact with the wooden back does not count) while it was still up on the boot (clod centre at most 0.01 m below the sole plane), and every clod centre lies inside the tray walls (x in [0.366, 0.694] m, y in [-0.184, 0.384] m) below the wall top (z < 0.931 m); (3) then, for 50 consecutive controls (1 s), all six clods stay in the tray with linear speed at most 0.05 m/s while the brush touches neither the boot nor any clod and is withdrawn (bristle-field centre at least 0.04 m above the sole plane, or at least 0.18 m horizontally from the sole centre). The episode ends with success at that moment; fewer than six clods never counts. The episode ends immediately with failure, checked after every 2 ms physics substep, when the boot moves more than 0.03 m or tilts more than 0.35 rad from its reset pose; when a clod touches the counter or the floor, falls below the counter top (z < 0.886 m) or leaves the workspace box x in [0.25, 1.2] m, y in [-0.45, 0.45] m, z in [0.886, 1.8] m; when any part of the hand touches a clod (clods must be brushed, not picked); when the brush touches the floor, the tray or the rack, falls below the counter top, leaves the workspace box, or is released in the air (it touches nothing but clods while its centre of mass sinks faster than 0.2 m/s); or when the physics becomes unstable; later actions cannot undo a failure. Only robot actuator targets are allowed: no welds, teleports, scripted object motion or applied object forces. The boot, brush and clods are free rigid bodies; the brush's 32 bristle tufts touch the world through one compliant bristle-pad contact proxy (individual fibre bending is not simulated) and the clods are rigid (no fracture or adhesion). The episode allows at most 3000 controls at 50 Hz; reaching that limit without success is a failure.

You control one dexterous hand mounted on a six-DoF wrist positioning stage (three prismatic and three serial revolute
joints, no arm). The stage and the fingers are position actuated in the physics engine under native force bounds;
grasping, carrying, brushing and releasing require physical contact. The controller runs at 50 Hz, with
ten 2 ms physics substeps. The frozen reset lets the boot, the clods and the brush settle for 0.5 s before control 1.

## Hands
Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success predicate are the same for both; only one hand is used per episode.
Both hands hang from the same six-axis wrist stage, with the same wrist joints, ranges, gains and start targets; with all six wrist targets at zero the palm faces down with the fingers pointing +y.
Choose the hand with `Session(..., hand="wuji")` or the environment variable `DEXHAND_HAND=wuji` (default `sharpa`). Action rows are `28` wide for `sharpa` and `26` wide for `wuji`; `s.actuator_names` gives the exact order. `s.save_trajectory(actions, path)` records the hand in the archive (`hand` member). The verifier rebuilds the scene with the recorded hand (default `sharpa` when the member is absent) and rejects a trajectory whose width does not match that hand; rows are never padded, truncated or converted between hands.

## Action layout
Each row is one 50 Hz control. The first six entries are the wrist-stage targets, identical for both hands:
`wrist_x, wrist_y, wrist_z` (metres, relative to the stage origin at world (0.55, -0.10, 1.10)) and
`wrist_rx, wrist_ry, wrist_rz` (radians, serial XYZ joints, not a quaternion; all zero = palm facing down, fingers
pointing +y, thumb on the -x side). The finger targets follow in native actuator order, in radians:

- `sharpa`: 28 values, the six wrist targets and 22 Sharpa Wave finger targets `right_thumb_CMC_FE` ... `right_pinky_DIP`.
- `wuji`: 26 values, the same six wrist targets and 20 Wuji Hand 2.2 finger targets `r_wuji_r_THJ0..3`,
  `r_wuji_r_FFJ0..3`, `r_wuji_r_MFJ0..3`, `r_wuji_r_RFJ0..3`, `r_wuji_r_LFJ0..3`.

Every target must lie within `s.model.actuator_ctrlrange`. Both hands start from the same wrist targets with open
fingers (`task.json` `initial_targets`).

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
s = Session("boot_sole_brush")               # default hand: DEXHAND_HAND or "sharpa"
s = Session("boot_sole_brush", hand="wuji")  # explicit hand
s.hand, s.action_dim, s.actuator_names       # selected hand, row width and exact row order
s.hold_action()                              # current motor targets
s.model.actuator_ctrlrange                   # native target limits
s.model, s.data                              # privileged MuJoCo model and state
s.status()                                   # success, done, reason, steps, stage, clods in tray/brushed, features
s.step(row)                                  # ten 2 ms physics substeps; a no-op once the episode is done
s.snapshot(), s.restore(snap)                # save / restore the full physics and predicate state
s.render_frame("overview")                   # RGB uint8 (480, 640, 3); also "closeup" and "side"
s.reset()                                    # exact frozen reset
s.replay(actions)                            # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
You may read the full simulator state (`s.model`, `s.data`) and the files next to `rcb_dexhand.py`: `task.json`
(frozen geometry, clod start poses, every predicate threshold), `scene.py`, `checker.py` and `runtime.py` (the exact
failure checks and stages). The world frame has z up; lengths are in metres and angles in radians. The counter top
is at z = 0.886 m; the brush starts bristles-down on the counter at (0.68, -0.28); the boot's sole plane is at about
z = 1.292 m with the toe towards -x and the sole centre at (0.53, 0.10); the clod start poses are in `task.json`.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
