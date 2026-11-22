# HumanoidBench · door (privileged)

## Task
A simulated Unitree H1 humanoid (HumanoidBench, MuJoCo). Walk to the door, press the handle, pull the door open towards
the robot, and walk through it. The scene is one fixed instance.
You have the full simulator to develop with; you hand in a trajectory of servo targets.

## Goal
Success: the episode's score reaches 600 (an episode has at most 1000 steps), which takes opening the door: the largest
parts of every control step's score are for the door standing open and for the torso being through the doorway, smaller
ones for reaching for the handle, turning it and posture. The episode ends early, with nothing more to score, when the
robot falls.

You cannot see the score here: the reward function is not in this container (`s.step()` returns `None` where the reward
would be, and `s.status()` reports no return). You do have the complete physical state (`s.obs()`, `s.low.model`,
`s.low.data`): build your own measure of what the episode is judged on and optimise against it; it should improve when
the robot visibly does the task better.

Deliverable: `/app/output/trajectory.npz`, written with `s.save_trajectory(...)`, at most 1000 rows (`s.max_steps`); it
is replayed open-loop from the fixed start and passes if the replayed episode's score reaches the mark. Also leave
`/app/output/gen.py`, the script that produced it, which must run and reproduce `trajectory.npz` (not a paraphrase of
it) reading nothing but `/app/instance.npz` and files under `/app/output/`, and `/app/output/NOTES.md`, at most 20
lines: your final approach and why it works, and the approaches you tried that failed and what each told you about the
task. Only the trajectory is scored. Save one as soon as you have any trajectory and overwrite it (with `gen.py` and
`NOTES.md` to match) whenever you have a better one; since you cannot see the score, keep improving it until the time is
up.

Rules: write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.

## Robot Interface
### Session
`/opt/tools/rcb_hb.py`, importable as `rcb_hb` (installed; run `python` from any directory):
```python
from rcb_hb import Session
s = Session("door", instance="/app/instance.npz")
s.reset()                          # back to the frozen initial state (unlimited)
obs = s.obs()                      # (55,) = qpos(28) + qvel(27), robot + door + handle state
obs, r, done = s.step(action)      # action: (19,) normalised joint-position targets in [-1, 1], 50 Hz
                                   # r is None here (see Goal)
s.max_steps                        # 1000 — the episode limit, and the longest trajectory accepted
s.low                              # the raw HumanoidBench env (s.low.model / s.low.data) for closed-loop control

with s.recording() as rec:         # capture every action you step
    ...
actions = rec.actions              # (T, 19)

s.status()                         # {'scored': False, 'sim_steps': int, 'state_sha': str, ...} -- no return
s.replay(actions)                  # resets, replays open-loop, returns status(); the same state_sha twice: it reproduces
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
The same replay from the shell: `python /opt/tools/rcb_hb.py replay --task door --instance /app/instance.npz --traj /app/output/trajectory.npz`.

### Actions
An action is one control step (50 Hz): normalised joint-position targets in [-1, 1], one per servo. -1 and +1 command
the two ends of a servo's range, linearly, so 0 is mid-range, not 0 rad. The 19 actuators are position servos, in this
order: `left_hip_yaw`, `left_hip_roll`, `left_hip_pitch`, `left_knee`, `left_ankle`, `right_hip_yaw`, `right_hip_roll`,
`right_hip_pitch`, `right_knee`, `right_ankle`, `torso`, `left_shoulder_pitch`, `left_shoulder_roll`,
`left_shoulder_yaw`, `left_elbow`, `right_shoulder_pitch`, `right_shoulder_roll`, `right_shoulder_yaw`, `right_elbow`. A
constant action commands joint *targets*, not a pose: whether the robot stays there depends on whether that pose is
stable under gravity and contact.

## Others
- The trajectory is replayed open-loop, but you may generate it closed-loop: MuJoCo on the CPU repeats exactly, so an
  action sequence recorded from a feedback controller reproduces when replayed. Hand-tuned poses, feedback control,
  sampling-based search and optimisation are all fine; `s.low.data` can be snapshotted and restored to branch rollouts.
- One 1000-step episode costs about 0.52 s of one core, and the container has 16, so large-scale search is affordable.
- Optional rendering: `Session("door", instance=..., enable_render=True)` then
  `s.render_video(actions, "/tmp/replay.mp4")`. It picks the GL backend for you — GPU if this container has one, CPU
  software rendering (~130 ms/frame) otherwise.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (the simulator's start-up too). At
  the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 16 CPUs, 20 GiB memory, 2048 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU. Over a cap a process can be killed (the CPU cap only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
