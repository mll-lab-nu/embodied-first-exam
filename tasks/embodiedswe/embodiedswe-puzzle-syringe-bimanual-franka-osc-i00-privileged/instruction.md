# EmbodiedSWE · draw and dose liquid with a syringe, two Frankas (privileged)

## Task
Fill the syringe from the beaker, put about a third of a syringe into each of the three test tubes, then lay the syringe
back down where it was on the shelf.

## Goal
Success: the syringe was filled nearly full from the beaker; each of the three tubes got between about a quarter and two
fifths of a full syringe; and the syringe now lies back at its starting spot on the shelf, roughly flat and at rest.
What counts is how things stand when the graded run of your program ends. Only success counts as solved; partial
progress (EmbodiedSWE's rubric for this task, `progress`) is recorded too and ranks your checkpoints.

Deliverable: the folder `/app/output/solution/`. Its entry point, `/app/output/solution/solve.py`, defines
`def solve(env) -> None`, which the graded run calls once (Robot Interface). Everything else in the folder ships with it
(helper modules, calibration data); nothing outside it does. At grading time `solve.py`'s directory is on the import
path, so sibling imports and files read relative to `__file__` work. Only regular files count (no symbolic links); at
most 20,000 files and 2 GiB. Keep module level light: no simulator launch or env build at import time (a
`if __name__ == "__main__":` block that builds an env with `make_env()` and calls `solve(env)` is a good pattern for
development). Save a valid one early and overwrite it when you have a better one.

Checkpoints, as in EmbodiedSWE: `submit "a short note"` copies `/app/output/solution/` as it is now to
`/app/output/submissions/NNNNNN/` (with a receipt, `submission.json`). At most 64 checkpoints; the final
`/app/output/solution/` is graded as well. Every distinct checkpoint and the final folder are each graded in their own
fresh simulator, as in the graded run (Robot Interface; 30 minutes each); identical copies are graded once. The result
is the version with the highest progress. On a tie, the one with success wins; if still tied, the earliest wins (the
final folder counts as the last). That version's success is the verdict. Do not edit `/app/output/submissions/` by hand:
a checkpoint whose files no longer match its receipt scores 0. Leaving the best version in `solution/` is enough;
checkpoints are a safety net for versions you might break later.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed. In the graded run, whatever the proxy lets through,
change the world only by stepping forward with `env.step`. Never reset, restore states, move objects, modify physics,
the task, the scene or the robot's controller, and never reach the grading code or its files.

## Robot Interface
Two Franka Emika Panda arms with parallel-jaw grippers, fixed to the table. You have the full simulator to develop with;
you hand in a program that completes the task (`/app/output/solution/`).

### Session
The env is EmbodiedSWE's `puzzle.syringe.bimanual_franka.osc` preset: one environment (`num_envs = 1`), seed 0, PhysX on
the GPU (`device="cuda:0"`), the same build as in grading. Build it as grading does (`/opt/efe/rcb_embodiedswe.py`):
```python
import sys; sys.path.insert(0, "/opt/efe")
from rcb_embodiedswe import make_env
env = make_env()        # launches Isaac Sim headless first, then builds and resets the env from /app/instance.json
```
`make_env()` checks the start state against the frozen instance of this task (`/app/instance.json`). In development
anything goes: reset it, restore states, read anything, make cameras, run many processes. `env.step(action)` takes a
`(1, 16)` tensor; one step is 0.066667 s of simulated time. `env.describe()`, `env.describe_stage()`, the scene's and
the robot's own methods and the source under `/opt/embodiedswe` tell you the rest. `env.scene.success()` tells whether
the task is done (a `(num_envs,)` bool tensor).

### Actions
The action vector is the two arms' actions concatenated in order ('left' dims [0:8), 'right' dims [8:16); total 16).
Each arm: control mode 'osc': 7 arm joints by operational-space control (joint torque); the action is 6 end-effector
pose deltas, plus 2 gripper fingers by direct position target. Action dim 8.

Action range. In each arm's 8-value slice, the first 6 values are end-effector pose deltas in action units (x 0.02 m for
position, x 0.097 rad for rotation). As in EmbodiedSWE, the controller scales them by these factors and does not clip
them (a larger value is a larger step); it clamps each joint torque to 100 N·m. The 2 finger values of each slice are
finger position targets in metres (0 closed, 0.04 open); the joint limits bound them.

