# DexHand: Turn one page of a board book

Turn one page of the board book lying open on the desk. The book shows pages 4 (left) and 5 (right). Turn the next right-hand board, leaf 2 (printed pages 5 and 6), over the spine onto the left stack so that the book shows pages 6 and 7, and take the hand off the book. Progress is measured by leaf 2's binding hinge angle (joint `leaf_2_binding`: 0 = flat on the right-hand stack, pi = flat on the left-hand stack; it starts at about 0.068 rad because the board rests on its binding springback stop). The stages must happen in this order: lifted (angle above 30 degrees), past vertical (above 90 degrees), laid. Laid means, all at the same control: angle above 170 degrees, leaf 2 in physical contact with the left-hand stack (leaf 0, leaf 1 or the left cover), leaf-2 hinge speed at most 0.2 rad/s, every other leaf and both covers within 5 degrees of their start angles, and no contact between the hand and any part of the book. The laid condition must then hold for 50 consecutive controls (1 s); the episode ends with success at that moment. A partly turned page never counts. The episode ends immediately with failure, checked after every 2 ms physics substep, when the book's spine body moves more than 3 cm or rotates more than 10 degrees from its start pose (book shoved or lifted), when any other leaf moves more than 30 degrees from its start angle (a second page turned), when either cover moves more than 30 degrees (the book closing), when the centre of mass of any book part is more than 2 mm below the desk top (z = 0.30 m), or when the physics becomes unstable; later actions cannot undo a failure. Only robot actuator targets are allowed; no object teleports, welds, scripted page motion or direct forces on the book. The book is free on the desk: eight rigid 1.2 mm laminated boards and two covers on passive binding hinges with friction and damping and a small vertical binding compliance; the board next to the open spread rests on its binding springback stop 4 degrees above the stack. The episode allows at most 3000 controls at 50 Hz; reaching that limit without success is a failure.

You control one dexterous hand mounted on a six-DoF wrist positioning stage (three prismatic and three serial revolute
joints, no arm). The stage and the fingers are position actuated in the physics engine under native force bounds;
lifting, carrying and laying the page down require physical contact. The controller runs at 50 Hz, with ten 2 ms
physics substeps. The book is not attached to anything: it rests on the desk under gravity and friction.

## Scene
World frame: z up, metres and radians. The desk top is the plane z = 0.30 m (desk x in [-0.55, 0.55] m,
y in [-0.35, 0.45] m). The board book lies open on the desk as one free body (`book_spine`, nothing anchors it): its
spine runs along the world y axis through x = 0, y = 0. Every board is a 0.1524 m x 0.1524 m (6 x 6 in), 1.2 mm
thick laminated board of 16 g; the right-hand boards extend from the spine toward +x, the left-hand boards toward -x,
and all boards span y in [-0.0762, 0.0762] m. Boards hinge at the spine about the y axis (`<board>_binding`, passive
friction 0.002 N m and damping 0.006 N m s/rad) on a small vertical binding compliance (`<board>_binding_compliance`,
200 N/m). Hinge-root heights above the desk top: leaf 0 2.0 mm, leaf 1 3.4 mm (left stack, leaf 1 on top), leaf 2
9.0 mm, leaf 3 7.6 mm, leaf 4 6.2 mm, leaf 5 4.8 mm, leaf 6 3.4 mm, leaf 7 2.0 mm (right stack, leaf 2 on top), both
covers 0.6 mm. **Leaf 2's binding hinge has a lower stop at 0.07 rad (4 degrees): the board to turn rests on that
springback stop, so its fore-edge (x = 0.152 m) stands about 11 mm above leaf 3**; every other board lies flat on
its stack. Covers are glued to the spine (hinge spring 0.5 N m/rad). Leaf hinge angles are measured from the flat
right-hand position for right-hand boards (0 = flat right, pi = flat left) and from the flat left-hand position for
left-hand boards (negative = lifted toward the right).

## Hands
Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success predicate are the same for both; only one hand is used per episode.
Both hands hang from the same six-axis wrist stage, with the same wrist joints, ranges, gains and start targets; Sharpa starts palm up with the index finger straight, Wuji with its fingers at 0.
The robot service runs the hand named by `DEXHAND_HAND` on the sim service (default `sharpa`); the agent cannot switch it during an episode. `spec()["hand"]` names it, and `spec()["action_types"]["joint_position"]` gives the row width (`28` for `sharpa`, `26` for `wuji`) and the exact order. The episode record names the hand, and grading replays with that hand.

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
or the first failure (see the task text); after that the service accepts no more actions until a reset (see
`## Episodes and resets`). The service records every action and watch step, then replays the graded episode with the
recorded hand in two fresh processes. Leave your controller at `/app/output/gen.py`; no trajectory hand-in is
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
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order: the wrist targets `wrist_x, wrist_y,
wrist_z` (metres) and `wrist_rx, wrist_ry, wrist_rz` (radians, serial XYZ joints), then the finger targets in radians.
`D` is 28 for `sharpa` (22 Sharpa Wave finger joints `right_thumb_CMC_FE` ... `right_pinky_DIP`) and 26 for `wuji`
(20 Wuji Hand 2.2 finger joints `r_wuji_r_THJ0..3`, `r_wuji_r_FFJ0..3`, `r_wuji_r_MFJ0..3`, `r_wuji_r_RFJ0..3`,
`r_wuji_r_LFJ0..3`). Actuator targets are clipped to the published joint limits and clipping is reported. `dt` must be
a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk covers at most 10 s. Hold interpolation holds each row for `dt`;
linear interpolation starts from the previous target. The robot has no scalar gripper opening. Quaternions in measured
poses use WXYZ; world z is up and the desk top is at z = 0.30 m. The book's spine runs along the world y axis through
x = 0, y = 0; the right-hand pages extend toward +x (6 x 6 in boards, 0.152 m from the spine to the fore-edge), the
left-hand pages toward -x. Cameras are overview, closeup, front and top, at 640 x 480.
Requests can return RGB frames or mp4, with depth `none`, `last` or `frames`. Each call returns at most 1,000 camera
images, counting per-frame depth; reduce cameras, fps or duration for larger chunks. `get_obs(seconds=...)` holds the
current targets for up to 30 s and records those steps. Calling it without seconds only observes the current state.
Forward kinematics uses only the robot's own links; no IK primitive is supplied. If the service connection fails,
call `r.wait_ready()` and inspect `r.status()` before continuing. Crash recovery resumes the same journaled episode,
without a reset, and the wall-clock budget keeps running.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
