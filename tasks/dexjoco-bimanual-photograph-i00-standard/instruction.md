# DexJoCo · bimanual_photograph — STANDARD MODE (robot as a service, eai-standard/2.2)

You control two Franka Panda arms, each with a 16-DoF Allegro hand, **as if it were real hardware**: the simulator runs in a service you cannot open. You get
one client and one episode. **Task:** Hold the camera with the left hand in front of the logo and press its shutter with the right hand. Success, at one control step: the camera's view point is inside the target region (0.16 m radius, +-0.10 m height, 0.40 m in front of the logo along -x, i.e. about 0.3 m above the table), the camera's viewing axis is within 10 degrees of world +x, and the shutter button is touched by something other than the camera.

The camera lies on the table between the robots; the logo disk stands at the far side of the table.

## Rules (real-robot rules)
- **No reset.** The episode starts when the service comes up and ends on success, on a task failure (see the task), when
  your time is up, or on a simulator error. Knocked-over objects stay knocked over.
- **No privileged state.** You see what the cameras see (RGB, and depth on request, with each camera's calibration) plus
  the robot's own proprioception (joints, tcp poses, the current targets). No object poses, no success check:
  `meta["done"]` / `meta["reason"]` tell you when the episode is over and why.
- Steps are unlimited; your only budget is the time limit (`## Time limit`; `meta["time_left_s"]` is the service's count of it). Actions and
  simulated time are reported as cost. Do not stop before the task is solved.
- There is nothing to hand in: the service records your episode as the trajectory and grades it. Leave your script at
  `/app/output/gen.py` for the record (save it early, update it as you go).
- **Nothing is put into your context automatically.** Images and videos come back as arrays/bytes in a Python object;
  what you look at and where you store it is your code's decision.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`)
```python
from rcb_client import Robot
r = Robot()                                   # connects (waits while the service starts)
spec = r.spec()                               # action types, cameras (+ calibration), proprio layout, robot_spec, kinematics, budget
obs = r.get_obs()                             # current frames of spec["default_cameras"]: obs.last[cam] -> uint8 (480, 640, 3)
obs = r.get_obs(cameras=["front", "handcam_rgb_right"], depth=True)   # + obs.last_depth[cam] -> float32 (480, 640) z-depth (m)
obs.meta["proprio"]                           # {"layout": [...], "now": [...]}; obs.group("tcp_pose", now=True)
obs.meta["cameras"]                           # per camera intrinsic_cv / extrinsic_cv / cam2world_gl for these frames
obs = r.get_obs(seconds=2.0, video="mp4")     # hold the current targets and watch for 2 s (max 30): obs.video[cam] = mp4 bytes

res = r.submit("ee_pose", rows, dt=0.1)       # rows: (T, 46) targets dt seconds apart, executed at 50 Hz with interpolation
res = r.submit("joint_position", q_rows, dt=0.1)   # (T, 46) joint targets instead (see below)
res.meta["done"], res.meta["reason"], res.meta["clipped"], res.meta["control_steps_chunk"]
res.video["front"]; res.last["front"]; res.proprio   # mp4 of the chunk, last frame, float32 (N, P) proprio per frame
res.save("/app/runs/003")                     # meta.json, <cam>.mp4, last/<cam>.jpg, proprio.npy, ...
r.fk(q); r.ik({"tcp_right": pose}, seed=q)  # kinematics of the robot (stateless: no physics, no time)
r.status()                                    # calls, control steps, done, reason, elapsed time
```
Cameras: `front`, `back`, `left`, `right`, `top0` (static), `handcam_rgb_right`, `handcam_rgb_left` (on the hand mounts; they move,
so use the calibration that comes with each response; `spec["cameras"][cam]["mount"]` gives the static pose or the mount
link), `cam_pos_z` (on an object of the scene and moves with it: images and depth only, no mount and no pose -- `extrinsic_cv` / `cam2world_gl` are null in `meta["cameras"]` and NaN per frame -- because its pose would be that object's). Resolution 640x480. Rendering runs on the CPU: ask only for the cameras you need; `video="none"` makes a chunk
fastest. One call returns at most 1000 images (cameras x frames at `video_fps`, default 10, at most 50; depth for
every frame counts again; `spec["max_frames_per_call"]`): a larger request is refused with a 400 before anything runs, so
ask for fewer cameras, a lower `video_fps` or a shorter call. If a call fails with a connection error the service may have crashed: it resumes the same episode;
`r.wait_ready()`, then check `r.status()` (`spec["on_service_error"]`).

### Action type `ee_pose` (46) — DexJoCo's own action
Per arm, right first: tcp target position (3, metres, world frame), tcp target orientation (4, quaternion wxyz), 16
Allegro joint targets (rad). The arm tracks the target through DexJoCo's operational-space controller (it lags a moving
target and stops where contact blocks it); the hand joints are position-controlled. Rows are `dt` apart (a whole multiple
of 1/50 s, at most 0.5 s); between rows positions and joints move linearly and orientations by slerp
(`interpolate="linear"`) or jump (`"hold"`); a chunk may cover at most 10 s. Hand targets outside the ranges
(`spec["action_types"]["ee_pose"]["hand_limits"]`) are clamped by the simulator and listed in `meta["clipped"]`. Build
the next row from the `tcp_target` and `hand_target` proprio groups to move smoothly.

### Action type `joint_position` (46)
Per arm, right first: 7 Panda joint targets, then the 16 Allegro joint targets (rad). The service turns the arm's targets
into a tcp target by forward kinematics and the same controller tracks it: the tcp reaches FK(q), but the measured arm
joints may differ from q in the arm's redundant direction (the controller's null space pulls towards a home posture).
Out-of-limit values are clipped and reported.

## Conventions
- World frame, metres, z up; the robots stand at low x and reach towards +x (right arm at y < 0, left arm at y > 0); each
  arm's base pose is in `spec["robot_spec"]["base"]`. No other world coordinates are given (D7: the cameras are
  calibrated, depth is available). Quaternions are **WXYZ**.
- The tcp (`tcp_right`, `tcp_left`) is the hand's mounting flange (`spec["robot_spec"]["tcp"]`), not the fingertips. Allegro joint
  order (right hand): index finger 0-3, middle 4-7, ring 8-11, thumb 12-15 (joint 0 of a finger = spread, 1-3 = flexion
  from the knuckle out; thumb 12 = opposition). The LEFT hand's 16 values are mirrored: ring 0-3, middle 4-7, index 8-11, thumb 12-15 (the joint names in `spec["proprio_layout"]` say which).
- Control runs at 50 Hz (10 physics substeps of 2 ms). There is no step budget: your wall-clock time is the limit.

## External material
You may install packages you need (pip, apt). Please solve the task yourself: do not look up or download a solution to it, such as this benchmark's own source code, published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` is its own count of this limit, from the service's start or from your first request, so it can differ from the time you really have left. Installing packages is not cheating (`## External material` above).
