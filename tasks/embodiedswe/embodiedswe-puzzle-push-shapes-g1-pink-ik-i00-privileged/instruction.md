# EmbodiedSWE · push the shapes onto their pads, Unitree G1 (privileged)

## Task
A Unitree G1 humanoid with three-finger hands, fixed at the pelvis (legs locked), a stationary upper-body manipulator. A
raised work board lies on the table in front of you, with three shape cutouts sunk into it: a T, a cross, and an L,
their recess floors coloured dark red, dark blue, and dark amber. Three flat coloured blocks rest on the board, each
some distance behind the cutout of its own shape: a red T, a blue cross, and an amber L. Each block starts rotated away
from its cutout's orientation. Slide every block across the board into the cutout of its own shape so that it drops in
and lies flat inside its recess, matching the recess outline in position and rotation. The blocks can only be pushed;
lifting them does not solve the task. A block that arrives misaligned will catch on the recess rim instead of dropping
in, and a wedged block is hard to recover — align each block before it reaches its cutout. You have the full simulator
to develop with; you hand in a program that completes the task (`/app/output/solution/`).

## Goal
Success: each block lies flat inside the cutout of its own shape, dropped into its recess and matching its outline in
place and turn, all three at once and at rest. What counts is how things stand when the graded run of your program ends:
a success reached earlier and lost by then does not count. Only success counts as solved; partial progress
(EmbodiedSWE's rubric for this task, `progress`) is recorded too and ranks your checkpoints.

Deliverable: the folder `/app/output/solution/`, whose entry point `/app/output/solution/solve.py` defines
`def solve(env) -> None`, run once in the graded run (Robot Interface). Everything else in the folder ships with it
(helper modules, calibration data); nothing outside it does. At grading time `solve.py`'s directory is on the import
path, so sibling imports and files read relative to `__file__` work. Only regular files count (no symbolic links); at
most 20,000 files and 2 GiB. Keep module level light: no simulator launch or env build at import time (a
`if __name__ == "__main__":` block that builds an env with `make_env()` and calls `solve(env)` is a good pattern for
development). Save a valid one early and overwrite it when you have a better one.

Checkpoints, as in EmbodiedSWE: `submit "a short note"` copies `/app/output/solution/` as it is now to
`/app/output/submissions/NNNNNN/` (with a receipt, `submission.json`). At most 64 checkpoints; the final
`/app/output/solution/` is graded as well. Every distinct checkpoint and the final folder are each graded in their own
fresh simulator, as in the graded run (Robot Interface; 30 minutes each); identical copies are graded once. The result
is the one with the highest progress; a tie goes to the one with success, then to the earliest (the final folder counts
as the last). Its success is the verdict. Do not edit `/app/output/submissions/` by hand: a checkpoint whose files no
longer match its receipt scores 0. Leaving the best version in `solution/` is enough; checkpoints are a safety net for
versions you might break later.

Rules: write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
In the graded run (whatever the proxy lets through): change the world only by stepping forward with `env.step`; never
reset, restore states, move objects, modify physics, the task, the scene or the robot's controller, or reach the grading
code or its files.

## Robot Interface
### Session
The env is EmbodiedSWE's `puzzle.push_shapes.g1.pink_ik` preset: one environment (`num_envs = 1`), seed 0, PhysX on the
GPU (`device="cuda:0"`), the same build as in grading. Build it as grading does (`/opt/efe/rcb_embodiedswe.py`):
```python
import sys; sys.path.insert(0, "/opt/efe")
from rcb_embodiedswe import make_env
env = make_env()        # launches Isaac Sim headless first, then builds and resets the env from /app/instance.json
```
`make_env()` checks the start state against the frozen instance of this task (`/app/instance.json`). In development
anything goes: reset it, restore states, read anything, make cameras, run many processes. `env.step(action)` takes a
`(1, 28)` tensor; one step is 0.016667 s of simulated time. `env.describe()`, `env.describe_stage()`, the scene's and
the robot's own methods and the source under `/opt/embodiedswe` tell you the rest. `env.scene.success()` tells whether
the task is done (a `(num_envs,)` bool tensor).

### Actions
Control mode 'pink_ik': 17 arm+waist joints driven by the Pink IK solver (absolute wrist poses), plus 14 hand joints by
direct position target. Action dim 28.

Action range. The tooling enforces no range on this robot's action: the wrist poses are absolute targets for the IK and
the hand joint targets are bounded by the joint limits.

### The graded run
Your `solve.py` runs in another process, as an unprivileged user with no network and no GPU, against a simulator built
from the same frozen instance and reset; it gets a proxy `env` that forwards to it:
- reading works as in development, but returns copies: `env.scene.<...>.data.root_pos_w` gives a CPU tensor, a list of
  assets gives proxies of them, and calling a method that only reads (`env.scene.success()`, `env.describe()`,
  `env.get_states()`, the scene's and robot's query methods) returns its result;
- `env.step(action)` steps the simulator; this is the only way your program changes anything;
- everything else is refused with `PermissionError`: `env.reset()`, `env.set_states(...)`, `env.sim.step()`, any
  `write_*` / `set_*` / `reset*` method of an asset, any method of the scene or the robot that is not one of their
  queries (state, progress and geometry reads such as `success()`, `seated()`, `get_state()`), assigning attributes, and
  private or `__dunder__` attributes. Modifying a tensor you read changes only your copy.
- if `env.step(action)` raises (the env cannot take that action, e.g. the controller hits a singular pose), the error is
  raised in `solve`, as in EmbodiedSWE: the run goes on if `solve` handles it, and otherwise ends there, with the
  verdict read on the state at that moment.

What `solve.py` can use: its process has no simulator and no Isaac Sim app; it is sandboxed and sees only its own files:
- it can import the Python standard library, `numpy`, `torch` (CPU only; 4 threads), `scipy`, `pinocchio` and `pink`,
  the pure-Python parts of `robobench` that import no Isaac module, and your own modules in `solution/`; it can read the
  files in `solution/` (relative to `__file__`) and the installed packages;
- it cannot import `isaaclab`, `isaacsim`, `omni` or `pxr` (they need the running app; `isaaclab.utils.math` included:
  copy the few quaternion helpers you need into your folder), and calling the robot's controller objects through the
  proxy is refused like any other non-read;
- it can write only to its own scratch directory (`$TMPDIR`, also its working directory and `$HOME`), not to
  `solution/`; it sees no other process, no `/tmp`, no `/app`, and has no network;
- it can start subprocesses (at most 512 processes in all); every one of them is ended with it.

The graded run has its own time limit of 30 minutes, counted from the start of the grading process: the simulator's
start-up and the import of `solve.py` count (as in EmbodiedSWE). It ends when `solve` returns or raises, its process
ends, or the 30 minutes are up; every process it started is then ended, and the verdict is read on the state at that
moment (a crash or a hang is not retried). That verdict is the run's result: success on that state, and EmbodiedSWE's
rubric score as progress.

Test the graded path itself before you finish:
`python /opt/efe/rcb_embodiedswe.py check --solution /app/output/solution` runs your folder exactly as grading does (a
fresh simulator, your `solve` as an unprivileged process behind the proxy, the same 30-minute limit from the process's
start) and prints, as its last line, a JSON summary with `success`, `n_actions`, `solve_status`, `boot_s` and the
proxy's refusals (it takes a few minutes: one Isaac Sim launch plus your rollout).

## Others
- The first Isaac Sim launch in the container takes a few minutes (shader cache); later ones are faster. Run long jobs
  in the background and poll their logs. Kit sometimes hangs on exit: `os._exit(0)` after your script has written its
  results is fine.
- Every Python process starts from a fresh simulator; nothing carries over between scripts.
- Physics runs on the GPU. Do not count on a recorded action sequence repeating exactly: the grading machine's GPU may
  be another model than yours, and drawing frames between steps changes later physics in some scenes. A closed-loop
  solve that reads the state and reacts is robust to both; the proxy adds a little time per call (about 0.05 ms per read
  or step request, measured), so reading state every step is fine.
- You can look at the scene: add a camera (`make_env(cameras=True)`, then Isaac Lab's `Camera`), save frames to PNG and
  look at the images themselves. The graded run draws nothing, so judge a solution by `check`, not by a rendered run.

## Limits
- Time: 14400 s of wall-clock time from the start of your session; everything counts (the simulator's start-up too). At
  the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 8 CPUs, 29 GiB memory, 16384 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  one GPU (16 GiB of its memory). Over a cap a process can be killed (the CPU cap only slows you down); usage:
  `/run/rcb-limits/usage.json`.
- Resets: as many as you like while you develop (`env.reset()`, restored states); none in the graded run.
