# humanoidbench-loco-sit-simple-i00

| | |
|---|---|
| Simulator / robot | HumanoidBench (MuJoCo + dm_control) / Unitree H1, 19 position-controlled joints |
| Family / instance | `sit_simple` (`h1-sit_simple-v0`, paper category *locomotion*) / seed 00 |
| Task type / tier | trajectory / privileged |
| Base image | `ghcr.io/jameskrw/rcb-humanoidbench:0.1.2` |
| Agent budget | 3600 s, 16 CPUs; GPU optional (see below) |

## Difficulty
The pass mark is a **threshold on the whole episode's return** (`>= 750` over 1000 steps), not a predicate
on the final pose, which changes what a solution has to look like:

- **No pose to snap to.** Reaching the chair late still forfeits the reward of every step spent standing,
  so the agent has to sit *early* and then stay still — a partial credit landscape, not a goal test.
- **Standing still is not a solution.** The H1's actuators are position servos, but holding the *initial
  standing* target does not hold that pose: measured, the nominal keyframe falls at step 96 and scores
  67/800. A seated target is different — the chair makes it statically stable — so the agent has to
  realise that the goal pose, not the starting one, is the one it can afford to just hold.
- **19 coupled DoF under gravity.** The agent has to work out *which* joints put a humanoid on a chair and
  how to get there without falling — from the raw state vector and the MuJoCo model, with no primitives.
- **The physics budget is generous on purpose.** One 1000-step episode is ~0.6 s of one core, and the
  container has 16, so sampling-based planning also fits comfortably inside the agent's hour.

**Measured difficulty** (`mini-swe-agent` + `meta/muse-spark-1.3`, first attempt): **solved, 979.03 / 750**
in 26 steps, 337 s of agent time and $0.36. It did not search — it read the model, picked a seated joint
target by hand (hip −1.4, knee 1.7, ankle −0.35), cosine-blended into it over 30 steps and held, then
self-checked with `Session.replay`. That beats this task's CEM-MPC oracle (820.28) and the published SAC
baseline (861), which needs millions of environment steps.

So this instance is **easier than it looks**, and honestly so: `sit_simple` rewards a static seated pose,
and a static pose is exactly what a competent agent can reason out. It earns its place as the first task
in the family — it proves the whole pipeline end to end with a solvable target — but it should not be read
as evidence that HumanoidBench is easy for coding agents. The tasks that need a *periodic gait*
(`walk`, `run`, `hurdle`) are where both this approach and training-free search fall over.

## Reference solution
`solution/sit_simple_actions.npy` — a 999-step action sequence that scores **820.28 / 750**, replayed by
`solution/oracle_sit_simple.py`. HumanoidBench ships no reference solutions (its "solutions" are training
curves), so this one was produced by training-free CEM-MPC against the simulator itself:
`solution/cem_mpc.py` reruns that search in ~2.5 minutes on 32 cores (last run: 817.7/750). It is a fresh
search, not a replay, so it produces an equivalent passing trajectory rather than this exact file.
`solve.sh` replays the recording instead of searching, so the oracle is deterministic and costs one episode.

## GPU
The task runs CPU-only by default and passing never depends on a GPU: MuJoCo physics has no GPU path, so
the only thing a GPU accelerates is offscreen rendering (osmesa ~130 ms/frame, egl ~0.4 ms). It is
therefore opt-in, in two independent layers:

| layer | who decides | how |
|---|---|---|
| does the container *see* a GPU | you, per run | `--extra-docker-compose environment/gpu.docker-compose.yaml` |
| which GL backend the process uses | `rcb_hb.py`, automatically | `_resolve_gl_backend()` |

`_resolve_gl_backend()` honours an explicit `MUJOCO_GL` and otherwise requires **both** `/dev/nvidiactl`
(the device, from `NVIDIA_VISIBLE_DEVICES`) **and** an NVIDIA EGL vendor ICD under
`/usr/share/glvnd/egl_vendor.d/` (the GL libraries, which the runtime mounts only when
`NVIDIA_DRIVER_CAPABILITIES` includes `graphics`). Requiring both is what separates "has a GPU" from
"can render on it": a CUDA-only container has the device node and would still fail with *an OpenGL
platform library has not been loaded*. The chosen backend is reported in
`/logs/verifier/diagnostics.json`.

The overlay is deliberately not named `docker-compose.yaml`, which Harbor would auto-load — an
unsatisfiable device reservation stops the container from starting at all on a machine without a GPU.

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.npz` in a fresh process, twice; pass
iff every replay's episode return reaches `success_bar` **and** the final-state hashes agree (bit-exact
determinism). `tests/grade.py` also writes `/logs/verifier/replay.mp4` and, because Harbor promotes every
`reward.json` key to a leaderboard metric, keeps the per-task numbers (`episode_return`, `success_bar`) in
`/logs/verifier/diagnostics.json`.
