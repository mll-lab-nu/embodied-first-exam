# autobio-insert-centrifuge-5430-i00-standard

| | |
|---|---|
| Benchmark | AutoBio |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `autobio-insert-centrifuge-5430-i00-privileged` |
| Simulator / robot | `autobio` / `ur5e-robotiq-2f85` |
| Family / instance | `insert_centrifuge_5430` / seed 0 (allowed seeds: [0, 1, 2]; PROTOCOL §2) |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:autobio-0.1.0` |

## Task
AutoBio's `insert_centrifuge_5430` (Load centrifuge rotor) on the same frozen instance as `autobio-insert-centrifuge-5430-i00-privileged`: Load a second 1.5 mL tube into the centrifuge's rotor, into the slot diametrically opposite the tube that is already in it (the rotor has 30 slots). The tube to load stands in the plate on the bench. Success the moment the tube is seated in that slot: its body within 5 mm of its seated position there, and its body's height within a fixed 6 mm window (AutoBio's test; standard mode gives no world heights). That seated position is computed when the episode starts: turning the rotor moves the slot away from it, so leave the rotor where it is. In this instance a tube that has been let go comes to rest just outside the 5 mm (5.0 to 5.1 mm away, AutoBio's own expert's tube included), so the test holds while the tube is still being lowered into the slot, held by the gripper; the episode ends in success at that moment.
On the bench: a centrifuge (an Eppendorf 5430 model) with its lid open and a 30-slot rotor holding one 1.5 mL tube, and a well plate with a second 1.5 mL tube standing in it. Standard mode (eai-standard/2.2): the agent drives the robot through a client in one episode, with only its proprioception and the scene's cameras.

## Difficulty
Same instance and success rule as `autobio-insert-centrifuge-5430-i00-privileged` (AutoBio's level: hard). A 1.5 mL tube is taken from a plate and seated within 5 mm in one particular slot of a 30-slot rotor, inside the centrifuge's bowl. In standard mode the agent loses resets, the simulator and the state of the tubes and instruments: it sees camera images and the robot's proprioception, acts in joint-position chunks, and gets one episode, so it has to find the things it handles in the images and recover from its own mistakes without starting over.

## Reference solution
`solution/oracle_stream.py` streams the privileged reference's rows (`solution/oracle.npz`, 4582 rows, float32-exact) through the client in `hold` chunks; it uses no privileged information at run time. The service's recorded trajectory is then exactly the privileged reference: success after 4582 control steps.

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
