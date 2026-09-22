# window — instance 00

You control a simulated Unitree H1 humanoid with two Shadow dexterous hands (HumanoidBench / MuJoCo)
via Python. **Task:** pick up the wiping tool and wipe the window with it, moving steadily up and
down.

This is a *fixed scene instance*: the window, the tool and the robot's initial pose never change
between resets. You may reset and retry as many times as you want. Your deliverable is **one
replayable trajectory**, not a general policy.

## Scoring
HumanoidBench scores a *whole episode*, not a final state: you pass iff the summed per-step reward
over the episode reaches `s.success_bar` (**650** here, out of 1000 steps). Two requirements gate
everything else, and both are factors rather than bonuses. The tool has to be in contact with the
glass — while it is not, that factor is zero and the step is worth nothing — and the wiping motion
is scored against a target vertical speed, so neither holding the tool still against the glass nor
waving it through the air earns anything. The episode ends immediately if the torso drops or the
tool falls, i.e. if it is dropped.

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
s = Session("window", instance="/app/instance.npz")
s.reset()                          # back to the frozen initial state (unlimited)
obs = s.obs()                      # (171,) = qpos(87) + qvel(84), robot + tool + window state
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
`python /opt/tools/rcb_hb.py replay --task window --instance /app/instance.npz --traj /app/output/trajectory.npz`

## What the deliverable does and does not constrain
The trajectory is replayed **open-loop**, but nothing stops you from *generating* it closed-loop:
MuJoCo on CPU is bit-exact, so an action sequence recorded from a feedback controller reproduces
exactly when replayed. Use whatever you like — hand-tuned poses, a feedback controller,
sampling-based search, optimisation. One 1000-step episode costs about 1.46 s of a single core and
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

Optional rendering: `Session("window", instance=..., enable_render=True)` then
`s.render_video(actions, "/app/output/replay.mp4")`. It picks the GL backend for you — GPU if this
container has one, CPU software rendering (~130 ms/frame) otherwise.
