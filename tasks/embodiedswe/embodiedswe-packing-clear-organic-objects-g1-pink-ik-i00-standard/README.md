# embodiedswe-packing-clear-organic-objects-g1-pink-ik-i00-standard

| | |
|---|---|
| Benchmark | EmbodiedSWE |
| Mode | standard (`eai-standard/3.0`) |
| Twin | `embodiedswe-packing-clear-organic-objects-g1-pink-ik-i00-privileged` |
| Simulator / robot | `embodiedswe` / `unitree-g1-dex3` |
| Family / instance | `packing.clear_organic_objects.g1.pink_ik` / seed 0 |
| Oracle | `none` — No reference solution in the repository, and no positive example yet; nop scored 0 (Harbor, L40S, 2026-10-29). Human review per family (PROTOCOL §4). |
| Agent time budget | 14400 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:embodiedswe-0.3.0` |

## Task
Put the two lemons from the front row of the table in the blue crate on your right, and the two limes from that row on the round tray on your left.

Sort the front-row items into the crate and onto the tray (Unitree G1, fixed pelvis, Pink IK): the scene, frozen instance and success predicate of `embodiedswe-packing-clear-organic-objects-g1-pink-ik-i00-privileged`, with a Unitree G1 humanoid with three-finger hands, its pelvis fixed, its arms and waist under EmbodiedSWE's Pink IK, in standard mode
(tasks/embodiedswe/README.md "Standard mode").

## Difficulty
That of the privileged twin, from camera images, depth and proprioception only: no resets, no object poses, no success predicate.

## Reference solution
None (`oracle = "none"`): no reference solution has been recorded through the standard API.

## Verification
Graded by the live episode: `tests/grade.py` reads the service's `final.json` (EmbodiedSWE's grader for this scene,
`environment/sim/grader/clear_organic_objects.py`, on the live state); tasks/embodiedswe/README.md "Standard mode".

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 24 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 8 | 24 GiB | 2048 | 18 GiB | — |
| verifier (as `main`) | 8 | 24 GiB | no cap | no GPU | 10 GiB |

- GPU: an RTX-class NVIDIA GPU (ray-tracing cores), one of the models in `gpu_types`: L40S, L40, L4, RTX 4090, RTX 6000 Ada, held by `sim`.
- Recommended GPU: L40S 48GB / L4 24GB / RTX 4090 24GB.
