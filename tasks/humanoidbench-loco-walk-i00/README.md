# humanoidbench-loco-walk-i00

| | |
|---|---|
| Simulator / robot | HumanoidBench (MuJoCo + dm_control) / Unitree H1 humanoid, 19 position-controlled joints |
| Family / instance | `walk` (`h1-walk-v0`, paper category *locomotion*) / seed 00 |
| Capability class | C1 · flat-ground periodic gait (see `local_docs/plan/06-task-selection.md`) |
| Task type / tier | trajectory / privileged |
| Base image | `ghcr.io/jameskrw/rcb-humanoidbench:0.1.5` |
| Agent budget | 3600.0 s, 16 CPUs; GPU optional (see below) |

## Difficulty
The pass mark is a **threshold on the whole episode's return** (`>= 700` over 1000 steps), not a
predicate on the final state.

- **The reward is a three-way product**: `small_control × stand_reward × move`. The `move` term rises
  linearly from 0 at standstill to 1 at 1 m/s of forward centre-of-mass speed, then is remapped to
  `(5·move + 1)/6`. Standing still therefore caps the episode near 170/700 — staying upright earns
  almost nothing by itself. Clearing the bar takes a *sustained* ~0.7 m/s.
- **A gait is a limit cycle, and greedy search cannot find one.** Any first step out of a standing pose
  is locally worse than not taking it: the centre of mass has to leave the support polygon before it
  gains anything. A search that only accepts locally improving actions structurally never takes that
  step. Planning with a horizon *can*, which is exactly what happened below.
- **Nothing is given away**: the published random-policy baseline is 2.38/700, and holding the starting
  pose scores 11.84 — the lowest give-away in the subset.

**Measured with a real agent** (`mini-swe-agent` + `claude-sonnet-5`, one attempt, full 1 h budget,
~$6, 200 steps): **passed, 784.54 / 700**, deterministic replay. What it reported trying, in order:
open-loop sine CPG (falls before step 100), CPG + LQR linearised at the initial state (survives all
1000 steps but caps near 200), CMA-ES over the CPG/Fourier parameters (plateaus at 190-210 -- it
concluded the parameterisation, not the search budget, was the limit), and finally receding-horizon
CEM-MPC against the task's own reward, which cleared the bar.

🚩 **That run had the reward function.** It is the reason the image no longer does: the winning
approach was to optimise the formula directly, which measures reading comprehension of a dense
reward rather than control. Re-run under the scrubbed image, the same approach needs the agent to
*write* the objective first -- see local_docs/plan/06-task-selection.md §B6.

**Measured floors** (this instance, `scripts/humanoidbench/gen_tasks.py verify`): an all-zero
trajectory scores **6.56 / 700** (the episode terminates at step 66 of 1000). Holding the starting
pose instead — the floor a competent agent gets before writing a controller — scores **1.7%** of the
bar; that is the number this task was selected on (`local_docs/plan/06-task-selection.md` §B5).
**External evidence**: published RL results reach **133%** of the bar (paper SAC 854, FastTD3 928,
bar 700) — training runs of millions of environment steps, not a one-hour coding session, so treat
it as proof that the task *has* a solution rather than as a target.

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
render walk`; the instance is reproducible with `gen_tasks.py instance walk` (seed 0, sha
`4863491aa1f3`).
