# AutoBio · thermal_cycler_open (standard)

## Task
Unlock the thermal cycler's lid with the lever on it and open the lid all the way.

## Goal
Success: the lever on the lid is turned all the way back to unlocked and the lid is fully open. A physics warning (an
unstable simulation, for instance after the robot was driven hard into something) ends the episode at once, as a
failure.

When you are done, send `/finish` to end the episode and get it graded. Only the state at that point counts.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- One episode, no reset: what you knock over stays knocked over.
- You get only the cameras and the robot's own proprioception (joint positions, velocities and drive efforts, gripper
  openings, the poses of its tool frames and the targets in effect): no poses of tubes, racks or instruments, no
  instrument state, no success signal.

## Robot Interface
A UR5e arm (6 joints) with a Robotiq 2F-85 gripper, fixed to the bench, in AutoBio's simulated biology laboratory
(MuJoCo). The robot runs as a service you reach through its client or its MCP tools, as if it were real hardware: one
live episode.

`POST /finish` (MCP tool `finish`): ends the episode; it is graded right away.

### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`:
```python
from rcb_client import Robot
r = Robot()                                    # connects (waits while the service starts)
spec = r.spec()                                # action layout and limits, robot_spec, cameras (+ intrinsics, mounting), proprio layout, kinematics, budget
obs = r.get_obs()                              # obs.last[cam] -> uint8 (480, 640, 3) (default cameras: table_cam_left, wrist_cam)
obs = r.get_obs(cameras=["table_cam_front"], depth=True)   # + obs.last_depth[cam] -> float32 (480, 640), metres
obs.meta["proprio"]                            # {"layout": [...], "now": [...]}: q_*, qd_*, *_opening, <tcp>_x..qz, effort_*, cmd_*
obs.meta["cameras"]                            # per camera intrinsic_cv / extrinsic_cv / cam2world_gl at the last frame
res = r.submit("joint_position", rows, dt=0.02)   # rows: (T, 7) targets, here one every 20 ms, reached linearly in 2 ms steps
res.meta["done"], res.meta["reason"], res.meta["control_steps_chunk"], res.meta["clipped"]; res.video[cam]; res.last[cam]; res.proprio
obs = r.hold(1.0)                              # hold the last targets for 1 s of robot time
obs = r.get_obs(last_s=1.0)                    # the frames recorded over the last 1 s (reading moves no time)
r.fk(q); r.ik({frame: pose})                   # kinematics of the arm joints (spec["kinematics"]): no physics, no collision check
r.submit("done", [])                           # the same as /finish: ends the episode now
r.status()                                     # calls, control steps, done, reason, elapsed time
```

Simulated time only advances with your commands (and `hold(s)`, which holds the last targets). If the service crashes, a
call fails with a connection error. The service restarts and resumes the same episode (never a reset), in the state
after the last call it completed. `r.wait_ready()` waits for it; then check `r.status()`. One call returns at most 3000
images; `video_fps` is up to 50, default 10.

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
Action type `joint_position` (7): 7 position targets per control step, in this order: `shoulder_pan`, `shoulder_lift`,
`elbow`, `wrist_1`, `wrist_2`, `wrist_3`, `2f85_fingers_actuator` (the Robotiq gripper: 0 open .. 255 closed). Arm
joints are in rad. Each entry is the target of a PD position drive (stiffness, damping and force limit per entry:
`spec["robot_spec"]["controller"]["gains"]`); a target outside the entry's range is clipped to it. Columns in
`spec["action_types"]["joint_position"]["layout"]` order. Rows are `dt` apart: `dt` is a whole multiple of the 2 ms
control period, at most 0.5 s, and a chunk covers at most 10 s. Interpolation is `interpolate="linear"` (the default,
from the previous target) or `"hold"`. The client sends rows as float32. The control rate is 500 Hz (one physics step
per control step).

### Observations
Cameras (`table_cam_front`, `table_cam_left`, `wrist_cam`; 640x480): `table_cam_front` and `table_cam_left` are fixed
and look at the bench from two sides; `wrist_cam` is mounted on the arm's last link and moves with it. `spec["cameras"]`
gives each camera's mounting and intrinsics, and every response carries each frame's pose. Proprioception
(`spec["proprio_groups"]`): `joint_pos` (`q_<joint>`), `joint_vel` (`qd_<joint>`), `gripper_opening` (metres between the
fingertips, per parallel gripper), `tcp_pose` (each tool frame, `tcp`: x y z + wxyz quaternion in the world frame),
`joint_effort` (`effort_<joint>`), `command` (`cmd_<entry>`, the targets in effect). `spec["robot_spec"]` is the robot's
spec sheet: where each arm's base stands, joint limits, the drives' gains, the grippers' commands, the tool frames.

## Limits
- Time: 3600 s of wall-clock time from the start of your session. Everything counts, including waiting for the service.
  At the end you are stopped without warning. Time left: `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`).
  Trust this file: the `time_left_s` in the service's replies starts only at your first request. A call into a
  long-running process can block for its whole wait time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, including the simulator's and the benchmark's source.
- Resources: 4 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Going over a cap can get a process killed (the CPU
  cap only slows you down). Usage: `/run/rcb-limits/usage.json`.
- Resets: none. You get one episode.
- Steps: no step budget. A technical cap (`spec["max_control_steps"]`) ends the episode after 600,000 control steps
  (1200 s of simulated time).
- Finish: if you never send `/finish`, the episode is graded when your session ends.
