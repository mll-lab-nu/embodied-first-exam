# roboengineer-g1-terrain-walk-i00-standard

| | |
|---|---|
| Benchmark | roboEngineer |
| Mode | standard (`eai-policy/1.1`) |
| Twin | — (none: roboEngineer has no privileged mode, PROTOCOL §2.15) |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `roboengineer/g1-terrain-walk` / seed 0 |
| Oracle | `partial` — Harbor 0.23.0 oracle agent on aws:rcb-gpu14 (L40S), 2026-10-18, images efe-private:control-transfer-0.2.0-train / 0.2.0, an earlier planner of the reference with a fixed first segment (2500 + 1733 + 1155 PPO iterations x 4096 environments from scratch; 12638 s of the 14400 s): the reference (trains the public curriculum from scratch on the agent's GPU, three deployments, the last sealed) succeeded on 1/12 held-out cases, mean engineering score 43.14; nop 0. No full oracle: human review (PROTOCOL §4). |
| Agent time budget | 14400 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe-private:control-transfer-0.2.0` |

## Task
Train a blind 29-DoF Unitree G1 policy in mjlab/MuJoCo Warp and transfer to CPU MuJoCo over flat, sloped, rough and stepped terrain. Stand 2 s, then follow a public forward velocity command of 0.5–0.65 m/s for 18 s.

## Difficulty
Infer transfer failures from video and noisy sensors across bounded adaptation rounds.

## Reference solution
Harbor 0.23.0 oracle agent on aws:rcb-gpu14 (L40S), 2026-10-18, images efe-private:control-transfer-0.2.0-train / 0.2.0, an earlier planner of the reference with a fixed first segment (2500 + 1733 + 1155 PPO iterations x 4096 environments from scratch; 12638 s of the 14400 s): the reference (trains the public curriculum from scratch on the agent's GPU, three deployments, the last sealed) succeeded on 1/12 held-out cases, mean engineering score 43.14; nop 0. No full oracle: human review (PROTOCOL §4).

## Verification
Frozen development and held-out banks, data-only deployment, fresh-process state hashes, separate no-network verifier. All numeric scores and physical outcomes are operator-only until submission closes.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 6 | 4 |
| Memory | 15 GB | 3 GB |
| GPU memory | 20 GB | 0 GB |

- GPU: required, any NVIDIA GPU; recommended: L40S 48GB (all measurements; a 24 GB card fits the memory but trains slower, so fewer iterations fit the cutoff).
- Measured: Harbor 0.23 oracle (the reference: 4096 environments, 12638 s of training and deployments) and smoke trials on aws:rcb-gpu14 / -gpu13 (L40S, 2026-10-18; docker stats + cgroup memory.peak + nvidia-smi per container every 3-6 s): the agent's container 16.1 GiB (16492 MiB) of GPU memory, 5.3 GiB memory (5.6 GiB cgroup peak, growing over the 3.5 h run), 1.0-1.6 cores (one Python thread drives the GPU); the public trainer's default 256 environments 1.8 GB, its cap of 1024 4.7 GB; the sidecar 2.2-2.6 cores during deployments (OSMesa), its 4-CPU cap during finalization (12 held-out cases x 2 + video: 419 s), peak 2.06 GiB. Minimum: GPU = 16.1 GiB x 1.15 = 18.5, raised to 20 (headroom for the pool's VRAM reservation); memory = the agent's 12 GB cap + the sidecar's peak x 1.2 + the monitor; CPU = the sidecar's ~2.5 during deployments + the training's 1.6, rounded up to leave the agent's 4-core cap some room; the monitor: <= 0.86 GiB of new files, <= 6 processes
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: 20 GiB GPU memory, 10 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 20 GiB GPU memory, 16 GiB memory. Limits measured: the reference (4096 environments) peaked at 16.1 GiB of GPU memory and 5.6 GiB of memory in the agent's container; 20 GiB of GPU memory = the declared minimum (enough for ~4900 environments); 10 GiB of memory leaves room for an agent's own CPU rollouts; trial = the agent's 10 GiB + the sidecar's 6 GB cap (its peak 2.1 GiB); disk 0.86 GiB and 6 processes in the reference, within the design defaults.

## Details

### Notes
Simulation transfer only, not hardware. Fixed 98→512→256→128→29 ELU actor and public PD wrapper. Coding-agent feedback is noisy joint angles, public commands and images.
