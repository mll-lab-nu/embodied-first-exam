# AutoBio · screw_loose — STANDARD MODE (robot as a service, eai-standard/2.2)

You control two **ALOHA arms** (`arm1` and `arm2`; 6 joints and a parallel gripper each), fixed to the bench on either side of the rack, **as if it were real**: the simulator (AutoBio's biology laboratory on MuJoCo 3.3.0) runs
in a service you cannot open. You get one client and one episode.
**Task:** Unscrew the cap of the 50 mL centrifuge tube and lift it off. Success the moment the cap, held by `arm1`'s gripper (the test looks for contact between the cap and that gripper's left finger), is at least 3 cm above where it sat when screwed on and its thread is clear of the tube's.

On the bench: a rack with a 50 mL tube standing in it, its cap screwed on. The thread is a real one: the cap comes off only by turning it. AutoBio's prompt for this task: "one stabilizes tube while the other twists cap".

## Rules
- **No reset.** The episode starts when the service comes up and ends the moment the goal is reached (success), when your time is up, or on a simulator
  error. A MuJoCo physics warning (an unstable simulation, for instance after the robot was driven hard into
  something) also ends it at once, as a failure: `meta["reason"]` is then `"failure: simulator warning (unstable state)"`.
- **No privileged state.** You see what the cameras see (RGB, and depth on request, with each camera's calibration) and
  the robot's own proprioception: joint positions, velocities and drive efforts, gripper openings, the
  poses of its tool frames and the targets in effect. No poses of tubes, racks or instruments, no instrument state, no
  success check: `meta["done"]` / `meta["reason"]` tell you when the episode is over and why.
- Steps are unlimited; your only budget is the time limit (`## Time limit`; `meta["time_left_s"]` is the service's count of it).
  Simulated time only advances with your commands (and `get_obs(seconds=...)`, which holds the last targets). Do not stop early.
- `r.submit("done", [])` ends the episode in its current state; before the goal is reached that is a failure.
- Nothing to hand in: the service records your episode and grades it. Leave your script at `/app/output/gen.py`.
- **If the service crashes**, a call fails with a connection error: it restarts and resumes the SAME episode (never a
  reset) in the state after the last call it completed. `r.wait_ready()` waits for it; then check `r.status()`.
- **Nothing is put into your context automatically.** Images and videos come back as arrays/bytes in a Python object.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`)
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
Cameras (`table_cam_front`, `table_cam_left`, `arm1_wrist_cam`, `arm2_wrist_cam`; 640x480): `table_cam_front` and `table_cam_left` are fixed and look at the bench from two sides;
`arm1_wrist_cam`, `arm2_wrist_cam` are mounted on the arms' last
links and move with them. `spec["cameras"]` gives each camera's mounting and intrinsics, and every response carries each
frame's pose. Rendering is on the CPU: ask only for the cameras you need; `video="none"` makes a chunk fastest.
Proprioception (`spec["proprio_groups"]`): `joint_pos` (`q_<joint>`), `joint_vel` (`qd_<joint>`), `gripper_opening`
(metres between the fingertips, per parallel gripper), `tcp_pose` (each tool frame, `arm1_tcp`, `arm2_tcp`: x y z + wxyz
quaternion in the world frame), `joint_effort` (`effort_<joint>`), `command` (`cmd_<entry>`, the targets in effect).
`spec["robot_spec"]` is the robot's spec sheet: where each arm's base stands, joint limits, the drives' gains, the
grippers' commands, the tool frames.

### Action type `joint_position` (14)
14 position targets per control step, in this order: `arm1_waist`, `arm1_shoulder`, `arm1_elbow`, `arm1_forearm_roll`, `arm1_wrist_angle`, `arm1_wrist_rotate`, `arm1_gripper` (the gripper's finger position: 0.002 m closed .. 0.037 m open), `arm2_waist`, `arm2_shoulder`, `arm2_elbow`, `arm2_forearm_roll`, `arm2_wrist_angle`, `arm2_wrist_rotate`, `arm2_gripper` (the gripper's finger position: 0.002 m closed .. 0.037 m open). Arm joints are in rad. Each entry is the target of a PD position drive (stiffness, damping and force limit per entry: `spec["robot_spec"]["controller"]["gains"]`); a target outside the entry's range is clipped to it. Columns in
`spec["action_types"]["joint_position"]["layout"]` order. Rows are `dt` apart (a whole multiple of the 2 ms control
period, at most 0.5 s; a chunk covers at most 10 s), `interpolate="linear"` (default, from the previous target) or
`"hold"`; the client sends them as float32. The control rate is 500 Hz (one physics step per control step). There is
no step budget: the one technical cap is `spec["max_control_steps"]`, 600000 (1200 s of simulated time), at which the
episode ends. A response carries at most 3000 frames per camera (`video_fps` up to 50, default 10).

## External material
You may install packages you need (pip, apt). Please solve the task yourself: do not look up or download a solution to it, such as this benchmark's own source code, published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
