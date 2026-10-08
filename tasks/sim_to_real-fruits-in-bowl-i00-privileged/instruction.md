# Sim-to-real · YAM · fruits in the bowl

A cluttered breakfast table in front of the **left arm**: a red **bowl** (16 cm across, 5.5 cm deep), a **banana**, a **lemon**, an **orange**, a red **mug** and a **tomato soup can**, all scanned household objects (YCB, from RoboLab's asset library) with their real masses (banana 66 g, lemon 29 g).
**Task:** put the **banana** and the **lemon** into the bowl. The other objects may stay where they are.

## The robot
An **I2RT YAM bimanual station**: two 6-joint YAM arms with `linear_4310` parallel grippers, mounted on the table top
0.61 m apart and both facing +x, a RealSense D405 on each wrist and a third D405 on the gantry above and behind them
(`top_cam`). This scene is the digital twin of the physical station the task will be reproduced on: the arm model is MuJoCo Menagerie's
`i2rt_yam/yam_linear_4310.xml` (derived from I2RT's SDK, with its PD gains and gravity compensation) and the cameras
sit at I2RT's CAD extrinsics. **The trajectory you hand in is meant to be replayed on the physical robot later**, so
it has to respect the real station's limits below.

World frame = the left arm's base frame: **+x forward, +y to the left, +z up, metres**; the table top is z = 0, the
right arm's base is at (0, -0.61, 0). Both arms start in their rest pose (all joints 0, folded) with the grippers open.

## Controls
One control step = 1/50 s (10 physics steps of 2 ms). Each step takes **14 position targets**, in this order
(`rcb_yam.ACTUATOR_NAMES`): `left/joint1..joint6`, `left/gripper`, `right/joint1..joint6`, `right/gripper`.
Joints in rad (limits `s.lower` / `s.upper`); the gripper is the finger rail travel in m: 0.0475 fully open, 0 closed,
down to -0.005 to squeeze a grasped object (the gap between the finger pads is 2 x travel).
- **Rate limit** (the speed limit the physical station runs with): each step moves every applied target at most
  3.0 rad/s x 0.02 s = 0.06 rad (joints) or 0.25 m/s x 0.02 s = 5 mm (grippers) towards your command. `s.step()`
  applies the limit and records the applied targets, so a recorded trajectory always respects it; the verifier
  rejects a trajectory in which two consecutive rows (or the first row and the start pose) differ by more.
- **The two arms must never touch each other** (any arm-to-arm contact during the trajectory fails it).
- The arms are position-controlled with gravity compensation (the PD gains of I2RT's SDK for this arm), so a joint does not land
  exactly on its target under load; check where the gripper actually is.

## Success
In both families an object counts as **in** its container exactly as in NVIDIA RoboLab's `object_in_container`: its centre of mass lies inside the container's bounding box in the container's own frame (with one container height of open-top slack above it) **and** it touches the container. At the **end of the trajectory** every goal object must be in, the container must be upright (within 20 degrees), every object must be at rest (speed below 5 cm/s) and touched by neither robot (the grippers have let go), and the two arms must never have touched each other. `s.check()` (also returned by `s.step`) computes exactly this. Fields: `banana_in_bowl`, `lemon_in_bowl`, `bowl_upright`, `at_rest`, `robot_touches_object`, `arm_collision`, `success`.

## Tooling (`/opt/tools/rcb_yam.py`, importable as `rcb_yam`)
```python
import numpy as np, rcb_yam as ry
s = ry.Session("/app/instance.json")   # the frozen instance; s.model / s.data are MuJoCo objects
st = s.state()      # joints, applied targets, objects {name: {pos, quat_wxyz}}, sites (left/right grasp_site position)
                    #   and site_mats (their rotation: z = approach direction, y = finger slide axis), success fields
s.record_start()
r = s.step(targets) # (14,) targets for one control step -> the success fields (see Success)
A = s.record_stop(); s.save_trajectory(A)          # -> /app/output/trajectory.npz
s.replay(A)         # fresh replay from the start (what the verifier does)
s.reset()           # back to the start (as often as you like)
img = s.render("top_cam")                           # also left/wrist_cam, right/wrist_cam (D405s), front_view
```
Everything in `s.model` / `s.data` is readable (privileged mode), e.g. for inverse kinematics with `mujoco.mj_jacSite`
on the `left/grasp_site` / `right/grasp_site` sites (the point between the finger pads). Each object is one body named
as above; its meshes (the textured `visual.obj` in the body frame and the convex collision hulls `col_NN.obj`) and its
`meta.json` (bounding box, mass) are in `/opt/eai_s2r/assets/objects/<name>/`.

## What you hand in
`/app/output/trajectory.npz` — the applied targets, shape `(T, 14)` (T ≤ 3000, i.e. at most 60 s), one row per
control step. Record it with the tooling so the layout and the rate limit are right. The verifier replays it from the
frozen start in a separate sandbox (MuJoCo on the CPU is bit-exact). Leave the script that produced it at
`/app/output/gen.py`. Save a trajectory early and improve it; only the last one counts.

## Rules
- Write your own controller; do not use trained policies from anywhere.
- Only the targets count: editing `s.data` while debugging changes nothing in the replay.
- You have 60 minutes of wall-clock time. Do not stop early: use the time to check your trajectory with `s.replay`.
