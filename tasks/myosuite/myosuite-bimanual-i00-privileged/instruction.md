# MyoSuite · bimanual (privileged)

## Task
Pick up the object with your right hand, pass it to the prosthetic left hand, and set it on top of the goal pillar. Each
hand must touch it for at least 1 s in total, and it must never touch the table or the floor.

## Goal
Success: the object rests on top of the goal pillar, touching only the pillar, after your right hand and the prosthetic
hand have each touched it for at least 1 s in total (in either order), and it has never touched the table or the
floor. The episode ends as
soon as the task is done. It ends as a failure if the object is dropped, and after 10 s.

Deliverable: `/app/output/trajectory.npz`, written with `s.save_trajectory(actions, path)`. It is replayed open-loop
from the same initial state and scores 1 if its episode ends in success. It holds at most 216,000 rows (one per control
step: 360 s of replay at the control rate), and a longer file scores 0. Leave the script that produced it at
`/app/output/gen.py`. Save a valid one early and overwrite it when you have a better one.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed.

## Robot Interface
The MyoArm + MPL, a musculoskeletal right arm and hand next to a motorized prosthetic left arm (the Modular Prosthetic
Limb) (MyoSuite, MuJoCo), driven only through its actuators (63 muscles and 17 other actuators): there is no joint-level
controller. The scene is one fixed instance. You have the full simulator to develop with; you hand in a trajectory of
actuator commands.

### Session
`rcb_myosuite` (installed; run `python` from any directory):
```python
from rcb_myosuite import Session
s = Session("bimanual", instance="/app/instance.npz")   # a few seconds
s.reset()                          # back to the frozen initial state (unlimited; an exact snapshot restore)
s.state()                          # the task's observation dict (privileged; see Observations)
s.actuators(); s.muscles(); s.joints()   # 80 actuators (kind, command); muscles; hinge/slide joints (qpos/dof address, range)
s.moment_arms()                    # (80, nv) actuator moment arms at the current pose
s.model, s.data                    # MuJoCo model / data: read them freely; only the actions you record are replayed
s.excitation(a); s.command_for(u)  # muscle command a -> excitation u = 1/(1+exp(-5(a-0.5))) and its inverse
s.step(a)                          # one control step (10 ms): 80 commands; False once the episode is over
s.rest_action()                    # every command at -1 (muscles relaxed)
s.status()                         # {'success', 'done', 'reason', 'steps', 'resets', 'solved_run', 'rule', 'state_sha', 'info', ...}
s.record_start(); ...; actions = s.record_stop()   # (T, 80) commands, one row per control step
s.replay(actions)                  # resets, replays open-loop until the episode ends, returns status
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_frame("front_view")            # RGB uint8 (480, 640, 3); cameras: side_view, front_view, hand_top, hand_bottom, hand_side_inter, hand_side_exter, plam_lookat
s.render_video(actions, "/app/output/check.mp4", cameras=["front_view"])
```
There are no motion primitives: every skill is yours to build from actuator commands. Control step 10 ms (5 physics
substeps). There is no step budget: your wall-clock time is the limit (~600 control steps/s here). An episode ends at
success or failure; `s.step` then refuses further actions until `s.reset()`.

### Actions
An action has 80 real numbers per control step, one per actuator in order: 63 muscles and 17 non-muscle actuators. A
muscle's command a maps to its excitation u = 1 / (1 + exp(-5 (a - 0.5))) and is not clipped (a = -1: u ~ 0.0006, a =
0.5: 0.5, a = 1: 0.92, a = 2: 0.9994). Activation follows excitation with a first-order delay (~10 ms up, ~40 ms down).
Muscles only pull, and one muscle can cross several joints. A muscle's force also depends on its length and velocity.
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
prosthesis/pinky_MCP).

### Observations
`s.state()`: the task's observation dict: `qp`, `qv`, `myohand_qpos`, `myohand_qvel`, `pros_hand_qpos`,
`pros_hand_qvel`, `object_qpos`, `object_qvel`, `start_pos`, `goal_pos`, `elbow_fle`, `max_force`, `touching_body`,
`palm_pos`, `fin0`, `fin1`, `fin2`, `fin3`, `fin4`, `Rpalm_pos`, `MPL_ori`, `MPL_ori_err`, `obj_pos`, `reach_err`,
`pass_err`, `act`.

## Others
- To check a trajectory the way it is graded, replay it from the command line:
  `python /opt/tools/rcb_myosuite.py replay --instance /app/instance.npz --traj /app/output/trajectory.npz`.

## Limits
- Time: 3600 s of wall-clock time from the start of your session. Everything counts, including the simulator's start-up.
  At the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). A call into a long-running process can block for its
  whole wait time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, including the simulator's and the benchmark's source.
- Resources: 4 CPUs, 12 GiB memory, 4096 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU. Going over a cap can get a process killed (the CPU cap only slows you down). Usage:
  `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
