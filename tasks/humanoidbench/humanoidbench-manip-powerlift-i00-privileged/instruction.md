# HumanoidBench · powerlift (privileged)

## Task
Lift the dumbbell off the floor to overhead and hold it there.

## Goal
Success: the dumbbell is held up overhead for most of the episode, with the robot standing steadily.

If the robot falls, the episode ends at once and nothing after that counts.

You cannot see the score here: the reward function is not in this container (`s.step()` returns `None` where the reward
would be, and `s.status()` reports no return). You do have the complete physical state (`s.obs()`, `s.low.model`,
`s.low.data`). Build your own measure of what the episode is judged on and optimise against it; your measure should
improve when the robot visibly does the task better.

Deliverable: `/app/output/trajectory.npz`, written with `s.save_trajectory(...)`, at most 1000 rows (`s.max_steps`). It
is replayed open-loop from the fixed start and passes if the replayed episode's score reaches the mark. Also leave two
files. `/app/output/gen.py` is the script that produced it; it must run and reproduce `trajectory.npz` (not a paraphrase
of it), reading nothing but `/app/instance.npz` and files under `/app/output/`. `/app/output/NOTES.md`, at most 20
lines, gives your final approach and why it works, and the approaches you tried that failed and what each told you about
the task. Only the trajectory is scored. Save one as soon as you have any trajectory. Overwrite it, with `gen.py` and
`NOTES.md` to match, whenever you have a better one. You cannot see the score, so keep improving it until the time is
up.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed.

## Robot Interface
A simulated Unitree H1 humanoid with two Shadow dexterous hands (HumanoidBench, MuJoCo). The scene is one fixed
instance. You have the full simulator to develop with; you hand in a trajectory of servo targets.

### Session
`/opt/tools/rcb_hb.py`, importable as `rcb_hb` (installed; run `python` from any directory):
```python
from rcb_hb import Session
s = Session("powerlift", instance="/app/instance.npz")
s.reset()                          # back to the frozen initial state (unlimited)
obs = s.obs()                      # (164,) = qpos(83) + qvel(81), robot + dumbbell state
obs, r, done = s.step(action)      # action: (61,) normalised joint-position targets in [-1, 1], 50 Hz
                                   # r is None here (see Goal)
s.max_steps                        # 1000 — the episode limit, and the longest trajectory accepted
s.low                              # the raw HumanoidBench env (s.low.model / s.low.data) for closed-loop control

with s.recording() as rec:         # capture every action you step
    ...
actions = rec.actions              # (T, 61)

s.status()                         # {'scored': False, 'sim_steps': int, 'state_sha': str, ...} -- no return
s.replay(actions)                  # resets, replays open-loop, returns status(); the same state_sha twice: it reproduces
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
The same replay from the shell: `python /opt/tools/rcb_hb.py replay --task powerlift --instance /app/instance.npz --traj /app/output/trajectory.npz`.

### Actions
An action is one control step (50 Hz): normalised joint-position targets in [-1, 1], one per servo. -1 and +1 command
the two ends of a servo's range, linearly, so 0 is mid-range, not 0 rad. The 61 actuators are position servos. The first
21 are the body, in this order: `left_hip_yaw`, `left_hip_roll`, `left_hip_pitch`, `left_knee`, `left_ankle`,
`right_hip_yaw`, `right_hip_roll`, `right_hip_pitch`, `right_knee`, `right_ankle`, `torso`, `left_shoulder_pitch`,
`left_shoulder_roll`, `left_shoulder_yaw`, `left_elbow`, `left_wrist_yaw`, `right_shoulder_pitch`,
`right_shoulder_roll`, `right_shoulder_yaw`, `right_elbow`, `right_wrist_yaw`. The remaining 40 are the two Shadow
hands, 20 each: `lh_A_*`, then `rh_A_*`. In each hand the first 2 are the wrist (`*_A_WRJ2`, `*_A_WRJ1`) and the other
18 are the fingers. Each of the 4 `*J0` actuators (`*_A_FFJ0`, `*_A_MFJ0`, `*_A_RFJ0`, `*_A_LFJ0`) drives a tendon that
moves two finger joints together. A constant action commands joint *targets*, not a pose: whether the robot stays there
depends on whether that pose is stable under gravity and contact.

### Speed and rendering
- One 1000-step episode costs about 1.18 s of one core, and the container has 16, so large-scale search is affordable.
- Optional rendering: `Session("powerlift", instance=..., enable_render=True)` then
  `s.render_video(actions, "/tmp/replay.mp4")`. It picks the GL backend for you — GPU if this container has one, CPU
  software rendering (~130 ms/frame) otherwise.

## Others
- The trajectory is replayed open-loop, but MuJoCo on the CPU repeats exactly, so actions recorded from a feedback
  controller reproduce when replayed. You can snapshot and restore `s.low.data` to branch rollouts.

## Limits
- Time: 3600 s of wall-clock time from the start of your session. Everything counts, including the simulator's start-up.
  At the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). A call into a long-running process can block for its
  whole wait time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, including the simulator's and the benchmark's source.
- Resources: 16 CPUs, 20 GiB memory, 2048 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU. Going over a cap can get a process killed (the CPU cap only slows you down). Usage:
  `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
