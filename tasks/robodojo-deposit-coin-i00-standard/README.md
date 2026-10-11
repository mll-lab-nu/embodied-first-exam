# robodojo-deposit-coin-i00-standard

| | |
|---|---|
| Benchmark | RoboDojo |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `robodojo-deposit-coin-i00-privileged` |
| Simulator / robot | `robodojo` / `arx-x5-bimanual` |
| Family / instance | `deposit_coin` |
| Oracle | `none` — no positive example yet (the privileged twin has a positive example (Codex + GPT-6 Luna, effort xhigh, run `codex-gpt6_luna-xhigh`, 2026-10-10)); no reference solution (RoboDojo releases no expert, and its training demonstrations carry no initial state); reported separately until one exists; human review in PR #142 |
| Agent time budget | 5400 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-robodojo:0.1.0` |

## Task
Standard-mode twin of `robodojo-deposit-coin-i00-privileged` (same frozen layout, RoboDojo's `arx_x5/0/deposit_coin_0.json`). Pick the coin up from the vertical coin holder and drop it into the piggy bank (coin bank) through its slot, then return the arm home. (RoboDojo's `deposit_coin`). The agent drives the
robot only through the eai-standard/2.2 client (the simulator runs in the `sim` sidecar), which owns the scene and records
the episode as a (T, 14) trajectory of RoboDojo's own joint action at 25 Hz.

## Difficulty
A RoboDojo Precision task (rigid objects), graded by RoboDojo's own success thresholds (its evaluation gives a policy 300 actions; no step cap here, PROTOCOL D1). Here the agent sees only the three cameras (RGB, optional depth) and the arms' proprioception: no object
poses, no success signal, no reset, one episode (no step cap; RoboDojo's own evaluation gives a policy 300 actions).

## Reference solution
None (see the privileged twin): RoboDojo releases no expert or planner script, and its training demonstrations record no
initial state, so none replays on a frozen layout. The task is reported separately until it has a positive example
(PROTOCOL §7, Open 4).

## Verification
The sim service ends the episode on RoboDojo's own check (success), a failed check, the runaway guard or the time limit, and
writes `/data/trajectory.npz`; the collect hook (`environment/sim/finalize.sh`) replays it from the frozen layout in two
fresh processes; `tests/grade.py` scores 1 iff the live episode succeeded and both replays succeed and both end in the same state hash. No oracle;
human review in PR #142 (no positive example yet). `nop` (no actions) scores 0.

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 8 | 8 |
| Memory | 20 GB | 19 GB |
| GPU memory | 11 GB | 11 GB |

- GPU: required, an RTX-class NVIDIA GPU (ray-tracing cores, for Isaac Sim / Omniverse RTX rendering); recommended: L40S 48GB / L4 24GB / RTX 4090 24GB.
- Measured: heaviest scene (pour_liquid_into_cup_random), a client driving 12 joint_position chunks, then the collect hook's two fresh-process replays (the first filmed): sim sidecar docker peak 16.0 GiB (anon 14.9), GPU 9.5 GiB, up to 16 cores while Isaac starts; agent container under 0.1 GiB; per-container sampler (docker stats, cgroup anon, nvidia-smi every 10 s), RTX 4090, 10-10; the verifier phase replays as the privileged verifier does (docker peak 15.7 GiB, GPU 9.6 GiB)
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 16 GiB GPU memory, 33 GiB memory. Limits measured: GPU (sim sidecar): 9.5 GiB on the heaviest scene (sampler, RTX 4090, 10-10) -> max(1.5 x peak, peak + 4), at least 16 for Isaac Sim; memory: agent container max(1.5 x peak, peak + 4, 8) = 8 (a client under 0.1 GiB; no agent-trial sample yet); whole trial: + the sim sidecar's 25 GiB (docker peak 16.0 GiB); processes 512 and disk 20 GiB: design defaults.

## Details
| | |
|---|---|
| Episode | one episode, no reset: it ends at the first action where RoboDojo's check passes, when a check fails for good, when the agent's time is up, or on a simulator error; no step cap (RoboDojo's evaluation gives a policy 300 actions; a runaway guard at 15000) |
| Action space | `submit` chunks of `joint_position` (14: RoboDojo's own action at 25 Hz, the agent's `dt` a multiple of 1/25 s) or `ee_pose` (16: both arms' link6 targets, IK per row); `observe` frames or a watch window; `/kinematics` (FK / IK of both arms, stateless); binary RCB1 responses |
| Source | RoboDojo @ `cb2a37d` (MIT), its Isaac Lab 2.3 fork @ `afca7b0`, its cuRobo fork @ `d17b54c`; assets from `RoboDojo-Benchmark/RoboDojo` @ `35efbc7` (Apache-2.0) |
| Benchmark notes | docs/benchmarks/robodojo.md |
