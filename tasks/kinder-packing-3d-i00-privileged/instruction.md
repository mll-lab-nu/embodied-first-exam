# packing-3d — instance i00

You control a simulated mobile manipulator (KinDER / PyBullet, kinematic: no dynamics) via Python: a mobile base and a Kinova Gen3 7-DoF arm with a gripper. **Task:** put the three flat green parts on the grey table, a square (`part0`) and two right triangles (`part1`, `part2`), each with a small red peg on top, into the purple tray in the middle of the table (`rack`). The task succeeds the moment the robot holds nothing and every part rests in the tray: its flat body (peg excluded) lies within the tray's inner outline, its underside is within 5 mm of the tray floor's height and its top is no more than 5 mm above the tray's rim, it is within 5 mm of the tray without penetrating it, and no two parts (pegs included) overlap.

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
obs = s.reset()                             # back to the frozen scene; obs: KinDER's state vector, (67,)
print(s.state().pretty_str())               # the same state with names: every object, every feature
obs, success, done = s.step(action)         # one control step; action: (11,), see below
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
Each action is 11 numbers, one control step, in KinDER's own order (`s.action_space`). KinDER documents them:

An action space for mobile manipulation with a 7 DOF robot that can open and close its gripper.

Actions are bounded relative base position, rotation, and joint positions, and open / close.

| **Index** | **Description** |
| --- | --- |
| 0 | delta base x |
| 1 | delta base y |
| 2 | delta base rotation |
| 3 | delta joint 1 |
| 4 | delta joint 2 |
| 5 | delta joint 3 |
| 6 | delta joint 4 |
| 7 | delta joint 5 |
| 8 | delta joint 6 |
| 9 | delta joint 7 |
| 10 | gripper open/close |

The open / close logic is: <-0.5 is close, >0.5 is open, and otherwise no change.

Bounds, value by value: `[0]` -0.2 to 0.2, `[1]` -0.2 to 0.2, `[2]` -0.2 to 0.2, `[3]` -0.2 to 0.2, `[4]` -0.2 to 0.2, `[5]` -0.2 to 0.2, `[6]` -0.2 to 0.2, `[7]` -0.2 to 0.2, `[8]` -0.2 to 0.2, `[9]` -0.2 to 0.2, `[10]` -1 to 1.

## What the deliverable does and does not constrain
The trajectory is replayed **open-loop**, but nothing stops you from *generating* it closed-loop: replayed from
`s.reset()`, KinDER on CPU is bit-exact, so actions recorded from a feedback controller reproduce exactly. Use whatever
you like -- scripted motions, feedback control, search, optimisation. One 3000-step episode costs about
48 s of one core and the container has 16. `s.env.unwrapped.set_state()` restores KinDER's
object-centric state only approximately, so a rollout continued from it can drift from the same actions replayed from
the start: check the final trajectory with `s.replay`.
