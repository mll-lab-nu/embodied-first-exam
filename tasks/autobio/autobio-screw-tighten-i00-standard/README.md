# autobio-screw-tighten-i00-standard

| | |
|---|---|
| Benchmark | AutoBio |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `autobio-screw-tighten-i00-privileged` |
| Simulator / robot | `autobio` / `aloha-2` |
| Family / instance | `screw_tighten` / seed 0 (allowed seeds: [0, 1, 2]; PROTOCOL §2) |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:autobio-0.1.0` |

## Task
AutoBio's `screw_tighten` (Screw on centrifuge tube cap) on the same frozen instance as `autobio-screw-tighten-i00-privileged`: Screw the cap onto the 50 mL centrifuge tube. The tube stands open in the rack; its cap lies on the bench. Success the moment the cap is on the tube's thread, its axis within 5 mm of the tube's, and screwed down to within 3.3 mm of fully on.
On the bench: a rack with an open 50 mL tube standing in it, and the tube's screw cap lying on the bench. The thread is a real one: the cap goes on only by turning it. AutoBio's prompt for this task: "one grips tube while the other twists cap". Standard mode (eai-standard/2.2): the agent drives the robot through a client in one episode, with only its proprioception and the scene's cameras.

## Difficulty
Same instance and success rule as `autobio-screw-tighten-i00-privileged` (AutoBio's level: hard). A real thread: the cap has to be picked off the bench, set on the tube within 5 mm of its axis and turned down to within 3.3 mm of fully on. In standard mode the agent loses resets, the simulator and the state of the tubes and instruments: it sees camera images and the robot's proprioception, acts in joint-position chunks, and gets one episode, so it has to find the things it handles in the images and recover from its own mistakes without starting over.

## Reference solution
`solution/oracle_stream.py` streams the privileged reference's rows (`solution/oracle.npz`, 7638 rows, float32-exact) through the client in `hold` chunks; it uses no privileged information at run time. The service's recorded trajectory is then exactly the privileged reference: success after 7638 control steps.

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
| Service | `environment/sim/server.py` (the adapter) on the shared 2.2 layer `rcb_limited.py` (`embodied_first_exam/standard/`); cameras `table_cam_front`, `table_cam_left`, `arm1_wrist_cam`, `arm2_wrist_cam` (640 x 480); action types `joint_position` and `done`; forward and inverse kinematics of the arm joints |
| Resources | 4 CPUs, no GPU (CPU physics, OSMesa rendering) |
