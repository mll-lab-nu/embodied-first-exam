# cluttered-retrieval-2d — instance i00

You control a simulated 2D robot (KinDER, kinematic: no dynamics) via Python: a circular base with a retractable arm and a vacuum end effector. **Task:** move the purple square block (`target_block`), which sits among ten red blocks (`obstruction0`–`obstruction9`) in the upper-right corner, into the brown square near the bottom (`target_region`). The task succeeds the moment all four corners of the purple block (0.14 on a side) are inside the brown square (0.21 on a side, tilted 7.3° clockwise).

This is a *fixed scene instance*: KinDER builds its scenes from a seed, and yours is pinned in `/app/instance.json`.
You may reset and retry as many times as you want. Your deliverable is **one replayable trajectory**, not a general
policy.

## Scoring
You pass iff the goal above is reached within **3000 control steps**. The judge
is KinDER's own goal check -- the environment's `terminated`, which `s.step()` returns as `success` -- and the episode
ends the moment it fires. Nothing else scores: there is no partial credit.

## Deliverable
Leave three files under `/app/output/`. **Only the first is scored**; the other two are how a human reads your work
afterwards, so keep them short and factual.

| file | what goes in it |
|---|---|
| `trajectory.npz` | the trajectory, written with `s.save_trajectory(...)` (below). Replayed open-loop from the same initial state in a fresh process, twice; scored 1 if both replays reach the goal within 3000 steps and end in the same state, else 0 |
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
obs = s.reset()                             # back to the frozen scene; obs: KinDER's state vector, (129,)
print(s.state().pretty_str())               # the same state with names: every object, every feature
obs, success, done = s.step(action)         # one control step; action: (5,), see below
s.max_steps                                 # 3000: the episode, and the longest trajectory that counts
s.env                                       # the KinDER environment itself, state access on (get_state / set_state)
s.images(["render"])                     # RGB images, if you want to look (s.cameras lists the cameras)

with s.recording() as rec:                  # capture every action you step
    ...
s.replay(rec.actions)                       # from the frozen scene, open-loop: {"success", "success_step", "state_sha", ...}
s.save_trajectory(rec.actions, "/app/output/trajectory.npz")
```
CLI equivalent: `python /opt/tools/rcb_kinder.py replay --traj /app/output/trajectory.npz`

## Actions
Each action is 5 numbers, one control step, in KinDER's own order (`s.action_space`). KinDER documents them:

The entries of an array in this Box space correspond to the following action features:
| **Index** | **Feature** | **Description** | **Min** | **Max** |
| --- | --- | --- | --- | --- |
| 0 | dx | Change in robot x position (positive is right) | -0.050 | 0.050 |
| 1 | dy | Change in robot y position (positive is up) | -0.050 | 0.050 |
| 2 | dtheta | Change in robot angle in radians (positive is ccw) | -0.196 | 0.196 |
| 3 | darm | Change in robot arm length (positive is out) | -0.100 | 0.100 |
| 4 | vac | Directly sets the vacuum (0.0 is off, 1.0 is on) | 0.000 | 1.000 |

Bounds, value by value: `[0]` -0.05 to 0.05, `[1]` -0.05 to 0.05, `[2]` -0.1963 to 0.1963, `[3]` -0.1 to 0.1, `[4]` 0 to 1.

## What the deliverable does and does not constrain
The trajectory is replayed **open-loop**, but nothing stops you from *generating* it closed-loop: replayed from
`s.reset()`, KinDER on CPU is bit-exact, so actions recorded from a feedback controller reproduce exactly. Use whatever
you like -- scripted motions, feedback control, search, optimisation. One 3000-step episode costs about
6 s of one core and the container has 16. `s.env.unwrapped.set_state()` restores KinDER's
object-centric state only approximately, so a rollout continued from it can drift from the same actions replayed from
the start: check the final trajectory with `s.replay`.
