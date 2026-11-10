# autobio-thermal-mixer-i00-standard

| | |
|---|---|
| Benchmark | AutoBio |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `autobio-thermal-mixer-i00-privileged` |
| Simulator / robot | `autobio` / `ur5e-robotiq-2f85` |
| Family / instance | `thermal_mixer` / seed 0 (allowed seeds: [0, 1, 2]; PROTOCOL §2) |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:autobio-0.1.0` |

## Task
AutoBio's `thermal_mixer` (Operate thermal mixer panel) on the same frozen instance as `autobio-thermal-mixer-i00-privileged`: Set the thermal mixer by pressing the buttons of its panel: time 30 s, temperature 33 °C, mixing speed 600 rpm. The panel's display shows the current settings (time, set / actual temperature, speed), and each setting has an up and a down button. The episode is judged in the state in which it ends: success iff the panel is then set to exactly these three values. The score reported as `progress` is 0.5 x temperature + 0.3 x time + 0.2 x speed, each term the fraction of the way from the initial to the target value.
On the bench: a thermal mixer (an Eppendorf ThermoMixer C model) with a thermoblock on top and a front panel: a display and buttons for time, temperature and speed (up and down each), menu navigation, five program keys, `short` and `start/stop`. Standard mode (eai-standard/2.2): the agent drives the robot through a client in one episode, with only its proprioception and the scene's cameras.

## Difficulty
Same instance and success rule as `autobio-thermal-mixer-i00-privileged` (AutoBio's level: hard). Three settings are changed by pressing small panel buttons with the gripper, the right number of times each; the final panel state is what counts, so an overshoot has to be corrected. In standard mode the agent loses resets, the simulator and the state of the tubes and instruments: it sees camera images and the robot's proprioception, acts in joint-position chunks, and gets one episode, so it has to find the things it handles in the images and recover from its own mistakes without starting over.

## Reference solution
`solution/oracle_stream.py` streams the privileged reference's rows (`solution/oracle.npz`, 8094 rows, float32-exact) through the client in `hold` chunks and ends the episode with `done`; it uses no privileged information at run time. The service's recorded trajectory is then exactly the privileged reference: success after 8094 control steps.

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
