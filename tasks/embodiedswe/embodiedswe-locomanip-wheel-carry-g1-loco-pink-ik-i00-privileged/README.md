# embodiedswe-locomanip-wheel-carry-g1-loco-pink-ik-i00-privileged

| | |
|---|---|
| Benchmark | EmbodiedSWE |
| Mode | privileged |
| Twin | `embodiedswe-locomanip-wheel-carry-g1-loco-pink-ik-i00-standard` |
| Simulator / robot | `embodiedswe` / `unitree-g1-dex3` |
| Family / instance | `locomanip.wheel_carry.g1.loco_pink_ik` / seed 0 |
| Oracle | `none` — No reference solution in the repository, and none written for this scene yet; the build, the start-state hash and a do-nothing run scoring 0 are checked. |
| Agent time budget | 14400 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:embodiedswe-0.3.0` |

## Task
Carry the steering wheel from the table in front of you to the basket on the other table, off to your right, and leave it in the basket.

Carry the wheel to the basket (Unitree G1, walking, Pink IK). EmbodiedSWE's `locomanip.wheel_carry.g1.loco_pink_ik` task (robobench at commit `67f44e8a2ca5`), privileged mode, with a program as the
deliverable: `solution/solve.py` exposing `solve(env)`.

## Difficulty
Loco-manipulation: the G1 walks under a frozen locomotion policy (base velocity commands), lifts a steering wheel off a table, carries it 3 m to a second table and leaves it resting in a basket.

## Reference solution
None in the repository (`oracle = "none"`). No scripted reference has been written for this scene yet.

## Verification
`tests/grade.py` with EmbodiedSWE's grader for this scene, `tests/grader/wheel_carry.py`, on the frozen instance (seed 0); the procedure (candidates, sandbox, 30-minute limit, selection, video) is the benchmark's, tasks/embodiedswe/README.md "Grading".

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 29 GiB | 16384 | 16 GiB | 10 GiB |
| verifier | no cap | no cap | no cap | 16 GiB | no cap |

- GPU: an RTX-class NVIDIA GPU (ray-tracing cores), one of the models in `gpu_types`: L40S, L40, L4, RTX 4090, RTX 6000 Ada, held by `main`.
- Recommended GPU: L40S 48GB / L4 24GB / RTX 4090 24GB.
