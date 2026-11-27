# embodiedswe-assembly-pc-gpu-ram-franka-osc-i00-privileged

| | |
|---|---|
| Benchmark | EmbodiedSWE |
| Mode | privileged |
| Twin | `embodiedswe-assembly-pc-gpu-ram-franka-osc-i00-standard` |
| Simulator / robot | `embodiedswe` / `franka-panda` |
| Family / instance | `assembly.pc_gpu_ram.franka.osc` / seed 0 |
| Oracle | `none` — No reference solution in the repository, and none written for this scene yet; the build, the start-state hash and a do-nothing run scoring 0 are checked. |
| Agent time budget | 14400 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:embodiedswe-0.3.0` |

## Task
Install the graphics card and the two RAM sticks in the PC. The card goes in the PCIe x16 slot, the stick from the holder farther from the robot in the outermost memory slot, and the other stick in the second slot from the CPU socket.

Install a graphics card and two RAM sticks (Franka, operational-space control). EmbodiedSWE's `assembly.pc_gpu_ram.franka.osc` task (robobench at commit `67f44e8a2ca5`), privileged mode, with a program as the
deliverable: `solution/solve.py` exposing `solve(env)`.

## Difficulty
Three sequential insertions in one case: the graphics card (slide-under-the-rear-panel then press) and two RAM sticks into the correct dual-channel slots, each pressed fully home.

## Reference solution
None in the repository (`oracle = "none"`). No scripted reference has been written for this scene yet.

## Verification
`tests/grade.py` with EmbodiedSWE's grader for this scene, `tests/grader/pc_gpu_ram_assembly.py`, on the frozen instance (seed 0); the procedure (candidates, sandbox, 30-minute limit, selection, video) is the benchmark's, tasks/embodiedswe/README.md "Grading".

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 29 GiB | 16384 | 16 GiB | 10 GiB |
| verifier | no cap | no cap | no cap | 16 GiB | no cap |

- GPU: an RTX-class NVIDIA GPU (ray-tracing cores), one of the models in `gpu_types`: L40S, L40, L4, RTX 4090, RTX 6000 Ada, held by `main`.
- Recommended GPU: L40S 48GB / L4 24GB / RTX 4090 24GB.
