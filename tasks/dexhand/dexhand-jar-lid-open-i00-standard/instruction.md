# DexHand: Open a jam jar and set the lid aside

Open the jam jar with the robot's right hand and set its lid aside on the worktop. Scene (world frame, metres, z up, +x forward from the robot): the worktop top is at z = 0.75 and spans |x| <= 0.45, |y| <= 0.58. A filled 297 ml glass jam jar (550 g, 67 mm body diameter, 110 mm tall, rim at z = 0.86) stands upright on the worktop centred at x = -0.22, y = -0.08. Nothing holds the jar: it stands on its own weight and glass-on-worktop friction, which resists only about 0.13 N m of twisting torque, so the hand must turn the lid without turning, sliding or tipping the jar. Its red 64.8 mm twist-off steel lid (32 g) is closed. Jar and lid are free rigid bodies. The closure is a lug thread made of contact geometry only: four inclined glass ramps on the jar neck hold four inward lugs of the lid, so the closed lid cannot be pulled off. Turning the lid counter-clockwise seen from above (positive rotation about +z relative to the jar) slides the lugs up the ramps; at 1.049 rad they pass the ramp ends, and while they sit in the gaps between the ramps (turn between 1.049 and about 1.26 rad) the lid lifts off freely; turned further without lifting, the lugs run into the next ramps' leads, and turning clockwise from the closed position tightens and jams. The lid is lightly closed: no vacuum, seal adhesion or tightening torque is modelled, and the jam is part of the jar's rigid mass, not a fluid. Complete three stages in this order. (1) Unscrew: while the lid is still seated on the thread (lid origin less than 6 mm above its closed height and within 4 mm of the jar axis, in the jar frame), its counter-clockwise turn relative to the jar, unwrapped after every physics substep, reaches at least 1.049 rad. (2) Lift clear: afterwards, the lowest point of the lid skirt rises more than 30 mm above the jar rim. (3) Set aside: afterwards, for 50 consecutive controls (1 s), the lid touches the worktop and touches neither the hand nor the jar, is upright (tilt at most 0.15 rad), has its centre at least 90 mm horizontally from the jar axis, moves at most 0.02 m/s and turns at most 0.3 rad/s, while the jar touches the worktop, is not touched by the hand, is upright within 0.10 rad and moves at most 0.02 m/s. The episode ends with success at that moment; a partial sequence never counts. The episode ends immediately with failure, checked after every 2 ms physics substep, when: the jar tilts more than 15 degrees (jar_tipped), slides more than 30 mm horizontally from its start (jar_slid) or is lifted more than 15 mm (jar_lifted); the lid touches the worktop before stage 2 (lid_knocked_off); the lid drops: at any substep it touches nothing (no hand, jar or worktop contact) while its centre of mass moves downward faster than 0.3 m/s (about a 5 mm free fall; there is no window to catch it again), or its centre of mass moves downward faster than 1.0 m/s whatever it touches (lid_dropped); the jar or the lid touches the floor, its origin falls more than 5 mm below the worktop top or leaves the worktop footprint (lid_off_table, jar_off_table) or the workspace box x in [-0.45, 0.45] m, y in [-0.40, 0.40] m, z in [0.73, 1.25] m (object_left_workspace); the lid leaves the thread upward while its lugs are not in the gaps between the ramps, i.e. its turn modulo pi/2 is outside [1.019, 1.291] rad (lid_forced_through_thread); the parked left arm or the left hand touches the jar or the lid (left_arm_contact; moving the left arm is not blocked, but the task is done by the right arm and hand); or the physics becomes unstable (unstable_physics). Later actions cannot undo a failure. Only robot actuator targets are allowed: the joints of the Marvin right arm and its hand (the left arm stays parked with its hand open), no object teleports, grasp welds, scripted object motion or direct object forces. Any robot part touching the jar or the lid counts as the hand touching it. The episode allows at most 3000 controls at 50 Hz; reaching that limit without success is a failure.

You control the right arm and right hand of a fixed Tianji Marvin robot: a stand with two 7-joint arms and a dexterous
hand on each wrist (the robot stands behind the worktop, its base centre at x = -0.56, y = 0.08 on the floor, facing
+x; shoulders at z = 1.121 m (1.221 m above the floor)). The left arm stays parked beside the torso with its hand open; the task is done
by the right arm and hand alone. Every arm and finger joint is a position servo inside the physics engine under native
force bounds; arm servos have stiffness 700 N m/rad, damping 48 N m s/rad and **no gravity compensation** (a held
target sags under the arm's weight unless your targets account for it). Turning, lifting, carrying and releasing the
lid require physical contact, and the jar is held by nothing but its own weight and friction on the worktop. The
controller runs at 50 Hz, with ten 2 ms physics substeps. At reset the right hand hangs open, palm down, about 0.1 m
above the lid with its fingers along +x; the left arm is at its parked pose.

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
joint positions, velocities, actuator efforts, wrist pose and current targets. The service serves no jar or lid pose,
contact, lid turn or stage; it reports only whether the episode has ended and whether in success or failure
(`task_failure`, without the failure's name). An episode ends at the first success or the first failure (see the task
text); after that the service accepts no more actions until a reset (see `## Episodes and resets`). The service records every action and watch step, then judges the graded episode as it ran
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
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order, all position targets in radians: the
14 Marvin arm joints (left arm `SHOULDER_PITCH_L_J1` ... `WRIST_ROLL_L_J7`, keep them at the parked start values;
then the right arm `..._R_J1` ... `..._R_J7`), then the left hand's and the right hand's finger joints. `D` is 58 for
`sharpa` (22 Sharpa Wave finger joints per hand, `left_thumb_CMC_FE` ... `left_pinky_DIP`, then `right_thumb_CMC_FE`
... `right_pinky_DIP`) and 54 for `wuji` (20 Wuji Hand 2.2 finger joints per hand, `l_wuji_l_THJ0..3` ...
`l_wuji_l_LFJ0..3`, then `r_wuji_r_THJ0..3` ... `r_wuji_r_LFJ0..3`). The arm servos have no gravity compensation. Actuator targets are clipped to the
published joint limits and clipping is reported. `dt` must be a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk
covers at most 10 s. Hold interpolation holds each row for `dt`; linear interpolation starts from the previous target.
The robot has no scalar gripper opening. Quaternions in measured poses use WXYZ; world z is up, +x points forward from
the robot, the jar stands at (-0.22, -0.08) and the worktop top is at z = 0.75 m. Cameras are overview, closeup, side
and wide, at 640 x 480. Requests can return
RGB frames or mp4, with depth `none`, `last` or `frames`. Each call returns at most 1,000 camera images, counting
per-frame depth; reduce cameras, fps or duration for larger chunks. `get_obs(seconds=...)` holds the current targets
for up to 30 s and records those steps. Calling it without seconds only observes the current state. Forward kinematics
uses only the robot's own links; no IK primitive is supplied. If the service connection fails, call `r.wait_ready()`
and inspect `r.status()` before continuing. Crash recovery resumes the same journaled episode, without a reset, and the
wall-clock budget keeps running.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
