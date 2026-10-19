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
The robot service runs the hand named by `DEXHAND_HAND` on the sim service (default `sharpa`); the agent cannot switch it during an episode. `spec()["hand"]` names it, and `spec()["action_types"]["joint_position"]` gives the row width (`58` for `sharpa`, `54` for `wuji`) and the exact order. The episode record names the hand; the service grades the episode it ran with that hand.

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
joint positions, velocities, actuator efforts, the hand root pose (`right_hand_C_MC`) and current targets. An episode ends at the first success
or the first failure (see the task text); after that the service accepts no more actions until a reset (see
`## Episodes and resets`). The service records every action and watch step, then judges the graded episode as it ran
(that is the verdict; nothing is replayed). Leave your controller at `/app/output/gen.py`; no trajectory hand-in is
needed.

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
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order (radians): the 7 left-arm joint targets
`SHOULDER_PITCH_L_J1_target ... WRIST_ROLL_L_J7_target`, the 7 right-arm joint targets `SHOULDER_PITCH_R_J1_target ...
WRIST_ROLL_R_J7_target`, then the left-hand and the right-hand finger targets. `D` is 58 for `sharpa` (22 Sharpa Wave
finger joints per hand, `left_thumb_CMC_FE` ... `right_pinky_DIP`) and 54 for `wuji` (20 Wuji Hand 2.2 finger joints
per hand, `l_wuji_l_THJ0` ... `r_wuji_r_LFJ3`). Keep the left arm at its start targets; only the right arm and hand do
the task. Actuator targets are clipped to the published joint limits and clipping is reported. `dt` must be
a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk covers at most 10 s. Hold interpolation holds each row for `dt`;
linear interpolation starts from the previous target. The robot has no scalar gripper opening. Quaternions in measured
poses use WXYZ; world z is up and the desk top is at z = 0.70 m. Cameras are overview, closeup and mouth (a low view of the envelope mouth), at 640 x 480.
Requests can return RGB frames or mp4, with depth `none`, `last` or `frames`. Each call returns at most 1,000 camera
images, counting per-frame depth; reduce cameras, fps or duration for larger chunks. `get_obs(seconds=...)` holds the
current targets for up to 30 s and records those steps. Calling it without seconds only observes the current state.
Forward kinematics uses only the robot's own links (the robot base is at (1.15, -0.25, 0.10) m, facing -x); no IK
primitive is supplied. If the service connection fails,
call `r.wait_ready()` and inspect `r.status()` before continuing. Crash recovery resumes the same journaled episode,
without a reset, and the wall-clock budget keeps running.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
