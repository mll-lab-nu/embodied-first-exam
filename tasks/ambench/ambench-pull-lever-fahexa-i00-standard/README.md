# ambench-pull-lever-fahexa-i00-standard

| | |
|---|---|
| Benchmark | AM-Bench |
| Mode | standard (`eai-standard/2.2`) |
| Twin | — (none: standard only, graded by the live episode; its physics does not replay bit for bit, PROTOCOL §4) |
| Simulator / robot | `ambench` / `ambench-fahexa` |
| Family / instance | `pull_lever_fahexa` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:ambench-0.3.1` |

## Task
Standard-only task (no privileged twin: its physics does not replay bit for bit, so an open-loop trajectory of it cannot be graded reproducibly; the frozen instance: AM-Bench environment `PullLever-Am-FAHexa-Abs-PID-Direct-v0`, its seeded reset with seed
0): A wall stands in front of the hovering aerial manipulator with a lever mounted on its front face: a bar sticking straight out of the wall toward the robot from a small dark-grey base, ending in a horizontal crossbar handle. The lever pivots at the base about a horizontal axis parallel to the wall. Pull the lever up: rotate it so its free end rises by more than 40 degrees from its starting direction, perpendicular to the wall (its travel ends at 45 degrees). The agent gets only the `eai-standard/2.2` client (docs/protocol/standard_mode.md); the simulator runs in
the `sim` sidecar (`environment/docker-compose.yaml`, GPU on the sidecar), which owns the scene and records the episode as a
(T, 8) trajectory of AM-Bench's own end-effector pose actions. The collect hook (`environment/sim/finalize.sh`) ends the
episode, lets the service exit, writes `final.json` from the live episode's record (no replay) and then films the
trajectory once (the video only); the verifier runs in a separate sandbox (`tests/Dockerfile`) over those artifacts.

## Difficulty
The lever is spring-loaded back to perpendicular and heavily damped, and it has to be driven past 40 degrees, within 5 degrees of its end stop, from a free-flying, hovering base; its place on the wall changes per instance. Here without resets, object poses or a success measure (the episode just ends, reason `success`, when the check holds): The lever's pose and angle are not given: the lever on the concrete wall has to be found with the onboard cameras (its base is dark grey) and related to the robot through proprioception (base and end-effector poses). The lever's angle can only be judged visually. The end-effector camera starts rolled by 90 degrees with the wrist.

## Reference solution
`solution/oracle_replay.py` streams the reference rows (`solution/oracle_qpos.npy`: AM-Bench's scripted expert for
this task, recorded on this instance, then 2 s of holding its last command; one row per control step) as one-second `ee_pose`
chunks (`hold`) through the client; after a service crash it waits for the resumed episode and continues from the control
step the service reports.

## Verification
Graded by the live episode, like every standard task: GPU PhysX does not replay it bit for bit (measured: the same rows, from identical states and identical controller outputs, resolve the first gripper contact differently in fresh processes), so `success` = the live episode's success, and no replay runs. The task is standard-only: an open-loop trajectory of it cannot be graded reproducibly. `tests/grade.py` reads `final.json` with no network and writes the reward fields (`graded_by_live` = 1,
`replays` = 0, `infra_error`, the crash-recovery fields), plus `/logs/verifier/replay.mp4` (the recorded rows drawn by the
render worker in one film pass after the verdict, an illustration: its failure costs the video only; here it usually reaches the
live outcome in other last bits, `video_matches_live` = 0, and a film with another outcome is dropped). AM-Bench's success
check is evaluated after every control step; the episode ends at the first step where it holds. Before serving, the
service checks the rebuilt scene's state hash against the frozen instance's (`instance_mismatch`: an infrastructure
failure), and GPU faults in the live episode's physics (`live_gpu_faults`) make it no verdict on the agent
(`infra_error`). Oracle: success at control step 899; the reference rows succeed in every fresh process measured but do not end in the same state (3 different end states in 6 fresh-process replays, all succeeding at control step 899): only the outcome is reproducible, which is why the live episode decides. `nop`: the episode ends at the
agent's time-out with the check never met, reward 0.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 2 | 4 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 11 | 21 GiB | 1024 | 16 GiB | — |
| verifier (as `main`) | 2 | 4 GiB | no cap | no GPU | 10 GiB |

- GPU: an RTX-class NVIDIA GPU (ray-tracing cores), one of the models in `gpu_types`: L40S, L40, RTX 4090, RTX PRO 6000 Blackwell, held by `sim`.
- Recommended GPU: L40S 48GB / RTX 4090 24GB.

## Details
| | |
|---|---|
| Episode | one episode, no reset, no step budget: it ends at the first control step where AM-Bench's success check holds, at the task's own time-out (episode length 20 s: control step 2399, reason `episode_timeout`), when the agent's time is up, or on a simulator error; simulated time advances only with the agent's calls |
| Action space | `submit` chunks of `ee_pose` (8: AM-Bench's own action, the tool frame's target pose + the gripper command, streamed at 120 Hz with the agent's `dt`, a multiple of 1/120 s, `hold` or `linear`); `observe` frames or a watch window; `/kinematics` (FK / IK of the arm on its airframe, stateless); binary RCB1 responses |
| Cameras | `ee_camera` (on the end effector), `base_camera` (on the airframe, looking forward), 384×384 RGB, z-depth on request; drawn by a render-only Isaac process from the physics state |
| Images | the `sim` sidecar runs efe-private:ambench (BUILD_ONLY, `images/ambench/BUILD_ONLY`); the agent container and the verifier run the shared client image with its pip pins (`embodied_first_exam/standard/client.env`) |
| Crash recovery | resume class `approx` (the physics does not replay bit for bit: a resume's deviation from the checkpointed state is recorded, `resume_state_mismatch`, and the live state after it is graded): every control step journaled, a checkpoint with the state hash after every call; `restart: on-failure:6`, the service resumes the same episode (docs/protocol/standard_mode.md §13) |
| Benchmark notes | tasks/ambench/README.md |
