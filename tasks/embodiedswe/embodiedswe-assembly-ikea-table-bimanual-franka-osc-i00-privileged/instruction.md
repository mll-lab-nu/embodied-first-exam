# Screw the four legs onto a side table (two Frankas, operational-space control)

You are in a container with NVIDIA Isaac Sim 5.1 / Isaac Lab 2.3.2 and EmbodiedSWE's robot benchmark package
(`robobench`, at `/opt/embodiedswe`, already on `PYTHONPATH`; read its source freely: scenes, robots, controllers).
An NVIDIA GPU is available. Your job: write a program that completes the task below, and leave it in
`/app/output/solution/`.

## The task

An IKEA-style side table, partly assembled, lying on a sturdy waist-high workbench. The free-standing tabletop slab (~0.55 x 0.55 m, 5 cm thick) carries 4 upright threaded studs at its corners (xy = (+0.25, +0.25), (-0.25, +0.25), (+0.25, -0.25), (-0.25, -0.25) m, relative to the slab centre). 4 loose legs — each a threaded nut on a graspable cylindrical shaft — lie on their side in a row near the centre of the workbench, ready to be picked up and fitted.
Goal: screw every leg down onto its stud (turn it clockwise while pressing down) until it seats. A seated leg locks in place. The table is assembled once all 4 legs are seated.

2 robots operating in the same workspace as one composite embodiment. The action vector is their actions concatenated in order ('left' dims [0:8), 'right' dims [8:16); total 16).
[left] A Franka Emika Panda arm with a parallel-jaw gripper, fixed to the table. Control mode 'osc': 7 arm joints by operational-space control (joint torque); the action is 6 end-effector pose deltas, plus 2 gripper fingers by direct position target. Action dim 8.
[right] A Franka Emika Panda arm with a parallel-jaw gripper, fixed to the table. Control mode 'osc': 7 arm joints by operational-space control (joint torque); the action is 6 end-effector pose deltas, plus 2 gripper fingers by direct position target. Action dim 8.

The task is complete when `env.scene.success()` is true for the env (a `(num_envs,)` bool tensor) at the end of the
graded run.
That is the verdict. Partial progress toward it is also recorded (EmbodiedSWE's rubric for this task, reported
as `progress`), but only success counts as solved.

## The environment

The env is EmbodiedSWE's `assembly.ikea_table.bimanual_franka.osc` preset: one environment (`num_envs = 1`), built with seed 0 and PhysX on the
GPU (`device="cuda:0"`, as EmbodiedSWE grades; grading uses the same build). Build it exactly as grading does:

```python
import sys; sys.path.insert(0, "/opt/efe")
from rcb_embodiedswe import make_env
env = make_env()        # launches Isaac Sim headless first, then builds and resets the env from /app/instance.json
```

`make_env()` compares the start state with the frozen instance of this task (`/app/instance.json`). In development
anything goes: reset it, restore states, read anything, make cameras, run many processes. `env.step(action)` takes a
`(1, 16)` tensor; one step is 0.066667 s of simulated time. `env.describe()`, `env.describe_stage()`, the
scene's and the robot's own methods and the source under `/opt/embodiedswe` tell you the rest.

This robot is bimanual: `env.robot.articulation` is `None`. Each arm is reached through
`env.robot.robots['left']` and `env.robot.robots['right']` (their articulations, bodies and joints), and
`env.robot.action_slices` says which part of the action vector drives which arm.

Action range. In each arm's 8-value slice, the first 6 values are end-effector pose deltas in action units
(x 0.02 m for position, x 0.097 rad for rotation). As in EmbodiedSWE, the controller scales them by these
factors and does not clip them (a larger value is a larger step); it clamps each joint torque to 100 N·m.
The 2 finger values of each slice are finger position targets in metres
(0 closed, 0.04 open); the joint limits bound them.

## Deliverable

The whole folder `/app/output/solution/`. Its entry point is `/app/output/solution/solve.py`, exposing

```python
def solve(env) -> None:
    ...
```

Everything else in the folder ships with it (helper modules, calibration data); nothing outside it does. At grading
time `solve.py`'s directory is on the import path, so sibling imports and files read relative to `__file__` work.
Only regular files count (no symbolic links); at most 20,000 files and 2 GiB.

## How it is graded

A fresh simulator, in a separate container, builds this env from the same frozen instance and resets it; that
simulator process is not yours. Your `solve.py` is imported and run in **another process**, as an unprivileged user,
with no network and no GPU, and receives a proxy `env` that forwards to the simulator:

- reading works as in development, but returns copies: `env.scene.<...>.data.root_pos_w` gives a CPU tensor, a list of
  assets gives proxies of them, and calling a method that only reads (`env.scene.success()`, `env.describe()`,
  `env.get_states()`, the scene's and robot's query methods) returns its result;
