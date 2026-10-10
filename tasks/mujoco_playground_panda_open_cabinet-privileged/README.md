# mujoco_playground_panda_open_cabinet-privileged

| | |
|---|---|
| Benchmark | MuJoCo Playground |
| Mode | privileged |
| Twin | `mujoco_playground_panda_open_cabinet-standard` |
| Simulator / robot | `mujoco` / `franka-panda` |
| Family / instance | `mujoco_playground/PandaOpenCabinet` / seed 60417 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-mujoco:0.1.2` |

## Task
MuJoCo Playground's `PandaOpenCabinet` ported to plain MuJoCo (CPU, deterministic) for this benchmark.

## Difficulty
MuJoCo Playground defines only a shaped RL reward; this task scores a binary success defined from it (handle within 1.5 cm of the target along x at the end), so a trajectory has to actually finish the manipulation rather than collect partial reward.

## Reference solution
`solution/oracle_ik.py`: to Playground's `home` posture, horizontal approach, pull with correction (3.7 mm, 457 control steps). The recorded solution moves the handle mostly by contact rather than a clean grasp; it still proves the target reachable

## Verification
Playground has only a shaped RL reward; defined here: handle within 1.5 cm of the target along x at the end

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 4 GB | 3 GB |
| GPU memory | 1.5 GB | 1.5 GB |

- GPU: required, any NVIDIA GPU; recommended: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).
- Measured: GPU 1.0-1.3 GB, vram_profile (batch_eval_live per-trial GPU peaks, 10-03..10); memory: privileged container p90 2.6 GB, sim 0.7 GB, mem_guard (docker memory per container, mll-4090-1, 10-02..10); CPU p90 1.9 cores, live sampler (docker stats + cgroup anon + nvidia-smi every 30 s, 13 AWS hosts + mll-4090-1, 10-10)
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; exceeding one fails the trial), every container of the trial: 4 GB GPU memory, 8 GB memory, 512 processes, 10 GB written under `/app`; sustained 60 s. Expected peak of the whole trial: 4 GB GPU memory, 8 GB memory.

## Details
| | |
|---|---|
| source | [MuJoCo Playground](https://github.com/google-deepmind/mujoco_playground) @ 4057c14 (Apache-2.0): `manipulation/franka_emika_panda/xmls/mjx_cabinet.xml`; Panda from MuJoCo Menagerie @ 1b86ece |
| physics | MuJoCo 3.3.7, 200 Hz (Playground's sim_dt), implicitfast; control 50 Hz (4 substeps) |
| instance | Playground's reset randomization (target x = 0.3 ± 0.1 m; arm start = `upright` + up to 30° per joint) drawn with seed 60417; initial-state hash in instance.json |
| success | Playground has only a shaped RL reward; defined here: handle within 1.5 cm of the target along x at the end |
| deliverable | `(T, 8)` actuator targets per control step, T ≤ 3000; bit-exact replay |
