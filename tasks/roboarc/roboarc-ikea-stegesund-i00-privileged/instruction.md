# IKEA MuJoCo · STEGESUND roll stand (privileged)

## Task
Build the STEGESUND roll stand: press half B onto half A at the two leg crossings, push the shelf in from the foot end,
drive the four bolts through the legs into the shelf's rail ends with the hex key, stand the frame up and drop the top
rod into the two crotches. Then let go of everything and move both arms clear.

## Goal
Success: the stand is assembled and upright: half B on half A at both crossings, the shelf in, all four bolts driven
home and the top rod lying in the two crotches; no arm touches any part and everything is still. Forcing parts deep into
each other breaks the simulation and ends the episode at once, without success. What counts is how things stand after
the last action of your trajectory, replayed from the fixed start. After your last row the grader holds it for 1 s more
and requires all of this again: end your rows with the parts released, the arms clear of them and everything at rest.

Deliverable: `/app/output/trajectory.npz`, written with `s.save_trajectory()`: `ctrl` (N, 16) float64, `substeps` = 4,
`timestep` = 0.000625, at most 714,000 rows (a longer one is refused). Leave the script that produced it at
`/app/output/gen.py`. It is replayed once from the fixed start; `s.final_check()` gives the grader's verdict on the
state now. Save a valid one early and overwrite it when you have a better one.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed.

## Robot Interface
Two 7-DoF Franka Panda arms, each with the MuJoCo Menagerie Panda hand (two-finger, tendon-coupled), at a table
(RoboARC's IKEA furniture-assembly suite, MuJoCo). The scene is one fixed instance. You have the full simulator to
develop with; you hand in a trajectory of robot actions.

### Session
`/opt/tools/rcb_ikea.py`, importable as `rcb_ikea`:
```python
from rcb_ikea import Session
s = Session("stegesund")                   # builds the frozen scene /opt/ikea/scenes/stegesund (scene.py load())
s.model, s.data                       # the MuJoCo MjModel / MjData (privileged: read anything; mujoco is importable)
s.S                                   # the scene object: s.S.mech (mechanism state), s.S.success(), s.S.task (task.json)
s.actuators                           # the 16 actuator names, in action order
s.step(row)                           # one control tick: data.ctrl[:] = s.applied(row) (ctrlrange + speed rule), 4 physics steps (+ the mechanism)
s.run(rows)                           # several ticks
s.hold_action()                       # the current ctrl row (repeating it holds the targets)
s.status()                            # {'success', 'goal', 'released', 'at_rest', 'breakdown', 'rows', 'state_sha', 'report', ...}
s.final_check()  # the grader's verdict: status() now and after holding the last row 1.0 s (state restored)
st = s.get_state(); s.set_state(st)   # save / restore: physics, mechanism and monitor state, and the rows recorded so far
s.reset()                             # a fresh build of the scene: exactly the grader's initial state; clears the rows
s.replay(rows)                        # reset, replay open-loop, return final_check()  -> use this to self-check
s.save_trajectory(path="/app/output/trajectory.npz")   # the rows recorded since the last reset (or pass rows)
```

- Scene details: `/opt/ikea/scenes/stegesund/` (scene.py, task.json, layout.json, the mechanism modules, scene.xml).
- There is no planner or skill library: inverse kinematics, grasping, screwing and every other skill are yours to build
  (MuJoCo's Jacobians, `mujoco.mj_jacSite`, and saved states make that practical).
- One `Session` per process (the scene's modules are imported once).
- The grader replays with this command (run it to self-check):
  `python /opt/tools/rcb_ikea.py replay --task stegesund --traj /app/output/trajectory.npz`

### Actions
- Action: one row of 16 actuator controls per control tick, float64: per arm (`left/`, then `right/`):
  `actuator1`..`actuator7` = joint position targets (rad; joint 7, the wrist, has no joint limit in these scenes, unlike
  the real Panda), `actuator8` = gripper command (0 = closed, 255 = open; the hand squeezes at its tendon force limit,
  about 70 N per finger, at any width when commanded 0). Out-of-range values are clamped to each actuator's ctrlrange.
  Speed rule (the robot's real limits; clamp, not fail; `rcb_ikea.JOINT_SPEED_LIMITS_RAD_S`): each arm joint target
  moves at most 0.0054375 rad per control tick on joints 1-4 (`actuator1`..`actuator4`: 2.175 rad/s) and 0.006525 rad on
  joints 5-7 (`actuator5`..`actuator7`: 2.61 rad/s), the Franka Panda's joint velocity limits, from the target applied
  on the previous tick; a target that asks for more is moved by the limit only (`Session.applied()`, in `s.step` and in
  the grader's replay alike), so a fast row is spread over the ticks after it. A row within the limit (+1e-9) is applied
  unchanged. The gripper command is not limited. The arms are position servos; the actuators' gains and force limits are
  in the model.
- Each row is applied for 4 physics steps of 0.625 ms: a 2.5 ms control tick (400 Hz). One control tick takes about 4.2
  ms of wall clock here: budget your experiments.
- World frame: MuJoCo's, +z up, metres; quaternions are MuJoCo's **WXYZ**. Tool frames (sites): `left/tcp` / `right/tcp`
  (between the fingertips).

### Grasping
- Grasps are physical: only the friction of the finger contacts holds a part; nothing attaches it to a gripper.

## Others
- A bolt goes in only by being turned with the hex key; once its head is home, the bolt and the half it clamps lock to
  the shelf. The leg crossings are held by friction only.

## Limits
- Time: 10800 s of wall-clock time from the start of your session; everything counts (the simulator's start-up too). At
  the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 4 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU. Over a cap a process can be killed (the CPU cap only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`; `s.get_state()` / `s.set_state()` save and restore states).
