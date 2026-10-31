# tactilelab-fem-plug-insert-i00-standard

| | |
|---|---|
| Benchmark | TactileLab |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `tactilelab-fem-plug-insert-i00-privileged` |
| Simulator / robot | `tactilelab` / `xtrainer-gsmini` |
| Family / instance | `fem_plug_insert` / seed 0 |
| Oracle | `full` — solution/: the privileged twin's reference trajectory (its scripted demonstration recorded through the Session), streamed through the client as float64 ee_pose rows; graded 1 by the live episode on an L40S (2026-10-29); nop graded 0. |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:tactilelab-0.2.0` |

## Task
Standard-mode twin of `tactilelab-fem-plug-insert-i00-privileged` (same frozen instance): the agent gets only the
`eai-standard/2.2` client; the simulator runs in the `sim` sidecar, which owns the scene, records the episode as a (T, 22)
trajectory of the privileged row format and films it.

## Difficulty
That of the privileged twin, without resets, object poses or the success predicate: every step is planned from the wrist
cameras, the tactile images and the robot's own proprioception.

## Reference solution
`solution/oracle_rows.npz`: the privileged twin's reference trajectory, streamed through the client as `ee_pose` rows of one control step each (`solution/oracle_client.py`); the service executes exactly those rows.

## Verification
Graded by the live episode (docs/protocol/standard_mode.md; tasks/tactilelab/README.md): the sim service judges the
task's success condition on the episode the agent ran (the 60-step hold included); `tests/grade.py` transcribes
`final.json`. Before serving, the rebuilt scene's state hash must equal `instance.json` `state_sha` (else
`instance_mismatch`, infrastructure). `nop`: the episode times out, reward 0.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 16 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 8 | 22 GiB | 2048 | 16 GiB | — |
| verifier (as `main`) | 8 | 16 GiB | no cap | no GPU | 10 GiB |

- GPU: an RTX-class NVIDIA GPU (ray-tracing cores), one of the models in `gpu_types`: L40S, L40, L4, RTX 4090, RTX 6000 Ada, held by `sim`.
- Recommended GPU: L40S 48GB.

## Details
| | |
|---|---|
| Episode | one episode, no reset; ends on success (after the 60-step hold), when the agent's time is up, on a simulator error, when the task fails for good, or after 4,740 control steps (`step_guard`); with the final hold at most `spec.max_control_steps` = 4,860 |
| Benchmark notes | tasks/tactilelab/README.md |
