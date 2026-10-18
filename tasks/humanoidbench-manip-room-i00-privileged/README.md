# humanoidbench-manip-room-i00-privileged

| | |
|---|---|
| Benchmark | HumanoidBench |
| Mode | privileged |
| Twin | `humanoidbench-manip-room-i00-standard` |
| Simulator / robot | `humanoidbench` / `unitree-h1hand` |
| Family / instance | `room` / seed 0 |
| Oracle | `none` — none known: no run has passed it, and published RL reaches 44% of the bar (paper 128, FastTD3 177, bar 400); human review in PR #9 |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-humanoidbench:0.2.0` |

## Task
HumanoidBench room: produce one replayable trajectory that tidies six objects scattered around a room with the Unitree H1, frozen scene instance 00.

## Difficulty
The pass mark is a **threshold on the whole episode's return** (`>= 400` over 1000 steps), not a
predicate on the final state.

- **The only task in the benchmark whose objective is a statistic, not a pose.** Upstream scores
  `tolerance(max(variance of the objects' x and y), margin=3)` — there is no destination to reach and no
  per-object goal. The agent has to invent the placement, which is a planning problem no other task in the
  subset poses. (This is also why the old "= `package` six times over" reading was wrong: `Room` is an
  independent `Task` with an independent reward.)
- **Six objects, 42 DoF of task state** — the widest scene in the subset — on top of 61 actuators.
  Every object moved is a chance to knock another one away.
- **Mobile manipulation without a script.** The robot must walk to each object, pick or push it, and
  return; the order is the agent's to choose, and a bad order costs the whole episode.
- **Holding the start pose lasts 123 steps** and earns 5% of the bar, so nothing is given away.

**Measured floors** (this instance, `scripts/humanoidbench/gen_tasks.py verify`): an all-zero
trajectory scores **8.84 / 400** (the episode terminates at step 70 of 1000). Holding the starting
pose instead — the floor a competent agent gets before writing a controller — scores **5.0%** of the
bar; that is the number this task was selected on (the give-away limit of `gen_tasks.py verify`).
**External evidence**: published RL results reach **44%** of the bar (paper 128, FastTD3 177, bar
400) — training runs of millions of environment steps, not a one-hour coding session, so treat it as
proof that the task *has* a solution rather than as a target.

**The agent does not see the reward function.** It is deleted from the image and restored only
inside the verifier (`images/humanoidbench/scrub_oracles.py`, `tests/rcb_rewards.py`), so the
numbers above are upstream's own scoring (on our physics: see *Physics vs upstream*) while the agent
works from the task statement and the physical state alone.

## Reference solution
None. Requiring one would cap the benchmark at what we can already solve, which systematically
removes the interesting tasks. What replaces it (docs/protocol/README.md §2.7): the floor above
(doing nothing cannot pass), the evidence that the task has a solution (`oracle_evidence` in
task.toml), and a human reviewer.

## Verification
In its own container, built from `tests/Dockerfile` (no network): the agent's container is gone by
then, and only `/app/output/` crosses over. Open-loop replay of `/app/output/trajectory.npz` from
`tests/instance.npz` in a fresh process, twice; pass iff every replay's episode return reaches
`success_bar` **and** the final-state hashes agree (bit-exact determinism). `tests/grade.py` also
writes `/logs/verifier/replay.mp4` and, because Harbor promotes every `reward.json` key to a
leaderboard metric, keeps the per-task numbers (`episode_return`, `success_bar`) in
`/logs/verifier/diagnostics.json`. No oracle; human review in PR #9. `nop` scores 0.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 4 GB | 3 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: GPU 1.1-2.3 GB, vram_profile (batch_eval_live per-trial GPU peaks, 10-03..10); memory: privileged container median 2.2 GB (p90 11 GB when agents run parallel rollouts), sim 0.7 GB, mem_guard (docker memory per container, ws-1, 10-02..10); CPU author estimate
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: no GPU, 16 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 16 GiB memory. Limits measured: memory: the [environment] cap 16 GiB, which every past trial ran under (docker peak 13.4 GiB over 27 samples, mem_guard (docker memory incl. page cache, top-4 containers every 10 min, ws-1, 10-02..10)); processes 512 and disk 10 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Capability class | C8 · mobile manipulation (see `scripts/humanoidbench/subset.toml`) |
| Physics vs upstream | upstream's model (HumanoidBench cb11890) on MuJoCo 3.3.7, not the 3.1.6 upstream pins, whose convex collision reported wrong contacts; results on image 0.1.6 or earlier are other physics and are reported apart (docs/benchmarks/humanoidbench.md, Physics). Also fixed here: **reset**: upstream's reset loops over seven objects in a scene of six and wrote the seventh's x/y into the right little finger's two joints (it started bent through its own fingertip, pressing on it with about 1.4 kN), and left the tilted headphones and a package 5-8 cm inside the floor. The finger now starts in range and every object on the floor, at upstream's positions; the frozen instance was redrawn with the fix (`images/humanoidbench/upstream-fixes.patch`). |

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
`tests/instance.npz`) is reproducible with `gen_tasks.py render room`; the instance with
`gen_tasks.py instance room` (seed 0, sha `b69705228ecf`).

### Change Log
- 2026-10-08: base image 0.1.6 -> 0.2.0: MuJoCo 3.3.7 instead of upstream's 3.1.6, and this task's own fix (*Physics vs upstream*) (docs/benchmarks/humanoidbench.md, Physics). The pass rule and verifier are unchanged, so the task keeps its name; results recorded on 0.1.6 are other physics and are reported separately.
- 2026-10-10: `reward.json` carries `deterministic` in every branch (0 where no replay ran; PROTOCOL §2.6). The verdict is unchanged.
