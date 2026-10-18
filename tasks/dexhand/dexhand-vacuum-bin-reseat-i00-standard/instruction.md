# DexHand: Remove and reinstall a vacuum dust bin

Remove the dust bin from the handheld vacuum on the counter and reinstall it. The bin is held by its two lower tabs on ledges at the bottom of the motor housing and by a spring latch at the top: the latch tooth on the red release button stops the bin's top catch from tilting out, and a fixed lip over the catch bridge stops it from being lifted straight out, so the top must tilt out from under the lip, which the tooth only allows while the button is pressed. Stages, in order: (1) release and remove: press the release button by at least 5.8 mm while the bin is still in its seat (bin origin within 5 mm of its seated pose), then take the bin away until its origin is more than 30 mm from its seated pose (both measured in the vacuum-body frame); (2) reinstall: put the bin back so that its origin is within 3 mm and its orientation within 0.05 rad of the seated pose (vacuum-body frame), the release button is back up (travel at most 1.5 mm, latch tooth raised) and the bin's catch is behind the tooth face (at most 0.5 mm in front of it); (3) let go: the stage-2 condition must hold with no hand contact on the bin, the vacuum body or the button, the bin and the vacuum body at rest (linear speed at most 0.01 m/s, bin angular speed at most 0.1 rad/s), for 50 consecutive controls (1 s). The episode ends with success at that moment; partial completion never counts. The episode ends immediately with failure, checked after every 1 ms physics substep, when the vacuum body moves more than 50 mm or tilts more than 0.35 rad from its start pose, when the bin falls (centre-of-mass downward speed above 0.99 m/s, i.e. a free fall from 5 cm, or above 0.55 m/s while nothing touches it), touches the floor or a table leg, its origin drops below the counter top (z < 0.65 m) or leaves the workspace box x in [0.2, 1.1] m, y in [-0.45, 0.45] m, z in [0.6, 1.2] m, when bin and vacuum geometry interpenetrate by more than 4 mm, or when the physics becomes unstable; later actions cannot undo a failure. Only robot actuator targets (the two wrist stages and the fingers of both hands) are allowed; no object teleports, welds or applied forces. The episode allows at most 3000 controls at 50 Hz.

You control two dexterous hands, each mounted on its own six-DoF wrist positioning stage (three prismatic and three
serial revolute joints, no arm): the right hand on the stage `wrist_stage` (origin (0.45, 0.0, 0.8) m) and
the left hand (the right hand's mirror image) on `left_wrist_stage` (origin (0.55, 0.3, 0.95) m).
Both are needed as in the real task: one hand steadies the vacuum (or works the button) while the other handles the
bin. The stages and the fingers are position actuated in the physics engine under native force bounds; the vacuum
body, the dust bin and the release button move only through contact and their passive dynamics (the button is a spring-loaded
slide). The controller runs at 50 Hz, with twenty 1 ms physics substeps.

## Hands
Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success predicate are the same for both; only one hand is used per episode.
Two hands, each on its own six-axis wrist stage. Sharpa (56): right stage (6), right fingers (22), left stage (6), left fingers (22). Wuji (52): right stage (6), left stage (6), right fingers (20), left fingers (20). The left hand is the right Wave mirrored in y (shared arm_rig.mirrored_left_wave); one row is one 50 Hz control (twenty 1 ms physics substeps).
The robot service runs the hand named by `DEXHAND_HAND` on the sim service (default `sharpa`); the agent cannot switch it during an episode. `spec()["hand"]` names it, and `spec()["action_types"]["joint_position"]` gives the row width (`56` for `sharpa`, `52` for `wuji`) and the exact order. The episode record names the hand; the service grades the episode it ran with that hand.

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
joint positions, velocities, actuator efforts, wrist pose and current targets. An episode ends at the first success
or the first failure (see the task text); after that the service accepts no more actions until a reset. The service
records every action and watch step, then judges the graded episode as it ran (that is the verdict; nothing is replayed).
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

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
