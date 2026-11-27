# MyoSuite · chase_tag (privileged)

## Task
Tag the opponent: get right next to it.

## Goal
Success: you get close enough to the opponent to tag it. The episode ends as soon as the task is done. It ends as a
failure if you fall, if you leave the arena, and after 20 s.

Deliverable: `/app/output/trajectory.npz`, written with `s.save_trajectory(actions, path)`. It is replayed open-loop
from the same initial state and scores 1 if its episode ends in success. It holds at most 432,000 rows (one per control
step: 360 s of replay at the control rate), and a longer file scores 0. Leave the script that produced it at
`/app/output/gen.py`. Save a valid one early and overwrite it when you have a better one.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed.

## Robot Interface
The MyoLegs, a free-standing musculoskeletal model of a human torso and both legs (MyoSuite, MuJoCo), driven only
through its actuators (80 muscles): there is no joint-level controller. The scene is one fixed instance. You have the
full simulator to develop with; you hand in a trajectory of actuator commands.

### Session
`rcb_myosuite` (installed; run `python` from any directory):
```python
from rcb_myosuite import Session
s = Session("chase_tag", instance="/app/instance.npz")   # a few seconds
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
s.render_frame("topview")            # RGB uint8 (480, 640, 3); cameras: topview, opponent_view, agent_view
s.render_video(actions, "/app/output/check.mp4", cameras=["topview"])
```
There are no motion primitives: every skill is yours to build from actuator commands. Control step 10 ms (10 physics
substeps). There is no step budget: your wall-clock time is the limit (~1200 control steps/s here). An episode ends at
success or failure; `s.step` then refuses further actions until `s.reset()`.

### Actions
An action has 80 real numbers per control step, one per actuator in order: 80 muscles. A muscle's command a maps to its
excitation u = 1 / (1 + exp(-5 (a - 0.5))) and is not clipped (a = -1: u ~ 0.0006, a = 0.5: 0.5, a = 1: 0.92, a = 2:
0.9994). Activation follows excitation with a first-order delay (~10 ms up, ~40 ms down). Muscles only pull, and one
muscle can cross several joints. A muscle's force also depends on its length and velocity.

### Observations
`s.state()`: the task's observation dict: `internal_qpos`, `internal_qvel`, `grf`, `torso_angle`, `muscle_length`,
`muscle_velocity`, `muscle_force`, `act`, `opponent_pose`, `opponent_vel`, `model_root_pos`, `model_root_vel`, `task`.

## Others
- To check a trajectory the way it is graded, replay it from the command line:
  `python /opt/tools/rcb_myosuite.py replay --instance /app/instance.npz --traj /app/output/trajectory.npz`.
- The opponent stands still.

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
