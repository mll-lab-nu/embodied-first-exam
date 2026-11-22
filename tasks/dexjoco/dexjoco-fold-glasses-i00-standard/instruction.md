# DexJoCo · fold_glasses (standard)

## Task
A Franka Panda arm with a 16-joint Allegro hand (DexJoCo, MuJoCo). Fold both temples of the glasses and put the glasses
into the open case. Open glasses lie on the table; the open case is next to them. Each temple is a hinge (`temple_0`,
`temple_1`).
The robot runs as a service you reach only through its client, as if it were real hardware: one live episode.

## Goal
Success: both temples are folded and the glasses lie inside the case, and they stay so for about a second. The episode
ends as soon as the task is done.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at `/app/output/gen.py`.

Real-robot rules:
- One episode, no reset: what you knock over stays knocked over.
- No privileged state: you get the robot's camera images (RGB, depth on request, with their calibration) and its own
  proprioception (joints, tcp poses, the current targets); no object poses, no scene layout, no score; the episode ends
  when the task is done, and the service tells you that it ended and why.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.

## Robot Interface
### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`:
```python
from rcb_client import Robot
r = Robot()                                   # connects (waits while the service starts)
spec = r.spec()                               # action types, cameras (+ calibration), proprio layout, robot_spec, kinematics, budget
obs = r.get_obs()                             # current frames of spec["default_cameras"]: obs.last[cam] -> uint8 (480, 640, 3)
obs = r.get_obs(cameras=["front", "handcam_rgb"], depth=True)   # + obs.last_depth[cam] -> float32 (480, 640) z-depth (m)
obs.meta["proprio"]                           # {"layout": [...], "now": [...]}; obs.group("tcp_pose", now=True)
obs.meta["cameras"]                           # per camera intrinsic_cv / extrinsic_cv / cam2world_gl for these frames
obs = r.get_obs(seconds=2.0, video="mp4")     # hold the current targets and watch for 2 s (max 30): obs.video[cam] = mp4 bytes

res = r.submit("ee_pose", rows, dt=0.1)       # rows: (T, 23) targets dt seconds apart, executed at 50 Hz with interpolation
res = r.submit("joint_position", q_rows, dt=0.1)   # (T, 23) joint targets instead (see below)
res.meta["done"], res.meta["reason"], res.meta["clipped"], res.meta["control_steps_chunk"]
res.video["front"]; res.last["front"]; res.proprio   # mp4 of the chunk, last frame, float32 (N, P) proprio per frame
r.fk(q); r.ik({"tcp": pose}, seed=q)  # kinematics of the robot (stateless: no physics, no time)
r.status()                                    # calls, control steps, done, reason, elapsed time
```
One call returns at most 1000 images. If a call fails with a connection error the service may have crashed: it resumes
the same episode; `r.wait_ready()`, then check `r.status()` (`spec["on_service_error"]`).

### Actions
- `ee_pose` (23 numbers, DexJoCo's own action): tcp target position (3, metres, world frame), tcp target orientation (4,
  quaternion wxyz), 16 Allegro joint targets (rad). The arm tracks the target through DexJoCo's operational-space
  controller (it lags a moving target and stops where contact blocks it); the hand joints are position-controlled. Rows
  are `dt` apart (a whole multiple of 1/50 s, at most 0.5 s); between rows positions and joints move linearly and
  orientations by slerp (`interpolate="linear"`) or jump (`"hold"`); a chunk may cover at most 10 s. Hand targets
  outside the ranges (`spec["action_types"]["ee_pose"]["hand_limits"]`) are clamped by the simulator and listed in
  `meta["clipped"]`. Build the next row from the `tcp_target` and `hand_target` proprio groups to move smoothly.
- `joint_position` (23 numbers): 7 Panda joint targets, then the 16 Allegro joint targets (rad). The service turns the
  arm's targets into a tcp target by forward kinematics and the same controller tracks it: the tcp reaches FK(q), but
  the measured arm joints may differ from q in the arm's redundant direction (the controller's null space pulls towards
  a home posture). Out-of-limit values are clipped and reported.
- Control runs at 50 Hz (10 physics substeps of 2 ms).

### Observations
- Cameras: `front`, `back`, `left`, `right`, `top0` (static), `handcam_rgb` (on the hand mount; they move, so use the
  calibration that comes with each response; `spec["cameras"][cam]["mount"]` gives the static pose or the mount link).
  Resolution 640x480. Rendering runs on the CPU: ask only for the cameras you need; `video="none"` makes a chunk
  fastest.
- Proprioception (`obs.meta["proprio"]`, its layout in `spec()["proprio_layout"]`): the joints, the tcp poses
  (`tcp_pose`), the current targets (`tcp_target`, `hand_target`).
- When the episode has ended, `meta["done"]` is set and `meta["reason"]` says why.

### Frames and joint order
- World frame, metres, z up; the robot stands at low x and reaches towards +x; each arm's base pose is in
  `spec["robot_spec"]["base"]`. No other world coordinates are given (the cameras are calibrated, depth is available).
  Quaternions are WXYZ.
- The tcp (`tcp`) is the hand's mounting flange (`spec["robot_spec"]["tcp"]`), not the fingertips.
- Allegro joint order: index finger 0-3, middle 4-7, ring 8-11, thumb 12-15 (joint 0 of a finger = spread, 1-3 = flexion
  from the knuckle out; thumb 12 = opposition).

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
- Resources: 4 CPUs, 10 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Steps: no limit; actions and simulated time are reported, as cost.
