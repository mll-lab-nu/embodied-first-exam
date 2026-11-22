# ambench-peg-in-hole-fahexa-i00-standard

| | |
|---|---|
| Benchmark | AM-Bench |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `ambench-peg-in-hole-fahexa-i00-privileged` |
| Simulator / robot | `ambench` / `ambench-fahexa` |
| Family / instance | `peg_in_hole_fahexa` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:ambench-0.3.1` |

## Task
Standard-mode twin of `ambench-peg-in-hole-fahexa-i00-privileged` (the same frozen instance: AM-Bench environment `PegInHole-Am-FAHexa-Abs-PID-Direct-v0`, its seeded reset with seed
0): The hovering aerial manipulator starts holding a metal peg (a cylinder 15 cm long and 4 cm in diameter) in its gripper, pointing straight ahead. A wall stands ahead with a blue square socket mounted on its front face: a square frame whose square opening faces the robot and is closed at the back by a red plate. Insert the peg: the centre of the peg's front end (the end pointing ahead at the start) must be inside the square opening and more than 2 cm deep into it (the opening is 3 cm deep up to the red plate). The agent gets only the `eai-standard/2.2` client (docs/protocol/standard_mode.md); the simulator runs in
the `sim` sidecar (`environment/docker-compose.yaml`, GPU on the sidecar), which owns the scene and records the episode as a
(T, 8) trajectory of AM-Bench's own end-effector pose actions. The collect hook (`environment/sim/finalize.sh`) ends the
episode, lets the service exit, writes `final.json` from the live episode's record (no replay) and then films the
trajectory once (the video only); the verifier runs in a separate sandbox (`tests/Dockerfile`) over those artifacts. Compare against the privileged task to measure the cost of losing
resets and privileged state.

## Difficulty
That of `ambench-peg-in-hole-fahexa-i00-privileged` (its README), without resets, object poses or the success signal: The socket's pose, the wall's tilt and the opening's size are not given, nor is the peg's pose (it can shift in the grip): the blue socket on the concrete wall has to be found with the onboard cameras (the held peg occupies part of the end-effector camera's view) and related to the robot through proprioception (base and end-effector poses). Insertion depth can only be judged visually.

## Reference solution
`solution/oracle_replay.py` streams the privileged oracle's rows (`solution/oracle_qpos.npy`: AM-Bench's scripted expert for
this task, recorded on this instance, then 2 s of holding its last command; one row per control step) as one-second `ee_pose`
chunks (`hold`) through the client; after a service crash it waits for the resumed episode and continues from the control
step the service reports.

## Verification
Graded by the live episode (owner 2026-10-17): `success` = the live episode's success, judged by the sim service on the episode the agent ran, with no grading replay (until 2026-10-17: live success ∧ two fresh-process replays that succeed and agree on the outcome). The live service runs camera-free physics (its cameras are drawn by a separate render process), the same computation as a fresh-process replay of its rows. `tests/grade.py` reads `final.json` with no network and writes the reward fields (`graded_by_live` = 1,
`replays` = 0, `infra_error`, the crash-recovery fields), plus `/logs/verifier/replay.mp4` (the recorded rows drawn by the
render worker in one film pass after the verdict, an illustration: its failure costs the video only). AM-Bench's success
check is evaluated after every control step; the episode ends at the first step where it holds. Before serving, the
service checks the rebuilt scene's state hash against the frozen instance's (`instance_mismatch`: an infrastructure
failure), and GPU faults in the live episode's physics (`live_gpu_faults`) make it no verdict on the agent
(`infra_error`). Oracle: success at control step 1041; the live
episode ended in the privileged oracle's end state (hash `88054491e8410ae5`; under the earlier rule both replays did too). `nop`: the episode ends at the
agent's time-out with the check never met, reward 0.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 2 | 4 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 11 | 21 GiB | 1024 | 16 GiB | — |
| verifier (as `main`) | 2 | 4 GiB | no cap | no GPU | 10 GiB |

- GPU: an RTX-class NVIDIA GPU (ray-tracing cores), one of the models in `gpu_types`: L40S, L40, L4, RTX 4090, RTX 6000 Ada, RTX PRO 6000 Blackwell, held by `sim`.
- Recommended GPU: L40S 48GB / L4 24GB / RTX 4090 24GB.

## Details
| | |
|---|---|
| Episode | one episode, no reset, no step budget: it ends at the first control step where AM-Bench's success check holds, at the task's own time-out (episode length 20 s: control step 2399, reason `episode_timeout`), when the agent's time is up, or on a simulator error; simulated time advances only with the agent's calls |
| Action space | `submit` chunks of `ee_pose` (8: AM-Bench's own action, the tool frame's target pose + the gripper command, streamed at 120 Hz with the agent's `dt`, a multiple of 1/120 s, `hold` or `linear`); `observe` frames or a watch window; `/kinematics` (FK / IK of the arm on its airframe, stateless); binary RCB1 responses |
| Cameras | `ee_camera` (on the end effector), `base_camera` (on the airframe, looking forward), 384×384 RGB, z-depth on request; drawn by a render-only Isaac process from the physics state |
| Images | the `sim` sidecar runs efe-private:ambench (BUILD_ONLY, `images/ambench/BUILD_ONLY`); the agent container and the verifier run the shared client image with its pip pins (`embodied_first_exam/standard/client.env`) |
| Crash recovery | resume class `approx` (GPU PhysX replays the journal to the checkpointed state almost always; a rare race can leave the last bits different, so a resume's deviation is recorded, `resume_state_mismatch`, and the episode continues; the live state after it is graded): every control step journaled, a checkpoint with the state hash after every call; `restart: on-failure:6`, the service resumes the same episode (docs/protocol/standard_mode.md §13) |
| Benchmark notes | tasks/ambench/README.md |
