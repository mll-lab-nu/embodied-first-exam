# humanoidbench-loco-reach-i00

| | |
|---|---|
| Simulator / robot | HumanoidBench (MuJoCo + dm_control) / Unitree H1 humanoid, 19 position-controlled joints |
| Family / instance | `reach` (`h1-reach-v0`, paper category *locomotion*) / seed 00 |
| Capability class | C8 · mobile manipulation (see `local_docs/plan/06-task-selection.md`) |
| Task type / tier | trajectory / privileged |
| Base image | `ghcr.io/jameskrw/rcb-humanoidbench:0.1.5` |
| Agent budget | 3600.0 s, 16 CPUs; GPU optional (see below) |

## Difficulty
The pass mark is a **threshold on the whole episode's return** (`>= 12000` over 1000 steps), not a
predicate on the final state.

- **Two regimes in one reward, and only the second clears the bar.** Getting within 1 m is worth 5 a
  step and is reachable by leaning; the last 5 cm is worth 10 more and needs precise, *held* placement.
  An agent that stops at the easy plateau lands around 10000 against a bar of 12000 and fails.
- **Holding is the hard part.** The bonus is paid per step inside the tolerance, not once on arrival, so
  the deliverable is a posture that stays put for hundreds of steps, not a reaching motion.
- **19 DoF makes this the cheap probe for its class**; the rest of C8 costs a walk across the room.
- **Upstream shipped trained policies for exactly this task** (`data/reach_*`, the hierarchical
  baseline's low level). They are deleted from the base image by
  `images/humanoidbench/scrub_oracles.py`; without that they would be a ready-made submission.

⚠️ **Instances of this family are not interchangeable.** The target is drawn uniformly from a ±2 m
box, so one seed can put it at the robot's feet and another 2.8 m away — a different task, not a
different sample of the same task. In this instance it sits **0.704 m from the left hand's starting
position** (0.88 m from the origin in the horizontal plane), i.e. reachable by leaning and a step
rather than by crossing the room. Any `i01`/`i02` must be filtered to a comparable distance band and
the band recorded here.

**Measured floors** (this instance, `scripts/humanoidbench/gen_tasks.py verify`): an all-zero
trajectory scores **275.22 / 12000**. The target sits 0.704 m from the left hand at the frozen pose.
Holding the starting pose instead — the floor a competent agent gets before writing a controller —
scores **5.1%** of the bar; that is the number this task was selected on
(`local_docs/plan/06-task-selection.md` §B5). **External evidence**: published RL results reach
**69%** of the bar (paper 8280, FastTD3 8147, bar 12000) — training runs of millions of environment
steps, not a one-hour coding session, so treat it as proof that the task *has* a solution rather
than as a target.

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
render reach`; the instance is reproducible with `gen_tasks.py instance reach` (seed 0, sha
`8014759785fe`).
