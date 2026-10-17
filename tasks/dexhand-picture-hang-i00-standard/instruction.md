# DexHand: Hang a large picture on two wall hooks

Hang the framed picture on the two wall hooks. The free 2.0 kg frame (52 x 52 x 6 cm) stands upright on a console; two brass picture hooks are installed on the wall and two D-rings on passive hinges are screwed to the back of the frame. Lift the frame off the console with both hands, engage BOTH D-rings on their matching hooks (left ring on the left hook, right ring on the right hook), then let go: the picture must hang still and level from both hooks with no hand touching it. Success requires, in this order: (1) lift-off: the frame origin (the centre of its bottom edge) at least 0.02 m above its start height z = 0.72 m and no contact with the console; (2) engagement: both rings threaded on their own hooks (the hook's load saddle passes through the ring's D loop, with the ring between the hook's upturned lip and the wall; a ring resting on top of the lip does not count) and each ring touching its hook; (3) a released hang for 50 consecutive controls (1 s): both rings threaded, each hook carrying at least 20 % of the frame's weight vertically through its ring and both hooks together at least 85 %, no hand touching the frame, no frame contact with the console or the floor, the frame's top edge level within 3 degrees, its tilt from upright at most 0.10 rad, its centre-of-mass speed at most 0.02 m/s and its angular speed at most 0.15 rad/s. The episode ends with success at that moment; one engaged hook, or rings left on the hook lips, never counts. The episode ends immediately with failure, checked after every 2 ms physics substep, when the frame touches the floor, when its origin leaves the workspace box x in [0.20, 0.76] m, y in [-0.45, 0.45] m, z in [0.60, 1.30] m, when it tilts more than 0.6 rad from upright, when after lift-off its origin falls more than 0.01 m below its start height, when after both rings were engaged no hand touches the frame while a ring is not threaded (it fell off a hook), when an arm, torso or stand link of the robot touches anything (only the hands may make contact), or when the physics becomes unstable; and when after lift-off the frame is held by nothing (no hand contact, no console contact and not hanging threaded on both hooks with both rings touching them): at the end of any control, or at any substep where its centre of mass is also moving down faster than 0.2 m/s (dropped, even if caught again, released early, dangling from one hook or resting on the hook lips). Later actions cannot undo a failure. Only the robot's actuator targets (14 arm joints and the fingers of both hands) are allowed; no grasp welds, scripted object motion or forces on the frame. The episode allows at most 3000 controls at 50 Hz; reaching that limit without success is a failure.

You control a fixed dual-arm robot (Tianji Marvin: two 7-joint arms on a stand) with a dexterous hand on each wrist. The arm joints and the fingers are position actuated in the physics engine under native force bounds;
the frame moves only through contact, gravity and its two passive ring hinges, so lifting, carrying,
hooking and releasing all require physical contact. The controller runs at 50 Hz, with ten 2 ms physics substeps.

## Scene (world frame: metres, z up, x pointing into the wall)
- Wall face at x = 0.74. Two installed brass picture hooks at (0.74, +0.255, 1.38) (left) and (0.74, -0.255, 1.38)
  (right): a back strap on the wall, a 6 mm wide load saddle (top face at z = 1.3805) projecting 12 mm from the wall,
  and an upturned 10 mm lip (1 mm wire radius, axis at x = 0.728) at its end.
- Console top at z = 0.72, spanning x 0.35 to 0.65 and y -0.19 to 0.19; the console stands on its two rear legs
  (x = 0.615) so that the robot stand's base plate fits under its front half.
- The frame: 0.52 m wide (y), 0.52 m tall (z), 0.06 m deep (x), 2.0 kg plus two 6 g D-rings; its origin is the centre
  of its bottom edge and it starts upright at (0.50, 0, 0.72), print facing the room (-x). Each D-ring hinges about the
  frame's y axis at frame-local (0.033, +-0.255, 0.478) (3 mm behind the back face, on the side rails) and can swing
  from upright (0 rad) up to 1 rad toward the wall; its D loop (2 mm brass wire) is 18 mm wide and 20 mm tall. Felt
  bumpers sit on the back of the bottom corners.
- The robot stand faces the wall (+x) in front of the console, its base origin at (0.18, 0.00, 0.20): it stands on a
  0.10 m plinth exactly under its base plate; the shoulders are 1.121 m above the base origin, at y = +-0.2215. Only
  the hands may touch anything: any contact of an arm, torso or stand link with the frame, the hooks, the wall, the
  console, the floor or the other hand ends the episode (`robot_collision`).
- At the start both hands hang palm-inward above the frame's side rails, fingers pointing down, thumbs toward the wall. With
  `sharpa` the right hand is the genuine Sharpa Wave right hand and the left hand is a declared mirror image of it (the
  right model reflected, same joints, ranges and force limits); with `wuji` both are the manufacturer's left and right
  Wuji Hand 2.2 models.

## Hands
Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success predicate are the same for both; only one hand is used per episode.
Each row starts with the 14 Marvin arm joint targets (left arm J1-J7, then right arm J1-J7, radians), followed by the left hand's finger targets and then the right hand's (22 per hand for `sharpa`: the genuine right Sharpa Wave on the right flange and its declared mirror image on the left flange; 20 per hand for `wuji`: the manufacturer's left and right Wuji Hand 2.2). Both arms and both hands perform the task.
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
joint positions, velocities, actuator efforts, both wrist poses and current targets; the frame's state is not
published, measure it with the cameras. An episode ends at the first success or the first failure (see the task text);
after that the service accepts no more actions until a reset (see `## Episodes and resets`). The service records every
action and watch step, then judges the graded episode as it ran (that is the verdict; nothing is replayed). Leave your
controller at `/app/output/gen.py`; no trajectory hand-in is needed.

```python
from rcb_client import Robot
r = Robot()
spec = r.spec()
spec["hand"]                   # "sharpa" or "wuji"
obs = r.get_obs(cameras=["overview", "hook_closeup"], depth=True)
obs.last["overview"]           # RGB uint8 (480, 640, 3)
obs.last_depth["overview"]     # z-depth in metres
obs.meta["proprio"]            # named robot measurements (tcp_pose: both palms, 7 columns each)
q = obs.group("joint_pos", now=True)
res = r.submit("joint_position", rows, dt=0.02, interpolate="hold", video="none")
r.fk(q)                       # robot-link forward kinematics; no physics is stepped
r.status()
res.save("/app/runs/001")
```
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order: the 14 Marvin arm joint targets in
radians (left arm `SHOULDER_PITCH_L_J1_target` ... `WRIST_ROLL_L_J7_target`, then the right arm `..._R_J1_target` ...
`..._R_J7_target`), then the left hand's and the right hand's finger targets in radians. `D` is 58 for `sharpa` (22 Sharpa
Wave finger joints per hand, `left_thumb_CMC_FE` ... `left_pinky_DIP`, then `right_thumb_CMC_FE` ... `right_pinky_DIP`)
and 54 for `wuji` (20 Wuji Hand 2.2 finger joints per hand, `l_wuji_l_THJ0..3, l_wuji_l_FFJ0..3, l_wuji_l_MFJ0..3,
l_wuji_l_RFJ0..3, l_wuji_l_LFJ0..3`, then the same for `r_wuji_r_`). Arm servos: kp 700 N m/rad, kv 48, force limits
108 / 108 / 66 / 66 / 18 / 18 / 18 N m (J1 ... J7), no gravity compensation; each hand sits rigidly on its arm's flange.
The start targets hold the hands above the frame with open fingers. Actuator targets are
clipped to the published joint limits and clipping is reported. `dt` must be a multiple of 0.02 s, between 0.02 and
0.5 s; a chunk covers at most 10 s. Hold interpolation holds each row for `dt`; linear interpolation starts from the
previous target. The robot has no scalar gripper opening. Quaternions in measured poses use WXYZ. Cameras are
overview, front, side and hook_closeup, at 640 x 480. Requests can return RGB frames or mp4, with depth `none`, `last`
or `frames`. Each call returns at most 1,000 camera images, counting per-frame depth; reduce cameras, fps or duration
for larger chunks. `get_obs(seconds=...)` holds the current targets for up to 30 s and records those steps. Calling it
without seconds only observes the current state. Forward kinematics uses only the robot's own links; no IK primitive is
supplied. If the service connection fails, call `r.wait_ready()` and inspect `r.status()` before continuing. Crash
recovery resumes the same journaled episode, without a reset, and the wall-clock budget keeps running.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
