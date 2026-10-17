# DexHand: Put a folded letter into an envelope

Put the folded letter into the envelope. A tri-folded A4 letter (a stiff 99 x 210 x 2 mm card, 5 g) lies flat on the desk at (0.48, -0.14) m; an empty DL wallet envelope (110 x 220 mm, 6 g) lies flat at (0.48, 0.16) m with its open mouth along its +X long edge and the open flap on the desk beyond the mouth. The envelope is a pocket: back and front walls 4 mm apart, permanent 3 mm side seams (narrowing to nothing over the last 10 mm before the mouth) and a 4 mm bottom seam, and a 30 mm elastic mouth lip that starts closed (flush with the front wall, 4 mm above the back wall); a fingertip or the letter can lift it. Both objects are free and move only through contact. Move the letter to the mouth and feed it in through the mouth, then let go. Stages, measured on the letter's four corners (centre plane) in the envelope's own frame (origin at the envelope centre on the desk, x towards the mouth, mouth line x = 55 mm): (1) the letter is at the mouth: both leading corners are at least 10 mm past the mouth line, inside the side seams (|y| <= 107.6 mm) and between the walls (height 1.2 to 4.4 mm) while both trailing corners are still outside the mouth line; (2) the letter is inserted: at most 5 % of its 99 mm length (4.95 mm) is outside the mouth line, all four corners are inside the side seams, in front of the bottom seam (x >= -51.6 mm) and between the walls; (3) released: stage 2 holds with no contact between the hand and the letter or the envelope, and both objects at rest (linear speed <= 0.01 m/s, angular speed <= 0.2 rad/s), for 50 consecutive controls (1 s). Stages count in order; the episode ends with success when the hold completes. The episode ends immediately with failure, checked after every 2 ms physics substep, when the letter or the envelope falls below the desk top (origin z < 0.698 m), touches the floor, is dropped (touches nothing - no hand, desk or envelope - while its centre of mass falls faster than 0.1 m/s), leaves the desk (origin x outside [0.18, 0.78] m, y outside [-0.40, 0.40] m, or z > 1.00 m), when the letter is pressed through an envelope wall, seam or the mouth lip (any point of the letter's mid-plane inside one of them) or interpenetrates the envelope by more than 0.7 mm, when the envelope is pushed more than 5 cm from its start or tilted more than 0.35 rad, when the robot's arm, stand or parked left hand touches the letter or the envelope, or when the physics becomes unstable; later actions cannot undo a failure. Only robot actuator targets are allowed; no object teleports, welds, scripted object motion or object forces. The episode allows at most 6000 controls at 50 Hz; reaching that limit without success is a failure. Simplifications: the folded letter is simulated as one rigid 2 mm card with rounded fold edges (paper bending is not simulated); the envelope is one rigid pocket whose seams are solid walls, whose open flap is a thin wedge on the desk and whose mouth lip is a passive spring hinge; the flap is never sealed. The hand is on the right arm of a dual-arm robot standing at the desk's +x edge; the left arm stays parked.

You control the right arm and hand of a fixed Tianji Marvin dual-arm robot (a stand with two seven-joint arms and a
dexterous hand on each wrist). The robot stands at the desk's +x edge (base origin (1.15, -0.25, 0.10) m, facing -x; its base plate stands on the floor at z = 0); the
left arm is parked beside the torso and only the right arm and hand do the task. Arm joints and fingers are position
servos in the physics engine under native force bounds; pressing, sliding, pushing and releasing require physical
contact. The controller runs at 50 Hz, with ten 2 ms physics substeps.

## Hands
Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success predicate are the same for both; only one hand is used per episode.
Each row starts with the 14 Marvin arm joint targets (left arm J1-J7, then right arm J1-J7), followed by the left hand's finger targets and then the right hand's (22 per hand for `sharpa`, 20 per hand for `wuji`); the left arm is parked and only the right arm/hand perform the task.
Choose the hand with `Session(..., hand="wuji")` or the environment variable `DEXHAND_HAND=wuji` (default `sharpa`). Action rows are `58` wide for `sharpa` and `54` wide for `wuji`; `s.actuator_names` gives the exact order. `s.save_trajectory(actions, path)` records the hand in the archive (`hand` member). The verifier rebuilds the scene with the recorded hand (default `sharpa` when the member is absent) and rejects a trajectory whose width does not match that hand; rows are never padded, truncated or converted between hands.

## Action layout
Each row is one 50 Hz control in native actuator order (`s.actuator_names`), radians:

- `sharpa`: 58 values: the 7 left-arm joint targets `SHOULDER_PITCH_L_J1_target, SHOULDER_ROLL_L_J2_target,
  ELBOW_PITCH_L_J3_target, ELBOW_YAW_L_J4_target, WRIST_PITCH_L_J5_target, WRIST_YAW_L_J6_target,
  WRIST_ROLL_L_J7_target`, the 7 right-arm joint targets (`..._R_J1_target` ... `..._R_J7_target`), then the 22
  left-hand and the 22 right-hand Sharpa Wave finger targets (`left_thumb_CMC_FE` ... `left_pinky_DIP`,
  `right_thumb_CMC_FE` ... `right_pinky_DIP`).
- `wuji`: 54 values: the same 14 arm targets, then the 20 left-hand and the 20 right-hand Wuji Hand 2.2 finger
  targets (`l_wuji_l_THJ0..3, FFJ0..3, MFJ0..3, RFJ0..3, LFJ0..3`, then the same for `r_wuji_r_`).

Every target must lie within `s.model.actuator_ctrlrange`. Both hands start from the same arm targets (`task.json`
`initial_targets`); keep the left arm parked (its start targets), it must not touch the letter or the envelope.

## Deliverable
Save `/app/output/trajectory.npz` with a finite numeric `actions` array of shape `(T, 58)` for `sharpa` or `(T, 54)`
for `wuji`, at most 6000 rows, plus the `hand` member (`s.save_trajectory` writes both), and
`/app/output/gen.py`, the script that produced it. The separate verifier rebuilds the frozen scene with the recorded
hand and replays only these motor targets in two fresh processes; both replays must succeed and end in the identical
state hash. A replay stops at the first success or the first failure; later rows are not executed. Object poses,
configuration overrides, pickled arrays and success claims are not deliverables and are never read.
Save the archive compressed (`numpy.savez_compressed`; `s.save_trajectory` does): an archive file larger than 64 MB is rejected with reward 0.

## Tooling
```python
from rcb_dexhand import Session
s = Session("envelope_letter_insert")               # default hand: DEXHAND_HAND or "sharpa"
s = Session("envelope_letter_insert", hand="wuji")  # explicit hand
s.hand, s.action_dim, s.actuator_names          # selected hand, row width and exact row order
s.hold_action()                                 # current motor targets
s.model.actuator_ctrlrange                      # native target limits
s.model, s.data                                 # privileged MuJoCo model and state
s.features()                                    # corners in the envelope frame, contacts, speeds, failure details
s.status()                                      # success, done, reason, steps, stage (completed stages), total_stages
s.step(row)                                     # ten 2 ms physics substeps; a no-op once the episode is done
s.render_frame("overview")                      # RGB uint8 (480, 640, 3); also "closeup", "mouth"
s.reset()                                       # exact frozen reset
s.replay(actions)                               # reset, run rows until the episode ends, return status()
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
Read `/opt/tools/task.json`, `scene.py`, `checker.py` and `runtime.py` for the complete geometry, failure checks and predicate.
The world frame has z up; lengths are in metres and angles in radians. The desk top is at z = 0.70 m. The robot's
base pose is `task.json` `marvin`; `s.data.xpos` / `s.data.xmat` of the body `right_hand_C_MC` (the hand root on the right
flange) give the hand's pose, and MuJoCo's Jacobians (`mujoco.mj_jacBody`) are available for your own inverse
kinematics (none is supplied). The envelope frame used by the predicate is the `envelope` body; the letter is the
`letter` body.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
