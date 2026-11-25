# MyoSuite · bimanual (standard)

## Task
Pick up the object with your right hand, pass it to the prosthetic left hand, and set it on top of the goal pillar. Each
hand must hold it for at least 1 s, and it must never touch the table or the floor.

## Goal
Success: the object rests on top of the goal pillar, touching only the pillar, after your right hand and then the
prosthetic hand have each held it for at least 1 s, and it has never touched the table or the floor. The episode ends as
soon as the task is done. It ends as a failure if the object is dropped, and after 10 s.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- Episodes: 10 resets, each a new episode from the same starting state (Robot Interface). Only the last episode is
  graded: a success ends the run at once (no reset after it), and when your time is up the episode then running is
  graded.
- You get only the cameras and the body's own proprioception (joint positions, velocities and actuator torques, muscle
  activations and lengths): no object, ball, opponent or goal poses; the episode ends when the task is done, and the
  service tells you that it ended and why.

## Robot Interface
The MyoArm + MPL, a musculoskeletal right arm and hand next to a motorized prosthetic left arm (the Modular Prosthetic
Limb) (MyoSuite, MuJoCo), driven only through its actuators (63 muscles and 17 other actuators): there is no joint-level
controller. The robot runs as a service you reach only through its client, as if it were real hardware.

### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`:
```python
from rcb_client import Robot
r = Robot()                                    # connects (waits while the service starts)
spec = r.spec()                                # actuators, joints, cameras (+ intrinsics, mounting), proprio layout, kinematics, budget
obs = r.get_obs()                              # obs.last[cam] -> uint8 (480, 640, 3) (default camera: front_view)
obs = r.get_obs(cameras=["side_view"], depth=True)   # + obs.last_depth[cam] -> float32 (480, 640), metres
obs.meta["proprio"]                            # {"layout": [...], "now": [...]}: q_*, qd_*, act_*, len_*, effort_*
obs.meta["cameras"]                            # per camera intrinsic_cv / extrinsic_cv / cam2world_gl at the last frame
res = r.submit("actuators", rows, dt=0.01)          # rows: (T, 80) commands, one row per control step
res.meta["done"], res.meta["reason"], res.meta["control_steps_chunk"]; res.video[cam]; res.last[cam]; res.proprio
obs = r.get_obs(seconds=1.0, video="mp4")      # hold the last command and watch for 1 s (max 30)
r.fk(q)                                        # forward kinematics of the listed links (no physics)
r.status()                                     # calls, control steps, done, reason, elapsed time, episode, resets_left
obs = r._post("/reset", {"cameras": ["side_view"]}, [], 900)   # POST /reset: a new episode (the 2.2 client has no reset())
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
Action type `actuators` (80): 80 real numbers per control step, one per actuator in order: 63 muscles and 17 non-muscle
actuators. A muscle's command a maps to its excitation u = 1 / (1 + exp(-5 (a - 0.5))) and is not clipped (a = -1: u ~
0.0006, a = 0.5: 0.5, a = 1: 0.92, a = 2: 0.9994); activation follows excitation with a first-order delay (~10 ms up,
~40 ms down); muscles only pull; one muscle can cross several joints; its force also depends on its length and velocity.
The non-muscle actuators: `prosthesis/Lshoulder_fe` (index 63): normalized: a in [-1, 1] maps linearly onto [-0.611,
2.792] (position of joint prosthesis/Lshoulder_fe); `prosthesis/Lshoulder_abad` (index 64): normalized: a in [-1, 1]
maps linearly onto [-2.792, 0] (position of joint prosthesis/Lshoulder_abad); `prosthesis/Lhumeral_rot` (index 65):
normalized: a in [-1, 1] maps linearly onto [-0.524, 1.483] (position of joint prosthesis/Lhumeral_rot);
`prosthesis/Lelbow` (index 66): normalized: a in [-1, 1] maps linearly onto [0.05, 2.356] (position of joint
prosthesis/Lelbow); `prosthesis/A_wrist_PRO` (index 67): normalized: a in [-1, 1] maps linearly onto [-1.57, 1.57]
(position of joint prosthesis/wrist_PRO); `prosthesis/A_wrist_UDEV` (index 68): normalized: a in [-1, 1] maps linearly
onto [-0.26, 0.79] (position of joint prosthesis/wrist_UDEV); `prosthesis/A_wrist_FLEX` (index 69): normalized: a in
[-1, 1] maps linearly onto [-1, 1] (position of joint prosthesis/wrist_FLEX); `prosthesis/A_thumb_ABD` (index 70):
normalized: a in [-1, 1] maps linearly onto [0, 2.1] (position of joint prosthesis/thumb_ABD); `prosthesis/A_thumb_MCP`
(index 71): normalized: a in [-1, 1] maps linearly onto [0, 1] (position of joint prosthesis/thumb_MCP);
`prosthesis/A_thumb_PIP` (index 72): normalized: a in [-1, 1] maps linearly onto [0, 1] (position of joint
prosthesis/thumb_PIP); `prosthesis/A_thumb_DIP` (index 73): normalized: a in [-1, 1] maps linearly onto [-0.82, 1.3]
(position of joint prosthesis/thumb_DIP); `prosthesis/A_index_ABD` (index 74): normalized: a in [-1, 1] maps linearly
onto [0, 0.34] (position of joint prosthesis/index_ABD); `prosthesis/A_index_MCP` (index 75): normalized: a in [-1, 1]
maps linearly onto [0, 1.6] (position of joint prosthesis/index_MCP); `prosthesis/A_middle_MCP` (index 76): normalized:
a in [-1, 1] maps linearly onto [0, 1.6] (position of joint prosthesis/middle_MCP); `prosthesis/A_ring_MCP` (index 77):
normalized: a in [-1, 1] maps linearly onto [0, 1.6] (position of joint prosthesis/ring_MCP); `prosthesis/A_pinky_ABD`
(index 78): normalized: a in [-1, 1] maps linearly onto [0, 0.34] (position of joint prosthesis/pinky_ABD);
`prosthesis/A_pinky_MCP` (index 79): normalized: a in [-1, 1] maps linearly onto [0, 1.6] (position of joint
prosthesis/pinky_MCP). Columns in `spec["action_types"]["actuators"]["layout"]` order. Rows are `dt` apart (a whole
multiple of the 10 ms control period, at most 0.5 s; a chunk covers at most 10 s), `interpolate="linear"` (default, from
the previous command) or `"hold"`; the client sends them as float32. The control rate is 100 Hz (5 physics substeps);
there is no step budget.

### Observations
Cameras: `side_view`, `front_view`, `hand_top`, `hand_bottom`, `hand_side_inter`, `hand_side_exter`, `plam_lookat`
(640x480; default `front_view`). `hand_top` and `hand_side_inter` are close-ups of the hand, mounted on the forearm (the
radius): they move with it (pronation turns them), so use the pose returned with each frame; `spec["cameras"]` gives
each camera's mounting (static, fixed to a body, or a MuJoCo tracking camera that follows one) and intrinsics, and every
response carries each frame's pose. Proprioception (`spec["proprio_groups"]`): `joint_pos` (`q_<joint>`), `joint_vel`
(`qd_<joint>`), `muscle_activation` (`act_<muscle>`), `muscle_length` (`len_<muscle>`, m), `joint_effort`
(`effort_<joint>`, the actuators' generalized force on each joint).

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 4 CPUs, 7 GiB memory, 2048 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 10 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
