# MolmoSpaces · pick-and-place-color — STANDARD MODE (robot as a service, eai-standard/2.2)

**Task:** Pick up the metal stopwatch with buttons and place it in or on the red bowl.

You control a Franka FR3 arm with a Robotiq 2F-85 gripper on a fixed base (the DROID setup) — **as if it were real hardware** — in one episode of Ai2's MolmoSpaces benchmark (an Objaverse object).
The simulator (upstream's own code: molmo-spaces 0.2.9, MuJoCo 3.5.0) runs in a service you cannot open. You get one
client and one episode.

## Rules (real-robot rules)
- **No reset.** One episode. You see the robot's cameras (RGB, depth if you ask) and its proprioception (joints,
  grippers, tool poses, velocities, efforts). No object poses, no success check.
- **The episode ends** after **606 control steps** (the benchmark's 40 s horizon at
  15.152 Hz; `spec["max_control_steps"]`, counted by `meta["control_steps"]`), when you submit `done`
  (`r.submit("done", [])`), or when your time is up.
- **Success** is upstream's `judge_success()` on the state at that moment: the rule of pick-and-place, for the receptacle of the named colour (the other, differently coloured receptacle does not count): the robot does not touch the object; that receptacle supports the object (at least 50% of its weight through contact, or upstream's on-receptacle test, or within 5 mm and 10 degrees, relative to the receptacle, of a pose in which it was supported at an earlier control step); and that receptacle has moved at most 15 cm and tilted at most 60 degrees. The task has to hold at the
  end: met earlier and undone by then does not count, so end the episode with `done` once it holds.
- Your only budget is the time limit (`## Time limit`), from your start (the service's `time_s`, `elapsed_s` and `time_left_s`
  count from its own start, a few minutes earlier, so `time_left_s` reaches 0 a little before your time is up).
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
res = r.submit("joint_position", A, dt=0.066)   # A: (T, 8) rows dt apart; res.video[cam], res.proprio, res.meta
obs = r.get_obs(seconds=2.0, video="mp4")      # hold the current targets and watch for 2 s (max 30; whole control
                                               # steps: obs.meta["seconds"] is what ran)
r.fk(q); r.ik({"gripper": pose7}, seed=q)        # upstream's kinematic model, no physics: tcp poses <-> joint positions
r.submit("done", [])                           # end the episode now
r.status()                                     # calls, control steps, done, reason, elapsed time
```
Cameras: `wrist_camera_zed_mini`, `droid_shoulder_light_randomization`, `randomized_zed2_analogue_1`, `randomized_zed2_analogue_2`, `randomized_gopro_analogue_1` (`spec["cameras"][cam]`: intrinsics and mount; every response carries each camera's pose).

### `joint_position` (8)
`fr3_joint1`, `fr3_joint2`, `fr3_joint3`, `fr3_joint4`, `fr3_joint5`, `fr3_joint6`, `fr3_joint7`, `gripper`: the targets of upstream's joint-position controllers (fr3_joint1..7 in rad; gripper: the Robotiq command, 0 = open .. 255 = closed). At t = 0 the gripper is open and its target is 0. Rows are `dt` apart (a
whole multiple of the 0.066 s control period, at most 0.5 s: up to 0.462 s), `interpolate="linear"` (default) or
`"hold"` between rows; a chunk covers at
most 10 s; values outside the limits (`spec["action_types"]["joint_position"]["limits"]`) are clipped and listed in
`res.meta["clipped"]`. `obs.meta["proprio"]["now"]` starts with the measured positions of the row's joints, in row
order (`["layout"]` names every entry); the gripper entries of a row are commands in the units above, not the measured
openings. `q` for `r.fk` / `r.ik` follows `spec["kinematics"]["joint_names"]`; poses are x y z qw qx qy qz in the house's
world frame (z up, metres).

## External material
You may install packages you need (pip, apt). Please solve the task yourself: do not look up or download a solution to it, such as this benchmark's own source code, published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 8 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` is its own count of this limit, from the service's start or from your first request, so it can differ from the time you really have left. Installing packages is not cheating (`## External material` above).
