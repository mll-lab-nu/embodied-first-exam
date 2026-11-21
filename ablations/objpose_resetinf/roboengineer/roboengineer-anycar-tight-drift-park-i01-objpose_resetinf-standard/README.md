# roboengineer-anycar-tight-drift-park-i01-standard

| | |
|---|---|
| Benchmark | roboEngineer |
| Mode | standard (`eai-policy/1.1`) |
| Twin | — (none: roboEngineer has no privileged mode, PROTOCOL §2) |
| Simulator / robot | `mujoco` / `anycar` |
| Family / instance | `roboengineer/anycar-tight-drift-park` / seed 1 |
| Oracle | `partial` — Harbor 0.23.0 oracle agent on a cloud CPU host, 2026-10-18, image efe-private:control-transfer-0.2.0: the reference controller (solution/, three feedback rounds) succeeded on 1/10 held-out cases, mean engineering score 6.86; nop 0. No full oracle: human review (PROTOCOL §4). |
| Agent time budget | 14400 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:control-transfer-0.2.0` |

## Task
Follow the ordered U-bend, then execute a 180-degree drifting turn into a tight inside parallel-parking space between two stationary cars and hold a precise stop.

## Difficulty
Infer transfer failures from video and noisy sensors across bounded adaptation rounds.

## Reference solution
Harbor 0.23.0 oracle agent on a cloud CPU host, 2026-10-18, image efe-private:control-transfer-0.2.0: the reference controller (solution/, three feedback rounds) succeeded on 1/10 held-out cases, mean engineering score 6.86; nop 0. No full oracle: human review (PROTOCOL §4).

## Verification
Frozen development and held-out banks, data-only deployment, fresh-process state hashes, separate no-network verifier. All numeric scores and physical outcomes are operator-only until submission closes.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 2 | 6 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 4 | 6 GiB | 1024 | no GPU | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: not needed.

## Details

### Notes
Rigid RC tire contact and rear-wheel dry-friction brake; not a calibrated pneumatic-tire drifting or vehicle-damage model.
