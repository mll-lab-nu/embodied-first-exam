# ambench-cabinet-pick-place-fahexa-i00-standard

| | |
|---|---|
| Benchmark | AM-Bench |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `ambench-cabinet-pick-place-fahexa-i00-privileged` |
| Simulator / robot | `ambench` / `ambench-fahexa` |
| Family / instance | `cabinet_pick_place_fahexa` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe-private:ambench-0.3.0` |

## Task
Standard-mode twin of `ambench-cabinet-pick-place-fahexa-i00-privileged` (the same frozen instance: AM-Bench environment `CabinetPickPlace-Am-FAHexa-Abs-PID-Direct-v0`, its seeded reset with seed
0): A tall wooden cabinet stands ahead of the hovering aerial manipulator, and a small soda can stands inside one of its shelf compartments, behind a closed sliding door. Get the can onto the top of the cabinet: AM-Bench counts success when the can's centre is less than 5 cm above a fixed height just below the cabinet's top surface (there is no horizontal condition) while the can moves slower than 0.1 m/s. The agent gets only the `eai-standard/2.2` client (docs/protocol/standard_mode.md); the simulator runs in
the `sim` sidecar (`environment/docker-compose.yaml`, GPU on the sidecar), which owns the scene and records the episode as a
(T, 8) trajectory of AM-Bench's own end-effector pose actions. The collect hook (`environment/sim/finalize.sh`) ends the
episode, lets the service exit, writes `final.json` from the live episode's record (no replay) and then films the
trajectory once (the video only); the verifier runs in a separate sandbox (`tests/Dockerfile`) over those artifacts. Compare against the privileged task to measure the cost of losing
resets and privileged state.

## Difficulty
That of `ambench-cabinet-pick-place-fahexa-i00-privileged` (its README), without resets, object poses or the success signal: Neither the cabinet's pose, the sliding door's position nor the can's pose is given: the cabinet, the door and its handle have to be found with the forward-looking onboard cameras, the can is hidden behind the closed door at the start, and whether the can ended at the right height and at rest can only be judged from the images together with proprioception. Success is not reported during the episode.

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
(`infra_error`). Oracle: success at control step 2752; the live
episode ended in the privileged oracle's end state (hash `c8c72a8b2031348e`; under the earlier rule both replays did too). `nop`: the episode ends at the
agent's time-out with the check never met, reward 0.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 8 | 8 |
| Memory | 24 GB | 20 GB |
| GPU memory | 8 GB | 8 GB |

- GPU: required, an RTX-class NVIDIA GPU (ray-tracing cores, for Isaac Sim / Omniverse RTX rendering); recommended: L40S 48GB / L4 24GB / RTX 4090 24GB.
- Measured: RTX 4090, 2026-10-14 (conformance run and oracle trials, nvidia-smi every 15 s): the sim sidecar runs the camera-free physics process (2.0 GiB of memory, 1.2 GiB of GPU memory with one environment's PhysX buffers; 2.65 GiB with Isaac Lab's) and the render worker (11.9 GiB, 3.4 GiB): 14 GiB and 4.6 GiB; the agent's container holds the client only; the collect hook replayed camera-free (1.2 GiB) and then filmed through the render worker (4.6 GiB) until 2026-10-17; since then it only films, through the render worker (4.6 GiB)
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 16 GiB GPU memory, 30 GiB memory. Limits measured: the agent's container holds Python and the client only (as every standard task's); the whole trial adds the sim sidecar (physics + render worker, the rule's measurement): provisional.

## Details
| | |
|---|---|
| Episode | one episode, no reset, no step budget: it ends at the first control step where AM-Bench's success check holds, at the task's own time-out (episode length 60 s: control step 7199, reason `episode_timeout`), when the agent's time is up, or on a simulator error; simulated time advances only with the agent's calls |
| Action space | `submit` chunks of `ee_pose` (8: AM-Bench's own action, the tool frame's target pose + the gripper command, streamed at 120 Hz with the agent's `dt`, a multiple of 1/120 s, `hold` or `linear`); `observe` frames or a watch window; `/kinematics` (FK / IK of the arm on its airframe, stateless); binary RCB1 responses |
| Cameras | `ee_camera` (on the end effector), `base_camera` (on the airframe, looking forward), 384×384 RGB, z-depth on request; drawn by a render-only Isaac process from the physics state |
| Images | the `sim` sidecar runs efe-private:ambench (BUILD_ONLY, `images/ambench/BUILD_ONLY`); the agent container and the verifier run the shared client image with its pip pins (`embodied_first_exam/standard/client.env`) |
| Crash recovery | resume class `approx` (GPU PhysX replays the journal to the checkpointed state almost always; a rare race can leave the last bits different, so a resume's deviation is recorded, `resume_state_mismatch`, and the episode continues; the live state after it is graded): every control step journaled, a checkpoint with the state hash after every call; `restart: on-failure:6`, the service resumes the same episode (docs/protocol/standard_mode.md §13) |
| Benchmark notes | tasks/ambench/README.md |

### Change Log
- 2026-10-17 (owner, boards 0150/0151; in place: a new DIGEST, PROTOCOL v2.0 §1 and H.8): standard modes graded by the live
  episode; no grading replay; video by one film pass after the verdict (`replay.mp4`, the render worker drawing the recorded
  rows; it never decides anything and is not run again). `success` is the live episode's success as the service judged it
  (AM-Bench's check at a control step); it was live success ∧ two camera-free fresh-process replays that succeed ∧ agree on
  the outcome (a task graded by verdict: the live success already, its replays recorded). The collect hook's limit 7200 s ->
  4800 s. The start-state check is made by the service before it serves the agent: a rebuilt scene whose state hash is not
  the frozen instance's ends the trial as an infrastructure failure (`instance_mismatch`, a give-up; before, the strict check
  made the service crash and restart until the hook timed out, and the replays checked it again). GPU faults logged by the
  live episode are an infrastructure failure for every task (before: for a task graded by verdict; for the others when the
  live outcome differed from the replays' or the live episode failed). A collect hook on `main` (`kill -9 -1`) now stops
  whatever the agent left running in its container before the service ends the episode (PROTOCOL H.4). reward.json:
  `graded_by_live` = 1, `replays` = 0, no `replay_success` / `deterministic`. The scene, the frozen instance, AM-Bench's
  success check, the agent's interface and the time limit are unchanged; a trial recorded before this date is re-scored by
  its live episode (tasks/ambench/README.md, Grading).
