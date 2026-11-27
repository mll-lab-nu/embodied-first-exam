# embodiedswe-assembly-so101-bimanual-franka-osc-i00-privileged

| | |
|---|---|
| Benchmark | EmbodiedSWE |
| Mode | privileged |
| Twin | `embodiedswe-assembly-so101-bimanual-franka-osc-i00-standard` |
| Simulator / robot | `embodiedswe` / `franka-panda-bimanual` |
| Family / instance | `assembly.so101.bimanual_franka.osc` / seed 0 |
| Oracle | `none` — No reference solution in the repository, and none written for this scene yet; the build, the start-state hash and a do-nothing run scoring 0 are checked. |
| Agent time budget | 14400 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:embodiedswe-0.3.0` |

## Task
Put the SO101 arm's elbow together with the screwdriver: seat the servo in the upper arm and fasten it with the four small screws, then fit the forearm onto the servo and fasten it with the eight larger screws.

Assemble the SO101 arm's elbow: servo, four tab screws, forearm, eight horn screws (two Frankas, operational-space control). EmbodiedSWE's `assembly.so101.bimanual_franka.osc` task (robobench at commit `67f44e8a2ca5`), privileged mode, with a program as the
deliverable: `solution/solve.py` exposing `solve(env)`.

## Difficulty
The longest scene of the benchmark: seat a loose servo in a slip-fit pocket, then pick up and drive twelve small screws one by one with a power screwdriver's magnetic bit (four M2 tab screws, eight M3 horn screws on both sides of the joint) and clip the forearm's fork onto the servo horn in between, with two arms sharing one 16-dim action under torque control (OSC).

## Reference solution
None in the repository (`oracle = "none"`). No scripted reference has been written for this scene yet.

## Verification
`tests/grade.py` with EmbodiedSWE's grader for this scene, `tests/grader/so101_assembly.py`, on the frozen instance (seed 0); the procedure (candidates, sandbox, 30-minute limit, selection, video) is the benchmark's, tasks/embodiedswe/README.md "Grading".

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
- Success predicate: the scene defines no `success()`, so EmbodiedSWE's own end predicate is its grader's
  `check_success` (tests/grader/so101_assembly.py, unchanged): every screw fastened, the servo seated and the forearm
  seated on the horn, on the final state. The verdict reads that grader; the tooling's `so101_success` is the same
  predicate for the development `check`, which has no grader.
- Budget: the slowest scene of the benchmark (two arms, 240 Hz physics, twelve screws with continuous collision
  detection); see the measured step time in the benchmark README.
