# DexJoCo · bimanual_hanoi (standard)

## Task
Stack all three disks on the post on the right arm's side, as in a Tower of Hanoi: the large disk at the bottom, then
the medium one, then the small one on top.

## Goal
Success: all three disks are on the right-hand post in that order, each slid down the post and at rest, with the other
two posts empty, for a moment. A larger disk left resting on a smaller one ends the episode as a failure. So does a disk
left resting on the table.

When you are done, send `/finish` to end the episode and get it graded. Only the state at that point counts.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- One episode, no reset: what you knock over stays knocked over.
- You get only the robot's camera images (RGB, depth on request, with their calibration) and its own proprioception
  (joints, tcp poses, the current targets): no object poses, no scene layout, no score, no success signal.

## Robot Interface
Two Franka Panda arms, each with a 16-joint Allegro hand (DexJoCo, MuJoCo). The robot runs as a service you reach
through its client or its MCP tools, as if it were real hardware: one live episode.

`POST /finish` (MCP tool `finish`): ends the episode; it is graded right away.

### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`:
```python
from rcb_client import Robot
r = Robot()                                   # connects (waits while the service starts)
spec = r.spec()                               # action types, cameras (+ calibration), proprio layout, robot_spec, kinematics, budget
obs = r.get_obs()                             # current frames of spec["default_cameras"]: obs.last[cam] -> uint8 (480, 640, 3)
obs = r.get_obs(cameras=["front", "handcam_rgb_right"], depth=True)   # + obs.last_depth[cam] -> float32 (480, 640) z-depth (m)
obs.meta["proprio"]                           # {"layout": [...], "now": [...]}; obs.group("tcp_pose", now=True)
obs.meta["cameras"]                           # per camera intrinsic_cv / extrinsic_cv / cam2world_gl for these frames
obs = r.hold(2.0)                             # hold the current targets for 2 s of robot time: obs.video[cam] = mp4 bytes
obs = r.get_obs(last_s=1.0)                   # the frames recorded over the last 1 s (reading moves no time)

res = r.submit("ee_pose", rows, dt=0.1)       # rows: (T, 46) targets dt seconds apart, executed at 50 Hz with interpolation
res = r.submit("joint_position", q_rows, dt=0.1)   # (T, 46) joint targets instead (see below)
res.meta["done"], res.meta["reason"], res.meta["clipped"], res.meta["control_steps_chunk"]
res.video["front"]; res.last["front"]; res.proprio   # mp4 of the chunk, last frame, float32 (N, P) proprio per frame
r.fk(q); r.ik({"tcp_right": pose}, seed=q)  # kinematics of the robot (stateless: no physics, no time)
r.status()                                    # calls, control steps, done, reason, elapsed time
```
One call returns at most 1000 images. If a call fails with a connection error, the service may have crashed; it resumes
the same episode. Call `r.wait_ready()`, then check `r.status()` (`spec["on_service_error"]`).

### MCP tools
- The same service is also an MCP server, `efe-robot` (in your tool list), with one tool per endpoint: `spec`,
  `observe`, `submit`, `kinematics`, `finish`. A tool takes its endpoint's request fields (any other field in `fields`)
  and returns the service's reply `meta` unchanged; images, arrays and video are written as files under `/app/obs/`
  (`.png`, `.npy`, `.mp4`) and the result lists them. Long action chunks can be passed as a file (`actions_file`).
- `observe` returns at once with what is already recorded: the current frame, or the last `last_s` seconds. Time passes
  only through `submit`, which answers when its rows have run; a `submit` with `interpolate` "hold", `seconds` and no
  rows lets time pass with the robot holding still.
- A call still running after 45 s returns `pending` with an `operation` id; `observe(operation=id)` collects its reply.
- The client and the tools drive the same robot in the same episode; use either, or both.

### Actions
- `ee_pose` (46 numbers, DexJoCo's own action): per arm, right first: tcp target position (3, metres, world frame), tcp
  target orientation (4, quaternion wxyz), 16 Allegro joint targets (rad). The arm tracks the target through DexJoCo's
  operational-space controller, which lags a moving target and stops where contact blocks it. The hand joints are
  position-controlled. Rows are `dt` apart (a whole multiple of 1/50 s, at most 0.5 s). With `interpolate="linear"`,
  positions and joints move linearly between rows and orientations by slerp; with `"hold"` they jump. A chunk may cover
  at most 10 s. Hand targets outside the ranges (`spec["action_types"]["ee_pose"]["hand_limits"]`) are clamped by the
  simulator and listed in `meta["clipped"]`. Build the next row from the `tcp_target` and `hand_target` proprio groups
  to move smoothly.
- `joint_position` (46 numbers): per arm, right first: 7 Panda joint targets, then the 16 Allegro joint targets (rad).
  The service turns the arm's targets into a tcp target by forward kinematics, and the same controller tracks it. The
  tcp reaches FK(q), but the measured arm joints may differ from q along the arm's redundant direction, because the
  controller's null space pulls towards a home posture. Out-of-limit values are clipped and reported.
- Control runs at 50 Hz (10 physics substeps of 2 ms).

### Observations
- Cameras: `front`, `back`, `left`, `right`, `top0` (static), `handcam_rgb_right`, `handcam_rgb_left` (on the hand
  mounts; they move, so use the calibration that comes with each response; `spec["cameras"][cam]["mount"]` gives the
  static pose or the mount link). Resolution 640x480. Rendering runs on the CPU: ask only for the cameras you need;
  `video="none"` makes a chunk fastest.
- Proprioception (`obs.meta["proprio"]`, its layout in `spec()["proprio_layout"]`): the joints, the tcp poses
  (`tcp_pose`), the current targets (`tcp_target`, `hand_target`).
- When the episode has ended, `meta["done"]` is set and `meta["reason"]` says why.

### Frames and joint order
- World frame, metres, z up; the robots stand at low x and reach towards +x (right arm at y < 0, left arm at y > 0);
  each arm's base pose is in `spec["robot_spec"]["base"]`. No other world coordinates are given (the cameras are
  calibrated, depth is available). Quaternions are WXYZ.
- The tcp (`tcp_right`, `tcp_left`) is the hand's mounting flange (`spec["robot_spec"]["tcp"]`), not the fingertips.
- Allegro joint order (right hand): index finger 0-3, middle 4-7, ring 8-11, thumb 12-15 (joint 0 of a finger = spread,
  1-3 = flexion from the knuckle out; thumb 12 = opposition). The LEFT hand's 16 values are mirrored: ring 0-3, middle
  4-7, index 8-11, thumb 12-15 (the joint names in `spec["proprio_layout"]` say which).

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning. Time left: `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the
  service's `time_left_s` (in every reply) starts at your first request, so the file is the one to trust. Calls into a
  long-running process can block for their whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 4 CPUs, 10 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Steps: no limit. Actions and simulated time are reported as cost.
- Finish: if you never send `/finish`, the episode is graded when your session ends.
