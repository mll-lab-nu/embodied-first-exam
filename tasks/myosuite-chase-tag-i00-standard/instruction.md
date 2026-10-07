# MyoSuite · chase_tag — STANDARD MODE (robot as a service, eai-standard/2.2)

You control the **MyoLegs**, a free-standing musculoskeletal model of a human torso and both legs, **as if it were real**: the simulator (MyoSuite 2.12.2 on MuJoCo) runs in a service
you cannot open. You get one client and one episode, and you act only through its actuators (80 muscles).
**Task:** Tag the opponent: bring your pelvis within 0.5 m of it (horizontal distance) within 20 s of simulated time (MyoChallenge 2023 ChaseTag P1, task CHASE). Failure (the episode ends): the time limit, leaving the 13 x 13 m arena, or the pelvis below 0.5 m (fallen).

A musculoskeletal body with two legs stands in a square arena; an opponent moves in it.

## Rules
- **No reset.** The episode starts when the service comes up and ends on success (the challenge's own success event), on its failure conditions or its own time limit, when your time is up, or on a simulator
  error.
- **No privileged state.** You see what the cameras see (RGB, and depth on request, with each camera's calibration) and
  the body's own proprioception: joint positions, velocities and actuator torques, muscle activations and lengths and the pose and velocity of your free-standing root (the pelvis: `root_pose`, `root_vel`).
  No object, ball, opponent or goal poses, no success check: `meta["done"]` / `meta["reason"]` tell you when the episode
  is over and why.
- Your wall-clock budget is 5400 s from your start (`meta["time_left_s"]`); steps are unlimited. Simulated time
  only advances with your commands (and `get_obs(seconds=...)`, which holds the last command). Do not stop early.
- Nothing to hand in: the service records your episode and grades it. Leave your script at `/app/output/gen.py`.
- **If the service crashes**, a call fails with a connection error: it restarts and resumes the SAME episode (never a
  reset) in the state after the last call it completed. `r.wait_ready()` waits for it; then check `r.status()`.
- **Nothing is put into your context automatically.** Images and videos come back as arrays/bytes in a Python object.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`)
```python
from rcb_client import Robot
r = Robot()                                    # connects (waits while the service starts)
spec = r.spec()                                # actuators, joints, cameras (+ intrinsics, mounting), proprio layout, kinematics, budget
obs = r.get_obs()                              # obs.last[cam] -> uint8 (480, 640, 3) (default camera: topview)
obs = r.get_obs(cameras=["topview"], depth=True)   # + obs.last_depth[cam] -> float32 (480, 640), metres
obs.meta["proprio"]                            # {"layout": [...], "now": [...]}: q_*, qd_*, act_*, len_*, effort_*, root_*
obs.meta["cameras"]                            # per camera intrinsic_cv / extrinsic_cv / cam2world_gl at the last frame
res = r.submit("muscle", rows, dt=0.01)          # rows: (T, 80) commands, one row per control step
res.meta["done"], res.meta["reason"], res.meta["control_steps_chunk"]; res.video[cam]; res.last[cam]; res.proprio
obs = r.get_obs(seconds=1.0, video="mp4")      # hold the last command and watch for 1 s (max 30)
r.fk(q)                                        # forward kinematics of the listed links (no physics)
r.status()                                     # calls, control steps, done, reason, elapsed time
```
Cameras: `topview`, `opponent_view`, `agent_view` (640x480; default `topview`). `spec["cameras"]` gives each camera's mounting (static, fixed to a body, or a MuJoCo tracking camera that follows one) and intrinsics, and every response carries each frame's pose. Rendering is on the CPU: ask only for the cameras you need; `video="none"` makes a
chunk fastest. Proprioception (`spec["proprio_groups"]`): `joint_pos` (`q_<joint>`), `joint_vel` (`qd_<joint>`),
`muscle_activation` (`act_<muscle>`), `muscle_length` (`len_<muscle>`, m), `joint_effort` (`effort_<joint>`, the
actuators' generalized force on each joint), `root_pose`, `root_vel`. `/kinematics` gives the camera mounts for any joint positions.

### Action type `muscle` (80)
80 real numbers per control step, one per actuator in order: 80 muscles. A muscle's command a maps to its excitation u = 1 / (1 + exp(-5 (a - 0.5))) and is not clipped (a = -1: u ~ 0.0006, a = 0.5: 0.5, a = 1: 0.92, a = 2: 0.9994); activation follows excitation with a first-order delay (~10 ms up, ~40 ms down); muscles only pull; one muscle can cross several joints; its force also depends on its length and velocity. Columns in `spec["action_types"]["muscle"]["layout"]` order. Rows are `dt` apart (a whole multiple of the
10 ms control period, at most 0.5 s; a chunk covers at most 10 s), `interpolate="linear"` (default, from the
previous command) or `"hold"`; the client sends them as float32. The control rate is 100 Hz (10 physics
substeps); there is no step budget.
