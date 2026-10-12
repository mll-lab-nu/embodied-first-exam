# cube — instance 00

You control a simulated Unitree H1 humanoid with two Shadow dexterous hands (HumanoidBench / MuJoCo)
via Python. **Task:** a cube starts just above and in front of each palm. Rotate both cubes to the
goal orientation without dropping them.

This is a *fixed scene instance*: the cubes' starting orientations, the goal orientation and the
robot's initial pose never change between resets. You may reset and retry as many times as you want.
Your deliverable is **one replayable trajectory**, not a general policy.

## Scoring
HumanoidBench scores a *whole episode*, not a final state: you pass iff the summed per-step reward
over the episode reaches `s.success_bar`, **370** here: a total of rewards, not a number of steps
(an episode is at most 500 steps). A weighted sum: the largest term is how closely each cube's
orientation matches the goal, averaged over the two hands; then how close each hand is to its cube;
then a small share for standing steadily without moving. The orientation term is sharp — it falls
away quickly as the orientation drifts, so approximate alignment earns much less than it looks like
it should — and it compares orientations as quaternions, sign included: of the two ways to turn a
cube onto the goal, only one scores, because the other ends at the same orientation with the
opposite sign, which counts as far off. The episode ends the moment either cube drops below a
height, or the pelvis does.

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
and `NOTES.md` to match) whenever you have a better one.** The time limit (`## Time limit`) ends
without warning; a run that ends with no file scores zero no matter how good the policy in your
scratch directory was. Do not stop early: you cannot see the score here, so a trajectory that looks
good may still fall short of the pass mark — keep improving it until the time is up. Saving is cheap
— a few hundred KB and well under a second.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_hb import Session
s = Session("cube", instance="/app/instance.npz")
s.reset()                          # back to the frozen initial state (unlimited)
obs = s.obs()                      # (181,) = qpos(90) + qvel(87) + the goal orientation as a quaternion(4)
obs, r, done = s.step(action)      # action: (61,) normalised joint-position targets in [-1, 1], 50 Hz
                                   # r is None here (see Scoring); obs and done are real
s.max_steps                        # 500 — the episode limit, and the longest trajectory accepted
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
`python /opt/tools/rcb_hb.py replay --task cube --instance /app/instance.npz --traj /app/output/trajectory.npz`

## What the deliverable does and does not constrain
The trajectory is replayed **open-loop**, but nothing stops you from *generating* it closed-loop:
MuJoCo on CPU is bit-exact, so an action sequence recorded from a feedback controller reproduces
exactly when replayed. Use whatever you like — hand-tuned poses, a feedback controller,
sampling-based search, optimisation. One 500-step episode costs about 0.58 s of a single core and
the container has 16, so large-scale search inside the container is affordable; `s.low.data` can be
snapshotted and restored if you want to branch rollouts.

The 61 actuators are position servos. The first 21 are the body, in this order: `left_hip_yaw`,
`left_hip_roll`, `left_hip_pitch`, `left_knee`, `left_ankle`, `right_hip_yaw`, `right_hip_roll`,
`right_hip_pitch`, `right_knee`, `right_ankle`, `torso`, `left_shoulder_pitch`,
`left_shoulder_roll`, `left_shoulder_yaw`, `left_elbow`, `left_wrist_yaw`, `right_shoulder_pitch`,
`right_shoulder_roll`, `right_shoulder_yaw`, `right_elbow`, `right_wrist_yaw`. The remaining 40 are
the two Shadow hands, 20 each — `lh_A_*` then `rh_A_*`; each hand's first 2 are its wrist
(`*_A_WRJ2`, `*_A_WRJ1`) and the other 18 its fingers, where each of the 4 `*J0` ones (`*_A_FFJ0`,
`*_A_MFJ0`, `*_A_RFJ0`, `*_A_LFJ0`) drives a tendon that moves two finger joints together. A
constant action commands joint *targets*, not a pose: whether the robot stays there depends on
whether that pose is stable under gravity and contact.

The goal orientation is not in `(qpos, qvel)` — upstream writes it into the MuJoCo model
(`body_quat`), drawn from the global `np.random` at reset. It is frozen into this instance, so it is
the same in your container and the verifier's, and it does not move between resets.

Optional rendering: `Session("cube", instance=..., enable_render=True)` then
`s.render_video(actions, "/tmp/replay.mp4")`. It picks the GL backend for you — GPU if this
container has one, CPU software rendering (~130 ms/frame) otherwise.

## External material
You may install packages you need (pip, apt). Please solve the task yourself: do not look up or download a solution to it, such as this benchmark's own source code, published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **16 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 16 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Installing packages is not cheating (`## External material` above).
