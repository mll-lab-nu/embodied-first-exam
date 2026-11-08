# robocasa365-drain-veggies-i00-privileged

| | |
|---|---|
| Benchmark | RoboCasa365 |
| Mode | privileged |
| Twin | `robocasa365-drain-veggies-i00-standard` |
| Simulator / robot | `robosuite` / `franka-panda-omron` |
| Family / instance | `robocasa365/DrainVeggies` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:robocasa365-0.1.0` |

## Task
RoboCasa365's `DrainVeggies` kitchen task with a Franka Panda arm on an Omron mobile base (with a torso lift): Dump the lettuce from the pot into the sink. Then turn on the water and wash the lettuce. Then turn off the water and put the lettuce back in the pot. Produce one replayable trajectory of the robot's native controller commands on one frozen instance; graded on the state after the last action. Benchmark notes in `tasks/robocasa365/README.md`.

## Difficulty
Full privileged state, unlimited resets and self-replay; a mobile manipulator in one of RoboCasa365's large, cluttered kitchens, long-horizon contact-rich manipulation with a 20 Hz controller. The standard twin removes the privileged state.

## Reference solution
Retargeted by PR #4 from official demonstration episode 0 (`demo_0`, 1250 recorded actions; RoboCasa365's demonstrations use a different arm controller): it follows the demonstration's recorded arm joint positions as this controller's absolute joint targets (PR #4 method `demo_joint`). Executed from the frozen scene by the robot's own controller: 1250 actions in `solution/oracle.npz`. Neither the demonstration nor the reference is in the image; the agent cannot reach them.

## Verification
`tests/grade.py` in a separate sandbox without network: one replay in a fresh process from the verifier's own copy of the instance; `success = success on the final state ∧ not solved at the start`. Reference: a fresh-process replay ends in the live run's state (hash `2ff5719b87e1…`) and succeeds. `nop`: no trajectory, reward 0; the instance is not solved at the start.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 20 GiB | 1024 | no GPU | 10 GiB |
| verifier | 4 | 16 GiB | no cap | no GPU | no cap |

- GPU: not needed.

## Details
| | |
|---|---|
| Source | [RoboCasa365](https://github.com/robocasa/robocasa) @ 4f8a298 (robocasa 1.0.1; MIT), robosuite @ 5ce6643 (1.5.2), MuJoCo 3.3.1; [environment source](https://github.com/robocasa/robocasa/blob/4f8a2980def75a55dff96b990745b83540425f09/robocasa/environments/kitchen/composite/washing_fruits_and_vegetables/drain_veggies.py#L4) |
| Instance | the initial state of official demonstration episode 0 (`demo_0`); MuJoCo state, model arrays, task state and RNG frozen in `instance.npz` (SHA-256 `59dae1f7b031…`, checked on load) |
| Deliverable | `(T, 13)` native controller commands, 1 ≤ T ≤ 3000, 20 Hz |
| Success | the environment's own check (`_check_success`) on the state after the last action: the lettuce has been washed: inside the sink with the water on for more than 10 consecutive checks (the check runs twice per control step: at least 6 control steps; once washed it stays washed); at the end the lettuce is in the pot and the water is off (the water is on while the faucet handle's on / off hinge is between 0.40 rad and π rad). The handle turns on two hinges at one pivot: the on / off hinge, whose range is 0 to 0.5 rad (so the water is on only over the last fifth of its travel), turns about the sink's front-to-back axis, so the handle swings sideways; the temperature hinge (about ±0.79 rad) tilts the handle toward or away from you and never turns the water on or off. |
