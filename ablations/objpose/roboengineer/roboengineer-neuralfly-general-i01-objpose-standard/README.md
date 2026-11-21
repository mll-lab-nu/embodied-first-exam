# roboengineer-neuralfly-general-i01-standard

| | |
|---|---|
| Benchmark | roboEngineer |
| Mode | standard (`eai-policy/1.1`) |
| Twin | — (none: roboEngineer has no privileged mode, PROTOCOL §2) |
| Simulator / robot | `mujoco` / `neural-fly-partial` |
| Family / instance | `roboengineer/neuralfly-general` / seed 1 |
| Oracle | `partial` — Harbor 0.23.0 oracle agent on a cloud CPU host, 2026-10-18, image efe-private:control-transfer-0.2.0: the reference controller (solution/, three feedback rounds) succeeded on 8/10 held-out cases, mean engineering score 71.61; nop 0. No full oracle: human review (PROTOCOL §4). |
| Agent time budget | 14400 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:control-transfer-0.2.0` |

## Task
Track six timed laps of a randomized figure eight: vertical, horizontal or inclined plane; yaw in [-pi,pi]; both traversal directions; half extents 0.9-1.5 m and 0.45-0.85 m; angular rate 0.8-1.1 rad/s; randomized phase, center and initial offset. Follow the provided world-frame position, velocity and acceleration commands.

## Difficulty
Infer transfer failures from video and noisy sensors across bounded adaptation rounds.

## Reference solution
Harbor 0.23.0 oracle agent on a cloud CPU host, 2026-10-18, image efe-private:control-transfer-0.2.0: the reference controller (solution/, three feedback rounds) succeeded on 8/10 held-out cases, mean engineering score 71.61; nop 0. No full oracle: human review (PROTOCOL §4).

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
Flight-data quadratic force surrogate and approximate rigid-body/actuator dynamics; not a learned aerodynamics model or flight-stack simulation. Fixed 50-degree command tilt envelope; 2.2 thrust-to-weight limit.
