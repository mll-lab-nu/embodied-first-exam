# roboEngineer · g1-terrain-walk (standard)

| | |
|---|---|
| Task ID | `roboengineer-g1-terrain-walk-i00-standard` |
| Benchmark | [roboEngineer](https://www.embodied-first-exam.ai/suite/roboengineer/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | Unitree G1 29-DoF humanoid |
| Mode | standard |
| Instance | `roboengineer/g1-terrain-walk`, seed 0 |
| Time limit | 4 h |
| Reference solution | Pipeline check only |

## Task
Make the G1 stand, then walk forward at its commanded speed over flat, sloped, rough or stepped ground without falling.

## Success criteria
There are 12 held-out cases, three on each kind of ground: flat, sloped, rough and stepped. Each is a 20 s episode in
which the forward speed command (0.5, 0.6 or 0.65 m/s) starts at 2 s. A case succeeds when the G1 does not fall during
the 20 s, its mean absolute error between forward speed and the command from 2 s on is below 0.25 m/s, its forward travel
from 2 s on is more than 65 % of the commanded distance (speed × 18 s), and its sideways travel is less than 2 m. The G1
has fallen, which ends the case as a failure, when its pelvis comes within 0.45 m of the ground below it or its body
tilts more than 60° from upright.

The evaluator grades one policy: the deployment round the agent sealed or, without a seal, the latest round that
completed before the agent's session ended (at the latest after 4 h). A round still running at that moment is
not graded, and with no completed round the score is 0. The evaluator runs that policy on every held-out case, each in
two fresh processes without rendering; the two runs must give the same state hash, metrics and noisy observations. The
task succeeds when every held-out case succeeds. `final_reward` is the mean case score (0 to 100); it does not decide
success. A case in which the simulation diverges fails. A failure of the evaluator itself (a missing or mismatched
asset or instance, a worker crash, two runs that disagree) is an infrastructure error, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 12 GiB | 1024 | 20 GiB | 10 GiB |
| `sim` | 4 | 6 GiB | 1024 | no GPU | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: any NVIDIA GPU, held by `main`.
- Recommended GPU: L40S 48GB (all measurements; a 24 GB card fits the memory but trains slower, so fewer iterations fit the cutoff).

## License
roboEngineer is an original suite of Embodied First Exam. Its components carry their own terms: AnyCar's car mechanism
([LeCAR-Lab/anycar](https://github.com/LeCAR-Lab/anycar) @ `20fc50a`, Apache License 2.0 as its README declares) and
F1DB's circuit outlines ([f1db/f1db](https://github.com/f1db/f1db) @ `7cf634e`, CC BY 4.0; `anycarbench/NOTICE`);
the Unitree G1 model and training task of [unitreerobotics/unitree_rl_mjlab](https://github.com/unitreerobotics/unitree_rl_mjlab)
@ `1425b15` (Apache License 2.0); MuJoCo Menagerie's Unitree Go2 (BSD 3-Clause, Unitree Robotics) and Skydio X2
(Apache License 2.0) models. The Neural Fly force fit is made from the flight logs of
[aerorobotics/neural-fly](https://github.com/aerorobotics/neural-fly) @ `0ed5024`, which are **for personal and
educational use only** (written permission from the authors is needed for further use); the fit is not distributed.
The Neural Landing residual is converted from the checkpoint of
[GuanyaShi/neural_lander_sim_1d](https://github.com/GuanyaShi/neural_lander_sim_1d) @ `30ab04c`, which states no
licence. The simulator is MuJoCo (Apache License 2.0).
