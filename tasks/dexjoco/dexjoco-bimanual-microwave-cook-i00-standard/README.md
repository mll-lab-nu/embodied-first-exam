# dexjoco-bimanual-microwave-cook-i00-standard

| | |
|---|---|
| Benchmark | DexJoCo |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `dexjoco-bimanual-microwave-cook-i00-privileged` |
| Simulator / robot | `dexjoco` / `franka-allegro-bimanual` |
| Family / instance | `bimanual_microwave_cook` / seed 0 (allowed seeds: [0, 1, 2]; PROTOCOL §2) |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:dexjoco-0.1.2` |

## Task
DexJoCo `bimanual_microwave_cook` (two Franka Panda arms, each with a 16-DoF Allegro hand) on the same frozen instance as `dexjoco-bimanual-microwave-cook-i00-privileged`: Open the microwave door, put the hot dog inside, close the door and press the start button. Success, at one control step: the hot dog is inside the cavity (1 cm margin), the door hinge is within 0.01 rad of closed, and the start button is in contact with something.
Standard mode (eai-standard/2.2): the agent drives the robot through a client in one episode, with the robot's own
sensors, calibrated cameras (RGB, optional depth) and the robot's kinematics.

## Difficulty
Same instance and success check as `dexjoco-bimanual-microwave-cook-i00-privileged`. In standard mode the agent loses resets, the
simulator and the object poses: it sees camera images and proprioception, acts in chunks of tcp-target + hand-joint rows
(or joint targets), and gets one episode, so it has to close the loop on what the cameras show and recover from its own
mistakes without starting over.

## Reference solution
`solution/oracle_stream.py` streams the privileged reference's rows (`solution/oracle_trajectory.npz`, 815 rows, float32-exact)
through the client as `ee_pose` chunks; it uses no privileged information at run time. The service's recorded
trajectory is then exactly the privileged reference, and the episode ends with success after 815 control steps.

## Verification
The verdict is the live episode's (`graded_by = "live"`, `replays = 0`): the sim service judges the episode it runs with
DexJoCo's own success check and records every executed control step. The collect hook
(`environment/sim/finalize.sh`) ends the service, writes that verdict into `final.json` (nothing is replayed to grade
it), then renders `replay.mp4` from the recorded trajectory in one video-only pass (`environment/sim/video.py`), which
never changes the verdict. `tests/grade.py` (separate sandbox, no network) passes iff the live episode ended in success.
The service checks the frozen instance when the episode begins: a scene that does not rebuild to the instance's recorded
state hash gets no episode (`instance_mismatch`, `grader_error` and `infra_error` = 1). A `final.json` that is missing,
unreadable or without a verdict (the hook did not finish), a give-up after crashes between the agent's calls, and a sim
sidecar that runs fewer than 4 OpenBLAS threads (fewer than 4 CPUs visible to it: the service starts no episode,
`too_few_cpus`, `grader_error` and `infra_error` = 1) are infrastructure failures (`infra_error = 1`), not the agent's 0.
Oracle: success after 815 control steps.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 10 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 4 | 6 GiB | 1024 | no GPU | — |
| verifier (as `main`) | 4 | 10 GiB | no cap | no GPU | 10 GiB |

- GPU: not needed.

## Details
| | |
|---|---|
| Upstream | DexJoCo @ 8d23b0f (brave-eai/dexjoco, MIT) on MuJoCo 3.4.0; CPU physics, OSMesa rendering, no GPU |
| Instance | the initial state of the human demonstration `microwave_cook_demo_10_2026-02-09_11-56-09_655851` (DexJoCo-Datasets-Raw); instance sha `6c16f3cfa1c737c7` |
| Service | `environment/sim/server.py` (the adapter) on the shared 2.2 layer `rcb_limited.py` (`embodied_first_exam/standard/`); action types `ee_pose` and `joint_position`; cameras `back`, `handcam_rgb_right`, `handcam_rgb_left` (640 x 480); `/kinematics` for the arm links, the hand mount and the tcp; crash recovery class `exact` |
| Resources | 4 CPUs, 8 GB, no GPU; `OPENBLAS_NUM_THREADS=4` in the sim sidecar (the service, a resume and the video pass: the simulation's result depends on the thread count below 4, tasks/dexjoco/README.md). The 4 CPUs must be visible to the sidecar (its cpuset / affinity; a `cpus:` quota does not matter): OpenBLAS runs no more threads than that. The collect hook replays nothing; its one video pass takes about 9 CPU-minutes per trial (median; at most 4500 s) |

### Provenance
Generated as its privileged twin is, from the same frozen instance.
