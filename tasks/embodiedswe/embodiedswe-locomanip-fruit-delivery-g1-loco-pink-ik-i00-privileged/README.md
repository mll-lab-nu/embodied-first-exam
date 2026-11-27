# embodiedswe-locomanip-fruit-delivery-g1-loco-pink-ik-i00-privileged

| | |
|---|---|
| Benchmark | EmbodiedSWE |
| Mode | privileged |
| Twin | `embodiedswe-locomanip-fruit-delivery-g1-loco-pink-ik-i00-standard` |
| Simulator / robot | `embodiedswe` / `unitree-g1-dex3` |
| Family / instance | `locomanip.fruit_delivery.g1.loco_pink_ik` / seed 0 |
| Oracle | `none` — No reference solution in the repository. A scripted reference solve() exists outside the repository (internal only, used to check the task is solvable through the grading path); it is not shipped. |
| Agent time budget | 14400 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:embodiedswe-0.3.0` |

## Task
Put every fruit on the table onto the clay plate on the far side of the table; nothing else goes on the plate.

Deliver the fruit to the plate (Unitree G1, walking, Pink IK). EmbodiedSWE's `locomanip.fruit_delivery.g1.loco_pink_ik` task (robobench at commit `67f44e8a2ca5`), privileged mode, with a program as the
deliverable: `solution/solve.py` exposing `solve(env)`.

## Difficulty
Loco-manipulation: the G1 walks under a frozen locomotion policy (base velocity commands) while its arms and hands pick fruit and carry it to a plate elsewhere in the room.

## Reference solution
None in the repository (`oracle = "none"`). A scripted reference `solve()` is kept outside the repository (internal only).

## Verification
`tests/grade.py` with EmbodiedSWE's grader for this scene, `tests/grader/fruit_delivery.py`, on the frozen instance (seed 0); the procedure (candidates, sandbox, 30-minute limit, selection, video) is the benchmark's, tasks/embodiedswe/README.md "Grading".

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 29 GiB | 16384 | 16 GiB | 10 GiB |
| verifier | no cap | no cap | no cap | 16 GiB | no cap |

- GPU: an RTX-class NVIDIA GPU (ray-tracing cores), one of the models in `gpu_types`: L40S, L40, L4, RTX 4090, RTX 6000 Ada, held by `main`.
- Recommended GPU: L40S 48GB / L4 24GB / RTX 4090 24GB.

## Details

### Review notes
- Contact artifact (reported, not changed): at a high grip closure (1.3 on the hand's closure scale) the middle
  fingertip of the G1's right hand stays attached to the lemon after the fingers open, and the lemon rises with the
  hand (3 of 3 trials; 0 of 4 at closure 0.9). It looks like a penetration artifact of the contact model. It makes
  the release harder than it is physically, and a solution could use it as glue while carrying.
  Observed with CPU PhysX; not re-checked with GPU PhysX.
