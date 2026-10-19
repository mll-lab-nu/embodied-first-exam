# myosuite-pen-twirl-i00-standard

| | |
|---|---|
| Benchmark | MyoSuite |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `myosuite-pen-twirl-i00-privileged` |
| Simulator / robot | `myosuite` / `myohand` |
| Family / instance | `pen_twirl` / seed 0 |
| Oracle | `none` — the privileged twin's positive example (Claude Code + Claude Opus 5.5 (run `claude_code-claude_opus_5_5-default`, 2026-09-28), trial `myosuite-pen-twirl-i00__UtTYzQE`, 513 rows) rounded to float32, as the client sends it, and streamed through the client: the service scores it 1 live and in both replays, in two fresh trials (tasks/myosuite/README.md); human review in PR #65 |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:myosuite-0.1.1` |

## Task
MyoSuite `myoHandPenTwirlFixed-v0` (MyoHand, 39 muscles) on the same frozen instance as `myosuite-pen-twirl-i00-privileged`: Rotate the pen in the hand until its axis points along the target orientation: the cosine between the pen's axis (bottom to top) and the target's axis above 0.95, with the pen within 0.075 m of its desired position, for 100 consecutive control steps (1.0 s). Failure (the episode ends): the pen more than 0.075 m from its desired position (dropped).
A pen lies across the fingers of the upturned hand; a translucent target pen shows the goal orientation. Standard mode (eai-standard/2.2): the agent drives the body through a client, with only its own proprioception and the scene's cameras, and 10 resets (only the last episode is graded).

## Difficulty
Same instance and success rule as `myosuite-pen-twirl-i00-privileged` (first-pass rating: hard). In standard mode the agent loses free resets, the simulator and the object state: it sees camera images and the limb's proprioception, acts in actuator-command chunks, and gets 10 resets, so it has to close the loop on what it sees and learn the body from a few real attempts.

## Reference solution
None. Solvability evidence: the privileged twin's positive example (Claude Code + Claude Opus 5.5 (run `claude_code-claude_opus_5_5-default`, 2026-09-28), trial `myosuite-pen-twirl-i00__UtTYzQE`, 513 rows) rounded to float32, as the client sends it, and streamed through the client: the service scores it 1 live and in both replays, in two fresh trials (tasks/myosuite/README.md); human review in PR #65.

