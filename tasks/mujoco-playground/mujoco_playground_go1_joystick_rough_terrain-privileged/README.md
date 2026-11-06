# mujoco_playground_go1_joystick_rough_terrain-privileged

| | |
|---|---|
| Benchmark | MuJoCo Playground |
| Mode | privileged |
| Twin | `mujoco_playground_go1_joystick_rough_terrain-standard` |
| Simulator / robot | `mujoco` / `unitree-go1` |
| Family / instance | `mujoco_playground/Go1JoystickRoughTerrain` / seed 1 |
| Oracle | `full` |
| Agent time budget | 1800 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:mujoco-0.1.3` |

## Task
MuJoCo Playground `Go1JoystickRoughTerrain` (Unitree Go1), rebuilt in plain MuJoCo from Playground's scene files: Make the Unitree Go1 follow the joystick command schedule on rough terrain (a 20 x 20 m heightfield, up to 5 cm high) for the whole 20 s episode without falling over.
For 20 s the robot gets a joystick command schedule (7 segments: planar velocity and yaw rate in its own frame) and must track it without falling over. The ground is a 20 x 20 m heightfield with bumps up to 5 cm. The deliverable is one replayable trajectory of joint position targets
(`/app/output/trajectory.npz`, `(T, 12)`, T = 1000 (the whole schedule)).

## Difficulty
Velocity tracking for 20 s: the agent has to make a 12-joint quadruped walk (a gait, not one motion) and steer it through the schedule's changes of speed, direction and turning rate, and an open-loop trajectory of 1000 steps only works if it is computed against the simulator. Torque limits and a soft PD drive leave little margin; Playground trains a neural policy with 200 M steps of PPO for this. On the heightfield the feet land at unpredictable heights: Playground's own Go1 policy, which made the reference, falls or loses track on some of the candidate seeds (the instance selection skips them).

## Reference solution
MuJoCo Playground's own Go1 joystick policy (`experimental/sim2sim/onnx/go1_policy.onnx` @4057c14, not in the image) run closed loop on this instance with the observation of Playground's `play_go1_joystick.py`, its targets recorded: worst segment errors 0.079 m/s and 0.114 rad/s. Replayed by `solution/solve.sh` (`solution/oracle.npy`, 1000 rows); the rows are float32-exact, so the
standard twin's client executes the same targets. Re-verified: two
fresh-process replays succeed and end in the same state.

## Verification
`tests/grade.py` in a separate sandbox without network: one replay, in a fresh process, from the verifier's own
copy of the instance (`tests/instance.json`; the start state is checked against its hash on every load); pass iff it
succeeds. Oracle: success, worst segment errors 0.079 m/s and 0.114 rad/s. `nop`: no trajectory, reward 0.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 10 GiB | 2048 | no GPU | 10 GiB |
| verifier | 4 | 8 GiB | no cap | no GPU | no cap |

- GPU: not needed.

## Details
| | |
|---|---|
| Upstream | MuJoCo Playground @ 4057c14 (Apache-2.0): `locomotion/go1/xmls/scene_mjx_feetonly_rough_terrain.xml`; MuJoCo Menagerie @ 1b86ece (`unitree_go1`); simulated in MuJoCo 3.3.7 on the CPU |
| Instance | Playground's `reset` with `jax.random.PRNGKey(1)` and Playground's command process over the 1000 steps; chosen (seed 1; skipped 0: reference fails) |
| Actions | 12 joint position targets per control step (0.02 s of simulated time); kp = 35 N m/rad, joint damping 0.5 N m s/rad |
| Resources | 4 CPUs, no GPU (CPU physics, EGL or OSMesa rendering) |
