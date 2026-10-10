# BEHAVIOR-1K · installing_a_modem — STANDARD MODE (robot as a service, eai-standard/2.2)

You drive an **R1Pro** mobile bimanual robot around a house **as if it were real hardware**: the simulator (BEHAVIOR-1K
v3.9.2, the 2026 BEHAVIOR Challenge stack) runs in a service you cannot open. You get one client and one episode.
**Task:** Install the modem. A modem, switched off, sits on the coffee table in the living room; the room also has two cabinets and a television. Switch the modem on and put it on the same cabinet as the television, next to it. Success means all of the following hold at the same time: (1) the modem is switched on; (2) the modem is next to the television; (3) the television and the modem both stand on top of the same cabinet. How the simulator judges them: ontop(A, B): A touches B and B is directly below A (and not above it). nextto(A, B): the gap between A's and B's axis-aligned bounding boxes is at most one sixth of the mean of their summed box dimensions, and nothing lies between them along a horizontal axis. toggled_on(A): A's switch is on. It flips when a robot finger touches A's toggle button for 5 consecutive control steps; touch it again, after letting go, to flip it back. The service checks the goal and the episode ends the moment it holds.

## Rules (real-robot rules)
- **No reset.** The episode starts when the service comes up and ends on success, when the robot has fallen over, when
  your time is up, or on a simulator error. Whatever you knock over or push away stays where it ends up.
- **A fall ends the episode as a failure** (`meta["reason"]` "failure: the robot fell over"): the robot has fallen over
  when its base has been tilted more than 41.4° from upright, or more than 3 cm below the floor, for 10 s of simulated
  time in a row (OmniGibson's own Falling rule; tilted means the z of the base's up axis is below 0.75, which the
  proprioception gives as cos(rx)·cos(ry) of `base_footprint_rx_joint` and `base_footprint_ry_joint`).
- **No privileged state.** You see what the robot's cameras see (RGB; depth on request) plus its own proprioception
  (joints, base pose, end-effector and fingertip poses, gripper openings). No object poses, no map, no success predicate.
- Steps are unlimited; your wall-clock budget is 4 h (14400 s; `meta["time_left_s"]`). Actions and simulated time
  are reported as cost.
- There is nothing to hand in: the service records your episode as the trajectory and grades it. Leave your script
  at `/app/output/gen.py` for the record.
- **Nothing is put into your context automatically.** Images and videos come back as arrays/bytes in a Python object;
  what you look at and where you store it is your code's decision.
- **If the service crashes** (a connection error or a 5xx answer), it restarts and resumes the SAME episode (never a
  reset) in the state after the last call it completed, which you may not have received: call `r.wait_ready()`, then
  check `r.status()` (`calls`, `control_steps`) before you continue. Resuming replays the episode so far (minutes in a long
  episode) on your wall clock. A call that runs longer than `spec["max_call_wall_s"]` (900 s) stops at the next control
  step and returns what it executed (`res.stopped`, `meta["executed_rows"]`).

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`)
```python
from rcb_client import Robot
r = Robot()                                   # connects (waits while Isaac Sim starts and loads the scene, ~3-5 min)
spec = r.spec()                               # actions, cameras, robot_spec, world, kinematics, budget, static facts

obs = r.get_obs()                             # current frames from the robot's 3 cameras: obs.last[cam] -> uint8 (224,224,3)
obs.meta["proprio"]                           # {"layout": [...], "now": [...]}: named columns (spec["proprio_groups"])
obs.meta["cameras"]                           # per-camera intrinsic_cv / extrinsic_cv / cam2world_gl of the LAST frame
obs = r.get_obs(seconds=2.0, video="mp4")     # hold the last command and watch for 2 s (max 30): obs.video[cam] = mp4 bytes

