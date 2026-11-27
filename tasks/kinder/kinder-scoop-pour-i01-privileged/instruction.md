# KinDER · scoop-pour (privileged)

## Task
Move all 50 small cubes from the yellow bin into the green bin. There is a scoop you can use.

## Goal
Success: all 50 cubes are well inside the green bin, below its rim. A replay ends as soon as the task is done; later
rows are not run.

Deliverable: `/app/output/trajectory.npz`, written with `s.save_trajectory(...)`, at most 1000 actions (`s.max_steps`,
100 s at 10 Hz); it is replayed open-loop from the fixed start and passes if the task is done within it. Also leave
`/app/output/gen.py`, the script that produced it; it must run and reproduce `trajectory.npz` reading nothing but
`/app/instance.json` and files under `/app/output/`. Also leave `/app/output/NOTES.md`, at most 20 lines: your final
approach and why it works, and the approaches that failed and what each told you about the task. Only the trajectory is
scored. Save a valid one early and overwrite it (with `gen.py` and `NOTES.md` to match) when you have a better one;
`s.replay(...)` tells you whether a trajectory does the task.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed.

## Robot Interface
A TidyBot++ mobile manipulator (a holonomic base, a Kinova Gen3 7-joint arm and a Robotiq 2F-85 gripper), in a simulated
scene (KinDER, MuJoCo). The scene is one fixed instance. You have the full simulator to develop with; you hand in a
trajectory of actions.

### Session
`/opt/tools/rcb_kinder.py`, importable as `rcb_kinder` (installed; run `python` from any directory):
```python
from rcb_kinder import Session
s = Session()                               # the instance in /app/instance.json
obs = s.reset()                             # back to the frozen scene; obs: KinDER's state vector, (915,)
print(s.state().pretty_str())               # the same state with names: every object, every feature
obs, success, done = s.step(action)         # one 10 Hz control step; action: (11,), see below
s.max_steps                                 # 1000: the episode, and the longest trajectory that counts
s.env                                       # the KinDER environment itself (get_state / set_state)
s.images(["task_view"])                     # RGB images, if you want to look (s.cameras lists the cameras)

with s.recording() as rec:                  # capture every action you step
    ...
s.replay(rec.actions)                       # from the frozen scene, open-loop: {"success", "success_step", "state_sha", ...}
s.save_trajectory(rec.actions, "/app/output/trajectory.npz")
```
The same replay from the shell: `python /opt/tools/rcb_kinder.py replay --traj /app/output/trajectory.npz`.

### Actions
Each action is 11 numbers, one 10 Hz control step, in KinDER's own order (`s.action_space`):
- `[0:3]` base: how far to move the base in x and y (metres) and turn it (radians, + = counter-clockwise), in the world
  frame, each at most 0.1 a step; the base's position controller tracks the new pose.
- `[3:10]` arm: radians to add to each of the 7 arm joints' measured angles, each at most 0.1 a step; the sums are the
  joints' new targets, which the arm's PD controller tracks.
- `[10]` gripper: 0 = open, 1 = closed (a command, not a change).
World frame: metres, z up. Everything in `s.env` (KinDER's state, every object and feature) is readable.

### Speed
- One 1000-step episode costs about 81 s of one core (more when the host is busy); the container has 16.

## Others
- The trajectory is replayed open-loop, but you may generate it closed-loop. KinDER on the CPU repeats exactly when
  replayed from `s.reset()`, so actions recorded from a feedback controller reproduce. Scripted motions, feedback
  control, search and optimisation are all fine.
- `s.env.unwrapped.set_state()` restores KinDER's object-centric state, not everything the physics carries. So a rollout
  continued from it can drift from the same actions replayed from the start: check the final trajectory with `s.replay`.

## Limits
- Time: 1800 s of wall-clock time from the start of your session. Everything counts, including the simulator's start-up.
  At the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). A call into a long-running process can block for its
  whole wait time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, including the simulator's and the benchmark's source.
- Resources: 16 CPUs, 7 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU. Going over a cap can get a process killed (the CPU cap only slows you down). Usage:
  `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
