# bigym2 flip-cup — instance i00

You control a simulated Unitree G1 humanoid robot with two-finger grippers (BiGym 2.0, MuJoCo) via Python. NVIDIA's
GR00T whole-body controller, a learned policy that runs inside every simulator step, drives its legs and waist and
keeps it balanced: you command where it walks, how high its pelvis is, how far its torso leans forward, its arm joints and its grippers.
**Task:** Turn the upside-down cup the right way up and gently set it back down.

At the start the cup stands upside down on the counter in front of you, about 0.6 m away, straight ahead, 0.96 m above the floor. (Distances are from your pelvis along the floor, directions from the way you face,
heights above the floor; measured on this scene.)

This is a *fixed scene instance* (BiGym's `flip_cup`, reset with seed 0). You may reset and retry as many
times as you want. Your deliverable is **one replayable trajectory**, not a general policy.

## Success
The episode succeeds when the following has held for **1 s (50 control steps in a row)**: the cup stands the right way up (its axis within 5 degrees of vertical), touching the counter, held by neither gripper. *Held* means that a finger of the gripper touches the object (BiGym's `is_gripper_holding_object`): an open gripper still resting against it holds it. The robot must not fall at any time: a fall (the pelvis tilted more than about 53 degrees from upright, or lower than 0.30 m) makes the episode a failure, but does not end it.

The episode ends when the success has held for 1 s (that step is the success), when the pelvis gets more
than 10 m from the scene's origin, on a physics error, or after **1850 control steps** (37 s at
50 Hz). The success check is BiGym's own (`is_success` in `bigym.loco.eval`); `s.status()["success"]` reports it.

## Deliverable
Leave three files under `/app/output/`. **Only the first is scored**; the other two are how a human reads your work
afterwards, so keep them short and factual.

| file | what goes in it |
|---|---|
| `trajectory.npz` | the trajectory, written with `s.save_trajectory(rows)` (below): `actions`, one row of 21 floats per control step. Replayed open-loop from the frozen instance in two fresh processes, one row per step until the episode ends; scored 1 if both replays succeed and end in the same state, else 0. At most 1850 rows; rows after the episode's end are ignored |
| `gen.py` | the script that produced it. It must **run and reproduce `trajectory.npz`**, reading nothing but `/app/instance.json` and files under `/app/output/` |
| `NOTES.md` | **at most 20 lines**: your final approach and why it works, and the approaches that failed and what each told you |

The tooling also appends its own log, `rcb_session_log.jsonl`, to `/app/output/`: leave it there and do not set
`RCB_SESSION_LOG`.

**Write `trajectory.npz` as soon as you have any trajectory at all, and overwrite it (with `gen.py` and `NOTES.md` to
match) whenever you have a better one.** Your wall-clock budget is 1 h and it ends without warning; a run that ends
with no file scores zero. Do not stop early: keep improving until the time is up.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_bigym2 import Session
s = Session("/app/instance.json")      # a few seconds: the scene + the controller's 200-step warm-up
s.layout                               # the 21 action slots, in order (below)
row = s.hold_row()                     # stand still: your last command with zero vx, vy, wz (before any: upstream's)
done = s.step(row)                     # one control step (50 Hz); True once the episode is over
s.status()                             # success, done, outcome, fell, steps, horizon, state_sha
s.reset()                              # back to the frozen instance (unlimited; under a second, a new Session ~3 s)
s.task                                 # BiGym's task env: its props (s.task.cup, ...) and s.task.robot
s.env, s.tools, s.model, s.data        # the env wrapper steps go through, BiGym's EnvTools, MuJoCo model and data
s.tools.ik(left_pos=p, right_pos=q)    # BiGym's IK: 14 arm targets (left 7, right 7) putting each gripper's
                                       # *_end_effector site (the point between its finger pads) at a world point
s.image("head", 256, 256)              # an onboard camera's RGB image (head, left_wrist, right_wrist); 84x84 by
                                       # default (upstream's size), up to 640x640
s.held(s.task.cup)                     # BiGym's "held", per gripper: {"left": bool, "right": bool}; the upstream call
                                       # takes the keys of s.task.robot.grippers (HandSide), not strings
s.replay(rows)                         # what the verifier does, here: {"success", "state_sha", ...}
s.save_trajectory(rows)                # writes the SCORED file /app/output/trajectory.npz; pass another path to explore
```
The simulator is deterministic on the CPU: the same rows from the frozen instance give the same state, so a trajectory
you generate closed-loop replays exactly. `python /opt/tools/rcb_bigym2.py replay --instance /app/instance.json --traj
/app/output/trajectory.npz --out /tmp/r.json` runs the verifier's replay from the shell. The BiGym package (`bigym`) is
installed; its documentation and source are in the package. On the G1, BiGym's `pinch_position` (a gripper's "pinch
site") is the wrist link's origin, 0.148 m behind the finger pads; the point between the pads is the
`left_end_effector` / `right_end_effector` site (`wrist_position`). The container reaches your model's API and nothing
else: BiGym's recorded demonstrations and other published trajectories are not part of this task.

## Action rows (21 floats, physical units)
| slot | name | bounds | meaning | at the start |
|---|---|---|---|---|
| 0 | `vx` | [-1, 1] | walking velocity command, forward (m/s, the robot's frame) | 0 |
| 1 | `vy` | [-1, 1] | walking velocity command, to the left (m/s) | 0 |
| 2 | `height` | [0.4, 1] | pelvis height command (m) | 0.74 |
| 3 | `wz` | [-1, 1] | turning rate command, + turns left (rad/s) | 0 |
| 4 | `pitch` | [-0.2, 0.8] | torso lean command, + leans forward (rad) | 0 |
| 5 | `left_shoulder_pitch_joint` | [-3.0892, 2.6704] | absolute joint target (rad) | 0 |
| 6 | `left_shoulder_roll_joint` | [-1.5882, 2.2515] | absolute joint target (rad) | 0 |
| 7 | `left_shoulder_yaw_joint` | [-2.618, 2.618] | absolute joint target (rad) | 0 |
| 8 | `left_elbow_joint` | [-1.0472, 2.0944] | absolute joint target (rad) | 0 |
| 9 | `left_wrist_roll_joint` | [-1.9722, 1.9722] | absolute joint target (rad) | 0 |
| 10 | `left_wrist_pitch_joint` | [-1.6144, 1.6144] | absolute joint target (rad) | 0 |
| 11 | `left_wrist_yaw_joint` | [-1.6144, 1.6144] | absolute joint target (rad) | 0 |
| 12 | `right_shoulder_pitch_joint` | [-3.0892, 2.6704] | absolute joint target (rad) | 0 |
| 13 | `right_shoulder_roll_joint` | [-1.5882, 2.2515] | absolute joint target (rad) | 0 |
| 14 | `right_shoulder_yaw_joint` | [-2.618, 2.618] | absolute joint target (rad) | 0 |
| 15 | `right_elbow_joint` | [-1.0472, 2.0944] | absolute joint target (rad) | 0 |
| 16 | `right_wrist_roll_joint` | [-1.9722, 1.9722] | absolute joint target (rad) | 0 |
| 17 | `right_wrist_pitch_joint` | [-1.6144, 1.6144] | absolute joint target (rad) | 0 |
| 18 | `right_wrist_yaw_joint` | [-1.6144, 1.6144] | absolute joint target (rad) | 0 |
| 19 | `left_gripper` | [0, 1] | 0 open .. 1 closed | 0.6 |
| 20 | `right_gripper` | [0, 1] | 0 open .. 1 closed | 0.6 |

`right_shoulder_roll_joint`'s bounds are BiGym's action bounds, not the joint's own range [-2.2515, 1.5882]: a command outside them is clipped.

Values outside the bounds are clipped; the last column is the row that stands still at the start. The whole-body controller, as BiGym's own notes for its coding agents describe it: it follows velocity commands with some lag and wobble, so read the pelvis pose and close the loop rather than dead-reckon; a planar speed command below 0.055 m/s means standing still (use 0 or at least 0.06); standing still, the base drifts a few centimetres, and further while the hands push on furniture or the torso leans far (measured here: 0.27 m and 15 degrees with the hands pressing on a cabinet, 0.11 m and 24 degrees from a 0.8 rad lean); heights above about 0.8 m lock the knees (the pelvis stays near 0.78 m); squatting (a lower height) is how the hands reach low objects, and while squatting the controller does not step: walk first, then squat in place. It keeps the robot balanced but does not stop it from walking into things.
