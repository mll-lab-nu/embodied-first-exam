# LIBERO-MAX · libero_goal · sensor-noise onset (standard)

| | |
|---|---|
| Task ID | `libero-max-goal-flat-stove-on-sensor-noise-onset-i00-standard` |
| Benchmark | [LIBERO-MAX](https://github.com/liberomax/LIBERO-MAX) (Zhang et al., 2026), upstream `liberomax/LIBERO-MAX@a1e3cef` |
| Robot | Franka Emika Panda arm on a fixed mount with its two-finger gripper (LIBERO's OSC_POSE controller) |
| Mode | standard |
| Instance | `libero-max/libero_goal/sensor_noise_onset`, seed 195 |
| Time limit | 30 min |
| Reference solution | Included |

## Task
Turn on the stove.

## Success criteria
Goal: the stove (`flat_stove_1`) is on: its knob's hinge is at 0.5 rad or more (the knob turns from -0.005 to 2.1 rad).

The scene changes once in the graded episode, at the first control step on which the hand (robosuite's end-effector point) is within 0.18 m of the position of the stove (`flat_stove_1`): LIBERO-MAX adds noise and occluding patches to the camera images. Only the camera images change; the goal check does not use them.

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
