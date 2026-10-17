# iSpatialGym — standard mode (robot as a service, eai-standard/2.2)

You drive an **R1Pro** mobile robot with two arms, in a house, **as if it were real hardware**. The simulator
(iSpatialGym on BEHAVIOR-1K's OmniGibson) runs in a service you cannot open: you get one Python client and one episode.

## Your task: make the scene look like a picture
`/app/goal.png` is what the robot's head camera (`robot_r1:zed_link:Camera:0`) sees once the task is done. It is the same
camera, resolution and intrinsics as the robot's own head camera. Change the scene so that it looks like the picture. No
sentence here names the objects that matter or what to do with them: the picture is the whole task. The robot does not have to
match the picture (its arms, grippers and base may be anywhere), and nothing the picture does not show is judged.

## When the episode succeeds
The sim service judges the episode while it runs.
After every control step it checks three conditions:
1. **Relations.** The objects the task is about stand in the relations the picture shows: what is on, in, under, next to
   or touching what, what is open, and which objects the robot holds or has let go of.
2. **Poses.** Every pose the task measures is within its tolerance of the pose in the picture:
   - one object's pose: orientation within 0.15 rad (8.6°)
3. **At rest.** Conditions 1 and 2 have both held at every one of the last **45 control steps** (1.5 s of
   simulated time), and during those steps the objects the task is about and the robot itself are still:
   - at every step, each of them moves slower than 0.001 m/s and 0.005 rad/s, and each robot joint slower than 0.02 rad/s;
   - over the whole window, none of them drifts more than 0.01 m or 0.05 rad, and no robot joint more than 0.05.

The episode succeeds at the first control step where all three hold, which is the last step of that window. This text does
not say which objects the task is about: the picture shows them.

**Once the scene looks right, stop the robot and keep it still for at least 45 control steps.** Simulated time passes
only while you submit rows or watch: first send a row with the base command at 0 (the base keeps its last
command until the next row), then submit rows that hold still, or watch with `r.get_obs(seconds=...)`, which holds
the last command.

## Rules (real-robot rules)
- **One episode, no reset.** The episode starts when the service is up. It ends on success; after **2272 control
  steps** (75.7 s of simulated time, `spec["max_control_steps"]`; the reason is
  "failed: the episode's control steps ran out"); when your time runs out; or on a simulator error.
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
                                              # (8-17 min measured; the first start in a container, while Isaac
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

The simulator runs at about 7 control steps per second of wall time, and your 2272 control steps are
the whole episode: look and plan before you spend them, and check `meta["done"]`.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 8 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
