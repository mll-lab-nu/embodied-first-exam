# bigym2-put-cups-i00-standard

| | |
|---|---|
| Benchmark | BiGym 2.0 |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `bigym2-put-cups-i00-privileged` |
| Simulator / robot | `bigym2` / `unitree-g1-dex1` |
| Family / instance | `put-cups` / seed 0 |
| Oracle | `none` — no reference solution (BiGym 2.0 ships no expert or planner; its demonstrations and its agents' programs stay off the agent's network); no positive example yet; human review in PR #123 |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:bigym2-0.1.1` |

## Task
Take the cups from the counter and gently put them away in the wall cabinet. (BiGym 2.0 `put_cups`; the robot as a service: its three onboard cameras and its proprioception only, one
episode.)

## Difficulty
Two stages: open the wall cabinet's glass door, then place two cups on its bottom shelf, released. In standard mode the agent sees only the robot's cameras (the head camera looks down at the hands at the
start) and proprioception, acts through the client, and gets one episode, no reset.

## Reference solution
None (as `bigym2-put-cups-i00-privileged`).

## Verification
The sim sidecar judges the live episode with BiGym's own success check (`is_success`: the task's success held for 1 s,
no fall) and writes that verdict to `/data/final.json` (`graded_by = "live"`); nothing is replayed to grade it (owner,
2026-10-17). The scene's start is checked against the frozen instance (`instance.json`'s `t0`) when an
episode begins (a mismatch is `instance_mismatch`, infrastructure). `tests/grade.py` reads `final.json`: pass iff the
live episode succeeded. The video (`replay.mp4`) is rendered from `trajectory.npz` in one pass after the verdict and
never changes it. Success condition: both cups touch the bottom shelf of the wall cabinet (its glass doors start closed) and neither is held by a gripper. No oracle; human review in PR #123 (PROTOCOL §4).

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 4 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 2 | 6 GiB | 1024 | 4 GiB | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: any NVIDIA GPU, held by `sim`.
- Recommended GPU: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).

## Details
| | |
|---|---|
| Service | `environment/sim/server.py` (the BiGym 2.0 adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_bigym2.py`, `instance.json` (= the privileged twin's) |
| Observations | three onboard RGB cameras (`RCB_IMAGE_HW`, default 84 px square, as upstream renders them, 60° field of view); upstream's low-dimensional observation (joints, grippers, tracked pelvis pose) |
| Horizon | 3000 control steps (60 s at 50 Hz) |
