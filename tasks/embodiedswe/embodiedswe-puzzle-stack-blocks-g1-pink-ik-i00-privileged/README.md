# embodiedswe-puzzle-stack-blocks-g1-pink-ik-i00-privileged

| | |
|---|---|
| Benchmark | EmbodiedSWE |
| Mode | privileged |
| Twin | `embodiedswe-puzzle-stack-blocks-g1-pink-ik-i00-standard` |
| Simulator / robot | `embodiedswe` / `unitree-g1-dex3` |
| Family / instance | `puzzle.stack_blocks.g1.pink_ik` / seed 0 |
| Oracle | `none` — No reference solution in the repository. A scripted reference solve() exists outside the repository (internal only, used to check the task is solvable through the grading path); it is not shipped. |
| Agent time budget | 14400 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:embodiedswe-0.3.0` |

## Task
Stack the four blocks into one tower on the square pad.

Stack the blocks (Unitree G1, fixed pelvis, Pink IK). EmbodiedSWE's `puzzle.stack_blocks.g1.pink_ik` task (robobench at commit `67f44e8a2ca5`), privileged mode, with a program as the
deliverable: `solution/solve.py` exposing `solve(env)`.

## Difficulty
Bimanual-capable humanoid upper body with three-finger hands driven by absolute wrist poses (Pink IK): grasping and placing blocks precisely enough to build a stable tower.

## Reference solution
None in the repository (`oracle = "none"`). A scripted reference `solve()` is kept outside the repository (internal only).

## Verification
`tests/grade.py` with EmbodiedSWE's grader for this scene, `tests/grader/stack_blocks.py`, on the frozen instance (seed 0); the procedure (candidates, sandbox, 30-minute limit, selection, video) is the benchmark's, tasks/embodiedswe/README.md "Grading".

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 29 GiB | 16384 | 16 GiB | 10 GiB |
| verifier | no cap | no cap | no cap | 16 GiB | no cap |

- GPU: an RTX-class NVIDIA GPU (ray-tracing cores), one of the models in `gpu_types`: L40S, L40, L4, RTX 4090, RTX 6000 Ada, held by `main`.
- Recommended GPU: L40S 48GB / L4 24GB / RTX 4090 24GB.
