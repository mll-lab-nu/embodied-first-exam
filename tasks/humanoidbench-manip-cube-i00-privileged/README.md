# humanoidbench-manip-cube-i00-privileged

| | |
|---|---|
| Benchmark | HumanoidBench |
| Mode | privileged |
| Twin | `humanoidbench-manip-cube-i00-standard` |
| Simulator / robot | `humanoidbench` / `unitree-h1hand` |
| Family / instance | `cube` / seed 0 |
| Oracle | `none` — none known: no run has passed it, and published RL reaches 60% of the bar (paper 135, FastTD3 221, bar 370); human review in PR #9 |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-humanoidbench:0.2.0` |

## Task
HumanoidBench cube: produce one replayable trajectory that reorients two cubes in the Unitree H1's hands, frozen scene instance 00.

## Difficulty
The pass mark is a **threshold on the whole episode's return** (`>= 370` over 500 steps), not a
predicate on the final state.

- **The only true in-hand reorientation in the benchmark.** Both hands work at once, and the object
  has to be rotated *within* the grasp — fingers must release and re-grip without letting the cube fall,
  which is a qualitatively different skill from `insert_normal`'s rigid-grip transport.
- **A sharp objective with a cliff on both sides.** The orientation term decays fast, and dropping a
  cube ends the episode; holding the start pose lasts only 83 steps.
- **Goal state outside `(qpos, qvel)`.** Upstream puts the target orientation in `model.body_quat[-1]`,
  drawn from the global `np.random` that `reset(seed=)` does not reach. The instance snapshot covers
  `body_quat` for exactly this task; without it, agent and verifier would
  be rotating towards different targets.
- **One instance only**: `env.py` forces `randomness = 0` for this family, as it does for
  `bookshelf_*` and `kitchen`.

**Measured floors** (this instance, `scripts/humanoidbench/gen_tasks.py verify`): an all-zero
trajectory scores **5.00 / 370** (the episode terminates at step 17 of 500). Holding the starting
pose instead — the floor a competent agent gets before writing a controller — scores **10.2%** of
the bar; that is the number this task was selected on (the give-away limit of `gen_tasks.py
verify`). **External evidence**: published RL results reach **60%** of the bar (paper 135, FastTD3
221, bar 370) — training runs of millions of environment steps, not a one-hour coding session, so
treat it as proof that the task *has* a solution rather than as a target.

**The agent does not see the reward function.** It is deleted from the image and restored only
inside the verifier (`images/humanoidbench/scrub_oracles.py`, `tests/rcb_rewards.py`), so the
numbers above are upstream's own scoring (on our physics: see *Physics vs upstream*) while the agent
works from the task statement and the physical state alone.

## Reference solution
None. Requiring one would cap the benchmark at what we can already solve, which systematically
removes the interesting tasks. What replaces it (docs/PROTOCOL.md §2.7): the floor above (doing
nothing cannot pass), the evidence that the task has a solution (`oracle_evidence` in task.toml),
and a human reviewer.

## Verification
In its own container, built from `tests/Dockerfile` (no network): the agent's container is gone by
then, and only `/app/output/` crosses over. Open-loop replay of `/app/output/trajectory.npz` from
`tests/instance.npz` in a fresh process, twice; pass iff every replay's episode return reaches
`success_bar` **and** the final-state hashes agree (bit-exact determinism). `tests/grade.py` also
writes `/logs/verifier/replay.mp4` and, because Harbor promotes every `reward.json` key to a
leaderboard metric, keeps the per-task numbers (`episode_return`, `success_bar`) in
`/logs/verifier/diagnostics.json`. No oracle; human review in PR #9. `nop` scores 0.

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 4 GB | 3 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: GPU 1.1-2.3 GB, vram_profile (batch_eval_live per-trial GPU peaks, 10-03..10); memory: privileged container median 2.2 GB (p90 11 GB when agents run parallel rollouts), sim 0.7 GB, mem_guard (docker memory per container, ws-1, 10-02..10); CPU author estimate
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: no GPU, 16 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 16 GiB memory. Limits measured: memory: the [environment] cap 16 GiB, which every past trial ran under (docker peak 13.4 GiB over 27 samples, mem_guard (docker memory incl. page cache, top-4 containers every 10 min, ws-1, 10-02..10)); processes 512 and disk 10 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Capability class | C7 · in-hand precision (see `scripts/humanoidbench/subset.toml`) |
| Physics vs upstream | upstream's model (HumanoidBench cb11890) on MuJoCo 3.3.7, not the 3.1.6 upstream pins, whose convex collision reported wrong contacts; results on image 0.1.6 or earlier are other physics and are reported apart (docs/benchmarks/humanoidbench.md, Physics). |

### GPU
Optional, and passing never depends on it: MuJoCo physics is CPU-only, so a GPU only speeds up the
agent's own offscreen rendering (osmesa ~130 ms/frame, egl ~0.4 ms). Hand one to the agent's
container with `--extra-docker-compose environment/gpu.docker-compose.yaml`; `rcb_hb.py` then picks
EGL by itself unless `MUJOCO_GL` says otherwise. The overlay is not named `docker-compose.yaml`
because Harbor would load that on every machine, and a device reservation the host cannot satisfy
stops the container from starting.

### Provenance
Generated by `scripts/humanoidbench/gen_tasks.py` from `scripts/humanoidbench/subset.toml`.
Everything in this directory except the instance (`environment/instance.npz` and its byte copy
`tests/instance.npz`) is reproducible with `gen_tasks.py render cube`; the instance with
`gen_tasks.py instance cube` (seed 0, sha `6d64a2c0cdbd`).

### Change Log
- 2026-10-08: base image 0.1.6 -> 0.2.0: MuJoCo 3.3.7 instead of upstream's 3.1.6 (docs/benchmarks/humanoidbench.md, Physics). The pass rule and verifier are unchanged, so the task keeps its name; results recorded on 0.1.6 are other physics and are reported separately.
- 2026-10-10: `reward.json` carries `deterministic` in every branch (0 where no replay ran; PROTOCOL §2.6). The verdict is unchanged.
