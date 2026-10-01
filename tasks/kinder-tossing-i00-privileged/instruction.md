# tossing — instance i00

You control a simulated TidyBot++ mobile manipulator (KinDER / MuJoCo) via Python: a holonomic base, a Kinova Gen3
7-DoF arm and a Robotiq 2F-85 gripper. **Task:** get the green cube lying on the floor into the yellow bin on the far side of the low wall that runs across the room. The task succeeds the moment the cube's centre is inside the bin's goal region, the translucent green box marked in the bin.

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
obs = s.reset()                             # back to the frozen scene; obs: KinDER's state vector, (61,)
print(s.state().pretty_str())               # the same state with names: every object, every feature
obs, success, done = s.step(action)         # one 10 Hz control step; action: (18,), see below
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
Each action is 18 numbers, one 10 Hz control step, in KinDER's own order (`s.action_space`):
- `[0:3]` base: how far to move the base in x and y (metres) and turn it (radians, + = counter-clockwise), in the world frame, each at most 0.1 a step; the base's position controller tracks the new pose.
- `[3:10]` arm: radians to add to each of the 7 arm joints' measured angles, each at most 0.1 a step; the sums are the joints' new targets, which the arm's PD controller tracks.
- `[10]` gripper: 0 = open, 1 = closed (a command, not a change).
- `[11:18]` arm: joint velocity targets, rad/s, unbounded, which the PD controller tracks along with the position targets.

## What the deliverable does and does not constrain
The trajectory is replayed **open-loop**, but nothing stops you from *generating* it closed-loop: replayed from
`s.reset()`, KinDER on CPU is bit-exact, so actions recorded from a feedback controller reproduce exactly. Use whatever
you like -- scripted motions, feedback control, search, optimisation. One 1000-step episode costs about
6 s of one core and the container has 16. `s.env.unwrapped.set_state()` restores KinDER's
object-centric state, not everything the physics carries, so a rollout continued from it can drift from the same actions
replayed from the start: check the final trajectory with `s.replay`.
