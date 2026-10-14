# DexHand: {{TITLE}}

{{TASK_TEXT}}

The robot is a fixed Tianji Marvin base with two seven-joint arms. The left arm's hand holds the dustpan by its
handle; the right arm's hand holds the broom by its shaft. Arms and fingers are position servos with native force
bounds; the broom, the dustpan and the debris move only through contact and gravity. At the start the current targets
keep both tools in the hands; the first 1.2 s are a settling period in which the grip is not yet judged. The simulator
integrates at 0.5 ms and every action row is one physics step, so rows are a 2000 Hz control. The service simulates
slower than real time (several seconds of CPU per simulated second).

{{HANDS}}
Sharpa rows
(58 targets): the 7 left-arm joints `SHOULDER_PITCH_L_J1_target ... WRIST_ROLL_L_J7_target`, the 7 right-arm joints
`SHOULDER_PITCH_R_J1_target ... WRIST_ROLL_R_J7_target` (radians), then the 22 left-hand and the 22 right-hand
Sharpa Wave finger targets (radians).
Wuji rows (54 targets): the same 14 arm targets, then the 20 left-hand and the 20 right-hand Wuji Hand 2.2
finger targets (`l_wuji_l_THJ0 ... l_wuji_l_LFJ3`, `r_wuji_r_THJ0 ... r_wuji_r_LFJ3`: thumb CMC flexion, CMC
abduction, MCP, IP, then index/middle/ring/pinky MCP flexion, MCP abduction, PIP, DIP; radians). With Wuji the start
differs only in the finger joints and their targets: both Wuji hands start closed on the same broom and dustpan
(the arm, tool, debris and bristle coordinates and the arm targets are those of the Sharpa start), and
the targets at the start keep them. The task, predicate and fail-fast rules are the same for both hands.

{{RESETS}}
## Robot service
The simulator runs in a separate service. You receive camera RGB, optional calibrated depth, and the robot's own joint
positions, velocities, actuator efforts, both palm poses (`l_hand_palm`, `r_hand_palm`) and current targets. Object poses, contacts and the predicate
state are not published. A failure ends the episode; a reset starts a new one (see `## Episodes and resets`). The
service records every executed row and replays the graded episode in two fresh processes. Leave your controller at `/app/output/gen.py`; no trajectory
hand-in is needed.

```python
from rcb_client import Robot
r = Robot()
spec = r.spec()
spec["hand"], spec["action_types"]["joint_position"]["layout"]
obs = r.get_obs(cameras=["work"], depth=True)
obs.last["work"]               # RGB uint8 (480, 640, 3)
obs.last_depth["work"]         # z-depth in metres
q = obs.group("joint_pos", now=True)
res = r.submit("joint_position", rows, dt=0.0005, interpolate="hold", video="none")
r.fk(q)                        # robot-link forward kinematics; no physics is stepped
r.status()
```
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order. `dt` must be a multiple of
`1 / spec["control_hz"]` (0.0005 s), at most 0.5 s; a chunk covers at most `spec["max_chunk_s"]` seconds. `hold`
keeps each row for `dt`; `linear` interpolates from the previous target. The client sends rows as float32. Targets are
clipped to the published joint limits and clipping is reported. Cameras are overview, work (the floor area and the pan),
pan and side, 640 x 480, fixed in the world. Requests return at most 1,000 camera images; ask for fewer cameras or a
lower `video_fps` for long chunks. `get_obs(seconds=...)` holds the current targets for up to 30 s and records those
steps; without seconds it only observes. Measured poses use WXYZ quaternions; world z is up, metres, the robot base at
the origin, the floor the plane z = -0.10 m. Forward kinematics covers the robot's own links; no IK primitive is
supplied. If the service connection fails, call `r.wait_ready()` and inspect `r.status()` before continuing. Crash
recovery resumes the same journaled episode, without a reset, and the wall-clock budget keeps running.
