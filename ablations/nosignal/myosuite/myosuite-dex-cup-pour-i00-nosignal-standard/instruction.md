# MyoSuite · dex_cup_pour (standard)

## Task
The MyoHand, a musculoskeletal model of a human forearm and hand (MyoSuite, MuJoCo), driven only through its actuators
(39 muscles and 6 other actuators): there is no joint-level controller. A cup stands on the table; the MyoHand is at its
pre-grasp pose. Move the cup along MyoDex's recorded pour motion (lift it and tilt it as if pouring): a reference of the
object's pose over 81 control steps (1.62 s), from motion capture. The robot runs as a service you reach only through its client, as if it were real hardware.

## Goal
Success: the cup follows the recorded motion closely: its movement and its rotation since the start match the
reference's at nearly every step and at the last one, and it never strays far from it. What counts is how things stand
at the end of the episode: a success reached earlier and lost by the end does not count, so finish in the state you want
graded and stop sending commands. The episode ends at once, as a failure, when the object gets far from the reference or
from the wrist.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at
`/app/output/gen.py`.

Real-robot rules:
- Episodes: 10 resets, each a new episode from the same starting state (Robot Interface). Only the last episode is
  graded: a success ends the run at once (no reset after it), and when your time is up the episode then running is
  graded.
- No privileged state: you get the robot's camera images (with their calibration) and its own sensor readings; no object
  poses, no scene layout, no success signal.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.

### This run: no success signal
This run changes how the episode ends.

- The robot never tells you whether you have succeeded: reaching the goal changes no response, status, error or counter,
  and the episode does not end there.
- You decide when you are done: send `POST /finish` with an empty JSON body (`{}`) to the service, on the same base URL
  as your other calls (`http://sim:8000` or `http://localhost:8000`; in Python, for example
  `requests.post(base + "/finish", json={})`). The state at that moment is graded with the task's success rule (with the
  task's settle or hold time described above, run from that state). After `/finish` every call is refused (409).
- If you do not call it, the state when your session ends (you stop, or your time runs out) is graded.
- A success reached earlier and then undone does not count: only the state at the end is graded. An event the task
  records once it happens (for example a scored goal or a completed stage sequence) stays part of that state, also when
  one of the task's failure rules ends the episode after it. Resets work as described above, within the budget, and only
  the episode that ends with `/finish` or at the end of your session is graded.
- The episode still ends on its own on a simulator error, at the task's technical step limit (graded as it stands), and
  where the task's own rules end it as a failure (for example a fall), as described above.

## Robot Interface
### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`:
```python
from rcb_client import Robot
r = Robot()                                    # connects (waits while the service starts)
spec = r.spec()                                # actuators, joints, cameras (+ intrinsics, mounting), proprio layout, kinematics, budget
obs = r.get_obs()                              # obs.last[cam] -> uint8 (480, 640, 3) (default camera: center_cam)
obs = r.get_obs(cameras=["left_cam"], depth=True)   # + obs.last_depth[cam] -> float32 (480, 640), metres
obs.meta["proprio"]                            # {"layout": [...], "now": [...]}: q_*, qd_*, act_*, len_*, effort_*
obs.meta["cameras"]                            # per camera intrinsic_cv / extrinsic_cv / cam2world_gl at the last frame
res = r.submit("actuators", rows, dt=0.02)          # rows: (T, 45) commands, one row per control step
res.meta["done"], res.meta["reason"], res.meta["control_steps_chunk"]; res.video[cam]; res.last[cam]; res.proprio
obs = r.get_obs(seconds=1.0, video="mp4")      # hold the last command and watch for 1 s (max 30)
r.fk(q)                                        # forward kinematics of the listed links (no physics)
r.status()                                     # calls, control steps, done, reason, elapsed time, episode, resets_left
obs = r._post("/reset", {"cameras": ["left_cam"]}, [], 900)   # POST /reset: a new episode (the 2.2 client has no reset())
```

Simulated time only advances with your commands (and `get_obs(seconds=...)`, which holds the last command). A reset
(`POST /reset`, the `_post` line above) puts the body and the scene back on the same frozen starting state and starts a
new episode, either abandoning the running one or after one has ended; it takes no simulated time and returns the
start's images and proprioception. Once an episode has ended, `submit` raises `EpisodeOver` until you reset. The wall
clock is the run's and never restarts; `meta["episode"]` and `meta["resets_left"]` count the episodes
(`meta["control_steps"]` is the current episode's). If the service crashes, a call fails with a connection error: it
restarts and resumes the same episode (never a reset) in the state after the last call it completed. `r.wait_ready()`
waits for it; then check `r.status()`. One call returns at most 1000 images. `r.fk(q)` (`/kinematics`) gives the
fingertip sites and the camera mounts for any joint positions.

### Actions
Action type `actuators` (45): 45 real numbers per control step, one per actuator in order: 39 muscles and 6 non-muscle
actuators. A muscle's command a maps to its excitation u = 1 / (1 + exp(-5 (a - 0.5))) and is not clipped (a = -1: u ~
0.0006, a = 0.5: 0.5, a = 1: 0.92, a = 2: 0.9994); activation follows excitation with a first-order delay (~10 ms up,
~40 ms down); muscles only pull; one muscle can cross several joints; its force also depends on its length and velocity.
The non-muscle actuators: `A_ARTx` (index 0): position target of joint ARTx in [-0.75, 0.5]; `A_ARTy` (index 1):
position target of joint ARTy in [-0.5, 0.5]; `A_ARTz` (index 2): position target of joint ARTz in [-0.5, 0.3]; `A_ARRx`
(index 3): position target of joint ARRx in [-1.75, 1.75]; `A_ARRy` (index 4): position target of joint ARRy in [-1.75,
1.75]; `A_ARRz` (index 5): position target of joint ARRz in [-1.75, 1.75]. Columns in
`spec["action_types"]["actuators"]["layout"]` order. Rows are `dt` apart (a whole multiple of the 20 ms control period,
at most 0.5 s; a chunk covers at most 10 s), `interpolate="linear"` (default, from the previous command) or `"hold"`;
the client sends them as float32. The control rate is 50 Hz (10 physics substeps); there is no step budget.

### Observations
Cameras: `left_cam`, `right_cam`, `center_cam`, `hand_top`, `hand_bottom`, `hand_side_inter`, `hand_side_exter`,
`plam_lookat` (640x480; default `center_cam`). `hand_top` and `hand_side_inter` are close-ups of the hand, mounted on
the forearm (the radius): they move with it (pronation turns them), so use the pose returned with each frame;
`spec["cameras"]` gives each camera's mounting (static, fixed to a body, or a MuJoCo tracking camera that follows one)
and intrinsics, and every response carries each frame's pose. Proprioception (`spec["proprio_groups"]`): `joint_pos`
(`q_<joint>`), `joint_vel` (`qd_<joint>`), `muscle_activation` (`act_<muscle>`), `muscle_length` (`len_<muscle>`, m),
`joint_effort` (`effort_<joint>`, the actuators' generalized force on each joint). The goal is a reference motion:
`spec["reference_motion"]` gives, per control step, the object's centre of mass relative to where it starts and its
orientation.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 4 CPUs, 7 GiB memory, 2048 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 10 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
