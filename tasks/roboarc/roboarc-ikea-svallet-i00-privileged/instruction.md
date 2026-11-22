# IKEA MuJoCo · SVALLET work lamp (privileged)

## Task
Two 6-DoF ViperX 300 s arms (MuJoCo Menagerie ALOHA), each with its own parallel gripper, at a table (RoboARC's IKEA
furniture-assembly suite, MuJoCo). Press the lamp shade's key down into the socket on top of the stand column until the
spring jaw snaps over it, then screw the E12 bulb up into the shade's socket until it seats. The scene is one fixed
instance. You have the full simulator to develop with; you hand in a trajectory of robot actions.

## Goal
Success: the shade's key is pressed into the socket on top of the stand column with the spring jaw snapped over it, and
the bulb is screwed fully up into the shade's socket; the stand rests upright on the bench as it started, the robot
touches no lamp part, and everything is at rest. Do not force parts into one another: a simulator breakdown (parts
pressed deep into each other) ends the episode at once, without success. What counts is how things stand after the last
action of your trajectory, replayed from the fixed start: a success reached earlier and lost by the end does not count.
After your last row the grader holds it for a second more and requires all of this again: end your rows with the parts
released, the arms clear of them and everything at rest.

Deliverable: `/app/output/trajectory.npz`, written with `s.save_trajectory()`: `ctrl` (N, 14) float64, `substeps` = 4,
`timestep` = 0.000625, at most 449,000 rows (a longer one is refused). Leave the script that produced it at
`/app/output/gen.py`. It is replayed once from the fixed start; `s.final_check()` gives the grader's verdict on the
state now. Save a valid one early and overwrite it when you have a better one.

Rules: write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
Only the actions count: changing the simulator's state, the model or the scene files while you develop changes nothing
in the replay.

## Robot Interface
### Session
`/opt/tools/rcb_ikea.py`, importable as `rcb_ikea`:
```python
from rcb_ikea import Session
s = Session("svallet")                   # builds the frozen scene /opt/ikea/scenes/svallet (scene.py load())
s.model, s.data                       # the MuJoCo MjModel / MjData (privileged: read anything; mujoco is importable)
s.S                                   # the scene object: s.S.mech (mechanism state), s.S.success(), s.S.task (task.json)
s.actuators                           # the 14 actuator names, in action order
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

- Scene details: `/opt/ikea/scenes/svallet/` (scene.py, task.json, layout.json, the mechanism modules, scene.xml).
- There is no planner or skill library: inverse kinematics, grasping, screwing and every other skill are yours to build
  (MuJoCo's Jacobians, `mujoco.mj_jacSite`, and saved states make that practical).
- One `Session` per process (the scene's modules are imported once).
- The grader replays with this command (run it to self-check):
  `python /opt/tools/rcb_ikea.py replay --task svallet --traj /app/output/trajectory.npz`

### Actions
- Action: one row of 14 actuator controls per control tick, float64: per arm (`left_`, then `right_`): `waist`,
  `shoulder`, `elbow`, `forearm_roll`, `wrist_angle`, `wrist_rotate` = joint position targets (rad; `wrist_rotate`
  unlimited), `gripper` = finger rail position target (0.002 m closed .. 0.037 m open). Out-of-range values are clamped
  to each actuator's ctrlrange. Speed rule (the robot's real limits; clamp, not fail;
  `rcb_ikea.JOINT_SPEED_LIMITS_RAD_S`): each arm joint target moves at most 0.00785397 rad per control tick on every arm
  joint (3.14159 rad/s, the ViperX 300 s joint velocity limit), from the target applied on the previous tick; a target
  that asks for more is moved by the limit only (`Session.applied()`, in `s.step` and in the grader's replay alike), so
  a fast row is spread over the ticks after it. A row within the limit (+1e-9) is applied unchanged. The gripper command
  is not limited. The arms are position servos; the actuators' gains and force limits are in the model.
- Each row is applied for 4 physics steps of 0.625 ms: a 2.5 ms control tick (400 Hz). One control tick takes about 4.4
  ms of wall clock here: budget your experiments.
- World frame: MuJoCo's, +z up, metres; quaternions are MuJoCo's **WXYZ**. Tool frames (sites): `left_gripper` /
  `right_gripper` (between the fingertips).

## Others
- The shade's barb pushes a spring jaw open, which snaps back over it. The bulb's thread (right-hand, 1.5 mm pitch)
  advances only by turning and seats on the socket's stop; both connections lock once seated. The cable is not modelled.
- Parts move only through contact with the robot, gravity and the scene's own mechanism.
- Grasps are physical: only the friction of the finger contacts holds a part; nothing attaches it to a gripper.

## Limits
- Time: 10800 s of wall-clock time from the start of your session; everything counts (the simulator's start-up too). At
  the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 4 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU. Over a cap a process can be killed (the CPU cap only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`; `s.get_state()` / `s.set_state()` save and restore states).
