# bigym2-sandwich-remove-i00-standard

| | |
|---|---|
| Benchmark | BiGym 2.0 |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `bigym2-sandwich-remove-i00-privileged` |
| Simulator / robot | `bigym2` / `unitree-g1-dex1` |
| Family / instance | `sandwich-remove` / seed 0 |
| Oracle | `none` — no reference solution (BiGym 2.0 ships no expert or planner; its demonstrations and its agents' programs stay off the agent's network); no positive example yet; human review in PR #123 |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-bigym2:0.1.1` |

## Task
Use the spatula to move the sandwich from the frying pan onto the chopping board. (BiGym 2.0 `sandwich_remove`; the robot as a service: its three onboard cameras and its proprioception only, one
episode.)

## Difficulty
Tool use: the sandwich may only be moved with the spatula (a gripper on it fails the episode), and must end flat on the board. In standard mode the agent sees only the robot's cameras (the head camera looks down at the hands at the
start) and proprioception, acts through the client, and gets one episode, no reset.

## Reference solution
None (as `bigym2-sandwich-remove-i00-privileged`).

## Verification
The sim sidecar judges the live episode with BiGym's own success check (`is_success`: the task's success held for 1 s,
no fall) and writes that verdict to `/data/final.json` (`graded_by = "live"`); nothing is replayed to grade it (owner,
2026-10-17, board 0151). The scene's start is checked against the frozen instance (`instance.json`'s `t0`) when an
episode begins (a mismatch is `instance_mismatch`, infrastructure). `tests/grade.py` reads `final.json`: pass iff the
live episode succeeded. The video (`replay.mp4`) is rendered from `trajectory.npz` in one pass after the verdict and
never changes it. Success condition: the sandwich lies flat (either face up, within 10 degrees of level) touching the chopping board. A finger of either gripper touching the sandwich ends the episode as a failure: move it with the spatula. No oracle; human review in PR #123 (PROTOCOL §2.7).

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 4 GB | 3 GB |
| GPU memory | 1.5 GB | 1.5 GB |

- GPU: required, any NVIDIA GPU; recommended: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).
- Measured: GPU 0.7-1.2 GB, vram_profile (batch_eval_live per-trial GPU peaks, 10-03..10); memory: privileged container 3.0 GB, mem_guard (docker memory per container, ws-1, 10-02..10); CPU author estimate (MuJoCo + two ONNX policies on the CPU)
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 6 GiB GPU memory, 16 GiB memory. Limits measured: GPU: 1.2 GiB (batch_eval_live vram_profile (per-trial GPU peaks by card, 10-03..10)) -> max(1.5 x peak, peak + 4); memory: no samples of the agent's container; floor 8 GiB (at most the 16 GiB cap); whole trial: + the sim service's 8 GiB (from the minimum: no samples); processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Service | `environment/sim/server.py` (the BiGym 2.0 adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_bigym2.py`, `instance.json` (= the privileged twin's) |
| Observations | three onboard RGB cameras (`RCB_IMAGE_HW`, default 84 px square, as upstream renders them, 60° field of view); upstream's low-dimensional observation (joints, grippers, tracked pelvis pose) |
| Horizon | 3150 control steps (63 s at 50 Hz) |

### Change Log
- 2026-10-11: `RCB_RESET_BUDGET`'s default 0 -> 10 (owner decision; PROTOCOL §4.5,
  docs/benchmarks/bigym2.md); the service already had `POST /reset`. The scene, instance, pass rule and verifier are
  unchanged, so the task keeps its name; runs recorded before this date had no reset and are reported separately.
- 2026-10-16: `RCB_RESET_BUDGET`'s default 10 -> 0 (author decision; PROTOCOL §2, the protocol's default,
  docs/benchmarks/bigym2.md): one episode, which the practice and the graded attempt share; the instruction says there
  is no reset. The scene, instance, pass rule and verifier are unchanged, so the task keeps its name; runs recorded
  with 10 resets are reported separately.
- 2026-10-17 (owner, board 0150/0151): graded by the live episode: `success` = BiGym's own `is_success` in the episode
  the sim service ran (the same rule, judged as it ran), and no grading replay runs (no `replay_success` /
  `deterministic` any more; `final.json` has `graded_by = "live"`, `replays = 0`, `reward.json` `graded_by_live = 1`).
  The video is one render pass over the trajectory after the verdict, as before. The scene's start is checked when an
  episode begins: a scene that does not rebuild the frozen instance's starting state (exactly, or within upstream's
  tolerance on another CPU) gives up as infrastructure (`instance_mismatch`). The scene, instance, pass rule and the
  agent's interface are unchanged, so the task keeps its name; every archived verdict is the same under the live rule.
