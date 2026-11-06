# labutopia-pour-i00-privileged

| | |
|---|---|
| Benchmark | LabUtopia |
| Mode | privileged |
| Twin | `labutopia-pour-i00-standard` |
| Simulator / robot | `labutopia` / `franka-panda` |
| Family / instance | `pour` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:labutopia-0.1.0` |

## Task
LabUtopia's `pour` (Pour (LabUtopia's level-2 PourLiquid is the same task)), with a Franka Panda arm (7 joints) with its two-finger gripper, fixed to a laboratory bench: Pick up the small beaker, pour it out over the large beaker and bring it back upright. There is no liquid in this simulation: the pour is judged by where the small beaker is and how far it is turned. Success, at the first control step at which the last condition is met: (1) the small beaker's centre has been more than 0.12 m above where it started; then, counted only at control steps at which its centre is within the pour distance of the large beaker's centre (horizontally; half the height of the small beaker's bounding box plus 0.03 m: 0.0776 m), (2) it has been turned more than 50 degrees from its orientation at the first step after (1), (3) then turned back to within 30 degrees of that orientation, and (4) then is more than 0.05 m above where it started at 84 control steps (1.4 s in all; they need not be consecutive).
On the bench in front of the arm: two glass beakers: a small one, about 11 cm across and 9.5 cm tall (the one to pour), and a large one, about 15.5 cm across and 13 cm tall (the one to pour into). The deliverable is one replayable trajectory of joint targets (`/app/output/trajectory.npz`, `(T, 18)`, one row per 1/60 s control step: 9 position targets, then 9 velocity targets).

## Difficulty
LabUtopia's level 1. Four conditions in a fixed order, three of them counted only while the held beaker is within 7.76 cm of the other one's axis: a tilt of more than 50 degrees and back, in the hand, without losing the beaker. The agent has full access to the simulator and to LabUtopia's scene and task code, but not to its scripted controller or its motion primitives: it has to build the motion itself from joint targets at 60 Hz.

## Reference solution
LabUtopia's scripted controller (pour, config level1_pour @ 8df7278), seed 0: the joint targets it sends, one row per control step (float32, as PhysX holds them), cut at the first step at which the rule is met: `solution/oracle.npz`, 985 rows, success after 985 control steps. Replayed and saved by `solution/solve.sh`; re-checked by the privileged verifier (`harbor run -a oracle`: two fresh-process replays, same final state).

## Verification
`tests/grade.py` in a separate sandbox without network: two replays of `/app/output/trajectory.npz`, each in a fresh process, from the verifier's own copy of the instance (`tests/instance.json`; the rebuilt placements are checked against its recorded hash); pass iff both episodes succeed (the first control step at which the rule is met ends the episode) in the same state (`deterministic`). `nop`: no trajectory, reward 0.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 32 GiB | 4096 | 16 GiB | 10 GiB |
| verifier | 8 | 32 GiB | no cap | 16 GiB | no cap |

- GPU: an RTX-class NVIDIA GPU (ray-tracing cores), one of the models in `gpu_types`: RTX 4090, L40S, held by `main`.
- Recommended GPU: RTX 4090 24GB / L40S 48GB.

## Details
| | |
|---|---|
| Upstream | LabUtopia (github.com/Rui-li023/LabUtopia @ 8df7278; code MIT, assets CC BY-NC 4.0) on NVIDIA Isaac Sim 6.1.0 (LabUtopia pins 5.1.0; the image is built locally, images/labutopia/BUILD_ONLY) |
| Instance | config `level1_pour` (task `pickpour`, stage `assets/chemistry_lab/lab_001/lab_001.usd`) after LabUtopia's reset with seed 0 and 5 physics steps; placement hash `a43276197ee1b849` (checked on every load), start-state hash `7f45793995a5c851` |
| Rule | `PourRule` in `rcb_labutopia.py`: the container's centre has been more than 0.12 m above where it started; then, counted only while its centre is within the pour distance of the target container's centre (horizontally), it has been turned more than 50 degrees, then brought back to within 30 degrees of its orientation before the turn, and then stays more than 0.05 m above where it started for 84 control steps (1.4 s) |
| Actions | 18 joint targets per control step (1/60 s, one physics step); the first step at which the rule is met ends the episode (tasks/labutopia/README.md) |
| Resources | an RTX-class NVIDIA GPU (Isaac Sim), 8 CPUs, 32 GB of RAM |
