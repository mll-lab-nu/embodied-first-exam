# labutopia-place-i00-privileged

| | |
|---|---|
| Benchmark | LabUtopia |
| Mode | privileged |
| Twin | `labutopia-place-i00-standard` |
| Simulator / robot | `labutopia` / `franka-panda` |
| Family / instance | `place` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:labutopia-0.1.0` |

## Task
LabUtopia's `place` (Place (LabUtopia's level-2 TransportBeaker is the same task)), with a Franka Panda arm (7 joints) with its two-finger gripper, fixed to a laboratory bench: Pick up the beaker and set it down on the square target plate. Success, at the first control step at which the second condition has held for 60 consecutive control steps (1 s): (1) the beaker's centre has been more than 0.10 m above where it started; (2) after that, its centre is within 0.05 m (horizontally) of the plate's centre and within 0.05 m of its initial height, and the hand (the point between the fingertips) is more than 0.05 m from the beaker's centre.
On the bench in front of the arm: a glass beaker, about 11 cm across and 9 cm tall, and a white square plate, 10 cm x 10 cm, lying flat on the bench. The deliverable is one replayable trajectory of joint targets (`/app/output/trajectory.npz`, `(T, 18)`, one row per 1/60 s control step: 9 position targets, then 9 velocity targets).

## Difficulty
LabUtopia's level 1. The beaker has to be lifted at least 10 cm, carried about half a metre and released upright within 5 cm of the centre of a 10 cm plate. The agent has full access to the simulator and to LabUtopia's scene and task code, but not to its scripted controller or its motion primitives: it has to build the motion itself from joint targets at 60 Hz.

## Reference solution
LabUtopia's scripted controller (place, config level1_place @ 8df7278), seed 0: the joint targets it sends, one row per control step (float32, as PhysX holds them), cut at the first step at which the rule is met: `solution/oracle.npz`, 836 rows, success after 836 control steps. Replayed and saved by `solution/solve.sh`; re-checked by the privileged verifier (`harbor run -a oracle`: one fresh-process replay).

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
| Instance | config `level1_place` (task `place`, stage `assets/chemistry_lab/lab_001/lab_001.usd`) after LabUtopia's reset with seed 0 and 5 physics steps; placement hash `80b18aa75143294a` (checked on every load), start-state hash `e11556dd2ab6ecd8` |
| Rule | `PlaceRule` in `rcb_labutopia.py`: the object's centre has been more than 0.10 m above where it started; after that it is within 0.05 m (horizontally) of the target's centre and within 0.05 m of its initial height, with the hand more than 0.05 m from the object's centre (released), for 60 consecutive control steps (1 s) |
| Actions | 18 joint targets per control step (1/60 s, one physics step); the first step at which the rule is met ends the episode (tasks/labutopia/README.md) |
| Resources | an RTX-class NVIDIA GPU (Isaac Sim), 8 CPUs, 32 GB of RAM |
