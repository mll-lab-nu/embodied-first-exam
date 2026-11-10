# bigym2-reach-target-dual-i00-realtime

| | |
|---|---|
| Benchmark | BiGym 2.0 |
| Mode | realtime (`eai-standard/2.3`) |
| Twin | `bigym2-reach-target-dual-i00-privileged` |
| Simulator / robot | `bigym2` / `unitree-g1-dex1` |
| Family / instance | `reach-target-dual` / seed 0 (allowed seeds: [0, 620100, 620101]; PROTOCOL §2) |
| Oracle | `none` — no reference solution (BiGym 2.0 ships no expert or planner; its demonstrations and its agents' programs stay off the agent's network); positive example graded 1 by the separate verifier: bigym2-reach-target-dual-i00-pri__fxPRBTg (run codex-gpt6_luna-medium, 2026-10-08, on an earlier text of the privileged task; regraded by its current verifier); human review in PR #123 |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Real time | slowdown S = 1 (the world runs at 1/S of real speed: one control step every S x control_dt s of wall time; `RCB_SLOWDOWN`'s default); reset budget 0 (`RCB_RESET_BUDGET`'s default) (PROTOCOL §3) |
| Base image | `ghcr.io/mll-lab-nu/efe:bigym2-0.1.1` |

## Task
Touch the red sphere with your left hand and the green sphere with your right hand at the same time. (BiGym 2.0 `reach_target_dual`; the robot as a service on a clock that does not stop: its three onboard cameras and
its proprioception only, one episode.)

## Difficulty
Both arms at once, each to its own 5 cm ball, while the controller balances the body; the shortest task (14 s). In realtime mode the robot keeps running at 50 Hz while the agent thinks, holding its last
command (standing still), so the agent drives it from a controller program of its own.

## Reference solution
None (as `bigym2-reach-target-dual-i00-privileged`).

## Verification
As `bigym2-reach-target-dual-i00-standard`: the sidecar judges the live episode with BiGym's own success check and writes that verdict to
`/data/final.json` (`graded_by = "live"`); nothing is replayed to grade it (owner, 2026-10-17). The
trajectory holds the commands the simulator executed at each control step, so it reproduces the live run whatever the
timing was; the video is rendered from it in one pass after the verdict. `tests/grade.py` reads `final.json`. After
the agent's first command, a simulator error raised by a control step and a simulator crash inside a control step (a
fatal signal) are the agent's 0; before it, a kill, a failed resume and a reset that does not rebuild the scene are infrastructure
(`infra_error = 1`; owner, 2026-10-17, docs/protocol/standard_mode.md). Success condition: the point between the left gripper's two finger pads is inside the red sphere and the right gripper's inside the green sphere at the same time: each within 0.05 m of its sphere's centre (the spheres' radius).
No oracle; human review in PR #123 (PROTOCOL §4).

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 4 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 4 | 6 GiB | 1024 | 4 GiB | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: any NVIDIA GPU, held by `sim`.
- Recommended GPU: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).

## Details
| | |
|---|---|
| Service | `environment/sim/rcb_realtime.py` (eai-standard/2.3) with the BiGym 2.0 adapter `server.py`, `rcb_bigym2.py`, `instance.json` (= the privileged twin's) |
| Clock | real time (`RCB_SLOWDOWN`, default 1) from the first `submit` |
| Horizon | 700 control steps (14 s at 50 Hz) |
