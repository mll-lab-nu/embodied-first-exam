# humanoidbench-manip-spoon-i00

| | |
|---|---|
| Simulator / robot | HumanoidBench (MuJoCo + dm_control) / Unitree H1 humanoid with two Shadow dexterous hands, 61 position-controlled joints |
| Family / instance | `spoon` (`h1hand-spoon-v0`, paper category *manipulation*) / seed 00 |
| Capability class | C6 · standing bimanual manipulation (see `local_docs/plan/06-task-selection.md`) |
| Task type / tier | trajectory / privileged |
| Base image | `ghcr.io/jameskrw/rcb-humanoidbench:0.1.6` |
| Agent budget | 3600.0 s, 16 CPUs; GPU optional (see below) |

## Difficulty
The pass mark is a **threshold on the whole episode's return** (`>= 650` over 1000 steps), not a
predicate on the final state.

- **Periodic end-effector tracking — the only instance of it in the subset.** `walk` needs a limit
  cycle in the legs against ground contact; this needs one in the hands against a clock, with the phase
  fixed by the environment rather than chosen by the agent. 40 steps per revolution at 50 Hz is 1.25
  revolutions a second.
- **🚩 The published best is *below* the give-away floor.** FastTD3 reaches 369/650; holding the starting
  pose scores 375.67 — standing and a hand near the handle pay for it, although the spoon starts on the
  table beside the cup. That is the sharpest illustration in the subset of why completion
  rate alone is the wrong selection criterion (06-task-selection.md §B4).
- **⚠️ The highest give-away in the scored subset: 57.8% of the bar.** It was kept on the argument that
  the remaining 42% is periodic tracking, but by the formula it is not: the circling term's tolerance
  (0.15 m) is wider than the circle's radius (0.06 m), so a spoon held still at the centre of the cup
  scores about 0.84 a step against the 0.65 the bar needs. What remains is getting the spoon into the
  cup, which makes this the first task to reconsider. The `verify` threshold carries an explicit
  exemption for it, so this is recorded in code and not just in prose.
- **61 actuators**, and the grip has to survive a sustained oscillation.

**Measured floors** (this instance, `scripts/humanoidbench/gen_tasks.py verify`): an all-zero
trajectory scores **7.48 / 650** (the episode terminates at step 63 of 1000). Holding the starting
pose instead — the floor a competent agent gets before writing a controller — scores **57.8%** of
the bar; that is the number this task was selected on (`local_docs/plan/06-task-selection.md` §B5).
**External evidence**: published RL results reach **57%** of the bar (paper 322, FastTD3 369, bar
650) — training runs of millions of environment steps, not a one-hour coding session, so treat it as
proof that the task *has* a solution rather than as a target.

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
render spoon`; the instance is reproducible with `gen_tasks.py instance spoon` (seed 0, sha
`11a38054aebb`).
