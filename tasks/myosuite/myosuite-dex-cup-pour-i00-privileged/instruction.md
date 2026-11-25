# MyoSuite · dex_cup_pour (privileged)

## Task
Pick up the cup and tilt it as if pouring, following the recorded reference motion.

## Goal
Success: the cup follows the recorded reference motion closely, in where it goes and how it turns, nearly all the way
and at the end, and never strays far from it. The episode lasts as long as the reference motion. It ends early, as a
failure, if the cup gets far from the reference motion or from your wrist.

Deliverable: `/app/output/trajectory.npz`, written with `s.save_trajectory(actions, path)`. It is replayed open-loop
from the same initial state and scores 1 if its episode ends in success. It holds at most 144,000 rows (one per control
step: 360 s of replay at the control rate), and a longer file scores 0. Leave the script that produced it at
`/app/output/gen.py`. Save a valid one early and overwrite it when you have a better one.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed.

## Robot Interface
The MyoHand, a musculoskeletal model of a human forearm and hand (MyoSuite, MuJoCo), driven only through its actuators
(39 muscles and 6 other actuators): there is no joint-level controller. The scene is one fixed instance. You have the
full simulator to develop with; you hand in a trajectory of actuator commands.

### Session
`rcb_myosuite` (installed; run `python` from any directory):
```python
from rcb_myosuite import Session
s = Session("dex_cup_pour", instance="/app/instance.npz")   # a few seconds
s.reset()                          # back to the frozen initial state (unlimited; an exact snapshot restore)
s.state()                          # the task's observation dict (privileged; see Observations)
s.actuators(); s.muscles(); s.joints()   # 45 actuators (kind, command); muscles; hinge/slide joints (qpos/dof address, range)
s.moment_arms()                    # (45, nv) actuator moment arms at the current pose
s.model, s.data                    # MuJoCo model / data: read them freely; only the actions you record are replayed
s.excitation(a); s.command_for(u)  # muscle command a -> excitation u = 1/(1+exp(-5(a-0.5))) and its inverse
s.step(a)                          # one control step (20 ms): 45 commands; False once the episode is over
s.rest_action()                    # every command at -1 (muscles relaxed)
s.status()                         # {'success', 'done', 'reason', 'steps', 'resets', 'solved_run', 'rule', 'state_sha', 'info', ...}
s.record_start(); ...; actions = s.record_stop()   # (T, 45) commands, one row per control step
s.replay(actions)                  # resets, replays open-loop until the episode ends, returns status
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_frame("center_cam")            # RGB uint8 (480, 640, 3); cameras: left_cam, right_cam, center_cam, hand_top, hand_bottom, hand_side_inter, hand_side_exter, plam_lookat
s.render_video(actions, "/app/output/check.mp4", cameras=["center_cam"])
```
There are no motion primitives: every skill is yours to build from actuator commands. Control step 20 ms (10 physics
substeps). There is no step budget: your wall-clock time is the limit (~400 control steps/s here). An episode ends at
success or failure; `s.step` then refuses further actions until `s.reset()`.

### Actions
An action has 45 real numbers per control step, one per actuator in order: 39 muscles and 6 non-muscle actuators. A
muscle's command a maps to its excitation u = 1 / (1 + exp(-5 (a - 0.5))) and is not clipped (a = -1: u ~ 0.0006, a =
0.5: 0.5, a = 1: 0.92, a = 2: 0.9994); activation follows excitation with a first-order delay (~10 ms up, ~40 ms down);
muscles only pull; one muscle can cross several joints; its force also depends on its length and velocity. The
non-muscle actuators: `A_ARTx` (index 0): position target of joint ARTx in [-0.75, 0.5]; `A_ARTy` (index 1): position
target of joint ARTy in [-0.5, 0.5]; `A_ARTz` (index 2): position target of joint ARTz in [-0.5, 0.3]; `A_ARRx` (index
3): position target of joint ARRx in [-1.75, 1.75]; `A_ARRy` (index 4): position target of joint ARRy in [-1.75, 1.75];
`A_ARRz` (index 5): position target of joint ARRz in [-1.75, 1.75].

### Observations
`s.state()`: the task's observation dict: `qp`, `qv`, `robot_err`, `curr_hand_qpos`, `curr_hand_qvel`, `targ_hand_qpos`,
`targ_hand_qvel`, `curr_obj_com`, `curr_obj_rot`, `wrist_err`, `base_error`, `targ_obj_com`, `targ_obj_rot`,
`hand_qpos_err`, `hand_qvel_err`, `obj_com_err`, `act`. The reference motion (the goal) is MyoDex's `s.base.ref` and,
per control step, the observation's `targ_obj_com` / `targ_obj_rot`; `curr_obj_com` / `curr_obj_rot` are the object's.

## Others
- To check a trajectory the way it is graded, replay it from the command line:
  `python /opt/tools/rcb_myosuite.py replay --instance /app/instance.npz --traj /app/output/trajectory.npz`.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (the simulator's start-up too). At
  the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 4 CPUs, 12 GiB memory, 4096 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU. Over a cap a process can be killed (the CPU cap only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
