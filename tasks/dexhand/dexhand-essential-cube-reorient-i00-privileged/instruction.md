# DexHand · Fixed-wrist multi-axis marked sphere reorientation (privileged)

## Task
Keep the wrist still. Turn the marked ball a quarter turn so that its top moves toward the fingertips, then a quarter
turn so that its top moves toward the thumb side, then back to how it started. Hold it still with at least 2 fingertips
at each of these 3 poses, and keep it in the hand with nothing else supporting it the whole time.

## Goal
Success: in this order, each held still for a moment with at least two fingertips on it, the ball is turned a quarter
turn with its top moving toward the fingertips, then from there a quarter turn with its top moving toward the thumb
side, then back to how it started; at the end it is held still there. A replay ends as soon as the task is done; later
rows are not run.

Any of these ends the episode at once as a failure, which later actions cannot undo:
- The sphere loses all contact with the hand or rests on anything else.
- The sphere moves far from its place in the hand or drops low.
- The fingers squeeze the sphere hard, or it is jerked violently.
- The palm moves.
- The physics becomes unstable.

Deliverable: `/app/output/trajectory.npz` and `/app/output/gen.py`, the script that produced it. The archive holds a
numeric `actions` array of shape `(T, 28)` for Sharpa or `(T, 26)` for Wuji (at most 50,000 rows) and the `hand` it was
made for, as written by `s.save_trajectory`. An archive without `hand` is replayed as Sharpa. Each row is one control
step: wrist x/y/z targets in metres, wrist XYZ Euler joint targets in radians, then the finger targets in
`s.actuator_names` order. NaN, infinity, object arrays and malformed or oversized trajectories are rejected. Save it
compressed with `numpy.savez_compressed` (`s.save_trajectory` does this). An archive larger than 64 MB is rejected. Save
a valid one early and overwrite it when you have a better one.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed.

Only the robot's actuator targets act on the scene: no object teleports, grasp welds, scripted object motion or applied
forces.

## Robot Interface
One dexterous hand on a six-axis wrist stage, the wrist locked (no arm), holding a free marked sphere (DexHand, MuJoCo).
The scene is one fixed instance. You have the full simulator to develop with; you hand in a trajectory of motor targets.

### Session
`/opt/tools/rcb_dexhand.py`, importable as `rcb_dexhand`:
```python
from rcb_dexhand import Session
s = Session("essential_cube_reorient")      # or Session("essential_cube_reorient", hand="wuji")
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
`DEXHAND_HAND=wuji` (default `sharpa`). `s.save_trajectory(actions, path)` records the hand in the archive as the `hand`
member; an archive without it counts as `sharpa`. A trajectory whose row width does not match its hand is rejected.
Action rows are `28` wide for `sharpa` and `26` wide for `wuji`; `s.actuator_names` gives the exact order. Both hands
are mounted in the same wrist frame. Each hand starts from its own finger pose (Wuji: `wuji_reset.json`), with the
object held as at the Sharpa start.

### Robot
Palm-local axes belong to a frame fixed to the palm; with the wrist locked it is aligned with the world axes: +X points
from the wrist toward the fingertips (world +x), +Y points across the palm from the thumb side toward the little-finger
side (world +y), and +Z points out of the palm, which faces up (world +z). In the simulator it has the orientation of
the `wrist_stage` body (the identity quaternion while the wrist is locked), not that of the palm link `right_hand_C_MC`,
whose own axes are rotated relative to it. A turn about a palm-local axis is about that palm-fixed axis (it does not
turn with the object), and a positive angle follows the right-hand rule: counterclockwise when seen from the positive
end of the axis looking back toward the palm. So +90 degrees about Y carries the side of the sphere that faces up toward
the fingertips, and +90 degrees about X carries the side that faces up toward the thumb side.

You control one dexterous hand on a six-DoF wrist positioning stage: a Sharpa Wave hand with 22 independently actuated
finger joints (the default) or a Wuji Hand 2.2 with 20 (see Hands). The wrist stage is position actuated in the physics
engine; grasping and manipulating require physical contact. The five fingers are thumb, index, middle, ring and pinky.
The controller runs at 50 Hz, with ten 2 ms physics substeps.

This is a fixed-wrist essential dexterity task. Native equality constraints lock all six wrist joints. The first six
entries of every action must remain [-0.08, 0, 0.29, 0, 0, 0]. If float32 rounding on the wire changes these values
slightly, that is accepted: they are set back to the exact fixed targets before physics runs. Use the declared target
values rather than copying measured wrist joint positions. Only the finger targets may change. Objects have no
actuators, scripted motion or grasp attachments; they move through contact and normal gravity.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (the simulator's start-up too). At
  the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 2 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU. Over a cap a process can be killed (the CPU cap only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
