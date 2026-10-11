# LabUtopia · pour — STANDARD MODE (robot as a service, eai-standard/2.2)

You control a **Franka Panda** arm (7 joints) with its two-finger gripper, fixed to a laboratory bench, **as if it were real**: the simulator (LabUtopia's chemistry laboratory on NVIDIA Isaac
Sim) runs in a service you cannot open. You get one client and one episode.
**Task:** Pick up the small glass beaker, pour it out over the large glass beaker and bring it back upright. There is no liquid in the simulation: the pour is judged by where the small beaker is and how far it is turned. Success the moment the last of these is met: (1) the small beaker's centre has been more than 12 cm above where it stood; then, counted only while its centre is within about 8 cm (horizontally) of the large beaker's centre, (2) it has been turned more than 50 degrees from its orientation right after (1), (3) then turned back to within 30 degrees of that orientation, and (4) then is more than 5 cm above where it stood at 84 control steps (1.4 s in all; they need not be consecutive, and like (2) and (3) they count only while it is within that distance).

On the bench in front of the arm: two glass beakers: a small one, about 11 cm across and 9.5 cm tall (the one to pour), and a large one, about 15.5 cm across and 13 cm tall (the one to pour into).

## Rules
- **No reset.** The episode starts when the service comes up and ends the moment the goal is reached (success), when
  your time is up, or on a simulator error.
- **No privileged state.** You see what the cameras see (RGB, and depth on request, with each camera's calibration) and
  the robot's own proprioception: joint positions, velocities and drive efforts, the gripper's opening, the pose of its
  tool frame and the targets in effect. No poses of the objects or instruments, no success check: `meta["done"]` /
  `meta["reason"]` tell you when the episode is over and why.
- Your wall-clock budget is 5400 s from your start (`meta["time_left_s"]`); steps are unlimited. **The service
  needs 5 to 10 minutes to come up** (Isaac Sim prepares the stage for its renderer once; longer on a busy host):
  `Robot()` waits for it (it prints its progress to stderr), and that wait is part of your budget. Simulated time only advances with your commands (and `get_obs(seconds=...)`, which
  holds the last targets). Do not stop early.
- Nothing to hand in: the service records your episode and grades it. Leave your script at `/app/output/gen.py`.
- **If the service crashes**, a call fails with a connection error: it restarts and resumes the SAME episode (never a
  reset) in the state after the last call it completed. `r.wait_ready()` waits for it; then check `r.status()`.
- **Nothing is put into your context automatically.** Images and videos come back as arrays/bytes in a Python object.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`)
```python
from rcb_client import Robot
r = Robot()                                    # connects; waits while the service starts (5 to 10 minutes; it gives up after 3600 s)
spec = r.spec()                                # action layouts and limits, robot_spec, cameras (+ intrinsics, mounting), proprio layout, kinematics, budget
obs = r.get_obs()                              # obs.last[cam] -> uint8 (512, 512, 3) (cameras: camera_1, camera_2, wrist_cam)
obs = r.get_obs(cameras=["camera_1"], depth=True)   # + obs.last_depth[cam] -> float32 (512, 512), metres
obs.meta["proprio"]                            # {"layout": [...], "now": [...]}: q_*, qd_*, gripper_opening, tcp_x..qz, effort_*, cmd_*
obs.meta["cameras"]                            # per camera intrinsic_cv / extrinsic_cv / cam2world_gl at the last frame
res = r.submit("joint_position", rows, dt=0.05)   # rows: (T, 9) position targets, here one every 50 ms, reached linearly in 1/60 s steps
res.meta["done"], res.meta["reason"], res.meta["control_steps_chunk"], res.meta["clipped"]; res.video[cam]; res.last[cam]; res.proprio
obs = r.get_obs(seconds=1.0, video="mp4")      # hold the last targets and watch for 1 s (max 30)
r.fk(q); r.ik({"tcp": pose})                   # kinematics of the seven arm joints (spec["kinematics"]): no physics, no collision check
r.status()                                     # calls, control steps, done, reason, elapsed time
```
Cameras (`camera_1`, `camera_2`, `wrist_cam`; 512x512): `camera_1`, `camera_2` are fixed (one looks at the bench from the front, one straight down from above); `wrist_cam` is mounted on the hand and moves with it. `spec["cameras"]` gives each camera's mounting and
intrinsics, and every response carries each frame's pose. Glassware is glass: nearly transparent in the RGB images
(an outline and reflections), and absent from the depth maps, which show what is behind it. Ask only for the cameras
you need; `video="none"` makes a chunk fastest.
Proprioception (`spec["proprio_groups"]`): `joint_pos` (`q_<joint>`: the seven arm joints, then the two fingers),
`joint_vel` (`qd_<joint>`), `gripper_opening` (metres between the fingers), `tcp_pose` (the tool frame `tcp`, the point
between the fingertips: x y z + wxyz quaternion in the world frame), `joint_effort` (`effort_<joint>`: what each drive
asks for by its own law, which grows when the arm or a finger pushes on something), `command` (`cmd_*`, the 18 targets
in effect). `spec["robot_spec"]` is the robot's spec sheet: where the arm's base stands, joint
limits, the drives' gains, the gripper's command, the tool frame.

### Action type `joint_position` (9)
Position targets of the joints' drives: `panda_joint1` .. `panda_joint7` (rad), then `panda_finger_joint1`,
`panda_finger_joint2` (m from the gripper's centre line: 0 closed .. 0.04 open; the second finger mirrors the first,
its target is ignored). The velocity targets are zero. Rows are `dt` apart (a whole multiple of the 1/60 s control
period, at most 0.5 s; a chunk covers at most 10 s), `interpolate="linear"` (default, from the previous target) or
`"hold"`; values outside the joints' ranges are clipped and reported; the client sends float32.

### Action type `joint_position_velocity` (18)
A position target and a velocity target for every joint's drive (effort = stiffness x (position target - q) + damping
x (velocity target - qdot), limited: `spec["robot_spec"]["controller"]`): 9 position targets as above, then 9 velocity
targets (rad/s; m/s). Here a position target may lie beyond a joint's range (`spec["action_types"]
["joint_position_velocity"]["limits"]`): the joint stops and the drive keeps pushing, so a finger target below the
point where the finger meets an object squeezes it (400 N/m of error, at most 7.2 N). Rows and `dt` as above; the
velocity targets of a row hold for its whole interval.

The control rate is 60 Hz (one physics step per control step). At the start the arm is not at rest: it stands
straight up and is moving towards its home pose (the targets in effect, `cmd_*` in the proprioception); holding them,
e.g. with `r.get_obs(seconds=2)`, brings it there in about two seconds. There is no step budget: the
one technical cap is `spec["max_control_steps"]`, 36000 (600 s of simulated time), at which the episode ends. A
response carries at most 300 frames per camera (`video_fps` up to 30, default 10).

## External material
You may install packages you need (pip, apt). Please solve the task yourself: do not look up or download a solution to it, such as this benchmark's own source code, published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 8 cores for your container; the cap only slows you down.
