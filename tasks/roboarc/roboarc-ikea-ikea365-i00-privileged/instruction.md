# IKEA MuJoCo · IKEA 365+ serving stand — frozen scene

You control a simulated robot (**two 7-DoF Franka Panda arms, each with the MuJoCo Menagerie Panda hand (two-finger, tendon-coupled)**; plain MuJoCo 3.14.0 on the CPU, float64) via Python.
**Task:** Rebuild the IKEA 365+ serving stand: take the screw out of member A and park it, lay member B across member A, bring the screw back and screw it in through both members until it seats, turn the stand over, and place the bowl on it.

## Success requirements

- The seven operations are accepted in this order: remove the screw, park the screw, cross the members, return the screw, reinstall the screw, turn the stand, place the bowl.
- At the end the screw is retained in member A and aligned with its seated pose relative to both members, and member B is retained and aligned with member A (gates: axial 0.1 mm, lateral 0.6 mm, axis 1.5 degrees; member B may be rotated 180 degrees).
- Released and settled: no robot contact with any part, every part slower than 0.025 m/s, the bench carries the parts; the bowl touches the members and member A is turned over (its z axis pointing down).
- A support probe on a copy of the final state: the bench must carry the whole weight, and the weight plus a 2 N downward test load on member A (the grader applies it; it never acts during your episode), with the arms holding their last commands.

The benchmark's terminal rules, the same in every IKEA MuJoCo task, come on top of these requirements. When your rows end: (1) the requirements above hold; (2) the parts are released: no robot link touches any part; (3) every part is at rest: at most 0.01 m/s and 0.05 rad/s; (4) the simulation never broke down: no non-finite state, no MuJoCo BADQACC / BADQPOS / BADQVEL warning, no contact of a part deeper than 10 mm, at any time. The grader then holds your last row for 1.0 s more and requires (1)-(4) again at its end.

The requirements are the scene's own `success.py` (`/opt/ikea/scenes/ikea365/success.py`); the terminal rules are the
tooling's (`rcb_ikea.py`, `Session.final_check()`). `s.status()` checks all of it on the current state
(`"goal"` = success.py, `"released"`, `"at_rest"`, `"breakdown"`, `"report"` = success.py's details);
`s.final_check()` is the grader's verdict on your rows (the current state, then the 1.0 s hold).

## Physics and mechanism

- Parts move only through contact with the robot, gravity and the scene's own mechanism. The M4 x 0.5 thread is exact convex pieces: the screw advances only by being turned. Two retention welds (screw to member A, member B to member A) switch on with the current relative pose once the reinstalled screw is seated.
- Grasps are physical: friction from the finger contacts. Nothing attaches a part to a gripper, and there is no assist.
- The scene (model, solver settings, mechanism) is frozen. The grader builds its own copy; changing the model or the
  scene files in your container has no effect on the grade.

This is a *fixed scene*: the parts and the robot start in the same state at every reset (the scene's keyframe `home`).
You may reset and retry as many times as you want, read any simulator state, and save and restore states. Your
deliverable is **one replayable trajectory**, not a general policy.

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below).
It is replayed open-loop from the same initial state in a fresh process, twice, and scored 1 if both replays pass
`final_check()` (the requirements and the terminal rules at the end of your rows and after the 1.0 s hold) and end in
the same state, else 0. Also leave the script that
produced it at `/app/output/gen.py`. Save a real trajectory as soon as practical and keep saving progress; do not stop
early.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_ikea import Session
s = Session("ikea365")                   # builds the frozen scene /opt/ikea/scenes/ikea365 (scene.py load())
s.model, s.data                       # the MuJoCo MjModel / MjData (privileged: read anything; mujoco is importable)
s.S                                   # the scene object: s.S.mech (mechanism state), s.S.success(), s.S.task (task.json)
s.actuators                           # the 16 actuator names, in action order
s.step(row)                           # one control tick: data.ctrl[:] = s.applied(row) (ctrlrange + speed rule), 4 physics steps (+ the mechanism)
s.run(rows)                           # several ticks
s.hold_action()                       # the current ctrl row (repeating it holds the targets)
s.status()                            # {'success', 'goal', 'released', 'at_rest', 'breakdown', 'rows', 'state_sha', 'report', ...}
s.final_check()                       # the grader's verdict: status() now and after holding the last row 1.0 s (state restored)
st = s.get_state(); s.set_state(st)   # save / restore: physics, mechanism and monitor state, and the rows recorded so far
s.reset()                             # a fresh build of the scene: exactly the grader's initial state; clears the rows
s.replay(rows)                        # reset, replay open-loop, return final_check()  -> use this to self-check
s.save_trajectory(path="/app/output/trajectory.npz")   # the rows recorded since the last reset (or pass rows)
```
Scene details: `/opt/ikea/scenes/ikea365/` (scene.py, task.json, layout.json, success.py, the mechanism modules, scene.xml).
There is no planner or skill library: inverse kinematics, grasping, screwing and every other skill are yours to build
(MuJoCo's Jacobians, `mujoco.mj_jacSite`, and saved states make that practical).

CLI equivalent of the grader's replay (one replay):
`python /opt/tools/rcb_ikea.py replay --task ikea365 --traj /app/output/trajectory.npz`

## Conventions
- Action: one row of 16 actuator controls per control tick, float64: per arm (`left_`, then `right_`): `actuator1`..`actuator7` = joint position targets (rad; joint 7, the wrist, has no joint limit in these scenes, unlike the real Panda), `actuator8` = gripper command (0 = closed, 255 = open; the hand squeezes at its tendon force limit, about 70 N per finger, at any width when commanded 0). Out-of-range values are
  clamped to each actuator's ctrlrange. Speed rule (the robot's real limits; clamp, not fail; `rcb_ikea.JOINT_SPEED_LIMITS_RAD_S`): each arm joint target moves at most 0.0054375 rad per control tick on joints 1-4 (`actuator1`..`actuator4`: 2.175 rad/s) and 0.006525 rad on joints 5-7 (`actuator5`..`actuator7`: 2.61 rad/s), the Franka Panda's joint velocity limits, from the target applied on the previous tick; a target that asks for more is moved by the limit only (`Session.applied()`, in `s.step` and in the grader's replay alike), so a fast row is spread over the ticks after it. A row within the limit (+1e-9) is applied unchanged. The gripper command is not limited. The arms are position servos; the actuators'
  gains and force limits are in the model.
- Trajectory file: `ctrl` (N, 16) float64, `substeps` = 4, `timestep` = 0.000625 (what `save_trajectory`
  writes). Each row is applied for 4 physics steps of 0.625 ms: a 2.5 ms control tick (400 Hz).
  At most 495000 rows (1237.5 s of simulated time): the grader refuses a longer trajectory (`bad_trajectory`), because its replays must fit the verifier's time limit. One control tick takes about 4.0 ms of wall clock here: budget your experiments against the
  time limit (`## Time limit`).
- World frame: MuJoCo's, +z up, metres; quaternions are MuJoCo's **WXYZ**. Tool frames (sites): `left_tcp` / `right_tcp` (between the fingertips).
- The episode does not end on success: the grader checks once, after your last row and again after the 1.0 s hold.
  End your rows with the parts released, the arms clear of them and everything at rest.
- One `Session` per process (the scene's modules are imported once).

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 10800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
