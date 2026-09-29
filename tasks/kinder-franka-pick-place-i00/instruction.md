# franka-pick-place — instance i00

You control a simulated Franka FR3 arm (KinDER / MuJoCo) via Python: 7-DoF, fixed to a desk, with a Robotiq 2F-85 gripper. **Task:** get the small dark-red cube on the desk into a rectangle on the desk top that is not marked: x from 0.45 to 0.65 m and y from 0.12 to 0.27 m in KinDER's world frame (the frame of the state's positions; the arm stands at x 0.15, y 0.02 facing +x, so the rectangle lies about 20 cm to the arm's left of the cube and 15 cm nearer the arm). The task succeeds the moment the cube's centre is inside that rectangle and at most 20 cm above the desk top (z from 0.754 to 0.954 m).

This is a *fixed scene instance*: KinDER builds its scenes from a seed, and yours is pinned in `/app/instance.json`.
You may reset and retry as many times as you want. Your deliverable is **one replayable trajectory**, not a general
policy.

## Scoring
You pass iff the goal above is reached within **1000 control steps** (100 s at 10 Hz). The judge
is KinDER's own goal check -- the environment's `terminated`, which `s.step()` returns as `success` -- and the episode
ends the moment it fires. Nothing else scores: there is no partial credit.

## Deliverable
Leave three files under `/app/output/`. **Only the first is scored**; the other two are how a human reads your work
afterwards, so keep them short and factual.

| file | what goes in it |
|---|---|
| `trajectory.npz` | the trajectory, written with `s.save_trajectory(...)` (below). Replayed open-loop from the same initial state in a fresh process, twice; scored 1 if both replays reach the goal within 1000 steps and end in the same state, else 0 |
| `gen.py` | the script that produced it. It must **run and reproduce `trajectory.npz`**, reading nothing but `/app/instance.json` and files under `/app/output/` |
| `NOTES.md` | **at most 20 lines**: your final approach and why it works, and the approaches that failed and what each told you about the task |

**Write `trajectory.npz` as soon as you have any trajectory at all, and overwrite it (with `gen.py` and `NOTES.md` to
match) whenever you have a better one.** You have a wall-clock budget (1 h) and it ends without
warning; a run that ends with no file scores zero. `s.replay(...)` tells you whether a trajectory reaches the goal:
once the saved one does, you are done; until then, do not stop early -- keep working until the time is up.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_kinder import Session
s = Session()                               # the instance in /app/instance.json
obs = s.reset()                             # back to the frozen scene; obs: KinDER's state vector, (42,)
print(s.state().pretty_str())               # the same state with names: every object, every feature
obs, success, done = s.step(action)         # one 10 Hz control step; action: (8,), see below
s.max_steps                                 # 1000: the episode, and the longest trajectory that counts
s.env                                       # the KinDER environment itself, state access on (get_state / set_state)
s.images(["task_view"])                     # RGB images, if you want to look (s.cameras lists the cameras)

with s.recording() as rec:                  # capture every action you step
    ...
s.replay(rec.actions)                       # from the frozen scene, open-loop: {"success", "success_step", "state_sha", ...}
s.save_trajectory(rec.actions, "/app/output/trajectory.npz")
```
CLI equivalent: `python /opt/tools/rcb_kinder.py replay --traj /app/output/trajectory.npz`

## Actions
Each action is 8 numbers, one 10 Hz control step, in KinDER's own order (`s.action_space`):
- `[0:7]` arm: radians to add to each of the 7 arm joints' measured angles, each at most 0.1 a step; the sums are the joints' new targets, which the arm's position actuators track.
- `[7]` gripper: 0 = open, 1 = closed (a command, not a change).

## What the deliverable does and does not constrain
The trajectory is replayed **open-loop**, but nothing stops you from *generating* it closed-loop: replayed from
`s.reset()`, KinDER on CPU is bit-exact, so actions recorded from a feedback controller reproduce exactly. Use whatever
you like -- scripted motions, feedback control, search, optimisation. One 1000-step episode costs about
8 s of one core and the container has 16. `s.env.unwrapped.set_state()` restores KinDER's
object-centric state, not everything the physics carries, so a rollout continued from it can drift from the same actions
replayed from the start: check the final trajectory with `s.replay`.
