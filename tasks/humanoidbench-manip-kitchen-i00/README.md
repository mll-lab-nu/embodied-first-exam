# humanoidbench-manip-kitchen-i00

| | |
|---|---|
| Simulator / robot | HumanoidBench (MuJoCo + dm_control) / Unitree H1 humanoid with two Shadow dexterous hands, 61 position-controlled joints |
| Family / instance | `kitchen` (`h1hand-kitchen-v0`, paper category *manipulation*) / seed 00 |
| Capability class | C9 · long-horizon multi-subtask (see `local_docs/plan/06-task-selection.md`) |
| Task type / tier | trajectory / privileged |
| Base image | `ghcr.io/jameskrw/rcb-humanoidbench:0.1.5` |
| Agent budget | 3600.0 s, 16 CPUs; GPU optional (see below) |

## Difficulty
The pass mark is a **threshold on the whole episode's return** (`>= 4` over 500 steps), not a
predicate on the final state.

- **🔑 The only task in the benchmark with a genuinely sparse reward.** Every other task, even the
  all-or-nothing ones like `push` and `basketball`, has *some* continuous term pointing the way. Here the
  return is an integer in 0..4 and nothing separates "nearly opened the microwave" from "did not move".
  That makes it the one task where search against the task's own signal is useless — there is no signal
  until the first success — and the strongest single answer to the concern in §B6 that dense shaping
  makes tasks planner-solvable.
- **Nobody has scored a single point.** The paper reports 0/4 and the current state of the art never ran
  this family. This is the subset's hardest deliberate ceiling; we expect it to stay at zero for a while
  and that is the point (06-task-selection.md §B3).
- **Different scale, same verdict.** `success_bar = 4` counts subtasks rather than summing a dense
  reward. It does not affect grading — the verifier writes a binary `success` and per-task numbers go to
  `diagnostics.json` — but do not compare 4 against another task's 700.
- **One instance only**: `env.py` forces `randomness = 0` for this family.

**Measured floors** (this instance, `scripts/humanoidbench/gen_tasks.py verify`): an all-zero
trajectory scores **0.00 / 4**. Holding the starting pose instead — the floor a competent agent gets
before writing a controller — scores **0.0%** of the bar; that is the number this task was selected
on (`local_docs/plan/06-task-selection.md` §B5). **External evidence**: published RL results reach
**0%** of the bar (paper 0 of 4; FastTD3 never ran this family) — training runs of millions of
environment steps, not a one-hour coding session, so treat it as proof that the task *has* a
solution rather than as a target.

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
render kitchen`; the instance is reproducible with `gen_tasks.py instance kitchen` (seed 0, sha
`0791215e783d`).
