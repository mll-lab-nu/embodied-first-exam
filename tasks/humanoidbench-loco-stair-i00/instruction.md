# stair — instance 00

You control a simulated Unitree H1 humanoid (HumanoidBench / MuJoCo) via Python. **Task:** walk the
robot forward over the stairs, up each flight and down the other side, without falling.

This is a *fixed scene instance*: the stairs and the robot's initial pose never change between
resets. You may reset and retry as many times as you want. Your deliverable is **one replayable
trajectory**, not a general policy.

## Scoring
HumanoidBench scores a *whole episode*, not a final state: you pass iff the summed per-step reward
over the episode reaches `s.success_bar`, **700** here: a total of rewards, not a number of steps
(an episode is at most 1000 steps). The same three multiplied requirements as walking on the flat —
forward speed (the target is on the order of 1 m/s), staying upright, low actuator force — with one
change that matters: the height part of "upright" is measured as the head's height *above the feet*,
not above the ground, because the ground rises and falls under you and so cannot be the yardstick,
and the torso tilt it accepts is looser than on the flat. Termination is also different: the episode
ends only when the torso tips close to horizontal, rather than when it drops to a fixed height.

**The reward function is not in this container.** `s.step()` returns `None` where the reward would
be and `s.status()` reports no return; the episode is scored in a separate process after you are
done.

You do have the complete physical state: `s.obs()`, and the MuJoCo model and data behind it
(`s.low.model`, `s.low.data`). Everything the reward could tell you is computable from those: how
fast the centre of mass is moving, how upright the torso is, what the actuator forces are, how far a
hand is from a target. Build your own measure of what the episode is judged on (above) and optimise
against it; as a sanity check, it should improve when the robot visibly does the task better.

## Deliverable
Leave three files under `/app/output/`. **Only the first is scored**; the other two are how a human
reads your work afterwards, so keep them short and factual rather than long.

| file | what goes in it |
|---|---|
| `trajectory.npz` | the trajectory, written with `Session.save_trajectory(...)` (below). Replayed open-loop from the same initial state in a fresh process and scored 1 if the replayed episode reaches the pass mark, else 0 |
| `gen.py` | the script that produced it. It must **run and reproduce `trajectory.npz`** — not a paraphrase of it — reading nothing but `/app/instance.npz` and files under `/app/output/` |
| `NOTES.md` | **at most 20 lines**: what your final approach is and why it works, plus the approaches you tried that failed and what each one told you about the task. No narration of your session, no restating this file |

**Write `trajectory.npz` as soon as you have any trajectory at all, and overwrite it (with `gen.py`
and `NOTES.md` to match) whenever you have a better one.** You have a wall-clock budget (1 h) and it
ends without warning; a run that ends with no file scores zero no matter how good the policy in your
scratch directory was. Do not stop early: you cannot see the score here, so a trajectory that looks
good may still fall short of the pass mark — keep improving it until the time is up. Saving is cheap
— a few hundred KB and well under a second.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_hb import Session
s = Session("stair", instance="/app/instance.npz")
s.reset()                          # back to the frozen initial state (unlimited)
obs = s.obs()                      # (51,) = qpos(26) + qvel(25), robot state only
obs, r, done = s.step(action)      # action: (19,) normalised joint-position targets in [-1, 1], 50 Hz
                                   # r is None here (see Scoring); obs and done are real
s.max_steps                        # 1000 — the episode limit, and the longest trajectory accepted
s.low                              # the raw HumanoidBench env (s.low.model / s.low.data) for closed-loop control

with s.recording() as rec:         # capture every action you step
    ...
actions = rec.actions              # (T, 19)

s.status()                         # {'scored': False, 'sim_steps': int, 'state_sha': str, ...} -- no return
s.replay(actions)                  # resets, replays open-loop, returns status()
                                   # use it to check your trajectory is reproducible: same state_sha twice
                                   # means the replay the grader does will land where your rollout did
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
CLI equivalent:
`python /opt/tools/rcb_hb.py replay --task stair --instance /app/instance.npz --traj /app/output/trajectory.npz`

## What the deliverable does and does not constrain
The trajectory is replayed **open-loop**, but nothing stops you from *generating* it closed-loop:
MuJoCo on CPU is bit-exact, so an action sequence recorded from a feedback controller reproduces
exactly when replayed. Use whatever you like — hand-tuned poses, a feedback controller,
sampling-based search, optimisation. One 1000-step episode costs about 0.34 s of a single core and
the container has 16, so large-scale search inside the container is affordable; `s.low.data` can be
snapshotted and restored if you want to branch rollouts.

The 19 actuators are position servos, in this order: `left_hip_yaw`, `left_hip_roll`,
`left_hip_pitch`, `left_knee`, `left_ankle`, `right_hip_yaw`, `right_hip_roll`, `right_hip_pitch`,
`right_knee`, `right_ankle`, `torso`, `left_shoulder_pitch`, `left_shoulder_roll`,
`left_shoulder_yaw`, `left_elbow`, `right_shoulder_pitch`, `right_shoulder_roll`,
`right_shoulder_yaw`, `right_elbow`. A constant action commands joint *targets*, not a pose: whether
the robot stays there depends on whether that pose is stable under gravity and contact.

Optional rendering: `Session("stair", instance=..., enable_render=True)` then
`s.render_video(actions, "/tmp/replay.mp4")`. It picks the GL backend for you — GPU if this
container has one, CPU software rendering (~130 ms/frame) otherwise.
