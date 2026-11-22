# BiGym 2.0 · pick-box (privileged)

## Task
A simulated Unitree G1 humanoid robot with two-finger grippers (BiGym 2.0, MuJoCo). NVIDIA's GR00T whole-body
controller, a learned policy that runs inside every control step, drives the legs and waist and keeps the robot
balanced: you command where it walks, how high its pelvis is, how far its torso leans forward, its arm joints and its
grippers. At the start the cardboard box stands on a low side table, about 1.3 m away, 52° to your right, 0.62 m above
the floor; the front edge of the kitchen counter's top is about 0.7 m away, straight ahead, 0.71 m above the floor.
(Distances are from your pelvis along the floor, directions from the way you face, heights above the floor; measured on
this scene.) Pick the cardboard box up from the side table and gently set it down on the kitchen counter. The scene is
one fixed instance. You have the full simulator to develop with; you hand in a trajectory of whole-body commands.

## Goal
Success: the box rests on the kitchen counter's top, let go, for a second. An object counts as held while a finger of a
gripper touches it: an open gripper still resting against it holds it. The episode ends as soon as the success has held
for a second; it also ends when the pelvis gets more than 10 m from the scene's origin, on a physics error, and after
4400 control steps (88 s at 50 Hz). A fall (the pelvis tipping far over, or dropping low) makes the episode a failure
without ending it.

Deliverable: three files under `/app/output/`; only the first is scored. `trajectory.npz`: the trajectory, written with
`s.save_trajectory(rows)`: `actions`, one row of 21 floats per control step, at most 4400 rows (rows after the episode's
end are ignored); it is replayed open-loop from the frozen instance, one row per step until the episode ends, and scores
1 if the replay succeeds. `gen.py`: the script that produced it; it must run and reproduce `trajectory.npz`, reading
nothing but `/app/instance.json` and files under `/app/output/`. `NOTES.md`: at most 20 lines: your final approach and
why it works, and the approaches that failed and what each told you. The tooling appends its own log,
`rcb_session_log.jsonl`, to `/app/output/`: leave it there and do not set `RCB_SESSION_LOG`. Save a valid trajectory
early and overwrite it (with `gen.py` and `NOTES.md` to match) when you have a better one.

Rules: write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
Only the trajectory's rows count: anything else you change in the simulator while you develop changes nothing in the
replay.

## Robot Interface
### Session
`rcb_bigym2` (installed; run `python` from any directory):
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
s.replay(rows)                         # replays from the start, as graded: {"success", "state_sha", ...}
s.save_trajectory(rows)                # writes the scored file /app/output/trajectory.npz; pass another path to explore
```

The simulator is deterministic on the CPU: the same rows from the frozen instance give the same state, so a trajectory
you generate closed-loop replays exactly. The BiGym package (`bigym`) is installed; its documentation and source are in
the package.

### Actions
Action type `whole_body`: rows of 21 floats in physical units, one per control step (0.02 s), in this order: `vx` (0):
walking velocity command, forward (m/s, the robot's frame), in [-1, 1]; `vy` (1): walking velocity command, to the left
(m/s), in [-1, 1]; `height` (2): pelvis height command (m), in [0.4, 1]; `wz` (3): turning rate command, + turns left
(rad/s), in [-1, 1]; `pitch` (4): torso lean command, + leans forward (rad), in [-0.2, 0.8]; 5-11: the left arm's 7
joints, 12-18: the right arm's, each in the order shoulder pitch, shoulder roll, shoulder yaw, elbow, wrist roll, wrist
pitch, wrist yaw: absolute joint targets (rad), bounds shoulder pitch [-3.0892, 2.6704], shoulder roll [-1.5882,
2.2515], shoulder yaw [-2.618, 2.618], elbow [-1.0472, 2.0944], wrist roll [-1.9722, 1.9722], wrist pitch [-1.6144,
1.6144], wrist yaw [-1.6144, 1.6144] (the same for both arms); `left_gripper` (19) and `right_gripper` (20): 0 open .. 1
closed, in [0, 1]. Values outside the bounds are clipped. The row that stands still at the start: zeros but `height`
0.74, `left_gripper` 0.6, `right_gripper` 0.6. `right_shoulder_roll_joint`'s bounds are BiGym's action bounds, not the
joint's own range [-2.2515, 1.5882]: a command outside them is clipped.

### Observations
`s.status()`, `s.task` (BiGym's task env: its props and `s.task.robot`), `s.model` / `s.data` (MuJoCo) and
`s.held(prop)` read the full state; `s.image(camera, w, h)` renders an onboard camera (`head`, `left_wrist`,
`right_wrist`).

## Others
- The whole-body controller: it follows velocity commands with some lag and wobble, so read the pelvis pose and close
  the loop rather than dead-reckon; a planar speed command below 0.055 m/s means standing still (use 0 or at least
  0.06); standing still, the base drifts a few centimetres, and further while the hands push on furniture or the torso
  leans far (measured here: 0.27 m and 15 degrees with the hands pressing on a cabinet, 0.11 m and 24 degrees from a 0.8
  rad lean); heights above about 0.8 m lock the knees (the pelvis stays near 0.78 m); squatting (a lower height) is how
  the hands reach low objects, and while squatting the controller does not step: walk first, then squat in place. It
  keeps the robot balanced but does not stop it from walking into things.
- To check a trajectory the way it is graded, replay it from the command line:
  `python /opt/tools/rcb_bigym2.py replay --instance /app/instance.json --traj /app/output/trajectory.npz --out /tmp/r.json`.
- On the G1, BiGym's `pinch_position` (a gripper's "pinch site") is the wrist link's origin, 0.148 m behind the finger
  pads; the point between the pads is the `left_end_effector` / `right_end_effector` site (`wrist_position`).

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
- Resources: 8 CPUs, 13 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  one GPU (5 GiB of its memory). Over a cap a process can be killed (the CPU cap only slows you down); usage:
  `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
