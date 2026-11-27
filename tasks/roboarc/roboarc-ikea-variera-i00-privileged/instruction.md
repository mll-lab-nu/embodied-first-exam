# IKEA MuJoCo · VARIERA shelf insert (privileged)

## Task
Assemble the VARIERA shelf insert: set up the two side frames, lower the shelf onto them, and screw the four screws
through the shelf holes into the frames until they seat. Then let go of everything and move both arms clear.

## Goal
Success: the four screws are screwed in (turned, not just pushed) through the shelf holes into four different holes in
the frames and seated; the frames stand lined up under the shelf, the insert stands on the bench on its own, no arm
touches it and everything is still. Forcing parts deep into each other breaks the simulation and ends the episode at
once, without success. Your trajectory is replayed from the fixed start. What counts is the state after its last action.
After your last row the grader holds it for 1 s more and requires all of this again: end your rows with the parts
released, the arms clear of them and everything at rest.

Deliverable: `/app/output/trajectory.npz`, written with `s.save_trajectory()`: `ctrl` (N, 16) float64, `substeps` = 4,
`timestep` = 0.000625, at most 463,000 rows (a longer one is refused). Leave the script that produced it at
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
s = Session("variera")                   # builds the frozen scene /opt/ikea/scenes/variera (scene.py load())
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

- Scene details: `/opt/ikea/scenes/variera/` (scene.py, task.json, layout.json, the mechanism modules, scene.xml).
- There is no planner or skill library: inverse kinematics, grasping, screwing and every other skill are yours to build
  (MuJoCo's Jacobians, `mujoco.mj_jacSite`, and saved states make that practical).
- One `Session` per process (the scene's modules are imported once).
- The grader replays with this command (run it to self-check):
  `python /opt/tools/rcb_ikea.py replay --task variera --traj /app/output/trajectory.npz`

### Actions
- Action: one row of 16 actuator controls per control tick, float64: per arm (`left_`, then `right_`):
  `actuator1`..`actuator7` = joint position targets (rad; joint 7, the wrist, has no joint limit in these scenes, unlike
  the real Panda), `actuator8` = gripper command (0 = closed, 255 = open). Commanded 0, the hand squeezes at its tendon
  force limit, about 70 N per finger, at any width. Out-of-range values are clamped to each actuator's ctrlrange. Speed
  rule (the robot's real limits; clamp, not fail; `rcb_ikea.JOINT_SPEED_LIMITS_RAD_S`): from the target applied on the
  previous tick, each arm joint target moves at most 0.0054375 rad per control tick on joints 1-4
  (`actuator1`..`actuator4`: 2.175 rad/s) and 0.006525 rad on joints 5-7 (`actuator5`..`actuator7`: 2.61 rad/s). These
  are the Franka Panda's joint velocity limits. A target that asks for more is moved by the limit only, so a fast row is
  spread over the ticks after it. This holds in `s.step` and in the grader's replay alike (`Session.applied()`). A row
  within the limit (+1e-9) is applied unchanged. The gripper command is not limited. The arms are position servos; the
  actuators' gains and force limits are in the model.
- Each row is applied for 4 physics steps of 0.625 ms: a 2.5 ms control tick (400 Hz). One control tick takes about 16.6
  ms of wall clock here: budget your experiments.
- World frame: MuJoCo's, +z up, metres; quaternions are MuJoCo's **WXYZ**. Tool frames (sites): `left_tcp` / `right_tcp`
  (between the fingertips).

### Grasping
- Grasps are physical: only the friction of the finger contacts holds a part; nothing attaches it to a gripper.

## Others
- A screw goes in only by being turned. Nothing else holds the parts together.

## Limits
- Time: 10800 s of wall-clock time from the start of your session. Everything counts, including the simulator's
  start-up. At the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time
  left: `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). A call into a long-running process can block for
  its whole wait time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, including the simulator's and the benchmark's source.
- Resources: 4 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU. Going over a cap can get a process killed (the CPU cap only slows you down). Usage: `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`; `s.get_state()` / `s.set_state()` save and restore states).