### The graded run
Your `solve.py` runs in another process, as an unprivileged user with no network and no GPU. The simulator it runs
against is built from the same frozen instance and reset. It gets a proxy `env` that forwards to that simulator:
- reading works as in development, but returns copies: `env.scene.<...>.data.root_pos_w` gives a CPU tensor, a list of
  assets gives proxies of them, and calling a method that only reads (`env.scene.success()`, `env.describe()`,
  `env.get_states()`, the scene's and robot's query methods) returns its result;
- `env.step(action)` steps the simulator; this is the only way your program changes anything;
- everything else is refused with `PermissionError`: `env.reset()`, `env.set_states(...)`, `env.sim.step()`, any
  `write_*` / `set_*` / `reset*` method of an asset, any method of the scene or the robot that is not one of their
  queries (state, progress and geometry reads such as `success()`, `seated()`, `get_state()`), assigning attributes, and
  private or `__dunder__` attributes. Modifying a tensor you read changes only your copy.
- if `env.step(action)` raises (the env cannot take that action, e.g. the controller hits a singular pose), the error is
  raised in `solve`, as in EmbodiedSWE. If `solve` handles it, the run goes on; otherwise the run ends there, and the
  verdict is read on the state at that moment.

What `solve.py` can use: its process has no simulator and no Isaac Sim app; it is sandboxed and sees only its own files:
- it can import the Python standard library, `numpy`, `torch` (CPU only; 4 threads), `scipy`, `pinocchio` and `pink`,
  the pure-Python parts of `robobench` that import no Isaac module, and your own modules in `solution/`; it can read the
  files in `solution/` (relative to `__file__`) and the installed packages;
- it cannot import `isaaclab`, `isaacsim`, `omni` or `pxr`, because they need the running app. That includes
  `isaaclab.utils.math`: copy the few quaternion helpers you need into your folder. Calling the robot's controller
  objects through the proxy is refused like any other non-read;
- it can write only to its own scratch directory (`$TMPDIR`, also its working directory and `$HOME`), not to
  `solution/`; it sees no other process, no `/tmp`, no `/app`, and has no network;
- it can start subprocesses (at most 512 processes in all); every one of them is ended with it.

The graded run has its own time limit of 30 minutes, counted from the start of the grading process: the simulator's
start-up and the import of `solve.py` count (as in EmbodiedSWE). The run ends when `solve` returns or raises, when its
process ends, or when the 30 minutes are up. Every process it started is then ended, and the verdict is read on the
state at that moment. A crash or a hang is not retried. That verdict is the run's result: success on that state, and
EmbodiedSWE's rubric score as progress.

Test the graded path itself before you finish.
`python /opt/efe/rcb_embodiedswe.py check --solution /app/output/solution` runs your folder exactly as grading does: a
fresh simulator, your `solve` as an unprivileged process behind the proxy, and the same 30-minute limit from the
process's start. Its last printed line is a JSON summary with `success`, `n_actions`, `solve_status`, `boot_s` and the
proxy's refusals. It takes a few minutes: one Isaac Sim launch plus your rollout.

### Development
- The first Isaac Sim launch in the container takes a few minutes (shader cache); later ones are faster. Run long jobs
  in the background and poll their logs. Kit sometimes hangs on exit: `os._exit(0)` after your script has written its
  results is fine.
- Physics runs on the GPU. Do not count on a recorded action sequence repeating exactly: the grading machine's GPU may
  be another model than yours, and drawing frames between steps changes later physics in some scenes. A closed-loop
  solve that reads the state and reacts is robust to both. The proxy adds a little time per call (about 0.05 ms per read
  or step request, measured), so reading state every step is fine.
- You can look at the scene: add a camera (`make_env(cameras=True)`, then Isaac Lab's `Camera`), save frames to PNG and
  look at the images themselves. The graded run draws nothing, so judge a solution by `check`, not by a rendered run.

## Others
- Liquid moves only while the syringe is held upright, plunger end up, with its tip right at a mouth: pulling the
  plunger on the beaker draws, pushing it on a tube fills that tube; anywhere else the liquid is wasted.
- A tube never empties again: overfilling one cannot be undone.
- The plunger is stiff: move it slowly and steadily.
- Every Python process starts from a fresh simulator; nothing carries over between scripts.

## Limits
- Time: 14400 s of wall-clock time from the start of your session; everything counts (the simulator's start-up too). At
  the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 8 CPUs, 29 GiB memory, 16384 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  one GPU (16 GiB of its memory). Over a cap a process can be killed (the CPU cap only slows you down); usage:
  `/run/rcb-limits/usage.json`.
- Resets: as many as you like while you develop (`env.reset()`, restored states); none in the graded run.