- `env.step(action)` steps the simulator; this is the only way your program changes anything;
- everything else is refused with `PermissionError`: `env.reset()`, `env.set_states(...)`, `env.sim.step()`, any
  `write_*` / `set_*` / `reset*` method of an asset, any method of the scene or the robot that is not one of their
  queries (state, progress and geometry reads such as `success()`, `seated()`, `get_state()`), assigning attributes,
  and private or `__dunder__` attributes. Modifying a tensor you read changes only your copy.
- if `env.step(action)` raises (the env cannot take that action, e.g. the controller hits a singular pose), the
  error is raised in `solve`, as in EmbodiedSWE: the run goes on if `solve` handles it, and otherwise ends
  there, with the verdict read on the state at that moment.

What `solve.py` can use in the graded run. Its process has **no simulator and no Isaac Sim app**; it is
sandboxed (Landlock) and sees only its own files:

- it can import the Python standard library, `numpy`, `torch` (CPU only; 4 threads), `scipy`, `pinocchio` and
  `pink`, the pure-Python parts of `robobench` that import no Isaac module, and your own modules in
  `solution/`; it can read the files in `solution/` (relative to `__file__`) and the installed packages;
- it cannot import `isaaclab`, `isaacsim`, `omni` or `pxr` (they need the running app; `isaaclab.utils.math`
  included: copy the few quaternion helpers you need into your folder), and calling the robot's controller
  objects through the proxy is refused like any other non-read;
- it can write only to its own scratch directory (`$TMPDIR`, also its working directory and `$HOME`), not to
  `solution/`; it sees no other process, no `/tmp`, no `/app`, and has no network;
- it can start subprocesses (at most 512 processes in all); every one of them is ended with it.

Keep module level light: no simulator launch or env build at import time (a `if __name__ == "__main__":` block that
builds an env with `make_env()` and calls `solve(env)` is a good pattern for development).

The graded run has **30 minutes** of wall-clock time, counted from the start of the grading process: the
simulator's start-up and the import of `solve.py` count (as in EmbodiedSWE). It ends when `solve` returns or raises,
its process ends, or the 30 minutes are up; every process it started is then ended, and the verdict is read on the
state at that moment (a crash or a hang is not retried). That verdict is the run's result: success = the task's
success predicate on that state, progress = EmbodiedSWE's rubric score. Every action is recorded, with the scene's
state every few steps; the video poses those recorded states afterwards and does not change the verdict.

## Checkpoints

As in EmbodiedSWE, you can freeze checkpoints while you work:

```
submit "a short note"
```

copies `/app/output/solution/` as it is now to `/app/output/submissions/NNNNNN/` (with a receipt, `submission.json`).
At most **64** checkpoints; the final `/app/output/solution/` is graded as well. Every distinct checkpoint and the
final folder are each graded in their own fresh simulator, exactly as above (30 minutes each); identical copies are
graded once. The result is the one with the highest progress; a tie goes to the one with success, then to the
earliest (the final folder counts as the last). Its success is the verdict. Do not edit `/app/output/submissions/`
by hand: a checkpoint whose files no longer match its receipt scores 0. Leaving the best version in `solution/`
is enough; checkpoints are a safety net for versions you might break later.

Rules of the graded run (they hold whatever the proxy lets through): change the world only by stepping forward with
`env.step`; never reset, restore states, move objects, modify physics, the task, the scene or the robot's controller,
or reach the grading code or its files.

Test the graded path itself before you finish:

```
python /opt/efe/rcb_embodiedswe.py check --solution /app/output/solution
```

runs your folder exactly as grading does (a fresh simulator, your `solve` as an unprivileged process behind the
proxy, the same 30-minute limit from the process's start) and prints, as its last line, a JSON summary with
`success`, `n_actions`, `solve_status`, `boot_s` and the proxy's refusals (it takes a few minutes: one Isaac Sim
launch plus your rollout).

## Practical notes

- The first Isaac Sim launch in the container takes a few minutes (shader cache); later ones are faster. Run long
  jobs in the background and poll their logs. Kit sometimes hangs on exit: `os._exit(0)` after your script has
  written its results is fine.
- Every Python process starts from a fresh simulator; nothing carries over between scripts.
- Physics runs on the GPU. Do not count on a recorded action sequence repeating exactly: the grading machine's GPU
  may be another model than yours, and drawing frames between steps changes later physics in some scenes. A
  closed-loop solve that reads the state and reacts is robust to both; the proxy adds a little time per call
  (about 0.05 ms per read or step request, measured), so reading state every step is fine.
- You can look at the scene: add a camera (`make_env(cameras=True)`, then Isaac Lab's `Camera`), save frames to PNG
  and look at the images themselves. The graded run draws nothing, so judge a solution by `check`, not by a
  rendered run.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resources
Your container: **8 CPUs**, **29 GiB of memory**, **16384 processes and threads**, **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`) and **one GPU, 16 GiB of its memory**. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 14400 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
