# vlabench-select-chemistry-tube-common-sense-i00-privileged

| | |
|---|---|
| Benchmark | VLABench |
| Mode | privileged |
| Twin | `vlabench-select-chemistry-tube-common-sense-i00-standard` |
| Simulator / robot | `vlabench` / `franka-panda` |
| Family / instance | `vlabench/select_chemistry_tube_common_sense` / seed 0 |
| Oracle | `full` |
| Agent time budget | 1800 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:vlabench-0.2.0` |

## Task
VLABench's `select_chemistry_tube_common_sense`: a Franka Panda arm at a table, instructed **"Take out the KMnO4 solution"** (a direct command: VLABench's common-sense variant names the target directly here). One
frozen scene instance (VLABench's own episode configuration for the task, seed 0); the deliverable is one
replayable trajectory of joint-position control steps (`/app/output/trajectory.npz`, `(T, 9)`, T ≤ 4000), graded by
VLABench's own success check at its end.

## Difficulty
Privileged mode: the agent has every entity's pose and grasp and place points, VLABench's general skills (pick, place,
pull, press, …) as planning primitives, inverse kinematics, unlimited resets and self-replay. What remains hard is the
task's own reasoning (the instruction is a direct command: VLABench's common-sense variant names the target directly here) and making the skills or a hand-written controller
succeed on this scene. The standard twin removes the privileged state.

## Reference solution
66 control steps on this instance (`solution/oracle.npy`), replayed by `solution/solve.sh`. Source:
VLABench's own expert (get_expert_skill_sequence) driving its general skills, recorded as control steps during PR #4's authoring; only the recorded steps were committed (PR #4 @ ad3c510, refs/pull/4/head). VLABench's experts are removed from the image. Re-verified: the
replay ends with the task's success at its last step.

## Verification
`tests/grade.py` in a separate sandbox without network: one replay in a fresh process from the verifier's own copy of
the instance (`tests/instance.json`); pass iff the task succeeds at
the last action (VLABench's termination condition; actions after it make the trajectory invalid). Oracle: the replay
ends in the live state (hash `24b4aeca09b5…`) and succeeds. `nop`: no trajectory, reward 0; the instance is not solved at
the start (checked on every load).

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 20 GiB | 1024 | no GPU | 10 GiB |
| verifier | 4 | 16 GiB | no cap | no GPU | no cap |

- GPU: not needed.

## Details
| | |
|---|---|
| Upstream | VLABench @ cf588fe (MIT), assets `lerobot/vlabench-assets` @ 08d7a44; MuJoCo 3.2.2, dm_control 1.0.22 |
| Actions | 9 absolute position targets per 0.1 s control step: 7 arm joints (rad), 2 fingers (m, 0 … 0.04) |
| Resources | 4 CPUs, no GPU (CPU physics, OSMesa rendering) |

### Provenance
The instance (`environment/instance.json`, byte copy in `tests/`) and the
reference come from PR #4 (closed without merging; commit ad3c510, still fetchable as `refs/pull/4/head`) and were re-verified in
`ghcr.io/mll-lab-nu/efe-private:vlabench-0.1.0`.
