# cube_stack — instance 00

You control a simulated franka-panda arm (robosuite / MuJoCo) via Python. **Task:** Stack the red cube on top of the green cube with the Franka arm, then release it so it stays stacked.

This is a *fixed scene instance*: object poses never change between resets. You may reset and retry as many
times as you want. Your deliverable is **one replayable trajectory**, not a general policy.

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below).
It is replayed open-loop from the same initial state in a fresh process and scored 1 if the task is
completed at the end of the replay, else 0. Also leave the script that produced it at `/app/output/gen.py`.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_traj import Session
s = Session("cube_stack", instance="/app/instance.npz")   # builds the env, starts the IK server if needed
s.reset()                          # back to the frozen initial state (unlimited)
p = s.primitives()                 # dict of callables, e.g. p["goto_pose"](pos, quat_wxyz, z_approach=0.1)
help(p["goto_pose"])               # every primitive has a docstring; read them
s.low                              # low-level cap-x env (robosuite env at s.low.robosuite_env) for closed-loop control
s.record_start(); ...; actions = s.record_stop()   # actions: (T, 9) joint targets + gripper, one row per sim step
s.status()                         # {'success': bool, 'reward': float, 'sim_steps': int, ...}
s.replay(actions)                  # resets, replays open-loop, returns status  -> use this to self-check
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
CLI equivalent of the grader:
`python /opt/tools/rcb_traj.py replay --task cube_stack --instance /app/instance.npz --traj /app/output/trajectory.npz`

Optional rendering: `Session("cube_stack", instance=..., enable_render=True)` then `s.low.render()` returns an RGB
array (software rendering, slow). Coordinates are in the robot base frame; quaternions are WXYZ.
