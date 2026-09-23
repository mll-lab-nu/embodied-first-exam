# humanoidbench-manip-highbar-simple-i00

| | |
|---|---|
| Simulator / robot | HumanoidBench (MuJoCo + dm_control) / Unitree H1 humanoid, 19 position-controlled joints |
| Family / instance | `highbar_simple` (`h1-highbar_simple-v0`, paper category *manipulation*) / seed 00 |
| Capability class | C5 · whole-body power and momentum (see `local_docs/plan/06-task-selection.md`) |
| Task type / tier | trajectory / privileged |
| Base image | `ghcr.io/jameskrw/rcb-humanoidbench:0.1.5` |
| Agent budget | 3600.0 s, 16 CPUs; GPU optional (see below) |

## Difficulty
The pass mark is a **threshold on the whole episode's return** (`>= 750` over 1000 steps), not a
predicate on the final state.

- **Energy injection, not stabilisation and not a gait.** Reaching an inverted pose from a hang takes
  pumping: small oscillations amplified by applying torque at the right phase. The code an agent has to
  write is a timed, large-amplitude joint trajectory — structurally unlike the feedback controllers of
  C3 or the contact schedules of C1/C2.
- **Hanging quietly scores zero.** Because the uprightness term is negated, the do-nothing basin is not
  a local optimum worth defending — it is exactly 0 (measured: 0.08/750 over a full 1000 steps), so
  there is no partial credit to coast on.
- **A receding horizon does not contain the answer.** Pumping pays off only after several swing cycles,
  so a planner optimising the next few dozen steps sees nothing but wasted effort. This is the clearest
  structural reason the task survives the CEM-MPC approach that solved `walk`.
- **This is the subset's ceiling, and it is kept on purpose.** A benchmark whose every task is solved
  saturates the moment models improve. Note the evidence here is the thinnest of the subset: neither upstream's
  curves (which cover only `highbar_hard`, whose best final return is 12 of 750) nor FastTD3 (h1hand only)
  report this family, so "very hard" is a reasonable prior but not an established fact.
- **Cleanest determinism in the subset**: 19 DoF, no objects, and upstream forces the reset noise to
  zero for this family — see the caveat below.

⚠️ **This family can only ever have one instance.** `HighBarBase.reset_model()` sets the
environment's `randomness` to 0, so every reset produces the identical pose. There is no `i01`/`i02`
to generate; that is upstream behaviour, not a defect in the instance.

**Measured floors** (this instance, `scripts/humanoidbench/gen_tasks.py verify`): an all-zero
trajectory scores **0.08 / 750**. Holding the starting pose instead — the floor a competent agent
gets before writing a controller — scores **0.0%** of the bar; that is the number this task was
selected on (`local_docs/plan/06-task-selection.md` §B5). **External evidence**: published RL
results reach **an unknown fraction** of the bar (neither upstream's curves (which cover only
highbar_hard) nor FastTD3 (h1hand only) report this family) — training runs of millions of
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
render highbar_simple`; the instance is reproducible with `gen_tasks.py instance highbar_simple`
(seed 0, sha `9cbea1804a71`).
