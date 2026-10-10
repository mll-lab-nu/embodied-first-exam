# bigym2-dishwasher-close-i00-standard-realtime

| | |
|---|---|
| Benchmark | BiGym 2.0 |
| Mode | standard-realtime (`eai-standard/2.3`) |
| Twin | `bigym2-dishwasher-close-i00-privileged` |
| Simulator / robot | `bigym2` / `unitree-g1-dex1` |
| Family / instance | `dishwasher-close` / seed 0 |
| Oracle | `none` — no reference solution (BiGym 2.0 ships no expert or planner; its demonstrations and its agents' programs stay off the agent's network); positive example graded 1 by the separate verifier: bigym2-dishwasher-close-i00-priv__BtaZZZZ (run codex-gpt6_luna-medium, 2026-10-08, on an earlier text of the privileged task; regraded by its current verifier); human review in PR #123 |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-bigym2:0.1.1` |

## Task
Push the dishwasher racks in and close the door. (BiGym 2.0 `dishwasher_close`; the robot as a service on a clock that does not stop: its three onboard cameras and
its proprioception only, one episode.)

## Difficulty
Three articulated joints low in front of the robot (two racks and a door), pushed fully closed to within 5% of their travel, which takes squatting and leaning. In standard-realtime mode the robot keeps running at 50 Hz while the agent thinks, holding its last
command (standing still), so the agent drives it from a controller program of its own.

## Reference solution
None (as `bigym2-dishwasher-close-i00-privileged`).

## Verification
As `bigym2-dishwasher-close-i00-standard`: the sidecar judges the live episode with BiGym's own success check and replays the commands the
simulator executed in a fresh simulator; `tests/grade.py` reads `/data/final.json`. Success condition: the door and both racks are closed to within 5% of their travel: the door within about 4.5 degrees of shut, the lower rack within 0.025 m and the upper rack within 0.0225 m of fully in.
No oracle; human review in PR #123 (PROTOCOL §2.7).

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 4 GB | 3 GB |
| GPU memory | 1.5 GB | 1.5 GB |

- GPU: required, any NVIDIA GPU; recommended: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).
- Measured: GPU 0.7-1.2 GB, vram_profile (batch_eval_live per-trial GPU peaks, 10-03..10); memory: privileged container 3.0 GB, mem_guard (docker memory per container, mll-4090-1, 10-02..10); CPU author estimate (MuJoCo + two ONNX policies on the CPU)
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; exceeding one fails the trial), the agent's container: no GPU, 16 GB memory, 512 processes, 10 GB written under `/app`; sustained 60 s. Expected peak of the whole trial: 4 GB GPU memory, 20 GB memory.

## Details
| | |
|---|---|
| Service | `environment/sim/rcb_realtime.py` (eai-standard/2.3) with the BiGym 2.0 adapter `server.py`, `rcb_bigym2.py`, `instance.json` (= the privileged twin's) |
| Clock | real time (`RCB_SLOWDOWN`, default 1) from the first `submit` |
| Horizon | 4650 control steps (93 s at 50 Hz) |
