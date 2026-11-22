# mujoco_playground_go1_joystick_rough_terrain-standard

| | |
|---|---|
| Benchmark | MuJoCo Playground |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `mujoco_playground_go1_joystick_rough_terrain-privileged` |
| Simulator / robot | `mujoco` / `unitree-go1` |
| Family / instance | `mujoco_playground/Go1JoystickRoughTerrain` / seed 1 |
| Oracle | `full` |
| Agent time budget | 1800 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:mujoco-0.1.3` |

## Task
MuJoCo Playground `Go1JoystickRoughTerrain` (Unitree Go1) on the same frozen instance as `mujoco_playground_go1_joystick_rough_terrain-privileged`: Make the Unitree Go1 follow the joystick command schedule on rough terrain (a 20 x 20 m heightfield, up to 5 cm high) for the whole 20 s episode without falling over.
For 20 s the robot gets a joystick command schedule (7 segments: planar velocity and yaw rate in its own frame) and must track it without falling over. The ground is a 20 x 20 m heightfield with bumps up to 5 cm. Standard mode (eai-standard/2.2): the agent drives the robot through a client, with 10 resets (only
the last episode is graded), the robot's own sensors and the cameras that follow it.

## Difficulty
Same instance and success check as `mujoco_playground_go1_joystick_rough_terrain-privileged`. In standard mode the agent loses free resets, the simulator and
the world state: it sees camera images and proprioception (joints, IMU, foot contacts), acts in joint position chunks,
and gets 10 resets (`RCB_RESET_BUDGET`, the compose file's default; PROTOCOL §2), so it has to close the loop
on the robot's own sensors; only the last episode is graded.

## Reference solution
`solution/oracle_replay.py` streams the privileged reference's rows (`solution/oracle.npy`, 1000 rows, float32-exact)
through the client in `hold` chunks; it uses no privileged information at run time. The service's recorded trajectory
is then exactly the privileged reference, and the episode ends after the 1000 steps of the schedule, with success.

## Verification
The verdict is the live episode's (`graded_by = "live"`, `replays = 0`): the sim service runs the task's check on the
episode it ran and records every executed control step. The collect hook (`environment/sim/finalize.sh`) ends the
service, writes that verdict into `final.json` (nothing is replayed to grade it), then renders `replay.mp4` from the
recorded trajectory in one video-only pass (`environment/sim/video.py`), which never changes the verdict;
`tests/grade.py` (separate sandbox, no network) passes iff the live check succeeded. The service checks the frozen
instance when it builds the scene: a start state that does not hash to the instance's `state_sha` gets no episode
(`instance_mismatch`, `infra_error = 1`). Oracle: success, worst segment errors 0.079 m/s and 0.114 rad/s.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 2 | 4 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 4 | 4 GiB | 1024 | no GPU | — |
| verifier (as `main`) | 2 | 4 GiB | no cap | no GPU | 10 GiB |

- GPU: not needed.

## Details
| | |
|---|---|
| Upstream | MuJoCo Playground @ 4057c14 (Apache-2.0): `locomotion/go1/xmls/scene_mjx_feetonly_rough_terrain.xml`; MuJoCo Menagerie @ 1b86ece (`unitree_go1`); MuJoCo 3.3.7 on the CPU |
| Service | `environment/sim/server.py` (the adapter) on the shared 2.2 layer `rcb_limited.py` (`embodied_first_exam/standard/`); cameras `track`, `side`, `back`, `top` (they follow the robot) (320 x 240), the feet's kinematics in the trunk frame |
| Resources | 4 CPUs, no GPU (CPU physics, EGL or OSMesa rendering); the collect hook replays nothing, its video pass takes well under a minute (at most the horizon, ~150 frames) |