## Verification
The sim service judges the episode live (the task's rule on the steps it ran: the goal held 100 control steps) and records every executed control step; it checks at the episode's start that the scene is the frozen instance (its recorded state hash; else `instance_mismatch`, an infrastructure failure). The collect hook (`environment/sim/finalize.sh`) ends the service and writes that live verdict to `final.json` (`graded_by` = `live`; nothing is replayed to grade it), then renders `replay.mp4` in one pass over the recorded trajectory, which decides nothing; `tests/grade.py` (separate sandbox, no network) passes iff the live episode succeeded. A missing or unreadable `final.json`, one without a verdict, or a give-up after crashes not all inside the agent's calls is an infrastructure failure (`infra_error = 1`), not the agent's 0. No oracle; human review in PR #65. `nop`: the episode times out, reward 0.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 4 GB | 3 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: memory: privileged container median 6.2 GB, sim p90 1.4 GB, verifier 1.4 GB, mem_guard (docker memory per container, 4090-ws1, 10-02..10); CPU-only; CPU author estimate
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 14 GiB memory. Limits measured: memory: no samples of the agent's container; floor 8 GiB (at most the 8 GiB cap); whole trial: + the sim service's 6 GiB (docker peak 1.4 GiB, 5 samples); processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Upstream | MyoSuite 2.12.2 (Apache-2.0) on MuJoCo 3.6.0, the models that ship in its wheel |
| Service | `environment/sim/server.py` (the adapter) on the shared 2.2 layer `rcb_limited.py` (`scripts/eai_standard/`); cameras `side_view`, `front_view`, `hand_top`, `hand_bottom`, `hand_side_inter`, `hand_side_exter`, `plam_lookat` (640 x 480); forward kinematics of the body's links |
| Resources | 4 CPUs, no GPU (CPU physics, OSMesa rendering); after the agent's phase the collect hook only renders the video (one pass over the graded episode), it replays nothing to grade |
| Reset budget | 10 (`RCB_RESET_BUDGET`, compose default; PROTOCOL §4.5): `POST /reset` starts a new episode from the frozen instance; only the last episode is graded, a success ends the trial; results under another budget are reported separately |

### Provenance
Generated by `scripts/myosuite/generate.py` from `scripts/myosuite/instances/pen_twirl.npz` and `pen_twirl.json`
(`make_facts.py`); see `tasks/myosuite/README.md`.

### Change Log
- 2026-10-09: the standard service's `effort_<joint>` proprioception (`joint_effort`) reads the force the physics
  applied (MyoSuite's robot data), not the mirror's zero-command force; and `RCB_RESET_BUDGET`'s default 0 ->
  10 (owner decision; PROTOCOL §4.5, tasks/myosuite/README.md), with `POST /reset` in the service. The
  scene, instance and pass rule are unchanged, so the task keeps its name; runs recorded before this date saw the wrong
  efforts and had no reset, and are reported separately.
- 2026-10-10: a malformed request field (a null or non-numeric `dt` / `seconds`, `cameras` that is not a list of names,
  a `note` that is not text) is answered with 400 before anything runs; before, it was a 500 that ended the episode
  (for `note`, after the chunk had run). `tests/grade.py` books a missing, unreadable or never-finalized `final.json`
  as `infra_error = 1` instead of the agent's 0, and `finalize.sh` writes `final.json` atomically. The scene, instance
  and pass rule are unchanged, so the task keeps its name; every verdict that was reached before is the same now.
- 2026-10-10 (board 0067, R2): the service no longer publishes the pose of a camera that rides on a body of the
  scene that is not the agent's own (decided from the model: the camera's body is a mocap body or sits behind a
  joint that is not the body's). This family has no such camera: nothing a run sees changes.
  The client (`environment/rcb_client.py`): `Robot()` waits up to 3600 s for the service (was 600 s; no effect
  here, the service is up in seconds) and prints its progress, and `cameras="name"` (a string) is one camera,
  no longer its characters.
- 2026-10-10 (review round 3, board 0067): the shared service layer and the client only
  (`environment/sim/rcb_limited.py`, `environment/rcb_client.py`). A camera named more than once in `cameras` is
  rendered and returned once (N copies of one name made the service build N x N images within the frame budget, which
  could exhaust its memory). A service that has given up on the episode (it could not start it, or could not resume it
  after its crashes) answers every request with 409 and the reason, and `Robot()` / `wait_ready()` raise `EpisodeOver`
  at once; before, nothing answered and they waited out their timeout (up to an hour). `environment/sim/server.py`
  waits for a port that is still held when it restarts (`rcb_limited.bind`) instead of exiting. The collect hook, the
  grader, the scene and the pass rule are unchanged.
- 2026-10-10 (review round 3, board 0067): `environment/sim/server.py` bounds the images of one call: at most
  1000 (cameras x frames, per-frame depth counted again; `/spec` `max_frames_per_call`, stated in the instruction);
  a larger request is a 400 and nothing runs. Before, a call had no bound, and one request within the documented
  ranges (a 30 s watch at the control rate, or several cameras with per-frame depth) could exhaust the sidecar's memory:
  the service was killed, and a trial that then failed was recorded as an infrastructure failure
  (`resource_service_oom`), not as a result. The default camera at the default 10 fps fits every chunk and watch
  (302 images at most). The scene, instance and pass rule are unchanged, so the task keeps its name.
- 2026-10-13 (owner, boards 0085 and 0087): the sim service's clock (`environment/sim/rcb_limited.py`,
  `environment/sim/server.py`, the docstring of `environment/rcb_client.py`). `meta["time_s"]` and
  `meta["time_left_s"]` count from the agent's first request to the service (any endpoint), and a restarted service
  keeps that moment; before, they counted from the service's own start of the episode (when its scene was ready).
  Where the service is ready before the agent's phase begins (the harness is installed in between: a median of 79 s
  over the recorded standard trials), that clock ran ahead of the agent's and `time_left_s` reached 0 while the agent
  still had that time. `/spec` says what the clock counts from (`budget.clock`), and the instruction's `## Time limit`
  tells the agent to plan by `time_left_s`. The service never ended an episode on this clock: the scene, the frozen
  instance, the pass rule and the grader are unchanged, so the task keeps its name and earlier results stand.
- 2026-10-17 (owner, boards 0150 and 0151): graded by the live episode; no grading replay. `environment/sim/finalize.sh`
  writes the live episode's verdict (the task's rule as the service applied it to the steps it ran, its hold or track
  window included; `graded_by` = `live`, `replays` = 0) and no longer replays the trajectory in two fresh processes;
  `replay.mp4` is rendered after the verdict by one pass over the trajectory (`environment/sim/video.py`), which
  decides nothing. `environment/sim/server.py` checks at the episode's start that the scene hashes to the frozen
  instance's recorded state (else `instance_mismatch`, an infrastructure failure, before the agent is served; before,
  the replays checked it). `tests/grade.py`: success = the live success; `reward.json` drops `replay_success`,
  `deterministic` and `live_matches_replay` and adds `graded_by_live`, `replays`. A collect hook on `main`
  (`kill -9 -1`) stops whatever the agent left running before the service ends the episode. The scene, the instance,
  the pass rule and everything the agent sees are unchanged, so the task keeps its name; a result graded before passed
  only if the live episode succeeded too.
