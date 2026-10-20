# humanoidbench-manip-window-i00-privileged

| | |
|---|---|
| Benchmark | HumanoidBench |
| Mode | privileged |
| Twin | `humanoidbench-manip-window-i00-standard` |
| Simulator / robot | `humanoidbench` / `unitree-h1hand` |
| Family / instance | `window` / seed 0 |
| Oracle | `none` — none known: no run has passed it, and published RL reaches 94% of the bar (paper 227, FastTD3 613, bar 650); human review in PR #9 |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:humanoidbench-0.2.0` |

## Task
HumanoidBench window: produce one replayable trajectory that wipes a window with a tool held by the Unitree H1, frozen scene instance 00.

## Difficulty
The pass mark is a **threshold on the whole episode's return** (`>= 650` over 1000 steps), not a
predicate on the final state.

- **Tool use with sustained contact.** The subset's one tool-use task, scored on the tool's contact
  with a surface. The tool is not the goal, it is the means: the
  robot has to grasp it, then control the *tool's* contact with a surface while moving. Losing the grip
  ends the episode.
- **61 actuators.** Two Shadow hands take the action from 19 numbers to 61 — the same capability class
  as `push` at triple the search dimension.
- **A zero-valued contact gate.** Wiping without touching the glass scores nothing for the contact half
  of the reward.
- **An all-zero trajectory terminates at step 17**, tied with `cube` for the fastest failure in the
  subset: the tool is dropped almost immediately.

**Measured floors** (this instance): an all-zero
trajectory scores **1.55 / 650** (the episode terminates at step 17 of 1000). Holding the starting
pose instead — the floor a competent agent gets before writing a controller — scores **1.4%** of the
bar; that is the number this task was selected on (the benchmark's give-away limit).
**External evidence**: published RL results reach **94%** of the bar (paper 227, FastTD3 613, bar
650) — training runs of millions of environment steps, not a one-hour coding session, so treat it as
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
- Measured: GPU 1.1-2.3 GB, evaluation-pool GPU profile (per-trial GPU peaks, 10-03..10); memory: privileged container median 2.2 GB (p90 11 GB when agents run parallel rollouts), sim 0.7 GB, mem_guard (docker memory per container, an RTX 4090 workstation, 10-02..10); CPU author estimate
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: no GPU, 16 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 16 GiB memory. Limits measured: memory: the [environment] cap 16 GiB, which every past trial ran under (docker peak 13.4 GiB over 27 samples, mem_guard (docker memory incl. page cache, top-4 containers every 10 min, an RTX 4090 workstation, 10-02..10)); processes 512 and disk 10 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Capability class | C6 · standing bimanual manipulation |
| Physics vs upstream | upstream's model (HumanoidBench cb11890) on MuJoCo 3.3.7, not the 3.1.6 upstream pins, whose convex collision reported wrong contacts; results on image 0.1.6 or earlier are other physics and are reported apart (tasks/humanoidbench/README.md, Physics). |

### GPU
Optional, and passing never depends on it: MuJoCo physics is CPU-only, so a GPU only speeds up the
agent's own offscreen rendering (osmesa ~130 ms/frame, egl ~0.4 ms). Hand one to the agent's
container with `--extra-docker-compose environment/gpu.docker-compose.yaml`; `rcb_hb.py` then picks
EGL by itself unless `MUJOCO_GL` says otherwise. The overlay is not named `docker-compose.yaml`
because Harbor would load that on every machine, and a device reservation the host cannot satisfy
stops the container from starting.

### Provenance
The instance (`environment/instance.npz` and its byte copy `tests/instance.npz`) is seed 0 (sha `260f3f1c4cff`).

### Change Log
- 2026-10-08: base image 0.1.6 -> 0.2.0: MuJoCo 3.3.7 instead of upstream's 3.1.6 (tasks/humanoidbench/README.md, Physics). The pass rule and verifier are unchanged, so the task keeps its name; results recorded on 0.1.6 are other physics and are reported separately.
- 2026-10-10: `reward.json` carries `deterministic` in every branch (0 where no replay ran; PROTOCOL §2.6). The verdict is unchanged.
