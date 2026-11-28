# roboEngineer · neuralfly-eight (standard)

| | |
|---|---|
| Task ID | `roboengineer-neuralfly-eight-i00-standard` |
| Benchmark | [roboEngineer](https://www.embodied-first-exam.ai/suite/roboengineer/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | Neural Fly quadrotor airframe, approximated as a symmetric X quadrotor |
| Mode | standard |
| Instance | `roboengineer/neuralfly-eight`, seed 0 |
| Time limit | 4 h |
| Reference solution | Included |

## Task
Fly the drone through six timed laps of a vertical figure eight, keeping close to the moving target the whole time.

## Success criteria
There are 10 held-out cases, two for each of five wind conditions.
The course is a vertical figure eight (2.5 m wide, 1.5 m tall) that the moving target runs in 2π s per lap.
Each case runs six laps of the figure eight. A case succeeds when the drone flies all six laps without a crash
and the root-mean-square distance between the drone and the moving target, over every control step (0.02 s) from the
first one, is below 0.25 m. A crash ends the case as a failure: any contact, a non-finite or unstable simulation state,
or the drone more than 5 m from the figure eight's centre.

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

## Others
This task needs the Neural Fly force fit, which is not distributed: build the evaluator image with
`images/control-transfer/fetch_assets.sh --fit-fly`, which makes the fit locally from the public flight logs.

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
