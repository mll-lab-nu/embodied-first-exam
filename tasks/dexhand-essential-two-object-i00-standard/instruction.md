# DexHand: Independent walnut rotation and selective release

Keep the wrist fixed. Turn walnut A +90 degrees around palm-local Y, return A to its initial orientation, then release only A into the catch tray. Maintain walnut B at its initial position and orientation throughout. The walnuts, standardized to the same maximum dimension, must never contact one another. Before selective release, keep both objects unsupported by the environment and in load-bearing hand contact. Finally let A settle in the tray while continuing to hold B. If walnut A drops toward the table (center below 0.135 m) or leaves the tray footprint (more than 0.10 m horizontally from the tray center), or walnut B slips, the episode fails immediately.

You control one dexterous hand on a six-DoF wrist positioning stage: a Sharpa Wave hand with 22 independently
actuated finger joints (the default) or a Wuji Hand 2.2 with 20 (see Hands).
The wrist stage is position actuated in the physics engine; grasping and manipulating require physical contact.
The five fingers are thumb, index, middle, ring and pinky. The controller runs at 50 Hz, with ten 2 ms physics substeps.

This is a fixed-wrist essential dexterity task. Native equality constraints lock all six wrist joints.
The first six entries of every action MUST remain [-0.08, 0, 0.29, 0, 0, 0].
Float32 wire-format rounding is accepted and normalized to those exact fixed targets before physics runs.
Use the declared target values rather than copying measured wrist joint positions. Only the finger targets may
change. Objects have no actuators, scripted motion or grasp attachments; they move through contact and normal gravity.

## Hands
Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success predicate are the same for both; only one hand is used per episode.
Sharpa rows: the six wrist targets, then `right_thumb_CMC_FE, right_thumb_CMC_AA, right_thumb_MCP_FE, right_thumb_MCP_AA, right_thumb_IP`, `right_<index|middle|ring>_MCP_FE, _MCP_AA, _PIP, _DIP` and `right_pinky_CMC, _MCP_FE, _MCP_AA, _PIP, _DIP`. Wuji rows: the same six wrist targets, then `r_wuji_r_THJ0..3` (thumb CMC flexion, CMC abduction, MCP, IP) and `r_wuji_r_FFJ0..3`, `MFJ0..3`, `RFJ0..3`, `LFJ0..3` (index, middle, ring, pinky: MCP flexion, MCP abduction, PIP, DIP). Both hands are mounted in the same wrist frame; Sharpa fingers use the dissipative velocity coefficient declared in the frozen instance, Wuji fingers the manufacturer's position servos. Sharpa starts from the instance's declared finger pose; Wuji starts from the pose in `wuji_reset.json` (neutral fingers when the file is absent), an authoring choice that keeps the object held at reset, not a policy. The wrist, fixtures and predicate are identical for both hands; where a Wuji grasp cannot hold an object at the Sharpa start pose, `wuji_reset.json` also declares the held objects' start poses in the Wuji grasp, and every reset-relative quantity is measured from the post-reset pose.
The robot service runs the hand named by `DEXHAND_HAND` on the sim service (default `sharpa`); the agent cannot switch it during an episode. `spec()["hand"]` names it, and `spec()["action_types"]["joint_position"]` gives the row width (`28` for `sharpa`, `26` for `wuji`) and the exact order. The episode record names the hand, and grading replays with that hand.

