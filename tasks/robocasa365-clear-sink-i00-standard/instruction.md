# RoboCasa365 · ClearSink — STANDARD MODE (robot as a service)

A **Franka Panda arm on an Omron mobile base** (with a torso lift) works in a kitchen: RoboCasa365's `ClearSink` kitchen task (robosuite, MuJoCo).
**Task: Remove the corn and carrot from the sink. Then move the bowl and cup from the counter to the sink for washing.**
The scene is one frozen instance: the initial state of one of the benchmark's official demonstrations.

You control the robot **as if it were real hardware**: the simulator runs in a service you cannot open. You get one
client and one episode.

## Rules (real-robot rules)
- **No reset.** What you knock over stays knocked over.
- **No privileged state.** You see what the robot's cameras see (RGB, optional depth, with each camera's
  calibration) and the robot's own state. No object poses, no scene layout, no success signal.
- Your wall-clock budget is 60 minutes (`meta["time_left_s"]`). There is nothing to hand in: the service records the
  episode as the trajectory and grades it. Leave your script at `/app/output/gen.py` for the record.
- Do not use the benchmark's demonstrations, trained policies or any published solution; write your own controller.
- Images come back as arrays in a Python object; what you look at and where you store it is up to your code.

## Scoring
The episode runs until your time is up. The service then replays the recorded episode in a fresh simulator and applies
the environment's own success check for `ClearSink` to the state **after the last executed control step**; it must hold
in the live episode and in the replay. A success reached earlier and then lost does not count: end in the state you
want graded and stop submitting.

The check for `ClearSink` requires that the corn and the carrot are not inside the sink, the bowl and the cup are inside it, and the gripper ends more than 0.25 m from all four.

How RoboCasa365's checks compute these terms (`robocasa/utils/object_utils.py`):
- *the gripper ends more than d m from X*: the distance from the robot's end-effector grip site to X's origin exceeds
  d. Opening the fingers is not enough: release, then move the hand away.
- *X is on / in Y* for an object Y (plate, tray, board, pan, pot, colander, tupperware, glass): X touches Y and their
  centres are within 0.7 × Y's horizontal radius of each other horizontally, unless a distance is given.
- *X touches* a counter, the dining counter or the stove: contact between X and that fixture.
- *X is inside* a fixture (a cabinet, the sink or one of its basins, the microwave): all eight corners of X's bounding
  box are within the fixture's interior region (5 cm tolerance).

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`)
```python
from rcb_client import Robot
r = Robot()                                   # connects (waits while the service starts: about a minute)
spec = r.spec()                               # control_dt, action layout + limits + kinds, cameras, proprio layout, budget
cams = list(spec["cameras"])                  # robot0_agentview_center, robot0_agentview_left, robot0_agentview_right, robot0_eye_in_hand
obs = r.get_obs(cameras=cams, include_depth=True)   # obs.last[cam] -> uint8 (240, 320, 3); obs.depth[cam] -> metres
obs.meta["proprio"]                           # {"layout": [...], "now": [...]}: joints, end effector, last command
obs.meta["cameras"]                           # per camera: intrinsic_cv, cam2world_gl (OpenGL: looks along -z), current
obs = r.get_obs(cameras=cams[:1], seconds=2.0, video="mp4")    # hold still and watch for 2 s (max 30)
res = r.submit("joint_position", A, cameras=cams[:1], video="mp4")   # A: (T, 13) rows, one per control step
res.meta["done"], res.meta["reason"], res.meta["control_steps"]
res.video[cam]; res.frames[cam]; res.last[cam]; res.proprio; res.save("/app/runs/003")
```
- Action `joint_position`: the robot's native controller command, applied once per control step (`control_dt` =
  0.05 s; float64). 13 channels, in order: `arm_joint1 .. arm_joint7` -- absolute joint position targets (rad, within the joint limits in `spec["action_types"]["joint_position"]` (`lower` / `upper`, from `r.spec()`)); `grip` (+1 closes, -1 opens); `base_x, base_y, base_yaw` -- the mobile base's velocities in its own frame (normalised, [-1, 1]); `torso` -- the torso lift's velocity; `hybrid_mode` (> 0: base mode; <= 0: arm mode, the default -1). Values are clipped to the limits. Rows are `dt` apart (default and minimum: `control_dt`; a chunk covers at
  most 10 s).
- `get_obs(seconds=s)` holds the robot still (delta channels zero, targets, grip and mode kept) while physics runs
  for `s` seconds; those control steps are part of the episode.
- The cameras are mounted on the robot and move with it: use the calibration that comes with each response.
- World frame: metres, z up.

## External material
You may install packages you need (pip, apt). Please solve the task yourself: do not look up or download a solution to it, such as this benchmark's own source code, published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.
