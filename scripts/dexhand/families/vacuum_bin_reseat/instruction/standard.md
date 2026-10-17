# DexHand: {{TITLE}}

{{TASK_TEXT}}

You control two dexterous hands, each mounted on its own six-DoF wrist positioning stage (three prismatic and three
serial revolute joints, no arm): the right hand on the stage `wrist_stage` (origin (0.45, 0.0, 0.8) m) and
the left hand (the right hand's mirror image) on `left_wrist_stage` (origin (0.55, 0.3, 0.95) m).
Both are needed as in the real task: one hand steadies the vacuum (or works the button) while the other handles the
bin. The stages and the fingers are position actuated in the physics engine under native force bounds; the vacuum
body, the dust bin and the release button move only through contact and their passive dynamics (the button is a spring-loaded
slide). The controller runs at 50 Hz, with twenty 1 ms physics substeps.

{{HANDS}}
## Scene and frames
The world frame has z up; lengths are in metres, angles in radians, quaternions WXYZ. A handheld vacuum (free body
`vacuum_body`, 0.752 kg) stands on its base skid on the counter (top at z = 0.65 m); its transparent dust bin (free body
`dust_container`, 0.18 kg) sits in front of the motor housing, with the nozzle overhanging the counter edge. The bin is
held at the bottom by two tabs resting on two ledges inside its mouth and at the top by the latch tooth of the red
release button (`release_button`, spring-loaded slide joint `button_depression`, 0 to 6 mm of travel, 600 N/m; the
source scene's values). The tooth's ramp lets the bin's catch push it down while the bin is closed; pressing the button
(nearly its full 6 mm) lowers the tooth below the catch. Latch tooth, catch and bridge have the source's plastic friction
0.55, so pushing the catch over the raised tooth needs a large closing force. A fixed lip on the housing sits 0.7 mm above the catch's bridge, so the seated bin cannot be
lifted straight out: its top has to tilt out from under the lip, which the raised tooth prevents. The vacuum-body frame is the body frame of `vacuum_body`; the seated bin pose in that frame is
fixed by the frozen start state (the bin starts seated). Cameras: `overview` (the counter
from the front left) and `closeup` (the latch and the bin).

{{RESETS}}
## Robot service
The simulator runs in a separate service. You receive camera RGB, optional calibrated depth, and the robot's own
joint positions, velocities, actuator efforts, wrist pose and current targets. An episode ends at the first success
or the first failure (see the task text); after that the service accepts no more actions until a reset. The service
records every action and watch step, then replays the graded episode with the recorded hand in two fresh processes.
Leave your controller at `/app/output/gen.py`; no trajectory hand-in is needed.

```python
from rcb_client import Robot
r = Robot()
spec = r.spec()
spec["hand"]                   # "sharpa" or "wuji"
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
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order. `D` is 56 for `sharpa`: the right
stage `wrist_x, wrist_y, wrist_z` (metres, offsets of the stage from its origin) and `wrist_rx, wrist_ry, wrist_rz`
(radians, serial XYZ joints), the 22 right Sharpa Wave finger targets `right_thumb_CMC_FE` ... `right_pinky_DIP`, the
left stage `left_wrist_x` ... `left_wrist_rz` and the 22 left finger targets `left_thumb_CMC_FE` ... `left_pinky_DIP`.
`D` is 52 for `wuji`: right stage, left stage, the right Wuji Hand 2.2 fingers `r_wuji_r_THJ0..3` ... `r_wuji_r_LFJ0..3`
and the left Wuji fingers `l_wuji_l_...` (the layout list is authoritative). Actuator targets are clipped to the published joint
limits and clipping is reported. `dt` must be a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk covers at most
10 s. Quaternions in measured poses use WXYZ; world z is up and the counter top is at z = 0.65 m. Cameras are overview
and closeup, at 640 x 480. Forward kinematics uses only the robot's own links; no IK primitive is supplied. If the
service connection fails, call `r.wait_ready()` and inspect `r.status()` before continuing.
