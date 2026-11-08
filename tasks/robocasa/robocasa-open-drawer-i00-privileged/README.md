# robocasa-open-drawer-i00-privileged

| | |
|---|---|
| Benchmark | RoboCasa |
| Mode | privileged |
| Twin | `robocasa-open-drawer-i00-standard` |
| Simulator / robot | `robosuite` / `franka-panda-omron` |
| Family / instance | `robocasa/OpenDrawer` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:robocasa-0.1.0` |

## Task
RoboCasa's `OpenDrawer` kitchen task with a Franka Panda arm on an Omron mobile base (with a torso lift): Open the right drawer. Produce one replayable trajectory of the robot's native controller commands on one frozen instance; graded on the state after the last action. Benchmark notes in `tasks/robocasa/README.md`.

## Difficulty
Full privileged state, unlimited resets and self-replay; a mobile manipulator in a cluttered kitchen, long-horizon contact-rich manipulation with a 20 Hz controller. The standard twin removes the privileged state.

## Reference solution
The demonstration's own actions (original: 201 actions), executed from the frozen scene by the robot's own controller: 201 actions in `solution/oracle.npz`. The demonstration is a reference solution: it is not in the image and the agent cannot reach it.

## Verification
`tests/grade.py` in a separate sandbox without network: one replay in a fresh process from the verifier's own copy of the instance; `success = success on the final state ∧ not solved at the start`. Reference: a fresh-process replay ends in the live run's state (hash `2b038b1ccb46…`) and succeeds. `nop`: no trajectory, reward 0; the instance is not solved at the start.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 15 GiB | 1024 | no GPU | 10 GiB |
| verifier | 4 | 16 GiB | no cap | no GPU | no cap |

- GPU: not needed.

## Details
| | |
|---|---|
| Source | [RoboCasa](https://github.com/robocasa/robocasa) @ 756598a (v0.2; MIT), robosuite 1.5.1, MuJoCo 3.2.6; [environment source](https://github.com/robocasa/robocasa/blob/756598a5be52e052339bb2d957426e39015c2afb/robocasa/environments/kitchen/single_stage/kitchen_drawer.py#L185) |
| Instance | the initial state of official demonstration episode 0 (`demo_1`, v0.1/single_stage/kitchen_drawer/OpenDrawer/2024-05-03); MuJoCo state, model arrays, task state and RNG frozen in `instance.npz` (SHA-256 `129942a0a014…`, checked on load) |
| Deliverable | `(T, 12)` native controller commands, 1 ≤ T ≤ 3000, 20 Hz |
| Success | the environment's own check (`_check_success`) on the state after the last action |