## Success predicate
The verifier evaluates these conditions on features it computes from simulator state (values rounded to six significant digits here; the verifier uses the frozen task's unrounded values, which differ from these only beyond the sixth significant digit). A stage or the terminal condition counts a control sample only if its bounds held at every 2 ms physics substep of that control interval; stages are completed in order and each starts after the previous one.

1. Stage `rotate_a_keep_b`: `0 <= a_quarter_turn_error <= 0.16`, `1 <= a_finger_contacts <= 5`, `0 <= speed <= 0.25`, for 5 consecutive control samples.
   While this stage is active (fail-fast): `a_hand_contacts >= 1`, `a_support == 0`, `0 <= a_position_error <= 0.035`, `0 <= speed <= 12`.
2. Stage `return_a_keep_b`: `0 <= a_orientation_error <= 0.16`, `1 <= a_finger_contacts <= 5`, `0 <= speed <= 0.25`, for 5 consecutive control samples.
   While this stage is active (fail-fast): `a_hand_contacts >= 1`, `a_support == 0`, `0 <= a_position_error <= 0.035`, `0 <= speed <= 12`.
3. Stage `release_a_only`: `a_hand_contacts == 0`, `deposit_support_a >= 1`, `0 <= a_deposit_distance <= 0.04`, for 5 consecutive control samples.
   While this stage is active (fail-fast): `0 <= a_linear_speed <= 2.5`, `0 <= a_angular_speed <= 80`.
4. Terminal hold after the last stage: `a_hand_contacts == 0`, `deposit_support_a >= 1`, `0 <= a_deposit_distance <= 0.04`, `1 <= b_finger_contacts <= 5`, `0 <= speed <= 0.06`, for 25 consecutive control samples.

Invariants, checked at every physics substep for the whole episode (fail-fast): `0 <= force <= 80`, `0 <= palm_drift <= 0.003`, `0 <= wrist_rotation <= 0.01`, `ball_pair_contacts == 0`, `0 <= b_position_error <= 0.015`, `0 <= b_orientation_error <= 0.2`, `b_support == 0`, `b_hand_contacts >= 1`, `1 <= b_finger_contacts <= 5`, `0 <= a_linear_speed <= 2.5`, `0 <= a_angular_speed <= 80`, `0.135 <= a_height <= 0.6`, `0 <= a_deposit_distance <= 0.1`.

The first violated invariant or guard, a non-finite feature or unstable physics fails the episode immediately and permanently: the episode ends there and later rows are not executed, so a dropped, slipped or knocked-away object can never be recovered in that episode (a reset starts a new one: `## Episodes and resets`). Success is reached when the terminal hold completes; the episode ends there too. Completing only some stages is a failure.

Feature definitions:
- `a_quarter_turn_error`: rotation between walnut A and its +90 degree target about the declared axis, rad
- `a_finger_contacts`: fingers touching walnut A (> 0.005 N)
- `speed`: largest absolute velocity of any task-object degree of freedom, m/s or rad/s (peak over the substeps)
- `a_hand_contacts`: contacts (> 0.005 N) between walnut A and the hand
- `a_support`: contacts (> 0.005 N) between walnut A and the environment
- `a_position_error`: walnut A displacement from its reset position in the palm frame, m
- `a_orientation_error`: walnut A rotation from its reset orientation in the palm frame, rad
- `deposit_support_a`: contacts between walnut A and the catch-tray floor
- `a_deposit_distance`: horizontal distance of walnut A from the catch-tray centre, m
- `a_linear_speed`: walnut A linear speed, m/s
- `a_angular_speed`: walnut A angular speed, rad/s
- `b_finger_contacts`: fingers touching walnut B (> 0.005 N)
- `force`: largest contact force on any task object, N (peak over the 2 ms substeps)
- `palm_drift`: palm displacement from its reset position, m
- `wrist_rotation`: palm rotation from its reset orientation, rad
- `ball_pair_contacts`: contacts between the two walnuts
- `b_position_error`: walnut B displacement from its reset position in the palm frame, m
- `b_orientation_error`: walnut B rotation from its reset orientation in the palm frame, rad
- `b_support`: contacts (> 0.005 N) between walnut B and the environment
- `b_hand_contacts`: contacts (> 0.005 N) between walnut B and the hand
- `a_height`: height of walnut A's centre, m (the tray floor is at about 0.155 m, the table top at 0.10 m)

## Episodes and resets
You have **20 resets** (`spec["budget"]["reset"]`, which is authoritative: if it says 0, there is no reset
and the one episode is the run). A reset puts the robot and every object back in the same frozen starting state and
starts a new episode, either abandoning the running one or after one has ended; it takes no simulated time and
returns the start's images and proprioception:
```python
res = r._post("/reset", {"cameras": ["overview"]}, [], 900)   # POST /reset (the 2.2 client has no reset())
res.meta["episode"], res.meta["resets_left"]
```
Once an episode has ended, `submit` raises `EpisodeOver` until you reset. **Only the last episode is graded**: an
episode you reset away is never graded, a success ends the run at once (no reset after it), and when your time is up
the episode then running is the one graded. The wall clock is the run's and never restarts; `meta["episode"]` and
`meta["resets_left"]` count the episodes (`meta["control_steps"]` is the current episode's,
`meta["control_steps_total"]` all of them).

## Robot service
The simulator runs in a separate service. You receive camera RGB, optional calibrated depth, and the robot's own
joint positions, velocities, actuator efforts, wrist pose and current targets. A failure ends an episode at once; a
reset starts a new one (see `## Episodes and resets`). The service records every action and watch step, then replays
the graded episode in two fresh processes. Leave your controller at `/app/output/gen.py`; no trajectory hand-in is
needed.

```python
from rcb_client import Robot
r = Robot()
spec = r.spec()
obs = r.get_obs(cameras=["overview", "inhand_top"], depth=True)
obs.last["overview"]           # RGB uint8 (480, 640, 3)
obs.last_depth["overview"]     # z-depth in metres
obs.meta["proprio"]            # named robot measurements
q = obs.group("joint_pos", now=True)
res = r.submit("joint_position", rows, dt=0.02, interpolate="hold", video="none")
r.fk(q)                       # robot-link forward kinematics; no physics is stepped
r.status()
res.save("/app/runs/001")
```
`rows` is `(T, 28)` (Sharpa) or `(T, 26)` (Wuji) in `spec["action_types"]["joint_position"]["layout"]` order: wrist XYZ translations (metres),
three serial XYZ rotational joints (radians), then the 22 or 20 finger joints (radians). Actuator targets are clipped to the
published joint limits and clipping is reported. `dt` must be a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk
covers at most 10 s. Hold interpolation holds each row for `dt`; linear interpolation starts from the previous target.
The robot has no scalar gripper opening. Quaternions in measured poses use WXYZ; world z is up. Cameras are overview,
side, palm (behind the hand), and two close-ups of the held object, `inhand_top` (from above the palm)
and `inhand_side` (from the thumb side), at 640 x 480; the default is overview and inhand_top. No object state is
published: the close-ups (with depth and their calibration) are how you see the object in the hand. Requests can return RGB frames or mp4, with depth `none`, `last` or `frames`. Each call
returns at most 1,000 camera images, counting per-frame depth; reduce cameras, fps or duration for larger chunks.
`get_obs(seconds=...)` holds the current targets for up to 30 s and records those steps. Calling it without seconds
only observes the current state. Forward kinematics uses only the robot's own links; no IK primitive is supplied.
If the service connection fails, call `r.wait_ready()` and inspect `r.status()` before continuing. Crash recovery
resumes the same journaled episode, without a reset, and the wall-clock budget keeps running.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
