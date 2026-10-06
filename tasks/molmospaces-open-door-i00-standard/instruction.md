# MolmoSpaces · open-door — STANDARD MODE (robot as a service, eai-standard/2.2)

**Task:** Pull the door open.

You control a Rainbow Robotics RB-Y1 mobile manipulator (upstream's RBY1M configuration): holonomic base, 6-joint torso, two 7-joint arms with parallel grippers, head camera — **as if it were real hardware** — in one episode of Ai2's MolmoSpaces benchmark (a door to pull).
The simulator (upstream's own code: molmo-spaces 0.2.9, MuJoCo 3.5.0) runs in a service you cannot open. You get one
client and one episode.

## Rules (real-robot rules)
- **No reset.** One episode. You see the robot's cameras (RGB, depth if you ask) and its proprioception (joints,
  grippers, tool poses, velocities, efforts). No object poses, no success check.
- **The episode ends** after **400 control steps** (the benchmark's 40 s horizon at
  10 Hz; `spec["max_control_steps"]`, counted by `meta["control_steps"]`), when you submit `done`
  (`r.submit("done", [])`), or when your time is up.
- **Success** is upstream's `judge_success()` on the state at that moment: the door's hinge is open at least 67% of its 90-degree range. The task has to hold at the
  end: met earlier and undone by then does not count, so end the episode with `done` once it holds.
- Your wall-clock budget is 3600 s from your start (the service's `time_s`, `elapsed_s` and `time_left_s` count from
  its own start, a few minutes earlier, so `time_left_s` reaches 0 a little before your budget ends).
  Simulated time only advances with your commands (and `get_obs(seconds=...)`).
- Nothing to hand in: the service records the episode and grades it. Leave your script at `/app/output/gen.py`.
- **If the service crashes**, a call fails with a connection error: it restarts and resumes the SAME episode (never a
  reset) in the state after the last call it completed. `r.wait_ready()` waits for it; then check `r.status()`.
- Nothing is put into your context automatically: images come back as arrays in Python objects.

## Client (`/opt/tools/rcb_client.py`)
```python
from rcb_client import Robot
r = Robot()                                    # connects (waits while the service builds the episode)
spec = r.spec()                                # action types, limits, cameras (+ calibration), robot_spec, kinematics, budget
obs = r.get_obs()                              # obs.last[cam] -> uint8 (H, W, 3); obs.meta["proprio"] {"layout", "now"}
obs = r.get_obs(depth=True)                    # + obs.last_depth[cam] -> float32 (H, W) z-depth in m (0 = no reading)
res = r.submit("joint_position", A, dt=0.1)   # A: (T, 25) rows dt apart; res.video[cam], res.proprio, res.meta
obs = r.get_obs(seconds=2.0, video="mp4")      # hold the current targets and watch for 2 s (max 30)
r.fk(q); r.ik({"left_gripper": pose7}, seed=q)        # upstream's kinematic model, no physics: tcp poses <-> joint positions
r.submit("done", [])                           # end the episode now
r.status()                                     # calls, control steps, done, reason, elapsed time
```
Cameras: `head_camera`, `wrist_camera_l`, `wrist_camera_r` (`spec["cameras"][cam]`: intrinsics and mount; every response carries each camera's pose).

### `joint_position` (25)
`base_x`, `base_y`, `base_theta`, `torso_0`, `torso_1`, `torso_2`, `torso_3`, `torso_4`, `torso_5`, `left_arm_0`, `left_arm_1`, `left_arm_2`, `left_arm_3`, `left_arm_4`, `left_arm_5`, `left_arm_6`, `right_arm_0`, `right_arm_1`, `right_arm_2`, `right_arm_3`, `right_arm_4`, `right_arm_5`, `right_arm_6`, `left_gripper`, `right_gripper`: the targets of upstream's joint-position controllers (base_x, base_y in m and base_theta in rad (world frame); torso, arm joints in rad; grippers: the finger motor's force, -100 .. 100 (positive closes, negative opens, 0 exerts none)). Rows are `dt` apart (a
whole multiple of the 0.1 s control period, at most 0.5 s), `interpolate="linear"` (default) or
`"hold"` between rows; a chunk covers at
most 10 s; values outside the limits (`spec["action_types"]["joint_position"]["limits"]`) are clipped and listed in
`res.meta["clipped"]`. `obs.meta["proprio"]["now"]` starts with the measured positions of the row's joints, in row
order (`["layout"]` names every entry); the gripper entries of a row are commands in the units above, not the measured
openings. `q` for `r.fk` / `r.ik` follows `spec["kinematics"]["joint_names"]`; poses are x y z qw qx qy qz in the house's
world frame (z up, metres).
