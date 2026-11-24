# labutopia-place-i00-standard

| | |
|---|---|
| Benchmark | LabUtopia |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `labutopia-place-i00-privileged` |
| Simulator / robot | `labutopia` / `franka-panda` |
| Family / instance | `place` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:labutopia-0.1.0` |

## Task
LabUtopia's `place` (Place (LabUtopia's level-2 TransportBeaker is the same task)) on the same frozen instance as `labutopia-place-i00-privileged`: Pick up the glass beaker, set it down on the white square plate and let go of it. Success the moment, after the beaker's centre has been more than 10 cm above where it stood, the beaker has stood on the plate for one second (60 control steps in a row): its centre within 5 cm (horizontally) of the plate's centre and within 5 cm of the height at which it started, with the gripper more than 5 cm away from the beaker's centre (measured from the point between the fingertips).
On the bench in front of the arm: a glass beaker, about 11 cm across and 9 cm tall, and a white square plate, 10 cm x 10 cm, lying flat on the bench. Standard mode (eai-standard/2.2): the agent drives the robot through a client in one episode, with only its proprioception and the scene's cameras.

## Difficulty
Same instance and success rule as `labutopia-place-i00-privileged` (LabUtopia's level 1). The beaker has to be lifted at least 10 cm, carried about half a metre and released upright within 5 cm of the centre of a 10 cm plate. In standard mode the agent loses resets, the simulator and the state of the objects: it sees camera images (glassware is nearly transparent in them and absent from the depth maps) and the robot's proprioception, acts in joint target chunks, and gets one episode, so it has to find the things it handles in the images and recover from its own mistakes without starting over.

## Reference solution
`solution/oracle_stream.py` streams the privileged reference's rows (`solution/oracle.npz`, 836 rows, float32) through the client as `joint_position_velocity` chunks; it uses no privileged information at run time. The service's recorded trajectory is then exactly the privileged reference: success after 836 control steps.

## Verification
Graded by the live episode (docs/protocol/README.md H.4): `success` = the live episode's success, judged by the sim service on the episode the agent ran, with no grading replay; an episode that ended in a simulator error scores 0. The service records every executed control step; the collect hook (`environment/sim/finalize.sh`) ends the service, writes `final.json` from the live episode's record and, after the verdict is on disk, replays the recorded trajectory once from the frozen instance to render `replay.mp4` (a failed video replay costs the video only). `tests/grade.py` (separate sandbox, no network) writes the reward fields (`graded_by_live` = 1, `replays` = 0, `infra_error`, the crash-recovery fields). A missing or unfinished `final.json` (the hook never wrote its verdict) and a live episode that did not start in the instance's recorded state are `infra_error = 1`, never the agent's 0. `nop`: the episode times out, reward 0.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 32 GiB | 16384 | no GPU | 20 GiB |
| `sim` | 16 | 24 GiB | 16384 | 16 GiB | — |
| verifier (as `main`) | 8 | 32 GiB | no cap | no GPU | 20 GiB |

- GPU: an RTX-class NVIDIA GPU (ray-tracing cores), one of the models in `gpu_types`: RTX 4090, L40S, held by `sim`.
- Recommended GPU: RTX 4090 24GB / L40S 48GB.

## Details
| | |
|---|---|
| Upstream | LabUtopia (github.com/Rui-li023/LabUtopia @ 8df7278; code MIT, assets CC BY-NC 4.0) on NVIDIA Isaac Sim 6.1.0 (LabUtopia pins 5.1.0; the image is built locally, images/labutopia/BUILD_ONLY) |
| Service | `environment/sim/server.py` (the adapter) on the shared 2.2 layer `rcb_limited.py` (`embodied_first_exam/standard/`); cameras `camera_1`, `camera_2`, `wrist_cam` (512 x 512); action types `joint_position` (9) and `joint_position_velocity` (18); forward and inverse kinematics of the arm |
| Resources | an RTX-class NVIDIA GPU for the `sim` sidecar (Isaac Sim), 8 CPUs, 32 GB of RAM |
