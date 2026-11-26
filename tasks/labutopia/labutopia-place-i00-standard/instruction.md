# LabUtopia · place (standard)

## Task
Pick up the beaker, lifting it more than a hand's width, and set it down in the middle of the white square plate; then
let go and move the hand away.

## Goal
Success: after being lifted more than a hand's width, the beaker rests in the middle of the white plate, with the hand
let go and moved away, for a second. The lift counts once it has happened; the rest is judged on how things stand when
the episode ends.

When you are done, send `/finish` to end the episode and get it graded.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- One episode, no reset: what you knock over stays knocked over.
- You get only the cameras and the robot's own proprioception (joint positions, velocities and drive efforts, the
  gripper's opening, the pose of its tool frame and the targets in effect): no poses of the objects or instruments, no
  success signal.

## Robot Interface
A Franka Panda arm (7 joints) with its two-finger gripper, fixed to a laboratory bench, in LabUtopia's simulated
chemistry laboratory (NVIDIA Isaac Sim). The robot runs as a service you reach through its client or its MCP tools, as
if it were real hardware: one live episode.

`POST /finish` (MCP tool `finish`): ends the episode; it is graded right away.

### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`:
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
obs = r.hold(1.0)                              # hold the last targets for 1 s of robot time
obs = r.get_obs(last_s=1.0)                    # the frames recorded over the last 1 s (reading moves no time)
r.fk(q); r.ik({"tcp": pose})                   # kinematics of the seven arm joints (spec["kinematics"]): no physics, no collision check
r.status()                                     # calls, control steps, done, reason, elapsed time
```

Simulated time only advances with your commands (and `hold(s)`, which holds the last targets). The service needs 5 to 10
minutes to come up (Isaac Sim prepares the stage for its renderer once; longer on a busy host): `Robot()` waits for it
(it prints its progress to stderr), and that wait is part of your budget. If the service crashes, a call fails with a
connection error: it restarts and resumes the same episode (never a reset) in the state after the last call it
completed. `r.wait_ready()` waits for it; then check `r.status()`. Ask only for the cameras you need; `video="none"`
makes a chunk fastest. One call returns at most 1800 images; `video_fps` is up to 30, default 10.

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
Action type `joint_position` (9): Position targets of the joints' drives: `panda_joint1` .. `panda_joint7` (rad), then
`panda_finger_joint1`, `panda_finger_joint2` (m from the gripper's centre line: 0 closed .. 0.04 open; the second finger
mirrors the first, its target is ignored). The velocity targets are zero. Rows are `dt` apart (a whole multiple of the
1/60 s control period, at most 0.5 s; a chunk covers at most 10 s), `interpolate="linear"` (default, from the previous
target) or `"hold"`; values outside the joints' ranges are clipped and reported; the client sends float32.

Action type `joint_position_velocity` (18): A position target and a velocity target for every joint's drive (effort =
stiffness x (position target - q) + damping x (velocity target - qdot), limited: `spec["robot_spec"]["controller"]`): 9
position targets as above, then 9 velocity targets (rad/s; m/s). Here a position target may lie beyond a joint's range
(`spec["action_types"]["joint_position_velocity"]["limits"]`): the joint stops and the drive keeps pushing, so a finger
target below the point where the finger meets an object squeezes it (400 N/m of error, at most 7.2 N). Rows and `dt` as
above; the velocity targets of a row hold for its whole interval.

The control rate is 60 Hz (one physics step per control step). At the start the arm is not at rest: it stands straight
up and is moving towards its home pose (the targets in effect, `cmd_*` in the proprioception); holding them, e.g. with
`r.hold(2)`, brings it there in about two seconds. There is no step budget: the one technical cap is
`spec["max_control_steps"]`, 36000 (600 s of simulated time), at which the episode ends.

### Observations
Cameras (`camera_1`, `camera_2`, `wrist_cam`; 512x512): `camera_1`, `camera_2` are fixed (one looks at the bench from
the front, one straight down from above); `wrist_cam` is mounted on the hand and moves with it. `spec["cameras"]` gives
each camera's mounting and intrinsics, and every response carries each frame's pose. Glassware is glass: nearly
transparent in the RGB images (an outline and reflections), and absent from the depth maps, which show what is behind
it. Proprioception (`spec["proprio_groups"]`): `joint_pos` (`q_<joint>`: the seven arm joints, then the two fingers),
`joint_vel` (`qd_<joint>`), `gripper_opening` (metres between the fingers), `tcp_pose` (the tool frame `tcp`, the point
between the fingertips: x y z + wxyz quaternion in the world frame), `joint_effort` (`effort_<joint>`: what each drive
asks for by its own law, which grows when the arm or a finger pushes on something), `command` (`cmd_*`, the 18 targets
in effect). `spec["robot_spec"]` is the robot's spec sheet: where the arm's base stands, joint limits, the drives'
gains, the gripper's command, the tool frame.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning. Time left: `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the
  service's `time_left_s` (in every reply) starts at your first request, so the file is the one to trust. Calls into a
  long-running process can block for their whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 8 CPUs, 32 GiB memory, 16384 processes and threads, 20 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Finish: if you never send `/finish`, the episode is graded when the step limit is reached or your session ends.
