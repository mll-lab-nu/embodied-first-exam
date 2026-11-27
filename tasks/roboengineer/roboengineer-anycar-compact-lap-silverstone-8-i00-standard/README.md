# roboEngineer · anycar-compact-lap-silverstone-8 (standard)

| | |
|---|---|
| Task ID | `roboengineer-anycar-compact-lap-silverstone-8-i00-standard` |
| Benchmark | [roboEngineer](https://www.embodied-first-exam.ai/suite/roboengineer/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | AnyCar 1/10-scale racing car (contact wheels, suspension, steering) |
| Mode | standard |
| Instance | `roboengineer/anycar-compact-lap-silverstone-8`, seed 0 |
| Time limit | 4 h |
| Reference solution | Included |

## Task
Drive the car round one lap of the small F1-style track, keeping up with the moving target that sets the pace, without a
collision or leaving the track.

## Success criteria
There are 10 held-out cases. Each is a 30 s episode on a 45 m closed loop shaped after the Silverstone circuit and
lined with barriers; the car is sampled every 0.02 s against a moving target that runs the lap in 27.5 s. The lap has
90 gates, lines across the route every 0.5 m; a gate counts when the car crosses it forward, in order, less than 0.45 m
from the centre line. A case succeeds when the car passes every gate within the episode, the root-mean-square distance
to the moving target is below 0.30 m, the mean heading error is below 0.18 rad, the mean speed error is below 0.25 m/s
and the final distance to the target is below 0.35 m. The case fails if the car or a tyre touches a barrier, the chassis
touches the ground, the car tips more than 60° from upright, or the car is ever more than 0.70 m from the centre line.

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
| `main` (the agent's) | 2 | 6 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 4 | 6 GiB | 1024 | no GPU | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: not needed.

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
