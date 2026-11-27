# LIBERO-MAX · libero_10 · obstacle insertion (standard)

| | |
|---|---|
| Task ID | `libero-max-long-black-bowl-in-wooden-cabinet-bottom-closed-obstacle-insertion-i00-standard` |
| Benchmark | [LIBERO-MAX](https://github.com/liberomax/LIBERO-MAX) (Zhang et al., 2026), upstream `liberomax/LIBERO-MAX@a1e3cef` |
| Robot | Franka Emika Panda arm on a fixed mount with its two-finger gripper (LIBERO's OSC_POSE controller) |
| Mode | standard |
| Instance | `libero-max/libero_10/obstacle_insertion`, seed 195 |
| Time limit | 30 min |
| Reference solution | Included |

## Task
Put the black bowl in the bottom drawer of the cabinet, then close the drawer all the way.

## Success criteria
Goal, both of: (1) the bowl (`black_bowl_1`) is in the bottom drawer's region (`wooden_cabinet_1_bottom_region`), which moves with the drawer: its origin lies inside the region's box, centred on the region, with half-sizes 2.99, 7.56 and 10.22 cm along the region's own axes (LIBERO turns them into the world frame and takes their absolute values) and its bottom lowered by 1 cm; contact is not checked; and (2) the bottom drawer is closed: its slide is above 0 m (the slide runs from -0.16 m, pulled out, to 0.01 m).

The scene changes once in the graded episode, at the first control step on which the hand (robosuite's end-effector point) is within 0.18 m of the position of the bowl (`black_bowl_1`): LIBERO-MAX places `wine_bottle_1` next to the bowl (`black_bowl_1`) as an obstacle. The obstacle is not part of the goal.

An object's origin is its body's position in the simulator. A control step is 1/20 s.

Graded is the one live episode (no reset), with the scene change applied as above. A success does not end it: the
episode ends at the agent's `POST /finish`, after 9,000 control steps, or when the agent's session ends, and the goal
is checked once, on the state after the last control step; a success earlier in the episode does not count. A
simulator error raised by the agent's actions ends the episode with 0, as do service crashes that all happened while
serving the agent's calls. A scene that does not start at the frozen instance's recorded state, service crashes outside
the agent's calls, a resume that fails or a verdict the service never writes is an infrastructure error, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 3 | 10 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 3 | 6 GiB | 1024 | no GPU | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: not needed.

## License
LIBERO-MAX ([liberomax/LIBERO-MAX](https://github.com/liberomax/LIBERO-MAX) @ `a1e3cef`; Zhang et al., 2026,
arXiv:2609.36518) has no licence file. Its authors gave written permission to redistribute the two parts used here, the
event parameters and case choice (the frozen instance) and the event runtime in the image, with attribution (cite the
paper and link the repository). The LIBERO package and object assets come from LIBERO-PRO
([Zxy-MLlab/LIBERO-PRO](https://github.com/Zxy-MLlab/LIBERO-PRO) @ `2b910b5`, MIT), built on
[LIBERO](https://github.com/Lifelong-Robot-Learning/LIBERO) (MIT); the task data (BDDL and initial-state files) is
LIBERO-PRO's dataset `zhouxueyang/LIBERO-Pro` @ `c86fc3b` (CC BY 4.0). robosuite 1.4.0: MIT; MuJoCo 3.2.6: Apache-2.0.
No part is under a non-commercial licence.
