# bigym2-wall-cupboard-open-i00-standard-realtime

| | |
|---|---|
| Benchmark | BiGym 2.0 |
| Mode | standard-realtime (`eai-standard/2.3`) |
| Twin | `bigym2-wall-cupboard-open-i00-privileged` |
| Simulator / robot | `bigym2` / `unitree-g1-dex1` |
| Family / instance | `wall-cupboard-open` / seed 0 |
| Oracle | `none` — no reference solution (BiGym 2.0 ships no expert or planner; its demonstrations and its agents' programs stay off the agent's network); positive example graded 1 by the separate verifier: bigym2-wall-cupboard-open-i00-pr__mcuR6nu (run codex-gpt6_luna-medium, 2026-10-08, on an earlier text of the privileged task; regraded by its current verifier); human review in PR #123 |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Real time | slowdown S = 1 (the world runs at 1/S of real speed: one control step every S x control_dt s of wall time; `RCB_SLOWDOWN`'s default); reset budget 0 (`RCB_RESET_BUDGET`'s default) (PROTOCOL §4b) |
| Base image | `ghcr.io/mll-lab-nu/efe:bigym2-0.1.1` |

## Task
Open both doors of the wall cabinet. (BiGym 2.0 `wall_cupboard_open`; the robot as a service on a clock that does not stop: its three onboard cameras and
its proprioception only, one episode.)

## Difficulty
Two hinged doors above the counter, both opened to within about 9 degrees of fully open at the same time. In standard-realtime mode the robot keeps running at 50 Hz while the agent thinks, holding its last
command (standing still), so the agent drives it from a controller program of its own.

## Reference solution
None (as `bigym2-wall-cupboard-open-i00-privileged`).

## Verification
As `bigym2-wall-cupboard-open-i00-standard`: the sidecar judges the live episode with BiGym's own success check and writes that verdict to
`/data/final.json` (`graded_by = "live"`); nothing is replayed to grade it (owner, 2026-10-17). The
trajectory holds the commands the simulator executed at each control step, so it reproduces the live run whatever the
timing was; the video is rendered from it in one pass after the verdict. `tests/grade.py` reads `final.json`. After
the agent's first command, a simulator error raised by a control step and a simulator crash inside a control step (a
fatal signal) are the agent's 0; before it, a kill, a failed resume and a reset that does not rebuild the scene are infrastructure
(`infra_error = 1`; owner, 2026-10-17, docs/protocol/standard_mode.md). Success condition: both doors of the wall cabinet are open to within 10% of their travel (within about 9 degrees of fully open), at the same time.
No oracle; human review in PR #123 (PROTOCOL §2.7).

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 4 GB | 3 GB |
| GPU memory | 1.5 GB | 1.5 GB |

- GPU: required, any NVIDIA GPU; recommended: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).
- Measured: GPU 0.7-1.2 GB, evaluation-pool GPU profile (per-trial GPU peaks, 10-03..10); memory: privileged container 3.0 GB, mem_guard (docker memory per container, an RTX 4090 workstation, 10-02..10); CPU author estimate (MuJoCo + two ONNX policies on the CPU)
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 6 GiB GPU memory, 16 GiB memory. Limits measured: GPU: 1.2 GiB (the evaluation pool's GPU profile (per-trial GPU peaks by card, 10-03..10)) -> max(1.5 x peak, peak + 4); memory: no samples of the agent's container; floor 8 GiB (at most the 16 GiB cap); whole trial: + the sim service's 8 GiB (from the minimum: no samples); processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Service | `environment/sim/rcb_realtime.py` (eai-standard/2.3) with the BiGym 2.0 adapter `server.py`, `rcb_bigym2.py`, `instance.json` (= the privileged twin's) |
| Clock | real time (`RCB_SLOWDOWN`, default 1) from the first `submit` |
| Horizon | 1450 control steps (29 s at 50 Hz) |

### Change Log
- 2026-10-17 (owner): graded by the live episode: `success` = BiGym's own `is_success` in the episode
  the sim service ran (the same rule, judged as it ran), and no grading replay runs (no `replay_success` /
  `deterministic` any more; `final.json` has `graded_by = "live"`, `replays = 0`, `reward.json` `graded_by_live = 1`).
  The video is one render pass over the trajectory after the verdict, as before. The scene's start is checked when an
  episode begins: a scene that does not rebuild the frozen instance's starting state (exactly, or within upstream's
  tolerance on another CPU) gives up as infrastructure (`instance_mismatch`). The scene, instance, pass rule and the
  agent's interface are unchanged, so the task keeps its name; every archived verdict is the same under the live rule.
- 2026-10-17 (2; owner): after the agent's first command a simulator error raised by a control step is the agent's 0
  (`sim_error = 1`, no longer `infra_error`), and so are simulator crashes with a fatal signal inside a control step (`sim_crashed_on_call`);
  kills, failed resumes, a reset that does not rebuild the scene and failures before the first command stay
  infrastructure.
