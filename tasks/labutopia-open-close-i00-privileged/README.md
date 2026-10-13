# labutopia-open-close-i00-privileged

| | |
|---|---|
| Benchmark | LabUtopia |
| Mode | privileged |
| Twin | `labutopia-open-close-i00-standard` |
| Simulator / robot | `labutopia` / `franka-panda` |
| Family / instance | `open_close` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-labutopia:0.1.0` |

## Task
LabUtopia's `open_close` (OpenClose), with a Franka Panda arm (7 joints) with its two-finger gripper, fixed to a laboratory bench: Open the top drawer of the cabinet, let go of it, then close it again and let go. Success, at the first control step at which the second condition has held for 60 consecutive control steps (1 s): (1) for 60 consecutive control steps, the drawer handle's centre (`/World/Cabinet_01/drawer_handle_top`) is more than 0.13 m from where it started and the hand (the point between the fingertips) is more than 0.04 m from the handle's centre; (2) after that, measured from where the handle was at the step (1) was met: the handle's centre is more than 0.13 m from there and nearer to where it started than it was at that step (the drawer has come back, not gone further out), and the hand is more than 0.04 m from the handle's centre.
On the bench in front of the arm: a grey cabinet with a white top, about 67 cm deep, 76 cm wide and 79 cm high: two drawers at the top, one above the other, each with a bar handle, and two doors below them. Everything is closed. The deliverable is one replayable trajectory of joint targets (`/app/output/trajectory.npz`, `(T, 18)`, one row per 1/60 s control step: 9 position targets, then 9 velocity targets).

## Difficulty
LabUtopia's level 2. Two manipulations of the same drawer in a row, each ending with the handle released for a second: pull it out more than 13 cm, then push it back more than 13 cm. The agent has full access to the simulator and to LabUtopia's scene and task code, but not to its scripted controller or its motion primitives: it has to build the motion itself from joint targets at 60 Hz.

## Reference solution
LabUtopia's scripted controller (openclose, config level2_openclose @ 8df7278), seed 0: the joint targets it sends, one row per control step (float32, as PhysX holds them), cut at the first step at which the rule is met: `solution/oracle.npz`, 1341 rows, success after 1341 control steps. Replayed and saved by `solution/solve.sh`; re-checked by `scripts/labutopia/make_facts.py --check` (two fresh processes, same final state).

## Verification
`tests/grade.py` in a separate sandbox without network: two replays of `/app/output/trajectory.npz`, each in a fresh process, from the verifier's own copy of the instance (`tests/instance.json`; the rebuilt placements are checked against its recorded hash); pass iff both episodes succeed (the first control step at which the rule is met ends the episode) in the same state (`deterministic`). `nop`: no trajectory, reward 0.

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 8 | 8 |
| Memory | 23 GB | 21 GB |
| GPU memory | 8.5 GB | 8.5 GB |

- GPU: required, an RTX-class NVIDIA GPU (ray-tracing cores, for Isaac Sim / Omniverse RTX rendering); recommended: RTX 4090 24GB / L40S 48GB.
- Measured: oracle checks on RTX 4090 (driver 580), lab_001 pick: rendering container peak 17 GB RAM, about 7 GB GPU, 8 CPUs (start-up bursts to 16 cores for about 70 s); author: lab_003 families 21 GB at the peak (8 vCPU host)
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: 16 GiB GPU memory, 32 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 16 GiB GPU memory, 32 GiB memory. Limits measured: GPU: about 7 GiB, oracle on an RTX 4090 (author); no trial data -> max(1.5 x peak, peak + 4), at least 16 for Isaac Sim; memory: the [environment] cap 32 GiB, which every past trial ran under (no samples); processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Upstream | LabUtopia (github.com/Rui-li023/LabUtopia @ 8df7278; code MIT, assets CC BY-NC 4.0) on NVIDIA Isaac Sim 6.1.0 (LabUtopia pins 5.1.0; the image is built locally, images/labutopia/BUILD_ONLY) |
| Instance | config `level2_openclose` (task `openclose`, stage `assets/chemistry_lab/lab_001/lab_001.usd`) after LabUtopia's reset with seed 0 and 5 physics steps; placement hash `911ba5ada025cd92` (checked on every load), start-state hash `0f55e340d5e61a7e` |
| Rule | `OpenCloseRule` in `rcb_labutopia.py`: first the handle's centre is more than 0.13 m from where it started with the hand more than 0.04 m from it, for 60 consecutive control steps (opened and released); then, measured from where the handle is at that moment, the handle is more than 0.13 m from there and nearer to where it started than it was, with the hand more than 0.04 m from it, for 60 consecutive control steps (closed and released) |
| Actions | 18 joint targets per control step (1/60 s, one physics step); the first step at which the rule is met ends the episode (docs/benchmarks/labutopia.md) |
| Resources | an RTX-class NVIDIA GPU (Isaac Sim), 8 CPUs, 32 GB of RAM |

### Provenance
Generated by `scripts/labutopia/generate.py` from `scripts/labutopia/instances/open_close.json` (`make_facts.py`),
`scripts/labutopia/oracles/open_close.npz` and `scripts/labutopia/families.json`; see `docs/benchmarks/labutopia.md`.

### Change Log
- 2026-10-10: the grader's time limits and flags; the scene, the frozen instance and the pass rule are unchanged, so the task keeps its name. `tests/grade.py`: each verdict replay may take 2400 s and the video replay gets what is left of the verifier's 5400 s (each of the three replays had 2400 s, together more than the verifier's 3600 s), so a reward is written before Harbor's timeout whatever the trajectory's length; a replay without a result also sets `infra_error` (with `grader_error`, as before), every `reward.json` carries `infra_error`, and an error inside the grader still writes a reward (`grader_error = 1`). A trajectory that was graded before gets the same verdict.
- 2026-10-10 (review round 2, board 0067): texts only. The renderer's first start is stated as measured (5 to 27 minutes by stage and host: 26-27 minutes for the `lab_003` stage on an 8-vCPU L40S host, where the texts said about 15), in the instruction and in the tooling's progress message. `pour` only: the instruction says that the last condition counts 84 control steps in all, not in a row (what the rule always did). Nothing else changes.
- 2026-10-10 (review round 3, board 0067): `tests/grade.py` only. A byte that is not valid UTF-8 in the session log the agent's tools write (`/app/output/rcb_session_log.jsonl`, read only for the self-reported `agent_*` cost fields) was graded `grader_error = 1` and `infra_error = 1` with reward 0, whatever the trajectory; the log is now read tolerantly and can no longer decide anything. A trial whose log is valid is graded as before; the pass rule is unchanged.
