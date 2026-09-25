# humanoidbench-loco-sit-simple-i00

| | |
|---|---|
| Simulator / robot | HumanoidBench (MuJoCo + dm_control) / Unitree H1 humanoid, 19 position-controlled joints |
| Family / instance | `sit_simple` (`h1-sit_simple-v0`, paper category *locomotion*) / seed 00 |
| Capability class | fixture (C3 · quasi-static stabilisation, too easy to score) (see `local_docs/plan/06-task-selection.md`) |
| Task type / tier | trajectory / privileged |
| Base image | `ghcr.io/jameskrw/rcb-humanoidbench:0.1.6` |
| Agent budget | 3600.0 s, 16 CPUs; GPU optional (see below) |

## Difficulty
The pass mark is a **threshold on the whole episode's return** (`>= 750` over 1000 steps), not a
predicate on the final state.

- **No pose to snap to.** Reaching the chair late still forfeits the reward of every step spent
  standing, so the agent has to sit *early* and then stay still — a partial credit landscape, not a
  goal test.
- **Doing nothing already gets 85% of the bar.** An all-zero action commands the mid-point of every
  actuator's range, which slumps the robot back against the chair's backrest with the pelvis just above
  the seat, and it stays there for the full episode: **637.6 /
  750**, measured. Holding the *starting* pose instead scores 468.12 (62.4%). That is the single clearest
  reason this task is a fixture and not a scored task — the gap a solution has to close is small enough
  that almost anything coherent closes it.
- **19 coupled DoF under gravity.** The agent has to work out *which* joints put a humanoid on a chair
  and how to get there without falling — from the raw state vector and the MuJoCo model, with no
  primitives.

**Measured difficulty** (`mini-swe-agent` + `meta/muse-spark-1.3`, first attempt): **solved, 979.03
/ 750** in 26 steps, 337 s of agent time and $0.36. It did not search — it read the model, picked a
seated joint target by hand (hip −1.4, knee 1.7, ankle −0.35), cosine-blended into it over 30 steps
and held, then self-checked with `Session.replay`. That beats this task's CEM-MPC oracle (820.28)
and the published SAC baseline (861), which needs millions of environment steps.

🚩 That run also read `Sit.get_reward()` and quoted its bounds back at us, which is the measurement
that led to the reward function being removed from the image entirely
(`images/humanoidbench/scrub_oracles.py`, and local_docs/plan/07-open-questions.md §1). The 979.03
is therefore a number from the old, reward-visible setup and is not reproducible as-is.

So this instance is **easier than it looks**, and honestly so: `sit_simple` rewards a static seated
pose, and a static pose is exactly what a competent agent can reason out. It earns its place as the
first task in the family — it proves the whole pipeline end to end with a solvable target — but it
is **not part of the scored subset**. It is kept as the template every other task is generated from
and as the CI fixture that distinguishes "the agent is broken" from "the task is hard".

⏳ **Scheduled for removal.** Delete this task once all 23 scored tasks are `verified` and at least
two of them, from different capability classes, have been passed end to end by different agents. The
original condition — "any scored task passed by a real agent" — was met by `walk` (784.54/700,
`claude-sonnet-5`), but that was a single run by a single model under the old reward-visible setup,
and the whole point of the fixture is to tell "the agent is broken" apart from "the task is hard".
That distinction is worth most while 23 task directories are being generated for the first time, and
this is the only task carrying an oracle, so it is also the only one where `ci_checks` can exercise
the oracle = 1 path.

**Measured floors** (this instance, `scripts/humanoidbench/gen_tasks.py verify`): an all-zero
trajectory scores **637.64 / 750**. Holding the starting pose instead — the floor a competent agent
gets before writing a controller — scores **62.4%** of the bar; that is the number this task was
selected on (`local_docs/plan/06-task-selection.md` §B5). **External evidence**: published RL
results reach **124%** of the bar (paper 861, FastTD3 929, bar 750) — training runs of millions of
environment steps, not a one-hour coding session, so treat it as proof that the task *has* a
solution rather than as a target.

**The agent does not see the reward function.** It is deleted from the image and restored only
inside the verifier (`images/humanoidbench/scrub_oracles.py`, `tests/rcb_rewards.py`), so the
numbers above are comparable with the paper while the agent works from the task statement and the
physical state alone.

## Reference solution
`solution/sit_simple_actions.npy` — a 999-step action sequence that scores **820.28 / 750**,
replayed by `solution/oracle_sit_simple.py`. HumanoidBench ships no reference solutions (its
"solutions" are training curves), so this one was produced by training-free CEM-MPC against the
simulator itself: `solution/cem_mpc.py` reruns that search in ~2.5 minutes on 32 cores (last run:
817.7/750). It is a fresh search, not a replay, so it produces an equivalent passing trajectory
rather than this exact file. `solve.sh` replays the recording instead of searching, so the oracle is
deterministic and costs one episode.

⚠️ The oracle searches against the reward function, which the task image no longer has. It runs with
the verifier's restore path (`tests/rcb_rewards.py`) or outside the container; it is a development
tool and a CI fixture, not something an agent could reproduce from inside.

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
render sit_simple`; the instance is reproducible with `gen_tasks.py instance sit_simple` (seed 0,
sha `ef2c205ae550`).
