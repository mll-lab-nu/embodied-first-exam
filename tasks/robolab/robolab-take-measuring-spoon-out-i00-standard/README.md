# robolab-take-measuring-spoon-out-i00-standard

| | |
|---|---|
| Benchmark | RoboLab |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `robolab-take-measuring-spoon-out-i00-privileged` |
| Simulator / robot | `robolab` / `franka-robotiq-2f85` |
| Family / instance | `take_measuring_spoon_out` / seed 0 |
| Oracle | `none` — No reference solution: RoboLab ships no expert or planner. Positive examples graded 1 by the separate verifier: robolab-take-measuring-spoon-out__vK2T2MY (robolab-take-measuring-spoon-out-i00-privileged before 2026-10-14, run codex-gpt6_luna-xhigh, robolab-lunacx-0925-2038); robolab-take-measuring-spoon-out__3KikKcU (robolab-take-measuring-spoon-out-i00-standard before 2026-10-14, run codex-gpt6_luna-xhigh, robolab-lunaxh-limited-0928). The standard positive ran on the lab host and was not re-graded; the privileged positive __vK2T2MY passes the 2026-10-14 term (2026-10-14). Human review per family (PROTOCOL §2.7). |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe-private:robolab-0.2.0` |

## Task
Standard-mode twin of `robolab-take-measuring-spoon-out-i00-privileged` (same frozen instance, the state after RoboLab's canonical seed-0 reset):
the agent gets only the `eai-standard/2.2` client (docs/protocol/standard_mode.md); the simulator runs in the `sim` sidecar
(`environment/docker-compose.yaml`, GPU on the sidecar), which owns the scene and records the episode as a (T, 8)
trajectory and films it (live video). The collect hook (`environment/sim/finalize.sh`) ends the episode, lets the
service exit, writes `final.json` from the live episode's record (no replay) and encodes the video; the verifier runs in a
separate sandbox (`tests/Dockerfile`) over those artifacts. Compare against the privileged task to measure the cost of losing resets, privileged state and primitives.

## Difficulty
That of `robolab-take-measuring-spoon-out-i00-privileged` (its README), without resets, object poses or the success predicate: every step is planned from camera images, depth and the robot's own proprioception, and a failed grasp or a knocked-over object stays that way.

## Reference solution
None: RoboLab ships no expert or planner, and no reference solution has been written for this family (`oracle = "none"`). Positive examples, model trials the separate verifier scored 1:
- `robolab-take-measuring-spoon-out__vK2T2MY` (privileged mode, on this task before 2026-10-14; run `codex-gpt6_luna-xhigh`, batch `robolab-lunacx-0925-2038`)
- `robolab-take-measuring-spoon-out__3KikKcU` (standard mode, on this task before 2026-10-14; run `codex-gpt6_luna-xhigh`, batch `robolab-lunaxh-limited-0928`)

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

No oracle; human review in PR #3 (PROTOCOL §2.7: per family, this task and its twin, a positive example and the `nop` result).

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 4 | 4 |
| Memory | 14 GB | 13 GB |
| GPU memory | 6.5 GB | 6.5 GB |

- GPU: required, an RTX-class NVIDIA GPU (ray-tracing cores, for Isaac Sim / Omniverse RTX rendering); recommended: L40S 48GB / L4 24GB / RTX 4090 24GB.
- Measured: GPU 4.0-5.5 GB per trial (one simulator), anon memory 7.6-10.3 GB, CPU p90 2.4-8 cores over 7 trials, live sampler (docker stats + cgroup anon + nvidia-smi every 30 s, 13 cloud GPU hosts + an RTX 4090 workstation, 10-10); evaluation-pool GPU profile peaks 14.5-15.7 GB include agents' extra simulator processes and Isaac's card-sized pools; author: one Isaac simulator per 32 GB of host RAM
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 24 GiB GPU memory, 27 GiB memory. Limits measured: GPU: 15.7 GiB on a 48 GB card, 15.3 on 24 GB (the evaluation pool's GPU profile (per-trial GPU peaks by card, 10-03..10); includes agents' extra simulators) -> max(1.5 x peak, peak + 4), at least 16 for Isaac Sim; memory: agent container docker peak 2.7 GiB over 1 samples (mem_guard (docker memory incl. page cache, top-4 containers every 10 min, an RTX 4090 workstation, 10-02..10)) -> max(1.5 x peak, peak + 4, 8), at most the 24 GiB cap; whole trial: + the sim service's 19 GiB (docker peak 12.3 GiB, 3 samples); processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Episode | one episode, no reset, no step budget: it ends at the first control step where RoboLab's success term holds, when the agent's time is up, on a simulator error, or at the technical cap of 100,000 control steps (`spec.max_control_steps`, reason `step_guard`; out of reach at 3-15 control steps/s); the wall clock is the only budget |
| Action space | `submit` chunks of `joint_position` (8, streamed at the 15 Hz control rate with the agent's `dt`, a multiple of 1/15 s) or `ee_pose` (8, differential IK per row); `observe` frames or a watch window; `/kinematics` (FK / IK, stateless); binary RCB1 responses |
| Images | the `sim` sidecar runs efe-private:robolab (BUILD_ONLY, `images/robolab/BUILD_ONLY`); the agent container and the verifier run the shared client image with its pip pins (`embodied_first_exam/standard/client.env`) |
| Crash recovery | resume class `exact`: every control step journaled, a checkpoint with the state hash after every call; `restart: on-failure:6`, the service resumes the same episode (docs/protocol/standard_mode.md §13) |
| Benchmark notes | tasks/robolab/README.md |

### Change Log
- 2026-10-10: grading robustness and time limits; the scene, the frozen instance and the pass rule
  (live ∧ replay ∧ deterministic) are unchanged, so the task keeps its name. `tests/grade.py`: a missing, unreadable or
  unfinalized `final.json`, or a replay process that ended without a result, is `infra_error` = 1 (it was the agent's 0, or
  no reward at all). `finalize.sh`: `final.json` replaced atomically, each replay time-boxed inside the hook and retried
  once when it dies; `[[verifier.collect]] timeout_sec` 15000 s (was 5400 s). Service: malformed requests (null or
  wrong-type fields, an `ee_pose` position more than 2 m from the base, a zero quaternion) are answered 400 before anything
  moves (some ended the episode with a simulator error); `/spec` states the 100,000-step cap (`max_control_steps`). The
  replay video of an episode longer than 9,000 control steps is a time lapse (at most 9,000 frames). A trial
  recorded before this date with reward 0 and one of these conditions was an infrastructure failure.
- 2026-10-10 (review round 2): the client only (`environment/rcb_client.py`). `Robot()` waits up to 3600 s for the service (was 600 s) and prints its progress to stderr once a minute, so the first `Robot()` outlasts the simulator's start (about 2 minutes here; longer than 600 s only on an overloaded host); `cameras="name"` (a string) is one camera, no longer its characters. The service, the collect hook, the grader, the scene and the pass rule are unchanged.
- 2026-10-10 (review round 3): the shared service layer and the client only (`environment/sim/rcb_limited.py`, `environment/rcb_client.py`). A camera named more than once in `cameras` is rendered and returned once (N copies of one name made the service build N x N images within the frame budget, which could exhaust its memory). A service that has given up on the episode (it could not start it, or could not resume it after its crashes) answers every request with 409 and the reason, and `Robot()` / `wait_ready()` raise `EpisodeOver` at once; before, nothing answered and they waited out their timeout (up to an hour). The adapter, the collect hook, the grader, the scene and the pass rule are unchanged.
- 2026-10-10 (owner decision): the agent's network egress is restricted to the model APIs (`[agent] network_mode = "allowlist"`, the hosts of `scripts/set_agent_egress.py`; since 2026-10-11 these include the package registries, PyPI and the Debian / Ubuntu archives, so that `pip install` and `apt-get install` work); it was open before (Harbor's default), and agents could download upstream sources, reference solutions and robot models from their own shell. The simulator image is `efe-private:robolab-0.1.2` (was 0.1.1): it holds the MDL materials and textures that RoboLab's asset library fetched from NVIDIA's Omniverse content bucket whenever a scene was built, so that the cameras show under the allowlist what they showed with open egress (on 0.1.1 without that download the table renders red). The scene, the frozen instance, the physics, the tooling and the pass rule are unchanged, so the task keeps its name; results from before this date were obtained with open egress.
- 2026-10-13 (owner, boards 0085 and 0087): the sim service's clock (`environment/sim/rcb_limited.py`, `environment/sim/server.py`, the docstring of `environment/rcb_client.py`). `meta["time_s"]` and `meta["time_left_s"]` count from the agent's first request to the service (any endpoint), and a restarted service keeps that moment; before, they counted from the service's own start of the episode (when its scene was ready). Where the service is ready before the agent's phase begins (the harness is installed in between: a median of 79 s over the recorded standard trials), that clock ran ahead of the agent's and `time_left_s` reached 0 while the agent still had that time. `/spec` says what the clock counts from (`budget.clock`), and the instruction's `## Time limit` tells the agent to plan by `time_left_s`. The service never ended an episode on this clock: the scene, the frozen instance, the pass rule and the grader are unchanged, so the task keeps its name and earlier results stand.
- 2026-10-14 (in place: a new DIGEST, PROTOCOL v2.0 §1 and H.8; the success rule changed). From the failure analysis of the 10-14 results (19 of 194 RoboLab successes fired before the task was done). (1) "The gripper" of every contact check is both Robotiq fingers (an object touching either finger is held); RoboLab's DROID setup watched the left inner finger alone, so a success could fire mid-carry. (2) `take_measuring_spoon_out` and `cooking_clear_plate` use RoboLab's own `object_outside_of_and_on_surface` (surface `table`) instead of `object_outside_of`. (3) When the agent's phase ends, the service holds the last command for 30 more control steps (2 s) while the term is checked; the fresh-process replays run the recorded episode as it is (`--no-settle`). (4) The instruction says that a client timeout while a call is in flight means the single-threaded service is busy, not crashed (agents waited for resumes that never came). The frozen instance and the time limit are unchanged; results recorded before this date (the earlier DIGEST) are not comparable with this version.
- 2026-10-16 (in place: a new DIGEST, PROTOCOL v2.0 §1 and H.8; texts only). From the instruction audit of 2026-10-16, the instruction now states the rules the grader applies: (1) the on-table rule of 2026-10-14 is now stated: the success predicate is RoboLab's `object_outside_of_and_on_surface` (surface `table`; the object rests on the table top, held in the air or dropped on the floor does not count); (2) the Rules state the pass rule: two fresh-process replays of the recorded episode, live success, both replays successful and both ending in the same state. The scene, the frozen instance, the tooling, the success term and the grader are unchanged, so the task keeps its name and results under the 2026-10-14 DIGEST are graded the same way.
- 2026-10-17 (owner, boards 0150/0151; in place: a new DIGEST, PROTOCOL v2.0 §1 and H.8): standard modes graded by the live episode; no grading replay; video by the sim service during the live episode (`live.mp4`). `success` is the live episode's success as the service judged it (RoboLab's success term at any control step, through the 30-step hold of the last command after the agent's phase, which the service already ran on the live simulator); it was live success ∧ both of two fresh-process replays successful ∧ equal end-state hashes. The collect hook no longer replays the trajectory: its time limit is 3600 s (was 15000 s) and it needs no GPU after the service exits. The start-state check is made by the service before it serves the agent: a rebuilt scene that is not the frozen instance ends the trial as an infrastructure failure (`instance_mismatch`, a give-up); before, the strict check made the service crash and restart until the hook timed out. The video (`replay.mp4` before) is filmed by the service during the episode, a frame every 3 control steps from the renders Isaac Lab makes with every step, and encoded after the verdict; it never decides anything. A collect hook on `main` (`kill -9 -1`) now stops whatever the agent left running in its container before the service ends the episode (PROTOCOL H.4), so nothing moves the robot after the deadline or during the hold. reward.json: `graded_by_live` = 1, `replays` = 0, no `replay_success` / `deterministic`. The scene, the frozen instance, the RoboLab success rule, the agent's interface and the time limit are unchanged; a trial recorded before this date scored live ∧ replay ∧ deterministic (tasks/robolab/README.md, Grading, says how to re-score it by its live episode).
