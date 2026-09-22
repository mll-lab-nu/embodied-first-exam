# spoon — instance 00

You control a simulated Unitree H1 humanoid with two Shadow dexterous hands (HumanoidBench / MuJoCo)
via Python. **Task:** take hold of the spoon and stir with it: keep the spoon in the cup and move
its head around a small circle, continuously, for the whole episode.

This is a *fixed scene instance*: the cup, the spoon and the robot's initial pose never change
between resets. You may reset and retry as many times as you want. Your deliverable is **one
replayable trajectory**, not a general policy.

## Scoring
HumanoidBench scores a *whole episode*, not a final state: you pass iff the summed per-step reward
over the episode reaches `s.success_bar` (**650** here, out of 1000 steps). A weighted sum of four
things: standing steadily, getting a hand to the spoon's handle, keeping the spoon's head inside the
cup, and — the largest single term — keeping that head close to a target point that **travels around
a small circle at a fixed rate, completing a revolution every 40 steps**. The first three are
largely satisfied by the starting arrangement; the gap to the bar is almost entirely the circling
term, so what this task asks for is periodic tracking rather than reaching a pose. The episode ends
if the torso drops.

**The reward function is not in this container.** `s.step()` returns `None` where the reward would
be and `s.status()` reports no return; the episode is scored in a separate process after you are
done. That is on purpose — HumanoidBench's rewards are dense and hand-tuned, so having the formula
turns the job into inverting an expression instead of controlling a robot.

You do have the complete physical state: `s.obs()`, and the MuJoCo model and data behind it
(`s.low.model`, `s.low.data`). Everything the reward could tell you is computable from those: how
fast the centre of mass is moving, how upright the torso is, what the actuator forces are, how far a
hand is from a target. The paragraph above says what this episode is judged on. Build the measure
you think it calls for and optimise against that; as a sanity check, your measure should improve
when the robot visibly does the task better.

## Deliverable
Leave three files under `/app/output/`. **Only the first is scored**; the other two are how a human
reads your work afterwards, so keep them short and factual rather than long.

| file | what goes in it |
|---|---|
| `trajectory.npz` | the trajectory, written with `Session.save_trajectory(...)` (below). Replayed open-loop from the same initial state in a fresh process and scored 1 if the replayed episode reaches the bar, else 0 |
| `gen.py` | the script that produced it. It must **run and reproduce `trajectory.npz`** — not a paraphrase of it |
| `NOTES.md` | **at most 20 lines**: what your final approach is and why it works, plus the approaches you tried that failed and what each one told you about the task. No narration of your session, no restating this file |

**Write `trajectory.npz` as soon as you have any trajectory at all, and overwrite it whenever you
have a better one.** You have a wall-clock budget (1 h) and it ends without warning; a run that ends
with no file scores zero no matter how good the policy in your scratch directory was. Saving is
cheap — a few hundred KB and well under a second.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_hb import Session
s = Session("spoon", instance="/app/instance.npz")
s.reset()                          # back to the frozen initial state (unlimited)
obs = s.obs()                      # (167,) = qpos(83) + qvel(81) + the stirring target point xyz(3) -- it moves, read it every step
obs, r, done = s.step(action)      # action: (61,) normalised joint-position targets in [-1, 1], 50 Hz
                                   # r is None here (see Scoring); obs and done are real
s.max_steps                        # 1000 — the episode limit, and the longest trajectory accepted
s.low                              # the raw HumanoidBench env (s.low.model / s.low.data) for closed-loop control

with s.recording() as rec:         # capture every action you step
    ...
actions = rec.actions              # (T, 61)

s.status()                         # {'scored': False, 'sim_steps': int, 'state_sha': str, ...} -- no return
s.replay(actions)                  # resets, replays open-loop, returns status()
                                   # use it to check your trajectory is reproducible: same state_sha twice
                                   # means the replay the grader does will land where your rollout did
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
CLI equivalent:
`python /opt/tools/rcb_hb.py replay --task spoon --instance /app/instance.npz --traj /app/output/trajectory.npz`

## What the deliverable does and does not constrain
The trajectory is replayed **open-loop**, but nothing stops you from *generating* it closed-loop:
MuJoCo on CPU is bit-exact, so an action sequence recorded from a feedback controller reproduces
exactly when replayed. Use whatever you like — hand-tuned poses, a feedback controller,
sampling-based search, optimisation. One 1000-step episode costs about 1.26 s of a single core and
the container has 16, so large-scale search inside the container is affordable; `s.low.data` can be
snapshotted and restored if you want to branch rollouts.

The 61 actuators are position servos. The first 21 are the body, in this order: `left_hip_yaw`,
`left_hip_roll`, `left_hip_pitch`, `left_knee`, `left_ankle`, `right_hip_yaw`, `right_hip_roll`,
`right_hip_pitch`, `right_knee`, `right_ankle`, `torso`, `left_shoulder_pitch`,
`left_shoulder_roll`, `left_shoulder_yaw`, `left_elbow`, `left_wrist_yaw`, `right_shoulder_pitch`,
`right_shoulder_roll`, `right_shoulder_yaw`, `right_elbow`, `right_wrist_yaw`. The remaining 40 are
the fingers, 20 per Shadow hand — `lh_A_*` then `rh_A_*`. A constant action commands joint
*targets*, not a pose: whether the robot stays there depends on whether that pose is stable under
gravity and contact.

**The target point is in your observation** (the last three numbers) and it moves every step, so you
do not have to reconstruct the circle — read it and track it.

Its phase is part of the task's internal state and advances one step per scored step. It is frozen
into this instance at the start of a revolution, so every reset begins at the same phase; upstream
never reset that counter, which meant a second rollout in one process was scored against a
differently-phased target. The frozen instance restores it (`Session._restore_extra`).

Optional rendering: `Session("spoon", instance=..., enable_render=True)` then
`s.render_video(actions, "/app/output/replay.mp4")`. It picks the GL backend for you — GPU if this
container has one, CPU software rendering (~130 ms/frame) otherwise.
