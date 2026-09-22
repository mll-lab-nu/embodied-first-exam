# humanoidbench-manip-package-i00

| | |
|---|---|
| Simulator / robot | HumanoidBench (MuJoCo + dm_control) / Unitree H1 humanoid, 19 position-controlled joints |
| Family / instance | `package` (`h1-package-v0`, paper category *manipulation*) / seed 00 |
| Capability class | C8 · mobile manipulation (see `local_docs/plan/06-task-selection.md`) |
| Task type / tier | trajectory / privileged |
| Base image | `ghcr.io/jameskrw/rcb-humanoidbench:0.1.5` |
| Agent budget | 3600.0 s, 16 CPUs; GPU optional (see below) |

## Difficulty
The pass mark is a **threshold on the whole episode's return** (`>= 1500` over 1000 steps), not a
predicate on the final state.

- **The hardest task in HumanoidBench by published result**: −7487 against a bar of 1500. Both
  baselines are deeply negative, which is what a dense penalty does to a policy that cannot complete
  the task at all.
- **Doing nothing is expensive, not neutral.** An all-zero trajectory scores −2192 and holding the start
  pose −2053: the distance penalty accrues every step whatever you do. This is the strongest
  "blank paper is punished" signal in the subset, and it is the reason the task cannot be gamed by
  submitting a safe do-nothing trajectory.
- **Three skills in strict sequence**: walk to the package, lift it (which changes the robot's own
  dynamics), carry it while balancing the load, place it. Failing any one caps the episode at the
  previous stage's plateau.
- **Goal state outside `(qpos, qvel)`.** `model.body_pos[-1]` holds the destination, drawn from the
  global `np.random`; the instance snapshot covers it (06-task-selection.md §F1).

⚠️ **Instances of this family are not interchangeable.** The package and the destination are each
drawn uniformly from a ±2 m box, so the distance between them can be 0.2 m or 5.6 m. Any `i01`/`i02`
must be filtered to a comparable distance band (2.0-3.0 m suggested) and the band recorded here.

**Measured floors** (this instance, `scripts/humanoidbench/gen_tasks.py verify`): an all-zero
trajectory scores **-2191.95 / 1500**. Holding the starting pose instead — the floor a competent
agent gets before writing a controller — scores **-136.9%** of the bar; that is the number this task
was selected on (`local_docs/plan/06-task-selection.md` §B5). **External evidence**: published RL
results reach **negative** of the bar (paper -6912, FastTD3 -7487, bar 1500) — training runs of
millions of environment steps, not a one-hour coding session, so treat it as proof that the task
*has* a solution rather than as a target.

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
render package`; the instance is reproducible with `gen_tasks.py instance package` (seed 0, sha
`2f0da1a56a33`).
