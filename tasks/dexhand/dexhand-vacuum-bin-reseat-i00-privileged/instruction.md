# DexHand · Remove and reinstall a vacuum dust bin (privileged)

## Task
Remove the dust bin from the handheld vacuum on the counter and reinstall it.

## Goal
Success: in this order, the red release button is pressed nearly all the way down while the bin is still seated, and the
bin is taken clear of its seat; the bin is put back exactly in its seat with the button back up and the bin's catch
behind the latch tooth; then no hand touches the bin, the vacuum or the button, and both are still for a second. A
replay ends as soon as the task is done; later rows are not run.

Any of these ends the episode at once as a failure, which later actions cannot undo:
- The vacuum body is moved or tilted.
- The bin falls, touches the floor or a table leg, drops below the counter top or leaves the work area.
- The bin and the vacuum are pressed into each other.
- The physics becomes unstable.

Deliverable: `/app/output/trajectory.npz` with a finite numeric `actions` array of shape `(T, 56)` for `sharpa` or
`(T, 52)` for `wuji`, at most 3000 rows, plus the `hand` member (`s.save_trajectory` writes both), and
`/app/output/gen.py`, the script that produced it. Save it compressed (`numpy.savez_compressed`; `s.save_trajectory`
does): an archive larger than 64 MB is rejected. Save a valid one early and overwrite it when you have a better one.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed.

Only the robot's actuator targets act on the scene: no object teleports, grasp welds, scripted object motion or applied
forces.

## Robot Interface
Two dexterous hands, each on its own six-axis wrist stage (no arm), at a counter (DexHand, MuJoCo). The scene is one
fixed instance. You have the full simulator to develop with; you hand in a trajectory of motor targets.

### Session
`/opt/tools/rcb_dexhand.py`, importable as `rcb_dexhand`:
```python
from rcb_dexhand import Session
s = Session("vacuum_bin_reseat")                # default hand: DEXHAND_HAND or "sharpa"
s = Session("vacuum_bin_reseat", hand="wuji")   # explicit hand
s.hand, s.action_dim, s.actuator_names          # selected hand, row width and exact row order
s.hold_action()                                 # current motor targets
s.model.actuator_ctrlrange                      # native target limits
s.model, s.data                                 # privileged MuJoCo model and state
s.features()                                    # seat error, button travel, catch clearance, contacts, speeds
s.status()                                      # success, done, reason, steps, stage (0..3), total_stages
s.step(row)                                     # twenty 1 ms physics substeps; a no-op once the episode is done
s.snapshot(), s.restore(snap)                   # save / restore the full simulator and task state
s.render_frame("overview")                      # RGB uint8 (480, 640, 3); also "closeup"
s.reset()                                       # exact frozen reset
s.replay(actions)                               # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
`s.features()` reports `seat_distance_m`, `seat_angle_rad`, `button_travel_m`, `released_in_seat`,
`catch_behind_tooth_m`, `hand_contacts`, the bin and vacuum speeds and `body_displacement_m`.

### Actions
Each row is one 50 Hz control holding a position target for every actuator, in native actuator order:

- `sharpa` (56 values): 0-5 the right stage `wrist_x, wrist_y, wrist_z` (metres, offsets from its origin, world axes)
  and `wrist_rx, wrist_ry, wrist_rz` (radians, serial XYZ joints, not a quaternion); 6-27 the 22 right Sharpa Wave
  finger targets `right_thumb_CMC_FE` ... `right_pinky_DIP`; 28-33 the left stage `left_wrist_x` ... `left_wrist_rz`
  (same convention, its hand mounted without rotation); 34-55 the 22 left finger targets `left_thumb_CMC_FE` ...
  `left_pinky_DIP`.
- `wuji` (52 values): 0-5 the right stage, 6-11 the left stage, 12-31 the right Wuji Hand 2.2 fingers
  `r_wuji_r_THJ0..3`, `r_wuji_r_FFJ0..3`, `r_wuji_r_MFJ0..3`, `r_wuji_r_RFJ0..3`, `r_wuji_r_LFJ0..3`, 32-51 the left
  Wuji fingers in the same order (`l_wuji_l_...`); `s.actuator_names` is authoritative.

Every target must lie within `s.model.actuator_ctrlrange`. The frozen start targets of each hand are in `task.json`
(`initial_targets`).

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both. Choose the hand with `Session(..., hand="wuji")` or the environment variable
`DEXHAND_HAND=wuji` (default `sharpa`). `s.save_trajectory(actions, path)` records the hand in the archive (`hand`
member, `sharpa` when absent); a trajectory whose row width does not match its hand is rejected. Action rows are `56`
wide for `sharpa` and `52` wide for `wuji`; `s.actuator_names` gives the exact order.

### Robot
You control two dexterous hands, each mounted on its own six-DoF wrist positioning stage (three prismatic and three
serial revolute joints, no arm): the right hand on the stage `wrist_stage` (origin `task.json` `wrist_stage.origin`) and
the left hand (the right hand's mirror image) on `left_wrist_stage` (origin `task.json` `left_wrist_stage.origin`). Both
are needed as in the real task: one hand steadies the vacuum (or works the button) while the other handles the bin. The
stages and the fingers are position actuated in the physics engine under native force bounds; the vacuum body, the dust
bin and the release button move only through contact and their passive dynamics (the button is a spring-loaded slide).
The controller runs at 50 Hz, with twenty 1 ms physics substeps.

Each stage's `x, y, z` targets are offsets (metres, along the world axes) from its origin; the rotations are serial XYZ
joints (radians).

Two hands, each on its own six-axis wrist stage. The left hand is the right Wave mirrored in y; one row is one 50 Hz
control (twenty 1 ms physics substeps).

### Scene
The world frame has z up; lengths are in metres, angles in radians, quaternions WXYZ. A handheld vacuum (free body
`vacuum_body`, 0.752 kg) stands on its base skid on the counter (top at z = 0.65 m); its transparent dust bin (free body
`dust_container`, 0.18 kg) sits in front of the motor housing, with the nozzle overhanging the counter edge. The bin is
held at the bottom by two tabs resting on two ledges inside its mouth and at the top by the latch tooth of the red
release button (`release_button`, spring-loaded slide joint `button_depression`, 0 to 6 mm of travel, 600 N/m). The
tooth's ramp lets the bin's catch push it down while the bin is closed; pressing the button (nearly its full 6 mm)
lowers the tooth below the catch. Latch tooth, catch and bridge have the source's plastic friction 0.55, so pushing the
catch over the raised tooth needs a large closing force. A fixed lip on the housing sits 0.7 mm above the catch's
bridge, so the seated bin cannot be lifted straight out: its top has to tilt out from under the lip, which the raised
tooth prevents. Cameras: `overview` (the counter from the front left) and `closeup` (the latch and the bin).

## Others
- The bin comes out only with its top tilted out from under a lip, and only while the release button is held down.

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
