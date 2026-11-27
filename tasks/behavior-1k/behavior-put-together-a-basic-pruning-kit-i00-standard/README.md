# BEHAVIOR-1K · put_together_a_basic_pruning_kit (standard)

| | |
|---|---|
| Task ID | `behavior-put-together-a-basic-pruning-kit-i00-standard` |
| Benchmark | [BEHAVIOR-1K](https://behavior.stanford.edu/) (Li et al., 2024), upstream `StanfordVL/BEHAVIOR-1K@b197991` |
| Robot | Galaxea R1 Pro mobile bimanual manipulator (holonomic wheeled base, 4-joint trunk, two 7-joint arms with parallel-jaw grippers) |
| Mode | standard |
| Instance | `put_together_a_basic_pruning_kit`, seed 301 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Put the pruner and the shears into the toolbox, close it, and leave it on the garage floor.

## Success criteria
The pruner and the shears are inside the toolbox, the toolbox is on the garage floor, and the toolbox is closed.

The relations above are OmniGibson's object states, evaluated on the simulator after every control step (30 Hz). An
object is *on* another (`ontop`) when the two touch and the other is directly below it; *inside* when the centre of its
bounding box lies in one of the other's container volumes; *next to* (`nextto`) when their bounding boxes are no farther
apart than a sixth of their mean side length and one is a horizontal neighbour of the other; *under* when the other is
directly above it; *touching* when the two are in contact. An object is *closed* when none of its openable joints is
more than 5 % of its range away from closed, and *switched on* when its toggle state is on.

Success needs more than these conditions: they hold for 30 consecutive control steps (1 s of simulated time), and on
each of those steps no object they name (furniture and floors included; a substance has no pose and is not checked) is
held by a gripper's assisted grasp, and each of those objects moves slower than 0.05 m/s. There is no partial credit.

Graded is the one live episode (no reset), judged by the simulator service; nothing is replayed. A success during the
episode neither ends it nor is reported. The episode ends at the agent's `/finish` or when the time limit (2 h)
is up. The robot then holds its last command with the base still for up to 150 control steps (5 s), and the task passes
if the success rule holds at the end of that window (it stops as soon as the rule holds; steps that held before the end
count toward the 30). The episode also ends, with 0, when the robot has fallen over (its base more than 3 cm below the
floor, or its up axis tilted more than 41.4° from vertical, for 300 consecutive control steps, also within the window),
on a simulator breakdown (a non-finite robot state, the robot or a named object more than 10 km from the origin, or the
base faster than 100 m/s), or on a simulator error raised by an agent's call. At the runaway guard of 200,000 control
steps the episode ends and is judged as it stands, without the window.

Repeated service crashes that all happened while serving the agent's calls score 0. A frozen start that does not rebuild
(checked before the agent is served), a crash the episode cannot be resumed from, or a service that leaves no finalized
result is an infrastructure error, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 24 GiB | 8192 | no GPU | 10 GiB |
| `sim` | 12 | 32 GiB | 4096 | 16 GiB | — |
| verifier (as `main`) | 8 | 24 GiB | no cap | no GPU | 10 GiB |

- GPU: an RTX-class NVIDIA GPU (ray-tracing cores), one of the models in `gpu_types`: L40S, L40, L4, RTX 4090, RTX 6000 Ada, held by `sim`.
- Recommended GPU: L40S 48GB / L4 24GB / RTX 4090 24GB.

## License
The task definitions (BDDL activity definitions) and the simulator are BEHAVIOR-1K's
([StanfordVL/BEHAVIOR-1K](https://github.com/StanfordVL/BEHAVIOR-1K) v3.9.2: OmniGibson and bddl, MIT License; paper: Li
et al., 2024, "BEHAVIOR-1K: A Human-Centered, Embodied AI Benchmark with 1,000 Everyday Activities and Realistic
Simulation", arXiv:2403.09227). The scenes, objects, robot assets and task instances are the BEHAVIOR Data Bundle, under
the BEHAVIOR Data Bundle End User License Agreement: **non-commercial academic research use only (NC)**, no
redistribution, use only within OmniGibson. It is never in an image or in this repository; each user downloads it after
accepting that licence and mounts it read-only. The simulator image contains NVIDIA Isaac Sim 5.1 and Omniverse Kit
(NVIDIA proprietary licence terms, accepted when the image is built).
