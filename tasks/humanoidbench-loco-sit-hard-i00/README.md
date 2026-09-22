# humanoidbench-loco-sit-hard-i00

| | |
|---|---|
| Simulator / robot | HumanoidBench (MuJoCo + dm_control) / Unitree H1 humanoid, 19 position-controlled joints |
| Family / instance | `sit_hard` (`h1-sit_hard-v0`, paper category *locomotion*) / seed 00 |
| Capability class | C8 · mobile manipulation (see `local_docs/plan/06-task-selection.md`) |
| Task type / tier | trajectory / privileged |
| Base image | `ghcr.io/jameskrw/rcb-humanoidbench:0.1.5` |
| Agent budget | 3600.0 s, 16 CPUs; GPU optional (see below) |

## Difficulty
The pass mark is a **threshold on the whole episode's return** (`>= 750` over 1000 steps), not a
predicate on the final state.

- **🚩 The task where completion rate lies hardest.** Published RL reaches 108% of the bar, which reads
  as "solved" — but holding the starting pose collapses at step 130 for 1.7% of the bar. Nothing is
  given away here; the 108% says a solution exists, not that it is easy. Selecting on completion rate
  alone would have cut this task, which is the case study behind 06-task-selection.md §B4.
- **Locomotion and a terminal posture in one episode, with a turn first.** The start heading is drawn
  from ±1.8 rad (up to ±103°), so the robot has to stabilise, turn, walk to the chair and then *stop
  being a walker* and become a static pose. That transition — handing off from a limit cycle to a fixed
  point — appears nowhere else in the subset.
- **Partial credit with a deadline.** Because reward is paid per step for being seated, arriving late is
  permanently expensive; the agent cannot amortise a slow approach.
- **Shares its reward function with the `sit_simple` fixture**, and that is the second demonstration
  after `balance_*` that the same formula can be two different problems: the fixture gives away 62.4% of
  its bar, this gives away 1.7%.

**Measured floors** (this instance, `scripts/humanoidbench/gen_tasks.py verify`): an all-zero
trajectory scores **13.56 / 750** (the episode terminates at step 115 of 1000). Holding the starting
pose instead — the floor a competent agent gets before writing a controller — scores **1.7%** of the
bar; that is the number this task was selected on (`local_docs/plan/06-task-selection.md` §B5).
**External evidence**: published RL results reach **108%** of the bar (paper TD-MPC2 811, FastTD3
726, bar 750) — training runs of millions of environment steps, not a one-hour coding session, so
treat it as proof that the task *has* a solution rather than as a target.

**The agent does not see the reward function.** It is deleted from the image and restored only
inside the verifier (`images/humanoidbench/scrub_oracles.py`, `tests/rcb_rewards.py`), so the
numbers above are comparable with the paper while the agent works from the task statement and the
physical state alone.

## Reference solution
No reference solution, on purpose. Requiring one would cap the benchmark at what we can already
solve, which systematically removes the interesting tasks — see `local_docs/plan/01-design.md` §D.
`solution/solve.sh` exists because the Harbor task contract requires it and exits non-zero with that
explanation. What replaces an oracle is the floor above: the task is known to be unreachable by
doing nothing, and known to be solvable by *something*.

## GPU
The task runs CPU-only by default and passing never depends on a GPU: MuJoCo physics has no GPU
path, so the only thing a GPU accelerates is offscreen rendering (osmesa ~130 ms/frame, egl ~0.4
ms). It is therefore opt-in, in two independent layers:

| layer | who decides | how |
|---|---|---|
| does the container *see* a GPU | you, per run | `--extra-docker-compose environment/gpu.docker-compose.yaml` |
| which GL backend the process uses | `rcb_hb.py`, automatically | `_resolve_gl_backend()` |

`_resolve_gl_backend()` honours an explicit `MUJOCO_GL` and otherwise requires **both**
`/dev/nvidiactl` (the device, from `NVIDIA_VISIBLE_DEVICES`) **and** an NVIDIA EGL vendor ICD under
`/usr/share/glvnd/egl_vendor.d/` (the GL libraries, which the runtime mounts only when
`NVIDIA_DRIVER_CAPABILITIES` includes `graphics`). Requiring both is what separates "has a GPU" from
"can render on it": a CUDA-only container has the device node and would still fail with *an OpenGL
platform library has not been loaded*. The chosen backend is reported in
`/logs/verifier/diagnostics.json`.

The overlay is deliberately not named `docker-compose.yaml`, which Harbor would auto-load — an
unsatisfiable device reservation stops the container from starting at all on a machine without a
GPU.

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.npz` in a fresh process,
twice; pass iff every replay's episode return reaches `success_bar` **and** the final-state hashes
agree (bit-exact determinism). `tests/grade.py` also writes `/logs/verifier/replay.mp4` and, because
Harbor promotes every `reward.json` key to a leaderboard metric, keeps the per-task numbers
(`episode_return`, `success_bar`) in `/logs/verifier/diagnostics.json`.

## Provenance
Generated by `scripts/humanoidbench/gen_tasks.py` from `scripts/humanoidbench/subset.toml`.
Everything in this directory except `environment/instance.npz` is reproducible with `gen_tasks.py
render sit_hard`; the instance is reproducible with `gen_tasks.py instance sit_hard` (seed 0, sha
`158f9910c628`).
