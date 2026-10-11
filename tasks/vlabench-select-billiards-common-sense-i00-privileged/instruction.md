# VLABench · select_billiards_common_sense — instance i00

You control a simulated **Franka Panda** arm (VLABench on MuJoCo) via Python. **Task: Please put the ball worth 7 score in the middle pocket on the robot's right (+x) side of the table, near x = 0.56, y = 0.02.**

This states exactly what VLABench's success check requires; VLABench's own wording (also in `s.state()["instruction"]`) is: "Please put the ball worth 7 score in hole".

This is a *fixed scene instance*: VLABench's own scene for `select_billiards_common_sense`, frozen (seed 0). You may reset and retry
as often as you like. Your deliverable is **one replayable trajectory** of control steps, not a general policy.

## Success
VLABench's own success check for `select_billiards_common_sense` (the task's termination condition). The episode **ends the moment it
holds**. The verifier replays your trajectory from the frozen start in a separate sandbox (twice, in fresh processes;
MuJoCo on the CPU is bit-exact) and passes it iff the task succeeds at its **last** action, the final state. A
trajectory that goes on after the task has terminated is invalid; one that never gets there fails. `s.step()` and
`s.status()` report `success` and `done`; `s.replay(A)` does exactly what the verifier does.

## Deliverable
Leave three files under `/app/output/`. **Only the first is scored**; the other two are for the humans who read your
work afterwards, so keep them short and factual.

| file | what goes in it |
|---|---|
| `trajectory.npz` | the trajectory, written with `s.save_trajectory()` (below): key `actions`, shape `(T, 9)`, 1 ≤ T ≤ 4000 |
| `gen.py` | the script that produced it; it should run and reproduce `trajectory.npz` from `/app/instance.json` |
| `NOTES.md` | at most 20 lines: your final approach and why it works, and what you tried that failed |

**Write `trajectory.npz` as soon as you have any trajectory at all, and overwrite it whenever you have a better one.**
You have 60 minutes of wall-clock time and it ends without warning; a run that ends with no file scores zero. Do not
stop early: keep improving and checking until you are sure the replay succeeds.

## Tooling (`/opt/tools/vlb_tool.py`, importable as `vlb_tool`)
```python
import numpy as np, vlb_tool
s = vlb_tool.Session("/app/instance.json")  # the frozen instance; s.env is the VLABench (dm_control) environment
st = s.state()           # entities {name: category, position, quaternion_wxyz, grasp keypoints / place point where
                         #   defined, joint_positions if articulated}, robot {joint, finger and tcp state}, success
s.step(a)                # one control step (0.1 s) -> {"success", "done", "control_steps", "state_sha"}
s.skill("pick", target_entity_name="...")   # VLABench's general skills (vlb_tool.SKILLS) as planning primitives;
                                            #   the control steps they execute are recorded like any other
s.ik(position, quaternion_wxyz)             # inverse kinematics for the hand -> {"success", "joint_positions"}
s.actions                # every control step since the last reset (what save_trajectory() writes)
s.save_trajectory()      # -> /app/output/trajectory.npz
s.replay(A)              # reset, then replay A (what the verifier does)
s.reset()                # back to the frozen start (bit-exact), as often as you like
o = s.observe("forward") # rgb, depth_m, intrinsic_cv, cam2world_gl; cameras forward, left, right, wrist
```
- An action is 9 absolute position targets for VLABench's own actuators: the 7 arm joints (rad) and the 2 fingers
  (m, 0 closed … 0.04 open), held for one control step (0.1 s, 100 physics steps). The model sets no arm joint
  limits; the Panda's own are [-2.90, 2.90], [-1.76, 1.76], [-2.90, 2.90], [-3.07, -0.07], [-2.90, 2.90], [-0.02, 3.75], [-2.90, 2.90] rad.
- World frame: metres; the robot's base is at (0, -0.4, 0.6) facing +y: x to the robot's right, y forward (across
  the table), z up; quaternions are w x y z.
- Everything in `s.env` and `s.physics` is readable (privileged mode). VLABench's expert solutions for its tasks are not
  in this image.

## Rules
- Write your own controller (the general skills are allowed). Do not use VLABench's expert solutions or any published
  solution for this benchmark.
- Only the recorded control steps count: editing `s.physics` directly while debugging changes nothing in the replay.

## External material
You may install packages you need (pip, apt). Please solve the task yourself: do not look up or download a solution to it, such as this benchmark's own source code, published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **16 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.
