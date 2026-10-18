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
- The sheet starts flat at z = 0.3012 m, spanning x from 0 to 0.16 m and y from -0.05 to 0.05 m. The half with
  x <= 0.08 m is glued down and never moves; the fold line is at x = 0.08 m (an orange guide line marks it). A fold
  brings the free edge (x = 0.16 m) back over the glued edge (x = 0): the free half rotates by more than 2.6 rad about
  the fold line, upward and over.
- The paper is a passive elastic/plastic sheet: it bends elastically about 0.5 rad beyond its rest shape and then
  yields, so a crease becomes permanent only when the paper is bent well past its current rest shape, and a fold
  that is merely held springs partly back when released. Contact compliance gives it an effective thickness of 0.7 mm.

{{HANDS}}
{{RESETS}}
## Robot service
The simulator runs in a separate service. You receive camera RGB, optional calibrated depth, and the robot's own
joint positions, velocities, actuator efforts, wrist pose and current targets; paper state is not published. An
episode ends at the first success or failure, and after at most 1500 controls; a reset starts a new one (see
`## Episodes and resets`). The service records every action and watch step, then judges the graded episode as it ran
(that is the verdict; nothing is replayed). Leave your controller at `/app/output/gen.py`; no trajectory hand-in is needed.

```python
from rcb_client import Robot
r = Robot()
spec = r.spec()
spec["hand"]                   # "sharpa" or "wuji" (set by the service)
obs = r.get_obs(cameras=["overview"], depth=True)
obs.last["overview"]           # RGB uint8 (480, 640, 3)
obs.last_depth["overview"]     # z-depth in metres
obs.meta["proprio"]            # named robot measurements
q = obs.group("joint_pos", now=True)
res = r.submit("joint_position", rows, dt=0.02, interpolate="hold", video="none")
r.fk(q)                       # robot-link forward kinematics; no physics is stepped
r.status()
res.save("/app/runs/001")
```
`rows` is `(T, 28)` for `sharpa` or `(T, 26)` for `wuji`, in `spec["action_types"]["joint_position"]["layout"]`
order: `wrist_x, wrist_y, wrist_z` translations (metres), `wrist_rx, wrist_ry, wrist_rz` serial XYZ rotational joints
(radians), then the finger joints (radians). Actuator targets are clipped to the published joint limits and clipping
is reported. `dt` must be a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk covers at most 10 s. Hold
interpolation holds each row for `dt`; linear interpolation starts from the previous target. The robot has no scalar
gripper opening. Quaternions in measured poses use WXYZ; world z is up. Cameras are overview and side, at 640 x 480.
Requests can return RGB frames or mp4, with depth `none`, `last` or `frames`. Each call returns at most 1,000 camera
images, counting per-frame depth; reduce cameras, fps or duration for larger chunks. `get_obs(seconds=...)` holds the
current targets for up to 30 s and records those steps (they count toward the 1500 controls). Calling it without
seconds only observes the current state. Forward kinematics uses only the robot's own links; no IK primitive is
supplied. If the service connection fails, call `r.wait_ready()` and inspect `r.status()` before continuing. Crash
recovery resumes the same journaled episode, without a reset, and the wall-clock budget keeps running.
