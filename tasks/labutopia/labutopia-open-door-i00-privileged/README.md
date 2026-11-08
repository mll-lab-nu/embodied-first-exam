# labutopia-open-door-i00-privileged

| | |
|---|---|
| Benchmark | LabUtopia |
| Mode | privileged |
| Twin | `labutopia-open-door-i00-standard` |
| Simulator / robot | `labutopia` / `franka-panda` |
| Family / instance | `open_door` / seed 4 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:labutopia-0.1.0` |

## Task
LabUtopia's `open_door` (Open Door), with a Franka Panda arm (7 joints) with its two-finger gripper, fixed to a laboratory bench: Open the door of the drying oven and let go of it. Success, at the first control step at which this has held for 60 consecutive control steps (1 s): the door handle's centre (`/World/DryingBox_01/handle`) is more than 0.12 m from where it started and the hand (the point between the fingertips) is more than 0.04 m from the handle's centre.
On the bench in front of the arm: a drying oven, a grey metal box about 58 cm deep, 74 cm wide and 63 cm high, with a blue door that has a window and a handle and is hinged on one side; a small control panel sits next to the door. The door is closed. The deliverable is one replayable trajectory of joint targets (`/app/output/trajectory.npz`, `(T, 18)`, one row per 1/60 s control step: 9 position targets, then 9 velocity targets).

## Difficulty
LabUtopia's level 1. A hinged door: the handle moves on an arc around the hinge, so the hand has to follow it, and the rule wants the door left open with the handle released. The agent has full access to the simulator and to LabUtopia's scene and task code, but not to its scripted controller or its motion primitives: it has to build the motion itself from joint targets at 60 Hz.

## Reference solution
LabUtopia's scripted controller (open, config level1_open_door @ 8df7278), seed 4: the joint targets it sends, one row per control step (float32, as PhysX holds them), cut at the first step at which the rule is met: `solution/oracle.npz`, 687 rows, success after 687 control steps. Replayed and saved by `solution/solve.sh`; re-checked by the privileged verifier (`harbor run -a oracle`: one fresh-process replay).

## Verification
`tests/grade.py` in a separate sandbox without network: one replay of `/app/output/trajectory.npz`, in a fresh process, from the verifier's own copy of the instance (`tests/instance.json`; the rebuilt placements are checked against its recorded hash); pass iff the episode succeeds (the first control step at which the rule is met ends the episode). `nop`: no trajectory, reward 0.

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
| Instance | config `level1_open_door` (task `openclose`, stage `assets/chemistry_lab/lab_001/lab_001.usd`) after LabUtopia's reset with seed 4 and 5 physics steps; placement hash `106ee1a5119756d2` (checked on every load), start-state hash `ac92955f6803b7d6` |
| Rule | `OpenRule` in `rcb_labutopia.py`: the handle's centre is more than 0.12 m from where it started and the hand is more than 0.04 m from the handle's centre (the handle is released), for 60 consecutive control steps (1 s) |
| Actions | 18 joint targets per control step (1/60 s, one physics step); the first step at which the rule is met ends the episode (tasks/labutopia/README.md) |
| Resources | an RTX-class NVIDIA GPU (Isaac Sim), 8 CPUs, 32 GB of RAM |
