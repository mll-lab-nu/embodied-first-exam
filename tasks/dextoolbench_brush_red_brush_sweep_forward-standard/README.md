# dextoolbench_brush_red_brush_sweep_forward-standard

| | |
|---|---|
| Benchmark | DexToolBench |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `dextoolbench_brush_red_brush_sweep_forward-privileged` |
| Simulator / robot | `mujoco` / `kuka-iiwa14-sharpa-ha4` |
| Family / instance | `dextoolbench/brush/red_brush/sweep_forward` / seed 0 |
| Oracle | `partial` — SimToolReal's pretrained policy, replayed in this scene, reaches 20/38 goals (solution/; README of dextoolbench_brush_red_brush_sweep_forward-privileged) |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-mujoco:0.1.2` |

## Task
Standard-mode twin of `dextoolbench_brush_red_brush_sweep_forward-privileged` (see its README): the same scene, instance and scoring, served as a robot service (`images/mujoco/limited/server_mj.py`, protocol eai-standard/2.1, tooling `rcb_dtb`). The agent sees camera RGB-D and proprioception only.

## Difficulty
Same scene, instance and success rule as `dextoolbench_brush_red_brush_sweep_forward-privileged` (see its Difficulty). In standard mode the agent loses resets, privileged state and planning primitives: it sees camera images and proprioception only, acts through the client, and gets one episode, so it has to estimate the scene from images and recover from its own mistakes without starting over.

## Reference solution
`solution/`: the privileged-mode oracle's recorded targets submitted through the client (one row per control step)

## Verification
the sidecar replays the recorded episode in a fresh simulator; `deterministic` = same final state as the live episode

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 4 GB | 3 GB |
| GPU memory | 1.5 GB | 1.5 GB |

- GPU: required, any NVIDIA GPU; recommended: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).
- Measured: GPU 0.3-0.9 GB on 24 GB cards, vram_profile (batch_eval_live per-trial GPU peaks, 10-03..10); memory: sim p90 0.9 GB, privileged container p90 4.4 GB, mem_guard (docker memory per container, mll-4090-1, 10-02..10); CPU author estimate
