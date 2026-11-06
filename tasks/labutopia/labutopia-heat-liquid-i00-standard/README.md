# labutopia-heat-liquid-i00-standard

| | |
|---|---|
| Benchmark | LabUtopia |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `labutopia-heat-liquid-i00-privileged` |
| Simulator / robot | `labutopia` / `franka-panda` |
| Family / instance | `heat_liquid` / seed 1 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:labutopia-0.1.0` |

## Task
LabUtopia's `heat_liquid` (HeatLiquid) on the same frozen instance as `labutopia-heat-liquid-i00-privileged`: Put the glass beaker on the heater's plate and press the heater's round red button. Success the moment the third of these is met: (1) the beaker's centre has been more than 5.89 cm above where it stood; (2) after that, the beaker has stood on the plate: its centre within 5 cm, in each horizontal direction, of the plate's centre and no more than 9.89 cm above where it stood at the start; (3) after that, with the beaker on the plate as in (2), the button is pressed down more than 10.3 mm.
On the bench in front of the arm: a small glass beaker, about 6.5 cm across and 10 cm tall, and a heater: a white hot plate about 25 cm x 18 cm x 9 cm with a square plate on top, a display on its front and a round red button at one front corner. Standard mode (eai-standard/2.2): the agent drives the robot through a client in one episode, with only its proprioception and the scene's cameras.

## Difficulty
Same instance and success rule as `labutopia-heat-liquid-i00-privileged` (LabUtopia's level 2). Two steps in order with one hand: the beaker has to stand within 5 cm of the plate's centre before the button, a few centimetres from the plate, is pressed down a centimetre without knocking the beaker off. In standard mode the agent loses resets, the simulator and the state of the objects: it sees camera images (glassware is nearly transparent in them and absent from the depth maps) and the robot's proprioception, acts in joint target chunks, and gets one episode, so it has to find the things it handles in the images and recover from its own mistakes without starting over.

## Reference solution
`solution/oracle_stream.py` streams the privileged reference's rows (`solution/oracle.npz`, 1264 rows, float32) through the client as `joint_position_velocity` chunks; it uses no privileged information at run time. The service's recorded trajectory is then exactly the privileged reference: success after 1264 control steps.

## Verification
Graded by the live episode (docs/protocol/README.md H.4): `success` = the live episode's success, judged by the sim service on the episode the agent ran, with no grading replay; an episode that ended in a simulator error scores 0. The service records every executed control step; the collect hook (`environment/sim/finalize.sh`) ends the service, writes `final.json` from the live episode's record and, after the verdict is on disk, replays the recorded trajectory once from the frozen instance to render `replay.mp4` (a failed video replay costs the video only). `tests/grade.py` (separate sandbox, no network) writes the reward fields (`graded_by_live` = 1, `replays` = 0, `infra_error`, the crash-recovery fields). A missing or unfinished `final.json` (the hook never wrote its verdict) and a live episode that did not start in the instance's recorded state are `infra_error = 1`, never the agent's 0. `nop`: the episode times out, reward 0.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 32 GiB | 16384 | no GPU | 20 GiB |
| `sim` | 16 | 32 GiB | 16384 | 16 GiB | — |
| verifier (as `main`) | 8 | 32 GiB | no cap | no GPU | 20 GiB |

- GPU: an RTX-class NVIDIA GPU (ray-tracing cores), one of the models in `gpu_types`: RTX 4090, L40S, held by `sim`.
- Recommended GPU: RTX 4090 24GB / L40S 48GB.

## Details
| | |
|---|---|
| Upstream | LabUtopia (github.com/Rui-li023/LabUtopia @ 8df7278; code MIT, assets CC BY-NC 4.0) on NVIDIA Isaac Sim 6.1.0 (LabUtopia pins 5.1.0; the image is built locally, images/labutopia/BUILD_ONLY) |
| Service | `environment/sim/server.py` (the adapter) on the shared 2.2 layer `rcb_limited.py` (`embodied_first_exam/standard/`); cameras `camera_1`, `camera_2`, `wrist_cam` (512 x 512); action types `joint_position` (9) and `joint_position_velocity` (18); forward and inverse kinematics of the arm |
| Resources | an RTX-class NVIDIA GPU for the `sim` sidecar (Isaac Sim), 8 CPUs, 32 GB of RAM |
