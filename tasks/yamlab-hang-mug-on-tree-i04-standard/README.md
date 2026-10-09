# yamlab-hang-mug-on-tree-i04-standard

| | |
|---|---|
| Benchmark | YAMLab |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `yamlab-hang-mug-on-tree-i04-privileged` |
| Simulator / robot | `yamlab` / `i2rt-yam-bimanual` |
| Family / instance | `hang_mug_on_tree` |
| Oracle | `full` |
| Agent time budget | 5400 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-yamlab:0.1.0` |

## Task
Standard-mode twin of `yamlab-hang-mug-on-tree-i04-privileged` (same frozen instance: YAMLab's objects `mug` = `Mug/mug_004` and `mug_tree` = `MugTree/mug_tree_004` as placed in teleoperation
demonstration `hangmug_004.hdf5 demo_1`, both arms at the home pose): the agent gets only the `eai-standard/2.2` client
(docs/STANDARD_MODE_2_2.md); the simulator runs in the `sim` sidecar (`environment/docker-compose.yaml`, GPU on the
sidecar), which owns the scene and records the episode as a (T, 14) trajectory of YAMLab's own actions. The collect hook
(`environment/sim/finalize.sh`) ends the episode, lets the service exit, replays the trajectory in two fresh processes and
writes `final.json`; the verifier runs in a separate sandbox (`tests/Dockerfile`) over those artifacts. Compare against
the privileged task to measure the cost of losing resets, privileged state and primitives.

## Difficulty
That of `yamlab-hang-mug-on-tree-i04-privileged` (its README), without resets, object poses or the success signal: every step of a two-arm
manipulation is planned from three cameras (one static, two on the wrists), depth and the robot's own proprioception, and a
missed grasp or a dropped object stays that way.

## Reference solution
`solution/oracle_replay.py` streams the privileged oracle's actions (`solution/oracle_qpos.npy`: the 1 s ramp from the home
pose and the recorded teleoperation demonstration `hangmug_004.hdf5 demo_1`, one row per control step, `hold`) as one-second
`joint_position` chunks through the client; after a service crash it waits for the resumed episode and continues from the
control step the service reports.

## Verification
`success` = live success ∧ replay success ∧ deterministic (two fresh-process replays agree), computed in the sidecar's
collect hook; `tests/grade.py` reads `final.json` with no network and writes the reward fields (with `infra_error` and the
crash-recovery fields), plus `/logs/verifier/replay.mp4`. YAMLab's success check (evaluation thresholds) is evaluated after
every control step; the episode ends at the first step where every stage has latched, live and in the replays. Oracle: the
live episode and both replays end in the privileged oracle's final state (hash `33e650bb549e3ddd`). `nop`: the episode ends
on the time-out with no stage reached, reward 0.

## Details
| | |
|---|---|
| Episode | one episode, no reset, no step limit: it ends at the first control step where every stage of YAMLab's success check has latched, when a task object falls off the table, when the agent's time is up, or on a simulator error; the wall clock is the only budget |
| Action space | `submit` chunks of `joint_position` (14: YAMLab's own action, streamed at the 30 Hz control rate with the agent's `dt`, a multiple of 1/30 s) or `ee_pose` (16: both tool frames, differential IK per row); `observe` frames or a watch window; `/kinematics` (FK / IK of both arms, stateless); binary RCB1 responses |
| Cameras | `top` (static), `left_wrist`, `right_wrist` (on each arm's link_6), 640×480 RGB, z-depth on request |
| Images | the `sim` sidecar runs eai-yamlab (BUILD_ONLY, `images/yamlab/BUILD_ONLY`); the agent container and the verifier run the shared client image with its pip pins (`scripts/eai_standard/client.env`) |
| Crash recovery | resume class `exact`: every control step journaled, a checkpoint with the state hash after every call; `restart: on-failure:6`, the service resumes the same episode (docs/STANDARD_MODE_2_2.md §13) |
| Generator | `scripts/yamlab/mk_tasks.py` (`scripts/yamlab/instances.json`, `frozen/`, `template/standard/`, `shared/`, `scripts/eai_standard/`); docs/benchmarks/yamlab.md |
