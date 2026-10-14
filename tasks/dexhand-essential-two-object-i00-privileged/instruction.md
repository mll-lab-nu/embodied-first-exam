# DexHand: Independent walnut rotation and selective release

Keep the wrist fixed. Turn walnut A +90 degrees around palm-local Y, return A to its initial orientation, then release only A into the catch tray. Maintain walnut B at its initial position and orientation throughout. The walnuts, standardized to the same maximum dimension, must never contact one another. Before selective release, keep both objects unsupported by the environment and in load-bearing hand contact. Finally let A settle in the tray while continuing to hold B. If walnut A drops toward the table (center below 0.135 m) or leaves the tray footprint (more than 0.10 m horizontally from the tray center), or walnut B slips, the episode fails immediately.

You control one dexterous hand on a six-DoF wrist positioning stage: a Sharpa Wave hand with 22 independently
actuated finger joints (see Hands).
The wrist stage is position actuated in the physics engine; grasping and manipulating require physical contact.
The five fingers are thumb, index, middle, ring and pinky. The controller runs at 50 Hz, with ten 2 ms physics substeps.

This is a fixed-wrist essential dexterity task. Native equality constraints lock all six wrist joints.
The first six entries of every action MUST remain [-0.08, 0, 0.29, 0, 0, 0].
Float32 wire-format rounding is accepted and normalized to those exact fixed targets before physics runs.
Use the declared target values rather than copying measured wrist joint positions. Only the finger targets may
change. Objects have no actuators, scripted motion or grasp attachments; they move through contact and normal gravity.

## Hands
This task uses the Sharpa Wave (22 finger actuators per hand). The Wuji Hand 2.2 is not offered for this task: no Wuji Hand 2.2 finger pose holds walnut B at the start, so a Wuji episode could only fail. Selecting Wuji is refused.

## Action rows
Rows are 28 wide: the six wrist targets, then `right_thumb_CMC_FE, right_thumb_CMC_AA, right_thumb_MCP_FE, right_thumb_MCP_AA, right_thumb_IP`, `right_<index|middle|ring>_MCP_FE, _MCP_AA, _PIP, _DIP` and `right_pinky_CMC, _MCP_FE, _MCP_AA, _PIP, _DIP`. The fingers use the dissipative velocity coefficient declared in the frozen instance and start from its declared finger pose.
`s.actuator_names` gives the exact order. `s.save_trajectory(actions, path)` records the hand in the archive (`hand` member); the verifier replays the rows with the Sharpa Wave and rejects an archive of another width or labelled with another hand.

## Success predicate
The verifier evaluates these conditions on features it computes from simulator state (values rounded to six significant digits here; the exact numbers are in `catalog.json`). A stage or the terminal condition counts a control sample only if its bounds held at every 2 ms physics substep of that control interval; stages are completed in order and each starts after the previous one.

1. Stage `rotate_a_keep_b`: `0 <= a_quarter_turn_error <= 0.16`, `1 <= a_finger_contacts <= 5`, `0 <= speed <= 0.25`, for 5 consecutive control samples.
   While this stage is active (fail-fast): `a_hand_contacts >= 1`, `a_support == 0`, `0 <= a_position_error <= 0.035`, `0 <= speed <= 12`.
2. Stage `return_a_keep_b`: `0 <= a_orientation_error <= 0.16`, `1 <= a_finger_contacts <= 5`, `0 <= speed <= 0.25`, for 5 consecutive control samples.
   While this stage is active (fail-fast): `a_hand_contacts >= 1`, `a_support == 0`, `0 <= a_position_error <= 0.035`, `0 <= speed <= 12`.
3. Stage `release_a_only`: `a_hand_contacts == 0`, `deposit_support_a >= 1`, `0 <= a_deposit_distance <= 0.04`, for 5 consecutive control samples.
   While this stage is active (fail-fast): `0 <= a_linear_speed <= 2.5`, `0 <= a_angular_speed <= 80`.
4. Terminal hold after the last stage: `a_hand_contacts == 0`, `deposit_support_a >= 1`, `0 <= a_deposit_distance <= 0.04`, `1 <= b_finger_contacts <= 5`, `0 <= speed <= 0.06`, for 25 consecutive control samples.

Invariants, checked at every physics substep for the whole episode (fail-fast): `0 <= force <= 80`, `0 <= palm_drift <= 0.003`, `0 <= wrist_rotation <= 0.01`, `ball_pair_contacts == 0`, `0 <= b_position_error <= 0.015`, `0 <= b_orientation_error <= 0.2`, `b_support == 0`, `b_hand_contacts >= 1`, `1 <= b_finger_contacts <= 5`, `0 <= a_linear_speed <= 2.5`, `0 <= a_angular_speed <= 80`, `0.135 <= a_height <= 0.6`, `0 <= a_deposit_distance <= 0.1`.

The first violated invariant or guard, a non-finite feature or unstable physics fails the episode immediately and permanently: the episode ends there and later rows are not executed, so a dropped, slipped or knocked-away object can never be recovered. Success is reached when the terminal hold completes; the episode ends there too. Completing only some stages is a failure.

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

## Deliverable
Save `/app/output/trajectory.npz` with a numeric `actions` array of shape `(T, 28)` (at most 50,000 rows),
as written by `s.save_trajectory`, and `/app/output/gen.py`, the script that produced it. Each row is one control
step: wrist x/y/z targets in metres, wrist XYZ Euler joint targets in radians, then the 22 Sharpa Wave finger targets
in `s.actuator_names` order. Do not save object
states as the deliverable: the verifier executes the actions from the frozen start twice in fresh processes.
NaN, infinity, object arrays and malformed or oversized trajectories are rejected.
Save the archive compressed (`numpy.savez_compressed`; `s.save_trajectory` does): an archive file larger than 64 MB is rejected with reward 0.

## Tooling
```python
from rcb_dexhand import Session
s = Session("essential_two_object")
s.action_dim, s.actuator_names  # 28; action order (s.joint_names: the joint each target drives)
s.state()                     # privileged qpos, qvel, ctrl, object poses and checker features
s.status()                    # success, done, reason, steps, stage, total_stages, state_sha
s.render_frame("overview")    # uint8 RGB 480 x 640; cameras: overview, side, palm
s.reset()                     # exact frozen reset; unlimited during development
s.step(row)                   # execute one position-target row
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.replay(actions)             # reset, execute rows and recompute the predicate
```
Tooling lives in `/opt/tools`. Read `catalog.json`, `scene.py` and `checker.py` for the physical scene and exact
predicate. Wrist XYZ targets are positions of the stage joints in the world frame, metres, z up; the rotational
targets are serial XYZ revolute joints, not a quaternion. Finger position targets are in radians.

## External material
You may install packages you need (pip, apt). Please solve the task yourself: do not look up or download a solution to it, such as this benchmark's own source code, published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
