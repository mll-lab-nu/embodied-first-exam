# robolab-bbq-sauce-in-bin-i00-standard

| | |
|---|---|
| Benchmark | RoboLab |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `robolab-bbq-sauce-in-bin-i00-privileged` |
| Simulator / robot | `robolab` / `franka-robotiq-2f85` |
| Family / instance | `bbq_sauce_in_bin` / seed 0 |
| Oracle | `none` — No reference solution: RoboLab ships no expert or planner. Positive examples graded 1 by the separate verifier: robolab-bbq-sauce-in-bin-i00__kHjYXj6 (robolab-bbq-sauce-in-bin-i00-privileged before 2026-10-14, run codex-gpt6_luna-xhigh, robolab-lunacx-0925-2038). The positives were graded before 2026-10-14 (one-finger gripper contact, no settle hold); not re-graded under the 2026-10-14 term unless stated here. Human review per family (PROTOCOL §4). |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:robolab-0.2.1` |

## Task
Standard-mode twin of `robolab-bbq-sauce-in-bin-i00-privileged` (same frozen instance, the state after RoboLab's canonical seed-0 reset):
the agent gets only the `eai-standard/2.2` client (docs/protocol/standard_mode.md); the simulator runs in the `sim` sidecar
(`environment/docker-compose.yaml`, GPU on the sidecar), which owns the scene and records the episode as a (T, 8)
trajectory and films it (live video). The collect hook (`environment/sim/finalize.sh`) ends the episode, lets the
service exit, writes `final.json` from the live episode's record (no replay) and encodes the video; the verifier runs in a
separate sandbox (`tests/Dockerfile`) over those artifacts. Compare against the privileged task to measure the cost of losing resets, privileged state and primitives.

## Difficulty
That of `robolab-bbq-sauce-in-bin-i00-privileged` (its README), without resets, object poses or the success predicate: every step is planned from camera images, depth and the robot's own proprioception, and a failed grasp or a knocked-over object stays that way.

## Reference solution
None: RoboLab ships no expert or planner, and no reference solution has been written for this family (`oracle = "none"`). Positive examples, model trials the separate verifier scored 1:
- `robolab-bbq-sauce-in-bin-i00__kHjYXj6` (privileged mode, on this task before 2026-10-14; run `codex-gpt6_luna-xhigh`, batch `robolab-lunacx-0925-2038`)

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

No oracle; human review in PR #3 (PROTOCOL §4: per family, this task and its twin, a positive example and the `nop` result).

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
