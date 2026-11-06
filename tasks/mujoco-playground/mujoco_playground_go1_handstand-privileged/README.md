# mujoco_playground_go1_handstand-privileged

| | |
|---|---|
| Benchmark | MuJoCo Playground |
| Mode | privileged |
| Twin | `mujoco_playground_go1_handstand-standard` |
| Simulator / robot | `mujoco` / `unitree-go1` |
| Family / instance | `mujoco_playground/Go1Handstand` / seed 0 |
| Oracle | `full` |
| Agent time budget | 1800 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:mujoco-0.1.3` |

## Task
MuJoCo Playground `Go1Handstand` (Unitree Go1), rebuilt in plain MuJoCo from Playground's scene files: Make the Unitree Go1 do a handstand: balance on its front legs, nose down, hind legs in the air, for 2 s.
From standing, it has 10 s to get into a handstand on its front legs and hold it for 2 s (Playground's handstand reward aims at the IMU 0.55 m high). The deliverable is one replayable trajectory of joint position targets
(`/app/output/trajectory.npz`, `(T, 12)`, 1 <= T <= 500).

## Difficulty
Dynamic balance on two legs: the robot has to throw its weight onto its front legs, lift the other pair and then balance an inverted, top-heavy body on two small feet with 35 N m/rad position drives, correcting continuously; a front leg touching the floor or a tip-over ends it. Playground's handstand is trained with 100 M steps of PPO.

## Reference solution
A policy trained here on Playground's Go1Handstand reward (PPO on the CPU; the training code is not in the image), run closed loop with Playground's action semantics (targets accumulate) until the hold completes: 115 control steps, pose angle 13.8 deg and IMU at 0.531 m at the end. Replayed by `solution/solve.sh` (`solution/oracle.npy`, 115 rows); the rows are float32-exact, so the
standard twin's client executes the same targets. Re-verified: two
fresh-process replays succeed and end in the same state.

## Verification
`tests/grade.py` in a separate sandbox without network: one replay, in a fresh process, from the verifier's own
copy of the instance (`tests/instance.json`; the start state is checked against its hash on every load); pass iff it
succeeds. Oracle: success after 115 control steps. `nop`: no trajectory, reward 0.

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
| Upstream | MuJoCo Playground @ 4057c14 (Apache-2.0): `locomotion/go1/xmls/scene_mjx_flat_terrain.xml`; MuJoCo Menagerie @ 1b86ece (`unitree_go1`); simulated in MuJoCo 3.3.7 on the CPU |
| Instance | Playground's `reset` with `jax.random.PRNGKey(0)` (xy, yaw and base velocity); chosen (seed 0; the first candidate) |
| Actions | 12 joint position targets per control step (0.02 s of simulated time); kp = 35 N m/rad, joint damping 0.5 N m s/rad |
| Resources | 4 CPUs, no GPU (CPU physics, EGL or OSMesa rendering) |
