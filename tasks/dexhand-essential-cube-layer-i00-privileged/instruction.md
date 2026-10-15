# DexHand: Free-held cube layer reversal

With the wrist locked, turn only the top layer +90 degrees, return it to zero, and turn it +90 degrees again. Stabilize the free cube body with other fingers; no external support or object actuation is allowed.

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
Choose the hand with `Session(..., hand="wuji")` or the environment variable `DEXHAND_HAND=wuji` (default `sharpa`). Action rows are `28` wide for `sharpa` and `26` wide for `wuji`; `s.actuator_names` gives the exact order. `s.save_trajectory(actions, path)` records the hand in the archive (`hand` member). The verifier rebuilds the scene with the recorded hand (default `sharpa` when the member is absent) and rejects a trajectory whose width does not match that hand; rows are never padded, truncated or converted between hands.

## Success predicate
The verifier evaluates these conditions on features it computes from simulator state (values rounded to six significant digits here; the exact numbers are in `catalog.json` in `/opt/tools`). A stage or the terminal condition counts a control sample only if its bounds held at every 2 ms physics substep of that control interval; stages are completed in order and each starts after the previous one.

1. Stage `quarter_turn`: `1.4508 <= top_turn <= 1.6908`, `1 <= base_contacts <= 5`, `1 <= mechanism_contacts <= 5`, for 5 consecutive control samples.
2. Stage `return_zero`: `-0.12 <= top_turn <= 0.12`, `1 <= base_contacts <= 5`, `1 <= mechanism_contacts <= 5`, for 5 consecutive control samples.
3. Stage `repeat_quarter_turn`: `1.4508 <= top_turn <= 1.6908`, `1 <= base_contacts <= 5`, `1 <= mechanism_contacts <= 5`, for 5 consecutive control samples.
4. Terminal hold after the last stage: `1.4508 <= top_turn <= 1.6908`, `1 <= base_contacts <= 5`, `0 <= speed <= 0.12`, for 15 consecutive control samples.

Invariants, checked at every physics substep for the whole episode (fail-fast): `0 <= force <= 80`, `0 <= speed <= 20`, `0 <= palm_drift <= 0.006`, `0 <= wrist_rotation <= 0.035`, `support == 0`, `0 <= body_drift <= 0.02`, `0 <= body_rotation <= 0.35`.

The first violated invariant or guard, a non-finite feature or unstable physics fails the episode immediately and permanently: the episode ends there and later rows are not executed, so a dropped, slipped or knocked-away object can never be recovered. Success is reached when the terminal hold completes; the episode ends there too. Completing only some stages is a failure.

Feature definitions:
- `top_turn`: angle of the cube's top layer relative to its body, rad
- `base_contacts`: fingers in contact (> 0.005 N) with the object's body / controller shell
- `mechanism_contacts`: fingers in contact (> 0.005 N) with the moving mechanism (top layer / thumbstick)
- `speed`: largest absolute velocity of any task-object degree of freedom, m/s or rad/s (peak over the substeps)
- `force`: largest contact force on any task object, N (peak over the 2 ms substeps)
- `palm_drift`: palm displacement from its reset position, m
- `wrist_rotation`: palm rotation from its reset orientation, rad
- `support`: contacts (> 0.01 N) between a task object and the environment (table, fixtures)
- `body_drift`: displacement of the free object's body from its reset position, m
- `body_rotation`: rotation of the free object's body from its reset orientation, rad

## Deliverable
Save `/app/output/trajectory.npz` with a numeric `actions` array of shape `(T, 28)` for Sharpa or `(T, 26)`
for Wuji (at most 50,000 rows) and the `hand` it was made for, as written by `s.save_trajectory` (an archive
without `hand` is replayed as Sharpa), and `/app/output/gen.py`, the script that produced it. Each row is one
control step: wrist x/y/z targets in metres, wrist XYZ Euler joint targets in radians, then the finger targets in
`s.actuator_names` order. Do not save object
states as the deliverable: the verifier executes the actions from the frozen start twice in fresh processes.
NaN, infinity, object arrays and malformed or oversized trajectories are rejected.
Save the archive compressed (`numpy.savez_compressed`; `s.save_trajectory` does): an archive file larger than 64 MB is rejected with reward 0.

## Tooling
```python
from rcb_dexhand import Session
s = Session("essential_cube_layer")      # or Session("essential_cube_layer", hand="wuji")
s.hand, s.action_dim          # "sharpa", 28 (or "wuji", 26)
s.actuator_names              # action order; s.joint_names: the joint each target drives
s.state()                     # privileged qpos, qvel, ctrl, object poses and checker features
s.status()                    # success, done, reason, steps, stage, total_stages, state_sha
s.render_frame("overview")    # uint8 RGB 480 x 640; cameras: s.cameras()
s.reset()                     # exact frozen reset; unlimited during development
s.step(row)                   # execute one position-target row
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.replay(actions)             # reset, execute rows and recompute the predicate
```
Tooling lives in `/opt/tools`. Read `catalog.json`, `scene.py` and `checker.py` for the physical scene and exact
predicate. Wrist XYZ targets are positions of the stage joints in the world frame, metres, z up; the rotational
targets are serial XYZ revolute joints, not a quaternion. Finger position targets are in radians.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
