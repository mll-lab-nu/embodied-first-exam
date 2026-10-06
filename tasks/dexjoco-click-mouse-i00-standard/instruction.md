# DexJoCo · click_mouse — STANDARD MODE (robot as a service, eai-standard/2.2)

You control a Franka Panda arm with a 16-DoF Allegro hand, **as if it were real hardware**: the simulator runs in a service you cannot open. You get
one client and one episode. **Task:** Put the computer mouse on the magenta mousepad and click its button. Success: the mouse is on the pad (its centre within the pad's 0.15 m radius horizontally and within 0.05 m of the pad's height), the button has been pressed while the mouse was on the pad (button joint more than 0.001 rad past its rest angle), which turns the monitor blue, and the mouse then stays on the pad for 10 consecutive control steps. A click while the mouse is off the pad does nothing.

The mouse lies on the table in front of the monitor; the round magenta mousepad is next to it at lower y. The button is a hinge on the mouse's front half.

## Rules (real-robot rules)
- **No reset.** The episode starts when the service comes up and ends on success, on a task failure (see the task), when
  your time is up, or on a simulator error. Knocked-over objects stay knocked over.
- **No privileged state.** You see what the cameras see (RGB, and depth on request, with each camera's calibration) plus
  the robot's own proprioception (joints, tcp poses, the current targets). No object poses, no success check:
  `meta["done"]` / `meta["reason"]` tell you when the episode is over and why.
- Steps are unlimited; your wall-clock budget (90 minutes) is the limit (`meta["time_left_s"]`). Actions and
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
obs = r.get_obs(cameras=["front", "handcam_rgb"], depth=True)   # + obs.last_depth[cam] -> float32 (480, 640) z-depth (m)
obs.meta["proprio"]                           # {"layout": [...], "now": [...]}; obs.group("tcp_pose", now=True)
obs.meta["cameras"]                           # per camera intrinsic_cv / extrinsic_cv / cam2world_gl for these frames
obs = r.get_obs(seconds=2.0, video="mp4")     # hold the current targets and watch for 2 s (max 30): obs.video[cam] = mp4 bytes

res = r.submit("ee_pose", rows, dt=0.1)       # rows: (T, 23) targets dt seconds apart, executed at 50 Hz with interpolation
res = r.submit("joint_position", q_rows, dt=0.1)   # (T, 23) joint targets instead (see below)
res.meta["done"], res.meta["reason"], res.meta["clipped"], res.meta["control_steps_chunk"]
res.video["front"]; res.last["front"]; res.proprio   # mp4 of the chunk, last frame, float32 (N, P) proprio per frame
res.save("/app/runs/003")                     # meta.json, <cam>.mp4, last/<cam>.jpg, proprio.npy, ...
r.fk(q); r.ik({"tcp": pose}, seed=q)  # kinematics of the robot (stateless: no physics, no time)
r.status()                                    # calls, control steps, done, reason, elapsed time
```
Cameras: `front`, `back`, `left`, `right`, `top0` (static), `handcam_rgb` (on the hand mount; they move,
so use the calibration that comes with each response; `spec["cameras"][cam]["mount"]` gives the static pose or the mount
link). Resolution 640x480. Rendering runs on the CPU: ask only for the cameras you need; `video="none"` makes a chunk
fastest. If a call fails with a connection error the service may have crashed: it resumes the same episode;
`r.wait_ready()`, then check `r.status()` (`spec["on_service_error"]`).

### Action type `ee_pose` (23) — DexJoCo's own action
tcp target position (3, metres, world frame), tcp target orientation (4, quaternion wxyz), 16
Allegro joint targets (rad). The arm tracks the target through DexJoCo's operational-space controller (it lags a moving
target and stops where contact blocks it); the hand joints are position-controlled. Rows are `dt` apart (a whole multiple
of 1/50 s, at most 0.5 s); between rows positions and joints move linearly and orientations by slerp
(`interpolate="linear"`) or jump (`"hold"`); a chunk may cover at most 10 s. Hand targets outside the ranges
(`spec["action_types"]["ee_pose"]["hand_limits"]`) are clamped by the simulator and listed in `meta["clipped"]`. Build
the next row from the `tcp_target` and `hand_target` proprio groups to move smoothly.

### Action type `joint_position` (23)
7 Panda joint targets, then the 16 Allegro joint targets (rad). The service turns the arm's targets
into a tcp target by forward kinematics and the same controller tracks it: the tcp reaches FK(q), but the measured arm
joints may differ from q in the arm's redundant direction (the controller's null space pulls towards a home posture).
Out-of-limit values are clipped and reported.

## Conventions
- World frame, metres, z up; the robot stands at low x and reaches towards +x; each
  arm's base pose is in `spec["robot_spec"]["base"]`. No other world coordinates are given (D7: the cameras are
  calibrated, depth is available). Quaternions are **WXYZ**.
- The tcp (`tcp`) is the hand's mounting flange (`spec["robot_spec"]["tcp"]`), not the fingertips. Allegro joint
  order: index finger 0-3, middle 4-7, ring 8-11, thumb 12-15 (joint 0 of a finger = spread, 1-3 = flexion
  from the knuckle out; thumb 12 = opposition).
- Control runs at 50 Hz (10 physics substeps of 2 ms). There is no step budget: your wall-clock time is the limit.
