# embodiedswe-assembly-bulb-franka-osc-i00-privileged

| | |
|---|---|
| Benchmark | EmbodiedSWE |
| Mode | privileged |
| Twin | `embodiedswe-assembly-bulb-franka-osc-i00-standard` |
| Simulator / robot | `embodiedswe` / `franka-panda` |
| Family / instance | `assembly.bulb.franka.osc` / seed 0 |
| Oracle | `none` — No reference solution in the repository, and none written for this scene yet; the build, the start-state hash and a do-nothing run scoring 0 are checked. |
| Agent time budget | 14400 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:embodiedswe-0.3.0` |

## Task
Pick up the light bulb and screw it into the lamp socket.

Screw a light bulb into its socket (Franka, operational-space control). EmbodiedSWE's `assembly.bulb.franka.osc` task (robobench at commit `67f44e8a2ca5`), privileged mode, with a program as the
deliverable: `solution/solve.py` exposing `solve(env)`.

## Difficulty
Contact-rich assembly: a grasp of a small round bulb, alignment on a threaded socket and a turn-while-pressing motion under torque control (OSC); EmbodiedSWE's GPT-6-class agents solve it within a few hours in their own runs.

## Reference solution
None in the repository (`oracle = "none"`). No scripted reference has been written for this scene yet.

## Verification
`tests/grade.py` with EmbodiedSWE's grader for this scene, `tests/grader/bulb_assembly.py`, on the frozen instance (seed 0); the procedure (candidates, sandbox, 30-minute limit, selection, video) is the benchmark's, tasks/embodiedswe/README.md "Grading".

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
- Solvability (no reference solution ships for this scene): the bulb is physically seatable. A development-only
  probe that presses and twists the bulb directly seats it, so the thread works.
- A scripted robot attempt stalls during the turn. Three properties of the controller and the gripper make
  the turn hard: the rotational stiffness of the operational-space controller; its nullspace posture spring,
  which pulls the last wrist joint back toward its rest angle; and the parallel jaw, which pivots on the round
  glass instead of holding it rigidly.
