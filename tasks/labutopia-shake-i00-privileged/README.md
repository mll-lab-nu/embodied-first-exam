# labutopia-shake-i00-privileged

| | |
|---|---|
| Benchmark | LabUtopia |
| Mode | privileged |
| Twin | `labutopia-shake-i00-standard` |
| Simulator / robot | `labutopia` / `franka-panda` |
| Family / instance | `shake` / seed 0 |
| Oracle | `full` |
| Agent time budget | 5400 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-labutopia:0.1.0` |

## Task
LabUtopia's `shake` (Shake (LabUtopia's level-2 ShakeBeaker is the same task)), with a Franka Panda arm (7 joints) with its two-finger gripper, fixed to a laboratory bench: Pick up the beaker, shake it, and hold it still. Nothing is counted at a control step at which the beaker's centre is less than 0.05 m above where it started. Success, at the first control step at which the second condition is met: (1) five times, the beaker's centre gets 0.05 m or more (horizontally) from where it was when that count began (each count begins at the next step); (2) after the fifth, its centre stays within 0.01 m in x and in y over 60 control steps (1 s).
On the bench in front of the arm: one small glass beaker, about 6.5 cm across and 10 cm tall. The deliverable is one replayable trajectory of joint targets (`/app/output/trajectory.npz`, `(T, 18)`, one row per 1/60 s control step: 9 position targets, then 9 velocity targets).

## Difficulty
LabUtopia's level 1. A small beaker has to survive five quick moves of 5 cm in the grip and then be held within 1 cm for a second: the grasp has to be firm enough for the accelerations. The agent has full access to the simulator and to LabUtopia's scene and task code, but not to its scripted controller or its motion primitives: it has to build the motion itself from joint targets at 60 Hz.

## Reference solution
LabUtopia's scripted controller (shake, config level1_shake @ 8df7278), seed 0: the joint targets it sends, one row per control step (float32, as PhysX holds them), cut at the first step at which the rule is met: `solution/oracle.npz`, 1087 rows, success after 1087 control steps. Replayed and saved by `solution/solve.sh`; re-checked by `scripts/labutopia/make_facts.py --check` (two fresh processes, same final state).

## Verification
`tests/grade.py` in a separate sandbox without network: two replays of `/app/output/trajectory.npz`, each in a fresh process, from the verifier's own copy of the instance (`tests/instance.json`; the rebuilt placements are checked against its recorded hash); pass iff both episodes succeed (the first control step at which the rule is met ends the episode) in the same state (`deterministic`). `nop`: no trajectory, reward 0.

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 8 | 8 |
| Memory | 28 GB | 26 GB |
| GPU memory | 8.5 GB | 8.5 GB |

- GPU: required, an RTX-class NVIDIA GPU (ray-tracing cores, for Isaac Sim / Omniverse RTX rendering); recommended: RTX 4090 24GB / L40S 48GB.
- Measured: oracle checks on RTX 4090 (driver 580), lab_001 pick: rendering container peak 17 GB RAM, about 7 GB GPU, 8 CPUs (start-up bursts to 16 cores for about 70 s); author: lab_003 families 21 GB at the peak (8 vCPU host)
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: 16 GiB GPU memory, 32 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 16 GiB GPU memory, 32 GiB memory. Limits measured: GPU: about 7 GiB, oracle on an RTX 4090 (author); no trial data -> max(1.5 x peak, peak + 4), at least 16 for Isaac Sim; memory: the [environment] cap 32 GiB, which every past trial ran under (no samples); processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Upstream | LabUtopia (github.com/Rui-li023/LabUtopia @ 8df7278; code MIT, assets CC BY-NC 4.0) on NVIDIA Isaac Sim 6.1.0 (LabUtopia pins 5.1.0; the image is built locally, images/labutopia/BUILD_ONLY) |
| Instance | config `level1_shake` (task `shake`, stage `assets/chemistry_lab/lab_003/lab_003.usd`) after LabUtopia's reset with seed 0 and 5 physics steps; placement hash `7b35fdf9cf30147c` (checked on every load), start-state hash `536512837f73b9e1` |
| Rule | `ShakeRule` in `rcb_labutopia.py`: counted only while the beaker's centre is at least 0.05 m above where it started: five times in a row the centre moves 0.05 m or more (horizontally) from where it was when that count began; after the fifth, the centre stays within 0.01 m in x and in y over 60 control steps (1 s) |
| Actions | 18 joint targets per control step (1/60 s, one physics step); the first step at which the rule is met ends the episode (docs/benchmarks/labutopia.md) |
| Resources | an RTX-class NVIDIA GPU (Isaac Sim), 8 CPUs, 32 GB of RAM |

### Provenance
Generated by `scripts/labutopia/generate.py` from `scripts/labutopia/instances/shake.json` (`make_facts.py`),
`scripts/labutopia/oracles/shake.npz` and `scripts/labutopia/families.json`; see `docs/benchmarks/labutopia.md`.

### Change Log
- 2026-10-10: the grader's time limits and flags; the scene, the frozen instance and the pass rule are unchanged, so the task keeps its name. `tests/grade.py`: each verdict replay may take 2400 s and the video replay gets what is left of the verifier's 5400 s (each of the three replays had 2400 s, together more than the verifier's 3600 s), so a reward is written before Harbor's timeout whatever the trajectory's length; a replay without a result also sets `infra_error` (with `grader_error`, as before), every `reward.json` carries `infra_error`, and an error inside the grader still writes a reward (`grader_error = 1`). A trajectory that was graded before gets the same verdict.
- 2026-10-10 (review round 2, board 0067): texts only. The renderer's first start is stated as measured (5 to 27 minutes by stage and host: 26-27 minutes for the `lab_003` stage on an 8-vCPU L40S host, where the texts said about 15), in the instruction and in the tooling's progress message. `pour` only: the instruction says that the last condition counts 84 control steps in all, not in a row (what the rule always did). Nothing else changes.