res = r.submit("joint_position", A, dt=0.1)   # A: (T, 25) rows dt seconds apart; streamed at 30 Hz
res = r.submit("ee_pose", P)                  # P: (T, 16) end-effector targets for both arms; cuRobo IK per row
res.meta["done"], res.meta["reason"], res.meta["plan"], res.meta["clipped"], res.meta["control_steps_chunk"]
res.video[cam]; res.frames[cam]; res.last[cam]; res.proprio   # execution video / frames / last frame per camera, proprio per frame
res.save("/app/runs/003")                     # meta.json, <cam>.mp4, frames/, last/, proprio.npy, depth, frame_meta.npz
```
Cameras: `robot_r1:zed_link:Camera:0` (head; moves with the base and trunk), `robot_r1:left_realsense_link:Camera:0` and
`robot_r1:right_realsense_link:Camera:0` (wrists), 224×224 each. They all move, so always use the calibration that
arrived with the image. The world frame is OmniGibson's (metres, +z up, the floor is the plane z = 0); poses are
position + quaternion **XYZW**.

### Action types
- `joint_position` (25), in the blocks `spec["action_types"]["joint_position"]["blocks"]` lists: base (3), trunk (4),
  left arm (7), left gripper (2), right arm (7), right gripper (2). Rows are `dt` apart (`1/30 ≤ dt ≤ 0.5` s, a multiple
  of the 30 Hz control period); a chunk may cover at most 10 s; out-of-limit values are clipped and listed in
  `meta["clipped"]`.
  - Trunk and arm entries are absolute joint targets (rad), linearly interpolated between rows (or held, `interpolate="hold"`).
  - **The three base entries are different**: they are position targets in the *robot's own frame* (x, y in m, yaw in
    rad), re-applied on every control step, so they act as a per-step displacement: a row held for N control steps drives
    roughly N times that far. They are bounded per step (0.15 m, 0.3 rad); zeros stand still. They switch at the row.
  - Each gripper is 2 finger targets in m (0 = closed, 0.05 = fully open); they switch at the row. Grasping is assisted:
    a finger commanded below 0.05 closes and holds what the pads touch; only both fingers at >= 0.05 let go, so open
    with 0.07 (0.05 + 0.02, the service's open command).
- `ee_pose` (16): left `x y z qx qy qz qw gripper`, right the same; OmniGibson world frame, quaternions **xyzw**, gripper
  1 = open, 0 = closed (switched at the start of the row). Each row is solved by cuRobo inverse kinematics for both end
  effectors together (the trunk may bend too; no collision checking) and driven to in joint space; `dt` is ignored and the
  base stands still. If no IK solution exists nothing moves, and `meta["plan"]` says so. The pose is the end-effector frame
  of the proprio `*_eef_*` entries, so an observed pose is a valid target. At most 50 rows per submit.

### Optional inputs (eai-standard/2.2; nothing changes unless you ask)
- **Depth**: `depth=True` on `get_obs` / `submit` adds `res.last_depth[cam]`, float32 (224, 224) z-depth in metres (0 = no
  reading), pixel-aligned with the RGB; `depth="frames"` also returns `res.depth[cam]` (N, 224, 224), one per frame.
- **Per frame**: `res.frame_step`, `res.frame_time_s` and `res.extrinsic_cv[cam]` (N, 3, 4; world -> camera, OpenCV
  axes). While the robot moves, a frame shows the scene 2 control steps before its `frame_step`; its `extrinsic_cv` is the
  pose it was rendered with. Intrinsics `spec["cameras"][cam]["intrinsic_cv"]`, mounting `spec["cameras"][cam]["mount"]`
  (parent link + fixed `link_T_cam_cv`).
- **Robot**: `spec["robot_spec"]`: joint names and real limits, gripper stroke and open/close rule, drive gains, the
  end-effector frame vs the fingertip centre (TCP, 1.88 cm further along the fingers), the base's per-step and speed
  limits; `spec["world"]`: frame, units, quaternion order, camera axes.
- **Proprioception**: named columns `spec["proprio_layout"]`, groups `spec["proprio_groups"]` (joint_pos, joint_vel,
  joint_effort, gripper_opening, tcp_pose, eef_pose, base_pose, ...): `res.group("tcp_pose")` per frame,
  `res.group("tcp_pose", now=True)` now.
- **Kinematics** (stateless: no physics, no time): `r.fk(q)`, `r.ik({"left_tcp": pose}, seed=q)`; q =
  `spec["kinematics"]["joint_names"]` (trunk + both arms, all proprio columns); poses in the robot's base frame, or in the
  world frame with `base_pose=` the 7 base proprio columns.

For scale: the 2026 challenge's human teleoperators needed 80 s on average (2,413 control steps) for this task, and the simulator runs at ~7-11 control steps/s. Budget your time, drive before you reach, and check `meta["done"]`.
