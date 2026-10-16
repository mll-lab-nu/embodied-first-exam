# iSpatialGym — standard mode (robot as a service, eai-standard/2.2)

You drive an **R1Pro** mobile robot with two arms, in a house, **as if it were real hardware**. The simulator
(iSpatialGym on BEHAVIOR-1K's OmniGibson) runs in a service you cannot open: you get one Python client and one episode.

$goal_rule

## Rules (real-robot rules)
- **One episode, no reset.** The episode starts when the service is up. It ends on success; after **$max_steps control
  steps** ($max_steps_s s of simulated time, `spec["max_control_steps"]`; the reason is
  "$max_steps_reason"); when your time runs out; or on a simulator error.
  Anything you knock over or push away stays where it ends up.
- **What you can sense.** RGB images from the robot's three cameras, and the robot's own proprioception (joints, base pose
  and velocity, end-effector and fingertip poses, gripper openings). Every pose is in the **odometry frame**: the robot's
  `base_link` at the start of the episode (x forward, y left, z up). You get no object poses, no map, no world frame, and
  no success signal before the episode ends.
- **A malformed request is refused with a 400 and nothing is executed** (a wrong type or shape, a value out of range,
  a `dt` that is not a whole number of control periods, `video_fps` outside 1-30, a call that would return more than
  300 images, cameras × frames, `spec["max_frames_per_call"]`): fix it and send it again.
- **Nothing to hand in.** The service records your episode as the trajectory and grades it. Leave your script at
  `/app/output/gen.py` for the record.
- **Nothing is put into your context automatically.** Images and videos come back as arrays/bytes in a Python object;
  what you look at and where you store it is your code's decision.
- **If the service crashes** (a connection error or a 5xx answer), it restarts and resumes the SAME episode (never a
  reset) in the state after the last call it completed, which you may not have received: call `r.wait_ready()`, then
  check `r.status()` (`calls`, `control_steps`) before you continue.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`)
```python
from rcb_client import Robot
r = Robot()                                   # connects: waits while Isaac Sim starts and loads the scene
                                              # ($load_mins min measured; the first start in a container, while Isaac
                                              # compiles its shaders, is the slow one; the wait is on your clock)
spec = r.spec()                               # actions, cameras, robot_spec, world, kinematics, budget

obs = r.get_obs()                             # the current head-camera frame: obs.last[cam] -> uint8 (1080, 1080, 3)
obs = r.get_obs(cameras=[...])                # any of the three cameras (spec["cameras"])
obs.meta["proprio"]                           # {"layout": [...], "now": [...]}: named columns (spec["proprio_groups"])
obs.meta["cameras"]                           # per camera: intrinsic_cv / extrinsic_cv (odometry -> camera) of the LAST frame
obs = r.get_obs(seconds=2.0, video="mp4")     # hold the last command and watch for 2 s (max 30): obs.video[cam] = mp4 bytes

res = r.submit("joint_position", A, dt=0.1)   # A: (T, 23) rows dt seconds apart; streamed at 30 Hz
res.meta["done"], res.meta["reason"], res.meta["clipped"], res.meta["control_steps_left"]
res.video[cam]; res.frames[cam]; res.last[cam]; res.proprio   # execution video / frames / last frame per camera, proprio per frame
```
Cameras: `robot_r1:zed_link:Camera:0` (head: the goal image's camera; it moves with the base and the trunk),
`robot_r1:left_realsense_link:Camera:0` and `robot_r1:right_realsense_link:Camera:0` (wrists), 1080×1080 RGB each, no
depth. They all move, so always use the calibration that arrived with the image. While the robot moves a frame shows the
scene 2 control steps (67 ms) before its `frame_step`; its `extrinsic_cv` is the pose it was rendered with.

### The action: `joint_position` (23)
Blocks (`spec["action_types"]["joint_position"]["blocks"]`): base (3), trunk (4), left arm (7), left gripper (1), right
arm (7), right gripper (1). Rows are `dt` apart (`1/30 ≤ dt ≤ 0.5` s, a multiple of the 30 Hz control period: `k/30` s;
any other `dt` is a 400); a chunk covers at most 10 s; out-of-limit values are clipped and listed in `meta["clipped"]`.
- **Base**: a velocity command in [-1, 1] in the robot's own frame (forward, left, yaw rate), scaled to 0.75 m/s,
  0.75 m/s and 1 rad/s; it switches at the row and holds until the next one; zeros stop.
- **Trunk and arms**: absolute joint targets (rad), linearly interpolated between rows (or held, `interpolate="hold"`).
- **Grippers**: one command each in [-1, 1]: -1 closed, 1 fully open, in between the fingers' target as a fraction of
  their travel; it switches at the row. Grasping is assisted: closing on an object holds what the finger pads touch, and
  the hand lets go only at 1.

### Optional inputs (eai-standard/2.2)
- **Per frame**: `res.frame_step`, `res.frame_time_s` and `res.extrinsic_cv[cam]` (N, 3, 4; odometry -> camera, OpenCV
  axes). Intrinsics `spec["cameras"][cam]["intrinsic_cv"]` (the goal image's are the head camera's), mounting
  `spec["cameras"][cam]["mount"]` (parent link + fixed `link_T_cam_cv`).
- **Robot**: `spec["robot_spec"]`: joint names and limits, the gripper rule, the end-effector frame and the fingertip
  centre (TCP), the base command.
- **Proprioception**: named columns `spec["proprio_layout"]`, groups `spec["proprio_groups"]` (joint_pos, joint_vel,
  joint_effort, gripper_opening, tcp_pose, eef_pose, base_pose, base_twist): `res.group("tcp_pose")` per frame,
  `res.group("tcp_pose", now=True)` now. Mind the joint order: the joint columns follow `spec["robot_spec"]["joints"]`
  (the trunk, then the two arms interleaved: left joint 1, right joint 1, left joint 2, ...), while the action's arm blocks
  and the kinematics' `q` are grouped (left arm joints 1-7, then right arm joints 1-7); map by name.
- **Kinematics** (stateless: no physics, no time): `r.fk(q)`, `r.ik({"left_tcp": pose}, seed=q)`; q =
  `spec["kinematics"]["joint_names"]` (trunk + both arms); poses in the robot's base frame, or in the odometry frame with
  `base_pose=` the 7 base_pose proprio columns.

The simulator runs at about $steps_per_s control steps per second of wall time, and your $max_steps control steps are
the whole episode: look and plan before you spend them, and check `meta["done"]`.
