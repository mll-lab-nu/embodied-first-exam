# AutoBio · pipette (standard)

## Task
Draw up liquid from the 50 mL tube with the pipette: press the plunger, push the tip down into the liquid near the
middle of the tube, let the plunger go, then lift the tip well out of the tube.

## Goal
Success: in that order, the tip goes down into the liquid near the middle of the tube with the plunger pressed, the
plunger is let go while the tip is still in the liquid, and the tip is then lifted well out of the tube. The episode
ends the moment that is reached. A physics warning (an unstable simulation, for instance after the robot was driven hard
into something) ends the episode at once, as a failure. Ending the episode yourself (`r.submit("done", [])`) before the
task is done is a failure.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- One episode, no reset: what you knock over stays knocked over.
- You get only the cameras and the robot's own proprioception (joint positions, velocities and drive efforts, gripper
  openings, the poses of its tool frames and the targets in effect): no poses of tubes, racks or instruments, no
  instrument state; the episode ends when the task is done, and the service tells you that it ended and why.

## Robot Interface
Two UR5e arms fixed to the bench: `arm1` carries a dexterous hand that holds a pipette (its thumb presses the plunger);
`arm2` has a Robotiq 2F-85 gripper, in AutoBio's simulated biology laboratory (MuJoCo). The robot runs as a service you
reach only through its client, as if it were real hardware: one live episode.

### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`:
```python
from rcb_client import Robot
r = Robot()                                    # connects (waits while the service starts)
spec = r.spec()                                # action layout and limits, robot_spec, cameras (+ intrinsics, mounting), proprio layout, kinematics, budget
obs = r.get_obs()                              # obs.last[cam] -> uint8 (480, 640, 3) (default cameras: table_cam_front, arm1_wrist_cam, arm2_wrist_cam)
obs = r.get_obs(cameras=["table_cam_front"], depth=True)   # + obs.last_depth[cam] -> float32 (480, 640), metres
obs.meta["proprio"]                            # {"layout": [...], "now": [...]}: q_*, qd_*, *_opening, <tcp>_x..qz, effort_*, cmd_*
obs.meta["cameras"]                            # per camera intrinsic_cv / extrinsic_cv / cam2world_gl at the last frame
res = r.submit("joint_position", rows, dt=0.02)   # rows: (T, 14) targets, here one every 20 ms, reached linearly in 2 ms steps
res.meta["done"], res.meta["reason"], res.meta["control_steps_chunk"], res.meta["clipped"]; res.video[cam]; res.last[cam]; res.proprio
obs = r.get_obs(seconds=1.0, video="mp4")      # hold the last targets and watch for 1 s (max 30)
r.fk(q); r.ik({frame: pose})                   # kinematics of the arm joints (spec["kinematics"]): no physics, no collision check
r.submit("done", [])                           # ends the episode now, in its current state
r.status()                                     # calls, control steps, done, reason, elapsed time
```

Simulated time only advances with your commands (and `get_obs(seconds=...)`, which holds the last targets). If the
service crashes, a call fails with a connection error: it restarts and resumes the same episode (never a reset) in the
state after the last call it completed. `r.wait_ready()` waits for it; then check `r.status()`. One call returns at most
3000 images; `video_fps` is up to 50, default 10.

### Actions
Action type `joint_position` (14): 14 position targets per control step, in this order: `arm1_shoulder_pan`,
`arm1_shoulder_lift`, `arm1_elbow`, `arm1_wrist_1`, `arm1_wrist_2`, `arm1_wrist_3`, `arm1_dh_rh_thj3` (the thumb joint
that presses the pipette's plunger: 0 .. 1.3 rad, larger presses), `arm2_shoulder_pan`, `arm2_shoulder_lift`,
`arm2_elbow`, `arm2_wrist_1`, `arm2_wrist_2`, `arm2_wrist_3`, `arm2_2f85_fingers_actuator` (the Robotiq gripper: 0 open
.. 255 closed). Arm joints are in rad. Each entry is the target of a PD position drive (stiffness, damping and force
limit per entry: `spec["robot_spec"]["controller"]["gains"]`); a target outside the entry's range is clipped to it.
Columns in `spec["action_types"]["joint_position"]["layout"]` order. Rows are `dt` apart (a whole multiple of the 2 ms
control period, at most 0.5 s; a chunk covers at most 10 s), `interpolate="linear"` (default, from the previous target)
or `"hold"`; the client sends them as float32. The control rate is 500 Hz (one physics step per control step). There is
no step budget: the one technical cap is `spec["max_control_steps"]`, 600000 (1200 s of simulated time), at which the
episode ends.

### Observations
Cameras (`table_cam_front`, `table_cam_left`, `arm1_wrist_cam`, `arm2_wrist_cam`; 640x480): `table_cam_front` and
`table_cam_left` are fixed and look at the bench from two sides; `arm1_wrist_cam`, `arm2_wrist_cam` are mounted on the
arms' last links and move with them. `spec["cameras"]` gives each camera's mounting and intrinsics, and every response
carries each frame's pose. Proprioception (`spec["proprio_groups"]`): `joint_pos` (`q_<joint>`), `joint_vel`
(`qd_<joint>`), `gripper_opening` (metres between the fingertips, per parallel gripper), `tcp_pose` (each tool frame,
`arm1_tcp`, `arm2_tcp`: x y z + wxyz quaternion in the world frame), `joint_effort` (`effort_<joint>`), `command`
(`cmd_<entry>`, the targets in effect). `spec["robot_spec"]` is the robot's spec sheet: where each arm's base stands,
joint limits, the drives' gains, the grippers' commands, the tool frames.

### Pipette
The plunger is worked by the hand's thumb, action entry `arm1_dh_rh_thj3`: a target above about 0.7 rad presses it, one
below about 0.45 rad releases it.

## Others
- No liquid actually moves in this simulation: the cameras show it as a blue surface inside the tube.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 4 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
