# MyoSuite · bimanual — STANDARD MODE (robot as a service, eai-standard/2.2)

You control the **MyoArm + MPL**, a musculoskeletal right arm and hand next to a motorized prosthetic left arm (the Modular Prosthetic Limb), **as if it were real**: the simulator (MyoSuite 2.12.2 on MuJoCo) runs in a service
you cannot open. You get one client and one episode, and you act only through its actuators (63 muscles and 17 other actuators).
**Task:** Hand the object over: pick it up with the MyoHand, pass it to the prosthetic hand, and place it on the goal pillar. Success: the object within 0.17 m of the pillar top after touching only the pillar for 10 control steps, and MyoChallenge 2024's contact check on its whole history passes (held by the MyoHand for at least 100 control steps, by the prosthesis for at least 100, only the pillar at the end, never the table or the floor). Failure (the episode ends): the object below 0.3 m (dropped), or 10 s of simulated time.

The MyoArm (right, muscles) and a prosthetic MPL arm (left, motors) stand at a table; an object lies in front of the MyoHand and a pillar marks the goal on the far side.

## Rules
- **No reset.** The episode starts when the service comes up and ends on success (the challenge's own success event), on its failure conditions or its own time limit, when your time is up, or on a simulator
  error.
- **No privileged state.** You see what the cameras see (RGB, and depth on request, with each camera's calibration) and
  the body's own proprioception: joint positions, velocities and actuator torques, muscle activations and lengths.
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
obs = r.get_obs()                              # obs.last[cam] -> uint8 (480, 640, 3) (default camera: front_view)
obs = r.get_obs(cameras=["side_view"], depth=True)   # + obs.last_depth[cam] -> float32 (480, 640), metres
obs.meta["proprio"]                            # {"layout": [...], "now": [...]}: q_*, qd_*, act_*, len_*, effort_*
obs.meta["cameras"]                            # per camera intrinsic_cv / extrinsic_cv / cam2world_gl at the last frame
res = r.submit("actuators", rows, dt=0.01)          # rows: (T, 80) commands, one row per control step
res.meta["done"], res.meta["reason"], res.meta["control_steps_chunk"]; res.video[cam]; res.last[cam]; res.proprio
obs = r.get_obs(seconds=1.0, video="mp4")      # hold the last command and watch for 1 s (max 30)
r.fk(q)                                        # forward kinematics of the listed links (no physics)
r.status()                                     # calls, control steps, done, reason, elapsed time
```
Cameras: `side_view`, `front_view`, `hand_top`, `hand_bottom`, `hand_side_inter`, `hand_side_exter`, `plam_lookat` (640x480; default `front_view`). `hand_top` and `hand_side_inter` are close-ups of the hand, **mounted on the forearm** (the radius): they move with it (pronation turns them), so use the pose returned with each frame; `spec["cameras"]` gives each camera's mounting (static, fixed to a body, or a MuJoCo tracking camera that follows one) and intrinsics, and every response carries each frame's pose. Rendering is on the CPU: ask only for the cameras you need; `video="none"` makes a
chunk fastest. Proprioception (`spec["proprio_groups"]`): `joint_pos` (`q_<joint>`), `joint_vel` (`qd_<joint>`),
`muscle_activation` (`act_<muscle>`), `muscle_length` (`len_<muscle>`, m), `joint_effort` (`effort_<joint>`, the
actuators' generalized force on each joint). `/kinematics` gives the fingertip sites and the camera mounts for any joint positions.

### Action type `actuators` (80)
80 real numbers per control step, one per actuator in order: 63 muscles and 17 non-muscle actuators. A muscle's command a maps to its excitation u = 1 / (1 + exp(-5 (a - 0.5))) and is not clipped (a = -1: u ~ 0.0006, a = 0.5: 0.5, a = 1: 0.92, a = 2: 0.9994); activation follows excitation with a first-order delay (~10 ms up, ~40 ms down); muscles only pull; one muscle can cross several joints; its force also depends on its length and velocity. The non-muscle actuators: `prosthesis/Lshoulder_fe` (index 63): normalized: a in [-1, 1] maps linearly onto [-0.611, 2.792] (position of joint prosthesis/Lshoulder_fe); `prosthesis/Lshoulder_abad` (index 64): normalized: a in [-1, 1] maps linearly onto [-2.792, 0] (position of joint prosthesis/Lshoulder_abad); `prosthesis/Lhumeral_rot` (index 65): normalized: a in [-1, 1] maps linearly onto [-0.524, 1.483] (position of joint prosthesis/Lhumeral_rot); `prosthesis/Lelbow` (index 66): normalized: a in [-1, 1] maps linearly onto [0.05, 2.356] (position of joint prosthesis/Lelbow); `prosthesis/A_wrist_PRO` (index 67): normalized: a in [-1, 1] maps linearly onto [-1.57, 1.57] (position of joint prosthesis/wrist_PRO); `prosthesis/A_wrist_UDEV` (index 68): normalized: a in [-1, 1] maps linearly onto [-0.26, 0.79] (position of joint prosthesis/wrist_UDEV); `prosthesis/A_wrist_FLEX` (index 69): normalized: a in [-1, 1] maps linearly onto [-1, 1] (position of joint prosthesis/wrist_FLEX); `prosthesis/A_thumb_ABD` (index 70): normalized: a in [-1, 1] maps linearly onto [0, 2.1] (position of joint prosthesis/thumb_ABD); `prosthesis/A_thumb_MCP` (index 71): normalized: a in [-1, 1] maps linearly onto [0, 1] (position of joint prosthesis/thumb_MCP); `prosthesis/A_thumb_PIP` (index 72): normalized: a in [-1, 1] maps linearly onto [0, 1] (position of joint prosthesis/thumb_PIP); `prosthesis/A_thumb_DIP` (index 73): normalized: a in [-1, 1] maps linearly onto [-0.82, 1.3] (position of joint prosthesis/thumb_DIP); `prosthesis/A_index_ABD` (index 74): normalized: a in [-1, 1] maps linearly onto [0, 0.34] (position of joint prosthesis/index_ABD); `prosthesis/A_index_MCP` (index 75): normalized: a in [-1, 1] maps linearly onto [0, 1.6] (position of joint prosthesis/index_MCP); `prosthesis/A_middle_MCP` (index 76): normalized: a in [-1, 1] maps linearly onto [0, 1.6] (position of joint prosthesis/middle_MCP); `prosthesis/A_ring_MCP` (index 77): normalized: a in [-1, 1] maps linearly onto [0, 1.6] (position of joint prosthesis/ring_MCP); `prosthesis/A_pinky_ABD` (index 78): normalized: a in [-1, 1] maps linearly onto [0, 0.34] (position of joint prosthesis/pinky_ABD); `prosthesis/A_pinky_MCP` (index 79): normalized: a in [-1, 1] maps linearly onto [0, 1.6] (position of joint prosthesis/pinky_MCP). Columns in `spec["action_types"]["actuators"]["layout"]` order. Rows are `dt` apart (a whole multiple of the
10 ms control period, at most 0.5 s; a chunk covers at most 10 s), `interpolate="linear"` (default, from the
previous command) or `"hold"`; the client sends them as float32. The control rate is 100 Hz (5 physics
substeps); there is no step budget.
