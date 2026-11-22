# roboengineer-g1-terrain-walk-i01-standard

| | |
|---|---|
| Benchmark | roboEngineer |
| Mode | standard (`eai-policy/1.1`) |
| Twin | — (none: roboEngineer has no privileged mode, PROTOCOL §2) |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `roboengineer/g1-terrain-walk` / seed 1 |
| Oracle | `partial` — Harbor 0.23.0 oracle agent on a cloud L40S host, 2026-10-18, images efe-private:control-transfer-0.2.0-train / 0.2.0 (200 + 2466 + 1479 + 986 PPO iterations x 4096 environments from scratch; 12009 s of the 14400 s; round 0 passed all four development cases, the later, sealed rounds drifted sideways): the reference (trains the public curriculum from scratch on the agent's GPU, three deployments, the last sealed) succeeded on 4/12 held-out cases, mean engineering score 82.68; nop 0. No full oracle: human review (PROTOCOL §4). |
| Agent time budget | 14400 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:control-transfer-0.2.0` |

## Task
Train a blind 29-DoF Unitree G1 policy in mjlab/MuJoCo Warp and transfer to CPU MuJoCo over flat, sloped, rough and stepped terrain. Stand 2 s, then follow a public forward velocity command of 0.5–0.65 m/s for 18 s.

## Difficulty
Infer transfer failures from video and noisy sensors across bounded adaptation rounds.

## Reference solution
Harbor 0.23.0 oracle agent on a cloud L40S host, 2026-10-18, images efe-private:control-transfer-0.2.0-train / 0.2.0 (200 + 2466 + 1479 + 986 PPO iterations x 4096 environments from scratch; 12009 s of the 14400 s; round 0 passed all four development cases, the later, sealed rounds drifted sideways): the reference (trains the public curriculum from scratch on the agent's GPU, three deployments, the last sealed) succeeded on 4/12 held-out cases, mean engineering score 82.68; nop 0. No full oracle: human review (PROTOCOL §4).

## Verification
Frozen development and held-out banks, data-only deployment, fresh-process state hashes, separate no-network verifier. All numeric scores and physical outcomes are operator-only until submission closes.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 12 GiB | 1024 | 20 GiB | 10 GiB |
| `sim` | 4 | 6 GiB | 1024 | no GPU | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: any NVIDIA GPU, held by `main`.
- Recommended GPU: L40S 48GB (all measurements; a 24 GB card fits the memory but trains slower, so fewer iterations fit the cutoff).

## Details

### Notes
Simulation transfer only, not hardware. Fixed 98→512→256→128→29 ELU actor and public PD wrapper. Coding-agent feedback is noisy joint angles, public commands and images.
