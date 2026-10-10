# labutopia-heat-liquid-i00-privileged

| | |
|---|---|
| Benchmark | LabUtopia |
| Mode | privileged |
| Twin | `labutopia-heat-liquid-i00-standard` |
| Simulator / robot | `labutopia` / `franka-panda` |
| Family / instance | `heat_liquid` / seed 1 |
| Oracle | `full` |
| Agent time budget | 5400 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-labutopia:0.1.0` |

## Task
LabUtopia's `heat_liquid` (HeatLiquid), with a Franka Panda arm (7 joints) with its two-finger gripper, fixed to a laboratory bench: Put the beaker on the heater's plate and press the heater's button. Success, at the first control step at which the third condition is met: (1) the beaker's centre has been above z = 0.82 m; (2) after that, the beaker has been on the plate: its centre at or below z = 0.86 m and within 0.05 m in x and in y of the plate's frame (`/World/heat_device/heat_device/heat_device/plat`); (3) after that, the beaker is on the plate as in (2) and the button's frame (`/World/heat_device/button`) is below z = 0.761 m.
On the bench in front of the arm: a small glass beaker, about 6.5 cm across and 10 cm tall, and a heater: a white hot plate about 25 cm x 18 cm x 9 cm with a square plate on top, a display on its front and a round red button at one front corner. The deliverable is one replayable trajectory of joint targets (`/app/output/trajectory.npz`, `(T, 18)`, one row per 1/60 s control step: 9 position targets, then 9 velocity targets).

## Difficulty
LabUtopia's level 2. Two steps in order with one hand: the beaker has to stand within 5 cm of the plate's centre before the button, a few centimetres from the plate, is pressed down a centimetre without knocking the beaker off. The agent has full access to the simulator and to LabUtopia's scene and task code, but not to its scripted controller or its motion primitives: it has to build the motion itself from joint targets at 60 Hz.

## Reference solution
LabUtopia's scripted controller (placepress, config level2_HeatLiquid @ 8df7278), seed 1: the joint targets it sends, one row per control step (float32, as PhysX holds them), cut at the first step at which the rule is met: `solution/oracle.npz`, 1264 rows, success after 1264 control steps. Replayed and saved by `solution/solve.sh`; re-checked by `scripts/labutopia/make_facts.py --check` (two fresh processes, same final state).

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
| Instance | config `level2_HeatLiquid` (task `placepress`, stage `assets/chemistry_lab/lab_003/lab_003.usd`) after LabUtopia's reset with seed 1 and 5 physics steps; placement hash `e43cba23cfe4d9ee` (checked on every load), start-state hash `8ca99a8368067f5d` |
| Rule | `HeatLiquidRule` in `rcb_labutopia.py`: the beaker's centre has been above z = 0.82 m; after that the beaker is on the heater's plate (its centre at or below z = 0.86 m and within 0.05 m in x and in y of the plate's centre); and, with the beaker there, the heater's button is pressed (the button below z = 0.761 m) |
| Actions | 18 joint targets per control step (1/60 s, one physics step); the first step at which the rule is met ends the episode (docs/benchmarks/labutopia.md) |
| Resources | an RTX-class NVIDIA GPU (Isaac Sim), 8 CPUs, 32 GB of RAM |

### Provenance
Generated by `scripts/labutopia/generate.py` from `scripts/labutopia/instances/heat_liquid.json` (`make_facts.py`),
`scripts/labutopia/oracles/heat_liquid.npz` and `scripts/labutopia/families.json`; see `docs/benchmarks/labutopia.md`.

### Change Log
- 2026-10-10: the grader's time limits and flags; the scene, the frozen instance and the pass rule are unchanged, so the task keeps its name. `tests/grade.py`: each verdict replay may take 2400 s and the video replay gets what is left of the verifier's 5400 s (each of the three replays had 2400 s, together more than the verifier's 3600 s), so a reward is written before Harbor's timeout whatever the trajectory's length; a replay without a result also sets `infra_error` (with `grader_error`, as before), every `reward.json` carries `infra_error`, and an error inside the grader still writes a reward (`grader_error = 1`). A trajectory that was graded before gets the same verdict.
- 2026-10-10 (review round 2, board 0067): texts only. The renderer's first start is stated as measured (5 to 27 minutes by stage and host: 26-27 minutes for the `lab_003` stage on an 8-vCPU L40S host, where the texts said about 15), in the instruction and in the tooling's progress message. `pour` only: the instruction says that the last condition counts 84 control steps in all, not in a row (what the rule always did). Nothing else changes.
