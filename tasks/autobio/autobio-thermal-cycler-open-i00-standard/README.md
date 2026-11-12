# autobio-thermal-cycler-open-i00-standard

| | |
|---|---|
| Benchmark | AutoBio |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `autobio-thermal-cycler-open-i00-privileged` |
| Simulator / robot | `autobio` / `ur5e-robotiq-2f85` |
| Family / instance | `thermal_cycler_open` / seed 0 (allowed seeds: [0, 1, 2]; PROTOCOL §2) |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:autobio-0.1.0` |

## Task
AutoBio's `thermal_cycler_open` (Open thermal cycler lid) on the same frozen instance as `autobio-thermal-cycler-open-i00-privileged`: Open the lid of the thermal cycler, which starts closed and locked: turn the lever on the lid back from its locked end (0.94 rad of travel) and swing the lid fully open (1.9 rad). Success the moment the lid and its lever are both within 0.003 rad of their fully open end positions.
On the bench: a thermal cycler (a Bio-Rad C1000 model) with its lid closed and locked by the lever on the lid. Standard mode (eai-standard/2.2): the agent drives the robot through a client in one episode, with only its proprioception and the scene's cameras.

## Difficulty
Same instance and success rule as `autobio-thermal-cycler-open-i00-privileged` (AutoBio's level: easy). Two articulated parts have to come back to their open end stops within 0.003 rad: the lever that locks the lid, and the lid. In standard mode the agent loses resets, the simulator and the state of the tubes and instruments: it sees camera images and the robot's proprioception, acts in joint-position chunks, and gets one episode, so it has to find the things it handles in the images and recover from its own mistakes without starting over.

## Reference solution
`solution/oracle_stream.py` streams the privileged reference's rows (`solution/oracle.npz`, 8251 rows, float32-exact) through the client in `hold` chunks; it uses no privileged information at run time. The service's recorded trajectory is then exactly the privileged reference: success after 8251 control steps.

## Verification
Graded by the live episode (docs/protocol/README.md H.4): `success` = the live episode's success, judged by the sim service on the episode the agent ran, with no grading replay; an episode that ended in a simulator error scores 0. The service records every executed control step; the collect hook (`environment/sim/finalize.sh`) ends the service, writes `final.json` from the live episode's record and, after the verdict is on disk, replays the recorded trajectory once from the frozen instance to render `replay.mp4` (a failed video replay costs the video only). `tests/grade.py` (separate sandbox, no network) writes the reward fields (`graded_by_live` = 1, `replays` = 0, `infra_error`, the crash-recovery fields). A missing or unfinished `final.json` (the hook never wrote its verdict) and a live episode that did not start in the instance's recorded state are `infra_error = 1`, never the agent's 0. `nop`: the episode times out, reward 0.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 4 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 4 | 12 GiB | 1024 | no GPU | — |
| verifier (as `main`) | 4 | 4 GiB | no cap | no GPU | 10 GiB |

- GPU: not needed.

## Details
| | |
|---|---|
| Upstream | AutoBio (github.com/autobio-bench/AutoBio @ 0850421, no licence stated: the image is built locally, images/autobio/BUILD_ONLY) on MuJoCo 3.3.0 |
| Service | `environment/sim/server.py` (the adapter) on the shared 2.2 layer `rcb_limited.py` (`embodied_first_exam/standard/`); cameras `table_cam_front`, `table_cam_left`, `wrist_cam` (640 x 480); action types `joint_position` and `done`; forward and inverse kinematics of the arm joints |
| Resources | 4 CPUs, no GPU (CPU physics, OSMesa rendering) |
