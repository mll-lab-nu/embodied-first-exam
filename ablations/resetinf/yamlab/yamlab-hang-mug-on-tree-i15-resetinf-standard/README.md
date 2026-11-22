# yamlab-hang-mug-on-tree-i15-standard

| | |
|---|---|
| Benchmark | YAMLab |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `yamlab-hang-mug-on-tree-i15-privileged` |
| Simulator / robot | `yamlab` / `i2rt-yam-bimanual` |
| Family / instance | `hang_mug_on_tree` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:yamlab-0.2.1` |

## Task
Standard-mode twin of `yamlab-hang-mug-on-tree-i15-privileged` (same frozen instance: YAMLab's objects `mug` = `Mug/mug_015` and `mug_tree` = `MugTree/mug_tree_015` as placed in teleoperation
demonstration `hangmug_015.hdf5 demo_0`, both arms at the home pose): the agent gets only the `eai-standard/2.2` client
(docs/protocol/standard_mode.md); the simulator runs in the `sim` sidecar (`environment/docker-compose.yaml`, GPU on the
sidecar), which owns the scene and records the episode as a (T, 14) trajectory of YAMLab's own actions. The collect hook
(`environment/sim/finalize.sh`) ends the episode, lets the service exit, writes `final.json` from the live episode's record
(no replay) and encodes the live video; the verifier runs in a separate sandbox (`tests/Dockerfile`) over those artifacts. Compare against
the privileged task to measure the cost of losing resets, privileged state and primitives.

## Difficulty
That of `yamlab-hang-mug-on-tree-i15-privileged` (its README), without resets, object poses or the success signal: every step of a two-arm
manipulation is planned from three cameras (one static, two on the wrists), depth and the robot's own proprioception, and a
missed grasp or a dropped object stays that way.

## Reference solution
`solution/oracle_replay.py` streams the privileged oracle's actions (`solution/oracle_qpos.npy`: the 1 s ramp from the home
pose and the recorded teleoperation demonstration `hangmug_015.hdf5 demo_0`, one row per control step, `hold`) as one-second
`joint_position` chunks through the client; after a service crash it waits for the resumed episode and continues from the
control step the service reports.

## Verification
Graded by the live episode (owner 2026-10-17): `success` = the live episode's success, judged by the sim
service on the episode the agent ran, with no grading replay. YAMLab's success check (evaluation thresholds) is evaluated
after every control step; the episode ends at the first step where every stage has latched. Before serving, the service
checks the rebuilt scene against the frozen instance (`instance.json` `state_sha`, else every object pose and joint within
tolerance); a mismatch is an infrastructure failure (`instance_mismatch`). `tests/grade.py` reads `final.json` with no
network and writes the reward fields (`graded_by_live` = 1, `replays` = 0, `infra_error`, the crash-recovery fields), plus
`/logs/verifier/live.mp4`: the service keeps a frame (top + both wrist cameras) at the control steps the agent's own calls
rendered (at most one per 6 steps; no extra render for the video), and the collect hook encodes it after the verdict (a
failed encode costs the video only). Compute: the collect hook needs no GPU after the service exits (it replayed the
episode in two fresh Isaac processes before 2026-10-17). Oracle: the live episode ended in the privileged oracle's final
state (hash `88753272376676eb`; under the earlier rule both replays did too). `nop`: the episode ends on the time-out with no
stage reached, reward 0.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 5 | 4 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 16 | 21 GiB | 2048 | 16 GiB | — |
| verifier (as `main`) | 5 | 4 GiB | no cap | no GPU | 10 GiB |

- GPU: an RTX-class NVIDIA GPU (ray-tracing cores), one of the models in `gpu_types`: L40S, L40, L4, RTX 4090, RTX 6000 Ada, RTX PRO 6000 Blackwell, held by `sim`.
- Recommended GPU: L40S 48GB / L4 24GB / RTX 4090 24GB.

## Details
| | |
|---|---|
| Episode | one episode, no reset, no step budget: it ends at the first control step where every stage of YAMLab's success check has latched, when a task object falls off the table, when the agent's time is up, on a simulator error, or at the technical cap of 100,000 control steps (`spec.max_control_steps`, reason `step_guard`; 55.6 min of simulated time); the wall clock is the only budget |
| Action space | `submit` chunks of `joint_position` (14: YAMLab's own action, streamed at the 30 Hz control rate with the agent's `dt`, a multiple of 1/30 s) or `ee_pose` (16: both tool frames, differential IK per row); `observe` frames or a watch window; `/kinematics` (FK / IK of both arms, stateless); binary RCB1 responses |
| Cameras | `top` (static), `left_wrist`, `right_wrist` (on each arm's link_6), 640×480 RGB, z-depth on request |
| Images | the `sim` sidecar runs efe-private:yamlab (BUILD_ONLY, `images/yamlab/BUILD_ONLY`); the agent container and the verifier run the shared client image with its pip pins (`embodied_first_exam/standard/client.env`) |
| Crash recovery | resume class `exact`: every control step journaled, a checkpoint with the state hash after every call; `restart: on-failure:6`, the service resumes the same episode (docs/protocol/standard_mode.md §13) |
| Benchmark notes | tasks/yamlab/README.md |
