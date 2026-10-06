# MyoSuite · dex_airplane_fly — STANDARD MODE (robot as a service, eai-standard/2.2)

You control the **MyoHand**, a musculoskeletal model of a human forearm and hand, **as if it were real**: the simulator (MyoSuite 2.12.2 on MuJoCo) runs in a service
you cannot open. You get one client and one episode, and you act only through its actuators (39 muscles and 6 other actuators).
**Task:** Move the toy airplane along MyoDex's recorded fly (lift it and fly it through the air) motion: a reference of the object's pose over 99 control steps (1.98 s), from GRAB motion capture (TCDM / MyoDex). The episode lasts exactly those 99 steps. Success: the object's motion follows the reference's: its centre of mass's displacement since the start within 0.03 m of the reference's displacement since the reference's start, and its rotation since the start within 0.5 rad of the reference's, at at least 90% of the control steps and at the last one, with the displacement error never above 0.05 m. Failure (the episode ends early): MyoDex's termination, the object more than 0.25 m from the reference or from the wrist.

A toy airplane lies on the table; the MyoHand is at its pre-grasp pose.

## Rules
- **No reset.** The episode starts when the service comes up and ends after 99 control steps (the reference motion; then it is judged), early at MyoDex's termination, when your time is up, or on a simulator
  error.
- **No privileged state.** You see what the cameras see (RGB, and depth on request, with each camera's calibration) and
  the body's own proprioception: joint positions, velocities and actuator torques, muscle activations and lengths.
  No object, ball, opponent or goal poses, no success check: `meta["done"]` / `meta["reason"]` tell you when the episode
  is over and why.
- The goal is a reference motion: `spec["reference_motion"]` gives, per control step, the object's centre of mass relative to where it starts and its orientation.
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
obs = r.get_obs()                              # obs.last[cam] -> uint8 (480, 640, 3) (default camera: center_cam)
obs = r.get_obs(cameras=["left_cam"], depth=True)   # + obs.last_depth[cam] -> float32 (480, 640), metres
obs.meta["proprio"]                            # {"layout": [...], "now": [...]}: q_*, qd_*, act_*, len_*, effort_*
obs.meta["cameras"]                            # per camera intrinsic_cv / extrinsic_cv / cam2world_gl at the last frame
res = r.submit("actuators", rows, dt=0.02)          # rows: (T, 45) commands, one row per control step
res.meta["done"], res.meta["reason"], res.meta["control_steps_chunk"]; res.video[cam]; res.last[cam]; res.proprio
obs = r.get_obs(seconds=1.0, video="mp4")      # hold the last command and watch for 1 s (max 30)
r.fk(q)                                        # forward kinematics of the listed links (no physics)
r.status()                                     # calls, control steps, done, reason, elapsed time
```
Cameras: `left_cam`, `right_cam`, `center_cam`, `hand_top`, `hand_bottom`, `hand_side_inter`, `hand_side_exter`, `plam_lookat` (640x480; default `center_cam`). `hand_top` and `hand_side_inter` are close-ups of the hand, **mounted on the forearm** (the radius): they move with it (pronation turns them), so use the pose returned with each frame; `spec["cameras"]` gives each camera's mounting (static, fixed to a body, or a MuJoCo tracking camera that follows one) and intrinsics, and every response carries each frame's pose. Rendering is on the CPU: ask only for the cameras you need; `video="none"` makes a
chunk fastest. Proprioception (`spec["proprio_groups"]`): `joint_pos` (`q_<joint>`), `joint_vel` (`qd_<joint>`),
`muscle_activation` (`act_<muscle>`), `muscle_length` (`len_<muscle>`, m), `joint_effort` (`effort_<joint>`, the
actuators' generalized force on each joint). `/kinematics` gives the fingertip sites and the camera mounts for any joint positions.

### Action type `actuators` (45)
45 real numbers per control step, one per actuator in order: 39 muscles and 6 non-muscle actuators. A muscle's command a maps to its excitation u = 1 / (1 + exp(-5 (a - 0.5))) and is not clipped (a = -1: u ~ 0.0006, a = 0.5: 0.5, a = 1: 0.92, a = 2: 0.9994); activation follows excitation with a first-order delay (~10 ms up, ~40 ms down); muscles only pull; one muscle can cross several joints; its force also depends on its length and velocity. The non-muscle actuators: `A_ARTx` (index 0): position target of joint ARTx in [-0.75, 0.5]; `A_ARTy` (index 1): position target of joint ARTy in [-0.5, 0.5]; `A_ARTz` (index 2): position target of joint ARTz in [-0.5, 0.3]; `A_ARRx` (index 3): position target of joint ARRx in [-1.75, 1.75]; `A_ARRy` (index 4): position target of joint ARRy in [-1.75, 1.75]; `A_ARRz` (index 5): position target of joint ARRz in [-1.75, 1.75]. Columns in `spec["action_types"]["actuators"]["layout"]` order. Rows are `dt` apart (a whole multiple of the
20 ms control period, at most 0.5 s; a chunk covers at most 10 s), `interpolate="linear"` (default, from the
previous command) or `"hold"`; the client sends them as float32. The control rate is 50 Hz (10 physics
substeps); there is no step budget.
