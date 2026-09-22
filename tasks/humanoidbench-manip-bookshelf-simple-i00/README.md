# humanoidbench-manip-bookshelf-simple-i00

| | |
|---|---|
| Simulator / robot | HumanoidBench (MuJoCo + dm_control) / Unitree H1 humanoid with two Shadow dexterous hands, 61 position-controlled joints |
| Family / instance | `bookshelf_simple` (`h1hand-bookshelf_simple-v0`, paper category *manipulation*) / seed 00 |
| Capability class | C9 · long-horizon multi-subtask (see `local_docs/plan/06-task-selection.md`) |
| Task type / tier | trajectory / privileged |
| Base image | `ghcr.io/jameskrw/rcb-humanoidbench:0.1.5` |
| Agent budget | 3600.0 s, 16 CPUs; GPU optional (see below) |

## Difficulty
The pass mark is a **threshold on the whole episode's return** (`>= 2000` over 1000 steps), not a
predicate on the final state.

- **Five subtasks, the longest chain in the subset** (`cabinet` has four, `kitchen` four). Each one is
  a pick-and-place at shelf height with a different target slot, so the state machine has five distinct
  strategies rather than a repeated one.
- **The widest scene state in the benchmark**: 84 DoF of objects (twelve candidates, five in play) on
  top of 61 actuators.
- **Dropping the active object ends the episode**, so the chain is fragile in a way `cabinet`'s hinges
  and drawers are not — there is nothing to catch a mistake.
- **`bookshelf_hard` is deliberately not in the subset.** It is the same class with `fixed = False`,
  which permutes the five destinations; its completion rate (36% vs 41%) and its give-away (2.7% vs
  2.6%) are both within noise of this one, so it would spend a slot on the same problem. The "hidden
  state" objection to it is gone — the permutation lives in `vars(task)` and `body_pos`, both frozen —
  so if a second instance of this class is ever wanted, `hard` is ready.
- **One instance only**: `env.py` forces `randomness = 0` for this family.

**Measured floors** (this instance, `scripts/humanoidbench/gen_tasks.py verify`): an all-zero
trajectory scores **30.45 / 2000** (the episode terminates at step 58 of 1000). Holding the starting
pose instead — the floor a competent agent gets before writing a controller — scores **2.6%** of the
bar; that is the number this task was selected on (`local_docs/plan/06-task-selection.md` §B5).
**External evidence**: published RL results reach **41%** of the bar (paper 763, FastTD3 822, bar
2000) — training runs of millions of environment steps, not a one-hour coding session, so treat it
as proof that the task *has* a solution rather than as a target.

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
render bookshelf_simple`; the instance is reproducible with `gen_tasks.py instance bookshelf_simple`
(seed 0, sha `94587d06b262`).
