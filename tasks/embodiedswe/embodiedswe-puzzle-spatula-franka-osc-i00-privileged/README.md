# embodiedswe-puzzle-spatula-franka-osc-i00-privileged

| | |
|---|---|
| Benchmark | EmbodiedSWE |
| Mode | privileged |
| Twin | `embodiedswe-puzzle-spatula-franka-osc-i00-standard` |
| Simulator / robot | `embodiedswe` / `franka-panda` |
| Family / instance | `puzzle.spatula.franka.osc` / seed 0 |
| Oracle | `none` — No reference solution in the repository, and none written for this scene yet; the build, the start-state hash and a do-nothing run scoring 0 are checked. |
| Agent time budget | 14400 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:embodiedswe-0.3.0` |

## Task
Flip the bread in the pan with the spatula, then lift it out on the spatula and set it down flat on the plate.

Flip a slice of bread in the pan with a spatula, then serve it onto the plate (Franka, operational-space control). EmbodiedSWE's `puzzle.spatula.franka.osc` task (robobench at commit `67f44e8a2ca5`), privileged mode, with a program as the
deliverable: `solution/solve.py` exposing `solve(env)`.

## Difficulty
Non-prehensile tool use: the bread is never grasped. Wedge the spatula's blade under the slice over the pan's rim, flip it so it lands flat and upside down in the pan, wedge it up again, carry it on the blade by friction alone over the rim and set it down flat on the plate, without the hand or fingers ever touching it, under torque control (OSC).

## Reference solution
None in the repository (`oracle = "none"`). No scripted reference has been written for this scene yet.

## Verification
`tests/grade.py` with EmbodiedSWE's grader for this scene, `tests/grader/spatula_flip_serve.py`, on the frozen instance (seed 0); the procedure (candidates, sandbox, 30-minute limit, selection, video) is the benchmark's, tasks/embodiedswe/README.md "Grading".

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
- Tool-only rule: the scene's description says that touching the bread with the fingers or the gripper disqualifies
  the episode, and its module leaves the check to the harness ("an EMBODIMENT clause, checked at the
  robot-binding/harness layer"); EmbodiedSWE's grader does not check it. Here the verifier does: PhysX contact
  reports on the bread (report only, threshold 0) and, after every physics substep, the contact forces between the
  bread in play and `panda_hand`, `panda_leftfinger`, `panda_rightfinger`; any nonzero force sets success 0 and
  progress 0. The spatula, welded to the hand by the scene's grasp contract, may touch the bread.
