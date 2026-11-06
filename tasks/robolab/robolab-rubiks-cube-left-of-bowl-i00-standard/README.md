# robolab-rubiks-cube-left-of-bowl-i00-standard

| | |
|---|---|
| Benchmark | RoboLab |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `robolab-rubiks-cube-left-of-bowl-i00-privileged` |
| Simulator / robot | `robolab` / `franka-robotiq-2f85` |
| Family / instance | `rubiks_cube_left_of_bowl` / seed 0 |
| Oracle | `full` — solution/oracle_replay.py scored 1 under Harbor -a oracle on this version (2026-10-14): trial robolab-rubiks-cube-left-of-bowl__mHPED7Z (2026-10-14, on these files under a temporary -i01 name: they differ from it only in that name in the resource-limit files and in one comment line of rcb_robolab.py; live 1, replay 1, deterministic 1, live_matches_replay 1, 183 control steps). Earlier versions: solution/oracle_replay.py scored 1 in 6/6 recorded runs on the pre-crash-recovery service with the same verdict formula (success = live, replay and deterministic), the latest robolab-rubiks-cube-left-of-bowl__YZj6yTp (job eq-oracle-rubiks-cube-left-of-bowl, 2026-09-29, the dev branch 9eb18edf version); not re-run on this version (crash recovery, the collect hook's `end`, one-second chunks): static validation only, 2026-10-01. Human review per family (PROTOCOL §4). |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:robolab-0.2.2` |

## Task
Standard-mode twin of `robolab-rubiks-cube-left-of-bowl-i00-privileged` (same frozen instance, the state after RoboLab's canonical seed-0 reset):
the agent gets only the `eai-standard/2.2` client (docs/protocol/standard_mode.md); the simulator runs in the `sim` sidecar
(`environment/docker-compose.yaml`, GPU on the sidecar), which owns the scene and records the episode as a (T, 8)
trajectory and films it (live video). The collect hook (`environment/sim/finalize.sh`) ends the episode, lets the
service exit, writes `final.json` from the live episode's record (no replay) and encodes the video; the verifier runs in a
separate sandbox (`tests/Dockerfile`) over those artifacts. Compare against the privileged task to measure the cost of losing resets, privileged state and primitives.

## Difficulty
That of `robolab-rubiks-cube-left-of-bowl-i00-privileged` (its README), without resets, object poses or the success predicate: every step is planned from camera images, depth and the robot's own proprioception, and a failed grasp or a knocked-over object stays that way.

## Reference solution
`solution/oracle_replay.py` streams the privileged oracle's joint targets (`oracle_qpos.npy`, one row per control step, `hold`) as one-second `joint_position` chunks through the client; after a service crash it waits for the resumed episode and continues from the control step the service reports.

## Verification
Graded by the live episode (owner 2026-10-17): `success` = the live episode's success, judged by the sim
service on the episode the agent ran, with no grading replay. RoboLab's success term is instantaneous: it is checked
after every control step and the first step where it holds ends the episode (RoboLab's own termination); when the
agent's time is up, the service holds the last command for 30 more control steps (2 s) on the live simulator, after the
agent's container is stopped, while the term is checked. Before serving, the service checks the rebuilt scene against the
frozen instance (`instance.json` `state_sha`, else every object pose and joint within tolerance); a mismatch is an
infrastructure failure (`instance_mismatch`). `tests/grade.py` reads `final.json` with no network and writes the reward
fields (`graded_by_live` = 1, `replays` = 0, `infra_error`, the crash-recovery fields), plus `/logs/verifier/live.mp4`:
the service films the live episode (a frame of the viewport and wrist cameras every 3 control steps, from the renders
Isaac Lab makes with every step), and the collect hook encodes it after the verdict (a failed encode costs the video
only). Compute: the collect hook needs no GPU after the service exits (it replayed the episode in two fresh Isaac
processes before 2026-10-17).

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 24 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 8 | 26 GiB | 4096 | 22 GiB | — |
| verifier (as `main`) | 8 | 24 GiB | no cap | no GPU | 10 GiB |

- GPU: an RTX-class NVIDIA GPU (ray-tracing cores), one of the models in `gpu_types`: L40S, L40, L4, RTX 4090, RTX 6000 Ada, RTX PRO 6000 Blackwell, held by `sim`.
- Recommended GPU: L40S 48GB / L4 24GB / RTX 4090 24GB.

## Details
| | |
|---|---|
| Episode | one episode, no reset, no step budget: it ends at the first control step where RoboLab's success term holds, when the agent's time is up, on a simulator error, or at the technical cap of 100,000 control steps (`spec.max_control_steps`, reason `step_guard`; out of reach at 3-15 control steps/s); the wall clock is the only budget |
| Action space | `submit` chunks of `joint_position` (8, streamed at the 15 Hz control rate with the agent's `dt`, a multiple of 1/15 s) or `ee_pose` (8, differential IK per row); `observe` frames or a watch window; `/kinematics` (FK / IK, stateless); binary RCB1 responses |
| Images | the `sim` sidecar runs efe-private:robolab (BUILD_ONLY, `images/robolab/BUILD_ONLY`); the agent container and the verifier run the shared client image with its pip pins (`embodied_first_exam/standard/client.env`) |
| Crash recovery | resume class `exact`: every control step journaled, a checkpoint with the state hash after every call; `restart: on-failure:6`, the service resumes the same episode (docs/protocol/standard_mode.md §13) |
| Benchmark notes | tasks/robolab/README.md |
