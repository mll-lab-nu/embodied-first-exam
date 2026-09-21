# sit_simple — instance 00

You control a simulated Unitree H1 humanoid (HumanoidBench / MuJoCo) via Python. **Task:** sit the robot
down on the chair and keep it seated, upright and still.

This is a *fixed scene instance*: the chair and the robot's initial pose never change between resets. You
may reset and retry as many times as you want. Your deliverable is **one replayable trajectory**, not a
general policy.

## Scoring
HumanoidBench scores a *whole episode*, not a final pose: you pass iff the summed per-step reward over the
episode reaches `s.success_bar` (**750.0** here, out of 1000 steps). Sitting down late still costs you the
steps you spent standing, so both *how fast* and *how steadily* the robot sits matter.

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below).
It is replayed open-loop from the same initial state in a fresh process and scored 1 if the replayed
episode reaches the bar, else 0. Also leave the script that produced it at `/app/output/gen.py`.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_hb import Session
s = Session("sit_simple", instance="/app/instance.npz")
s.reset()                          # back to the frozen initial state (unlimited)
obs = s.obs()                      # (51,) = qpos(26) + qvel(25), robot + chair state
obs, r, done = s.step(action)      # action: (19,) normalised joint-position targets in [-1, 1], 50 Hz
s.max_steps                        # 1000 — the episode limit, and the longest trajectory accepted
s.low                              # the raw HumanoidBench env (s.low.model / s.low.data) for closed-loop control

with s.recording() as rec:         # capture every action you step
    ...
actions = rec.actions              # (T, 19)

s.status()                         # {'success': bool, 'episode_return': float, 'success_bar': 750.0, ...}
s.replay(actions)                  # resets, replays open-loop, returns status  -> use this to self-check
s.save_trajectory(actions, "/app/output/trajectory.npz")
```
CLI equivalent of the grader:
`python /opt/tools/rcb_hb.py replay --task sit_simple --instance /app/instance.npz --traj /app/output/trajectory.npz`

## What the deliverable does and does not constrain
The trajectory is replayed **open-loop**, but nothing stops you from *generating* it closed-loop: MuJoCo on
CPU is bit-exact, so an action sequence recorded from a feedback controller reproduces exactly when
replayed. Use whatever you like — hand-tuned poses, a feedback controller, sampling-based search,
optimisation. One 1000-step episode costs about 0.6 s of a single core and the container has 16, so
large-scale search inside the container is affordable; `s.low.data` can be snapshotted and restored if you
want to branch rollouts.

The 19 actuators are position servos, in this order: left/right `hip_yaw, hip_roll, hip_pitch, knee,
ankle`, then `torso`, then left/right `shoulder_pitch, shoulder_roll, shoulder_yaw, elbow`. A constant
action commands a joint *target*, not a pose: whether the robot stays there depends on whether that pose
is stable under gravity and contact. Holding the initial standing target, for instance, falls over at
about step 96.

Optional rendering: `Session("sit_simple", instance=..., enable_render=True)` then
`s.render_video(actions, "/app/output/replay.mp4")`. It picks the GL backend for you — GPU if this
container has one, CPU software rendering (~130 ms/frame) otherwise.
