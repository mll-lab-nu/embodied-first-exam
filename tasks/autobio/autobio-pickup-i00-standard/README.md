# autobio-pickup-i00-standard

| | |
|---|---|
| Benchmark | AutoBio |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `autobio-pickup-i00-privileged` |
| Simulator / robot | `autobio` / `aloha-2-arm` |
| Family / instance | `pickup` / seed 0 (allowed seeds: [0, 1, 2]; PROTOCOL §2) |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:autobio-0.1.0` |

## Task
AutoBio's `pickup` (Pick up centrifuge tube) on the same frozen instance as `autobio-pickup-i00-privileged`: Pick up the 50 mL centrifuge tube (orange screw cap) that stands in the blue rack: hold it by its cap and lift it at least 9.5 cm. Success the moment the tube is that high while the gripper holds it by the cap (the test looks for contact between the cap and the gripper's left finger, so the cap has to be between the fingers).
On the bench: a 10-slot tube rack (2 rows of 5) with one capped 50 mL tube standing in it. Standard mode (eai-standard/2.2): the agent drives the robot through a client in one episode, with only its proprioception and the scene's cameras.

## Difficulty
Same instance and success rule as `autobio-pickup-i00-privileged` (AutoBio's level: easy). The tube is lifted out of its rack slot by its screw cap; the check needs the cap between the fingers while the tube is 9.5 cm up. In standard mode the agent loses resets, the simulator and the state of the tubes and instruments: it sees camera images and the robot's proprioception, acts in joint-position chunks, and gets one episode, so it has to find the things it handles in the images and recover from its own mistakes without starting over.

## Reference solution
`solution/oracle_stream.py` streams the privileged reference's rows (`solution/oracle.npz`, 3945 rows, float32-exact) through the client in `hold` chunks; it uses no privileged information at run time. The service's recorded trajectory is then exactly the privileged reference: success after 3945 control steps.

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
