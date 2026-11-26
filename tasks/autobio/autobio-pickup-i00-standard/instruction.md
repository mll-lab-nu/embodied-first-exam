# AutoBio · pickup (standard)

## Task
Pick up the 50 mL tube from the rack by its cap and lift it more than a hand's width.

## Goal
Success: the gripper holds the tube by its cap and has lifted it more than a hand's width. A physics warning (an
unstable simulation, for instance after the robot was driven hard into something) ends the episode at once, as a
failure.

Success is judged on how things stand when the episode ends. It ends when you call finish (Limits) or when your session
ends. The robot never tells you whether you have succeeded.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- One episode, no reset: what you knock over stays knocked over.
- You get only the cameras and the robot's own proprioception (joint positions, velocities and drive efforts, gripper
  openings, the poses of its tool frames and the targets in effect): no poses of tubes, racks or instruments, no
  instrument state, no success signal.

## Robot Interface
An ALOHA arm (6 joints and a parallel gripper), fixed to the bench, in AutoBio's simulated biology laboratory (MuJoCo).
The robot runs as a service you reach through its client or its MCP tools, as if it were real hardware: one live
episode.

### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`:
```python
from rcb_client import Robot
r = Robot()                                    # connects (waits while the service starts)
spec = r.spec()                                # action layout and limits, robot_spec, cameras (+ intrinsics, mounting), proprio layout, kinematics, budget
obs = r.get_obs()                              # obs.last[cam] -> uint8 (480, 640, 3) (default cameras: table_cam_front, wrist_cam)
obs = r.get_obs(cameras=["table_cam_front"], depth=True)   # + obs.last_depth[cam] -> float32 (480, 640), metres
obs.meta["proprio"]                            # {"layout": [...], "now": [...]}: q_*, qd_*, *_opening, <tcp>_x..qz, effort_*, cmd_*
obs.meta["cameras"]                            # per camera intrinsic_cv / extrinsic_cv / cam2world_gl at the last frame
res = r.submit("joint_position", rows, dt=0.02)   # rows: (T, 7) targets, here one every 20 ms, reached linearly in 2 ms steps
res.meta["done"], res.meta["reason"], res.meta["control_steps_chunk"], res.meta["clipped"]; res.video[cam]; res.last[cam]; res.proprio
obs = r.hold(1.0)                              # hold the last targets for 1 s of robot time
obs = r.get_obs(last_s=1.0)                    # the frames recorded over the last 1 s (reading moves no time)
r.fk(q); r.ik({frame: pose})                   # kinematics of the arm joints (spec["kinematics"]): no physics, no collision check
r.submit("done", [])                           # the same as finish (Limits): ends the episode now
r.status()                                     # calls, control steps, done, reason, elapsed time
```

Simulated time only advances with your commands (and `hold(s)`, which holds the last targets). If the service crashes, a
call fails with a connection error: it restarts and resumes the same episode (never a reset) in the state after the last
call it completed. `r.wait_ready()` waits for it; then check `r.status()`. One call returns at most 3000 images;
`video_fps` is up to 50, default 10.

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
Action type `joint_position` (7): 7 position targets per control step, in this order: `waist`, `shoulder`, `elbow`,
`forearm_roll`, `wrist_angle`, `wrist_rotate`, `gripper` (the gripper's finger position: 0.002 m closed .. 0.037 m
open). Arm joints are in rad. Each entry is the target of a PD position drive (stiffness, damping and force limit per
entry: `spec["robot_spec"]["controller"]["gains"]`); a target outside the entry's range is clipped to it. Columns in
`spec["action_types"]["joint_position"]["layout"]` order. Rows are `dt` apart (a whole multiple of the 2 ms control
period, at most 0.5 s; a chunk covers at most 10 s), `interpolate="linear"` (default, from the previous target) or
`"hold"`; the client sends them as float32. The control rate is 500 Hz (one physics step per control step). There is no
step budget: the one technical cap is `spec["max_control_steps"]`, 600000 (1200 s of simulated time), at which the
episode ends.

### Observations
Cameras (`table_cam_front`, `table_cam_left`, `wrist_cam`; 640x480): `table_cam_front` and `table_cam_left` are fixed
and look at the bench from two sides; `wrist_cam` is mounted on the arm's last link and moves with it. `spec["cameras"]`
gives each camera's mounting and intrinsics, and every response carries each frame's pose. Proprioception
(`spec["proprio_groups"]`): `joint_pos` (`q_<joint>`), `joint_vel` (`qd_<joint>`), `gripper_opening` (metres between the
fingertips, per parallel gripper), `tcp_pose` (each tool frame, `tcp`: x y z + wxyz quaternion in the world frame),
`joint_effort` (`effort_<joint>`), `command` (`cmd_<entry>`, the targets in effect). `spec["robot_spec"]` is the robot's
spec sheet: where each arm's base stands, joint limits, the drives' gains, the grippers' commands, the tool frames.

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
- Finish: when you are done, call finish: `POST /finish` with an empty JSON body to the service, at the client's base
  URL (`http://sim:8000` or `http://localhost:8000`; in Python `requests.post(r.base + "/finish", json={})` with your
  client `r`). It ends the episode, and every call after it is refused. Reaching the goal changes no reply and does not
  end the episode; if you never call finish, the end of your session ends it.
