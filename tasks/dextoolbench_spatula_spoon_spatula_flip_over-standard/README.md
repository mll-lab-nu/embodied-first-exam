# dextoolbench_spatula_spoon_spatula_flip_over-standard

| | |
|---|---|
| Benchmark | DexToolBench |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `dextoolbench_spatula_spoon_spatula_flip_over-privileged` |
| Simulator / robot | `mujoco` / `kuka-iiwa14-sharpa-ha4` |
| Family / instance | `dextoolbench/spatula/spoon_spatula/flip_over` / seed 0 |
| Oracle | `partial` — SimToolReal's pretrained policy, replayed in this scene, reaches 6/40 goals (solution/; README of dextoolbench_spatula_spoon_spatula_flip_over-privileged) |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/jameskrw/rcb-mujoco:0.1.2` |

## Task
Standard-mode twin of `dextoolbench_spatula_spoon_spatula_flip_over-privileged` (see its README): the same scene, instance and scoring, served as a robot service (`images/mujoco/limited/server_mj.py`, protocol eai-standard/2.1, tooling `rcb_dtb`). The agent sees camera RGB-D and proprioception only.

## Difficulty
Same scene, instance and success rule as `dextoolbench_spatula_spoon_spatula_flip_over-privileged` (see its Difficulty). In standard mode the agent loses resets, privileged state and planning primitives: it sees camera images and proprioception only, acts through the client, and gets one episode, so it has to estimate the scene from images and recover from its own mistakes without starting over.

## Reference solution
`solution/`: the privileged-mode oracle's recorded targets submitted through the client (one row per control step)

## Verification
the sidecar replays the recorded episode in a fresh simulator; `deterministic` = same final state as the live episode
