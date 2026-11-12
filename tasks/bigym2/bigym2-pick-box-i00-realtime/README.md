# bigym2-pick-box-i00-realtime

| | |
|---|---|
| Benchmark | BiGym 2.0 |
| Mode | realtime (`eai-standard/2.3`) |
| Twin | `bigym2-pick-box-i00-privileged` |
| Simulator / robot | `bigym2` / `unitree-g1-dex1` |
| Family / instance | `pick-box` / seed 0 (allowed seeds: [0, 620100, 620101]; PROTOCOL §2) |
| Oracle | `none` — no reference solution (BiGym 2.0 ships no expert or planner; its demonstrations and its agents' programs stay off the agent's network); no positive example yet; human review in PR #123 |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Real time | slowdown S = 1 (the world runs at 1/S of real speed: one control step every S x control_dt s of wall time; `RCB_SLOWDOWN`'s default); reset budget 0 (`RCB_RESET_BUDGET`'s default) (PROTOCOL §3) |
| Base image | `ghcr.io/mll-lab-nu/efe:bigym2-0.1.1` |

## Task
Pick the cardboard box up from the side table and gently set it down on the kitchen counter. (BiGym 2.0 `pick_box`; the robot as a service on a clock that does not stop: its three onboard cameras and
its proprioception only, one episode.)

## Difficulty
Whole-body carry: squat to a low side table, lift a 3 kg box with two palmless grippers, turn and walk, set it on the counter. In realtime mode the robot keeps running at 50 Hz while the agent thinks, holding its last
command (standing still), so the agent drives it from a controller program of its own.

## Reference solution
None (as `bigym2-pick-box-i00-privileged`).

## Verification
As `bigym2-pick-box-i00-standard`: the sidecar judges the live episode with BiGym's own success check and writes that verdict to
`/data/final.json` (`graded_by = "live"`); nothing is replayed to grade it (owner, 2026-10-17). The
trajectory holds the commands the simulator executed at each control step, so it reproduces the live run whatever the
timing was; the video is rendered from it in one pass after the verdict. `tests/grade.py` reads `final.json`. After
the agent's first command, a simulator error raised by a control step and a simulator crash inside a control step (a
fatal signal) are the agent's 0; before it, a kill, a failed resume and a reset that does not rebuild the scene are infrastructure
(`infra_error = 1`; owner, 2026-10-17, docs/protocol/standard_mode.md). Success condition: the box rests on the kitchen counter's top: touching it, its centre above the counter top, its lowest point within 0.03 m of the top's height; held by neither gripper.
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
| Horizon | 4400 control steps (88 s at 50 Hz) |
