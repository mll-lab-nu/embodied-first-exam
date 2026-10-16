# ambench-peg-in-hole-fahexa-i00-standard

| | |
|---|---|
| Benchmark | AM-Bench |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `ambench-peg-in-hole-fahexa-i00-privileged` |
| Simulator / robot | `ambench` / `ambench-fahexa` |
| Family / instance | `peg_in_hole_fahexa` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-ambench:0.2.0` |

## Task
Standard-mode twin of `ambench-peg-in-hole-fahexa-i00-privileged` (the same frozen instance: AM-Bench environment `PegInHole-Am-FAHexa-Abs-PID-Direct-v0`, its seeded reset with seed
0): The hovering aerial manipulator starts holding a metal peg (a cylinder 15 cm long and 4 cm in diameter) in its gripper, pointing straight ahead. A wall stands ahead with a blue square socket mounted on its front face: a square frame whose square opening faces the robot and is closed at the back by a red plate. Insert the peg: the centre of the peg's front end (the end pointing ahead at the start) must be inside the square opening and more than 2 cm deep into it (the opening is 3 cm deep up to the red plate). The agent gets only the `eai-standard/2.2` client (docs/STANDARD_MODE.md); the simulator runs in
the `sim` sidecar (`environment/docker-compose.yaml`, GPU on the sidecar), which owns the scene and records the episode as a
(T, 8) trajectory of AM-Bench's own end-effector pose actions. The collect hook (`environment/sim/finalize.sh`) ends the
episode, lets the service exit, replays the trajectory in two fresh processes and writes `final.json`; the verifier runs in a
separate sandbox (`tests/Dockerfile`) over those artifacts. Compare against the privileged task to measure the cost of losing
resets and privileged state.

## Difficulty
That of `ambench-peg-in-hole-fahexa-i00-privileged` (its README), without resets, object poses or the success signal: The socket's pose, the wall's tilt and the opening's size are not given, nor is the peg's pose (it can shift in the grip): the blue socket on the concrete wall has to be found with the onboard cameras (the held peg occupies part of the end-effector camera's view) and related to the robot through proprioception (base and end-effector poses). Insertion depth can only be judged visually.

## Reference solution
`solution/oracle_replay.py` streams the privileged oracle's rows (`solution/oracle_qpos.npy`: AM-Bench's scripted expert for
this task, recorded on this instance, then 2 s of holding its last command; one row per control step) as one-second `ee_pose`
chunks (`hold`) through the client; after a service crash it waits for the resumed episode and continues from the control
step the service reports.

## Verification
`success` = live success ∧ replay success ∧ deterministic (two fresh-process replays agree), computed in the sidecar's collect hook. The live service runs the same camera-free physics as the replays (its cameras are drawn by a separate render process), so the live episode and the replays are one computation. `tests/grade.py` reads `final.json` with no network and writes the reward fields (with `infra_error` and the
crash-recovery fields), plus `/logs/verifier/replay.mp4` (the same rows drawn by the render worker, an illustration).
AM-Bench's success check is evaluated after every control step; the episode ends at the first step where it holds, live and
in the replays. Oracle: success at control step 1041; the live
episode and both replays end in the privileged oracle's end state (hash `88054491e8410ae5`). `nop`: the episode ends at the
agent's time-out with the check never met, reward 0.

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 8 | 8 |
| Memory | 24 GB | 20 GB |
| GPU memory | 8 GB | 8 GB |

- GPU: required, an RTX-class NVIDIA GPU (ray-tracing cores, for Isaac Sim / Omniverse RTX rendering); recommended: L40S 48GB / L4 24GB / RTX 4090 24GB.
- Measured: RTX 4090, 2026-10-14 (conformance run and oracle trials, nvidia-smi every 15 s): the sim sidecar runs the camera-free physics process (2.0 GiB of memory, 1.2 GiB of GPU memory with one environment's PhysX buffers; 2.65 GiB with Isaac Lab's) and the render worker (11.9 GiB, 3.4 GiB): 14 GiB and 4.6 GiB; the agent's container holds the client only; the collect hook replays camera-free (1.2 GiB), then films through the render worker (4.6 GiB)
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 16 GiB GPU memory, 30 GiB memory. Limits measured: the agent's container holds Python and the client only (as every standard task's); the whole trial adds the sim sidecar (physics + render worker, the rule's measurement): provisional.

## Details
| | |
|---|---|
| Episode | one episode, no reset, no step budget: it ends at the first control step where AM-Bench's success check holds, at the task's own time-out (episode length 20 s: control step 2399, reason `episode_timeout`), when the agent's time is up, or on a simulator error; simulated time advances only with the agent's calls |
| Action space | `submit` chunks of `ee_pose` (8: AM-Bench's own action, the tool frame's target pose + the gripper command, streamed at 120 Hz with the agent's `dt`, a multiple of 1/120 s, `hold` or `linear`); `observe` frames or a watch window; `/kinematics` (FK / IK of the arm on its airframe, stateless); binary RCB1 responses |
| Cameras | `ee_camera` (on the end effector), `base_camera` (on the airframe, looking forward), 384×384 RGB, z-depth on request; drawn by a render-only Isaac process from the physics state |
| Images | the `sim` sidecar runs eai-ambench (BUILD_ONLY, `images/ambench/BUILD_ONLY`); the agent container and the verifier run the shared client image with its pip pins (`scripts/eai_standard/client.env`) |
| Crash recovery | resume class `approx` (GPU PhysX replays the journal to the checkpointed state almost always; a rare race can leave the last bits different, so a resume's deviation is recorded, `resume_state_mismatch`, and the episode continues; the verdict comes from fresh replays of the whole trajectory): every control step journaled, a checkpoint with the state hash after every call; `restart: on-failure:6`, the service resumes the same episode (docs/STANDARD_MODE.md §13) |
| Generator | `scripts/ambench/mk_tasks.py` (`scripts/ambench/instances.json`, `frozen/`, `template/standard/`, `shared/`, `scripts/eai_standard/`); docs/benchmarks/ambench.md |
