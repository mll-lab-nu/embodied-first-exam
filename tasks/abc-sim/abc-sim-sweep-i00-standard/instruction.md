# ABC Sim · sweep paper scraps -- STANDARD MODE (robot as a service, eai-standard/2.2)

You control a bimanual robot -- two I2RT YAM arms (6 revolute joints and a parallel two-finger gripper each) side by side at the near edge of a table, facing +x (the left arm is the one at +y) -- **as if it were real**: the simulator (ABC Sim on MuJoCo 3.6.0) runs in a
service you cannot open. You get one client and one episode, and you act only through the robot's joint targets.
**Task:** Get the paper scraps into the trash can: sweep them into the dustpan with the brush and empty it into the can, or any other way. Success: all 2 scraps are inside the trash can at the same time (each scrap's centre within the can's inner radius of its axis and between its floor and its rim). Pushing scraps off the table does not count. The goal must hold for 30 consecutive control steps (1.02 s); the episode then ends in success.

2 crumpled paper scraps lie on the table, with a brush, a dustpan and a trash can (all loose objects).

## Rules
- **One episode.** It starts when the service comes up and ends on success,
  when your time is up, or on a simulator error. There is no reset (`spec["budget"]["reset"]` is 0): the one episode is
  the run. Once it has ended, `submit` raises `EpisodeOver`.
- **No privileged state.** You see what the cameras see (RGB, and depth on request, with each camera's calibration) and
  the robot's own proprioception: joint positions, velocities and efforts, gripper openings, tool-frame poses. No object
  poses, no success check: `meta["done"]` / `meta["reason"]` tell you when the episode is over and why.
- Steps are unlimited; your only budget is the time limit (`## Time limit`; `meta["time_left_s"]` is the service's count
  of it). Simulated time only advances with your commands (and `get_obs(seconds=...)`, which holds the last command),
  so the scene waits while you think. Do not stop early: while the episode runs, the run can still pass.
- Nothing to hand in: the service records your episode and grades it. Leave your script at `/app/output/gen.py`.
- **If the service crashes**, a call fails with a connection error: it restarts and resumes the SAME episode in the
  state after the last call it completed. `r.wait_ready()` waits for it; then check `r.status()`.
- **Nothing is put into your context automatically.** Images and videos come back as arrays/bytes in a Python object.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`)
```python
from rcb_client import Robot
r = Robot()                                    # connects (waits while the service starts)
spec = r.spec()                                # action layout and limits, cameras (+ intrinsics, mounting), proprio layout, kinematics
obs = r.get_obs()                              # obs.last[cam] -> uint8 (480, 640, 3) (default cameras: top, left, right)
obs = r.get_obs(cameras=["top"], depth=True)   # + obs.last_depth[cam] -> float32 (480, 640), metres
obs.meta["proprio"]                            # {"layout": [...], "now": [...]}: q_*, qd_*, gripper openings, tcp poses, efforts
obs.meta["cameras"]                            # per camera intrinsic_cv / extrinsic_cv / cam2world_gl at the last frame
res = r.submit("joint_position", rows, dt=0.034)   # rows: (T, 14) targets, one row per control step
res.meta["done"], res.meta["reason"], res.meta["control_steps_chunk"]; res.video[cam]; res.last[cam]; res.proprio
obs = r.get_obs(seconds=1.0, video="mp4")      # hold the last targets and watch for 1 s (max 30)
r.fk(q14); r.ik({"left_tcp": [x, y, z, qw, qx, qy, qz]})   # the robot's kinematic model (no physics)
r.status()                                     # calls, control steps, done, reason, elapsed time
```
Cameras: `top` (above and behind the arms, looking down at the table), `left` and `right` (wrist cameras on the arms), `overhead`, `left_side`, `right_side` (640x480; default `top`, `left`, `right`); `spec["cameras"]` gives each camera's mounting (static,
or on an arm link: the wrist cameras move with the arm, so use the pose returned with each frame) and intrinsics, and
every response carries each frame's pose. Rendering runs on the service's GPU (a few milliseconds a frame): ask only for
the cameras you need; `video="none"` makes a chunk fastest. One call returns at most 1000 images (cameras x frames at
`video_fps`, default 10; depth for every frame counts again; `spec["max_frames_per_call"]`): a larger request is refused
with a 400 before anything runs. Proprioception (`spec["proprio_groups"]`): `joint_pos` (`q_<entry>`, the 14 action
coordinates measured), `joint_vel` (`qd_<entry>`), `gripper_opening` (m), `tcp_pose` (each arm's tool centre point,
world frame, `wxyz`), `joint_effort` (`effort_<entry>`). `/kinematics` (`r.fk`, `r.ik`) gives the tool frames `left_tcp`,
`right_tcp`, `left_grasp`, `right_grasp` and the arm links for any joint positions, and solves IK for the tool frames.

### Action type `joint_position` (14)
14 numbers per control step: `[left_joint1..6, left_gripper, right_joint1..6, right_gripper]` -- each arm's six joint position targets (rad) and its gripper opening (0 = closed, 1 = open, each finger 0.0475 m from closed; up to 1.042). The joints and grippers are position servos that track the targets (MuJoCo position actuators with damping and force limits); a target outside a joint's range is clamped to it, and the simulator rounds every command to float32. One control step = 17 physics steps of 2 ms = 0.034 s (29.4 Hz). Columns in `spec["action_types"]["joint_position"]["layout"]` order. Rows are `dt` apart (a whole multiple
of the 0.034 s control period, at most 0.5 s; a chunk covers at most 10 s), `interpolate="linear"` (default, from the
previous targets) or `"hold"`; the client sends them as float32. There is no step budget.

### World frame
The table's: x forward (away from the arms' bases), y to the left as the arms face the table, z up; metres, radians,
quaternions `wxyz`. Directions are as the arms face the table: left = +y, right = -y, behind = +x (farther from the arms), in front = -x (nearer to them). No positions of the scene are given; the arms' base poses are in `spec["robot_spec"]["base"]`.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
