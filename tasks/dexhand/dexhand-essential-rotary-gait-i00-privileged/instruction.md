# DexHand · Multi-turn encoder knob with fixed-wrist finger gait (privileged)

## Task
One dexterous hand on a six-axis wrist stage, the wrist locked (no arm), with a rotary encoder knob under its fingers
(DexHand, MuJoCo). Keep the wrist fixed. Rotate the knob to +720 degrees (two turns), then back to +360 degrees and hold
it still, regripping as you go: at least four contact handoffs between finger sets that share a finger. The scene is one
fixed instance.
You have the full simulator to develop with; you hand in a trajectory of motor targets.

## Goal
Success: the knob has turned two full turns forward, with at least four handoffs between finger sets that share a
finger, then one full turn back, so that it ends one turn from its start, held still by the fingers. A replay ends as
soon as the task is done; later rows are not run.

The episode ends at once as a failure if the hand loses contact with the knob, presses it hard, the palm moves, or the
physics becomes unstable. Later actions cannot undo a failure.

Deliverable: `/app/output/trajectory.npz` with a numeric `actions` array of shape `(T, 28)` for Sharpa or `(T, 26)` for
Wuji (at most 50,000 rows) and the `hand` it was made for, as written by `s.save_trajectory` (an archive without `hand`
is replayed as Sharpa), and `/app/output/gen.py`, the script that produced it. Each row is one control step: wrist x/y/z
targets in metres, wrist XYZ Euler joint targets in radians, then the finger targets in `s.actuator_names` order. NaN,
infinity, object arrays and malformed or oversized trajectories are rejected. Save it compressed
(`numpy.savez_compressed`; `s.save_trajectory` does): an archive larger than 64 MB is rejected. Save a valid one early
and overwrite it when you have a better one.

Rules: write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
Only the actuator targets count: changing `s.data` or the scene while you develop changes nothing in the replay.

Only the robot's actuator targets act on the scene: no object teleports, grasp welds, scripted object motion or applied
forces.

## Robot Interface
### Session
`/opt/tools/rcb_dexhand.py`, importable as `rcb_dexhand`:
```python
from rcb_dexhand import Session
s = Session("essential_rotary_gait")      # or Session("essential_rotary_gait", hand="wuji")
s.hand, s.action_dim          # "sharpa", 28 (or "wuji", 26)
s.actuator_names              # action order; s.joint_names: the joint each target drives
s.state()                     # privileged qpos, qvel, ctrl, object poses and checker features
s.status()                    # success, done, reason, steps, stage, total_stages, state_sha
s.render_frame("overview")    # uint8 RGB 480 x 640; cameras: s.cameras()
s.reset()                     # exact frozen reset; unlimited during development
s.step(row)                   # execute one position-target row
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.replay(actions)             # reset, execute rows and check the task
```
Wrist XYZ targets are positions of the stage joints in the world frame, metres, z up; the rotational targets are serial
XYZ revolute joints, not a quaternion. Finger position targets are in radians.

### Actions
Sharpa rows: the six wrist targets, then
`right_thumb_CMC_FE, right_thumb_CMC_AA, right_thumb_MCP_FE, right_thumb_MCP_AA, right_thumb_IP`,
`right_<index|middle|ring>_MCP_FE, _MCP_AA, _PIP, _DIP` and `right_pinky_CMC, _MCP_FE, _MCP_AA, _PIP, _DIP`. Wuji rows:
the same six wrist targets, then `r_wuji_r_THJ0..3` (thumb CMC flexion, CMC abduction, MCP, IP) and `r_wuji_r_FFJ0..3`,
`MFJ0..3`, `RFJ0..3`, `LFJ0..3` (index, middle, ring, pinky: MCP flexion, MCP abduction, PIP, DIP).

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both. Choose the hand with `Session(..., hand="wuji")` or the environment variable
`DEXHAND_HAND=wuji` (default `sharpa`). `s.save_trajectory(actions, path)` records the hand in the archive (`hand`
member, `sharpa` when absent); a trajectory whose row width does not match its hand is rejected. Action rows are `28`
wide for `sharpa` and `26` wide for `wuji`; `s.actuator_names` gives the exact order. Both hands are mounted in the same
wrist frame. Each hand starts from its own finger pose (Wuji: `wuji_reset.json`), with the object held as at the Sharpa
start.

### Robot
You control one dexterous hand on a six-DoF wrist positioning stage: a Sharpa Wave hand with 22 independently actuated
finger joints (the default) or a Wuji Hand 2.2 with 20 (see Hands). The wrist stage is position actuated in the physics
engine; grasping and manipulating require physical contact. The five fingers are thumb, index, middle, ring and pinky.
The controller runs at 50 Hz, with ten 2 ms physics substeps.

This is a fixed-wrist essential dexterity task. Native equality constraints lock all six wrist joints. The first six
entries of every action must remain [-0.08, 0, 0.29, 0, 0, 0]. Float32 wire-format rounding is accepted and normalized
to those exact fixed targets before physics runs. Use the declared target values rather than copying measured wrist
joint positions. Only the finger targets may change. Objects have no actuators, scripted motion or grasp attachments;
they move through contact and normal gravity.

## Others
- The knob is a real encoder cap with its rounded outer profile, normal surface friction and bearing resistance on a
  passive hinge that turns without limit; nothing turns it but the fingers.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (the simulator's start-up too). At
  the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 2 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU. Over a cap a process can be killed (the CPU cap only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
