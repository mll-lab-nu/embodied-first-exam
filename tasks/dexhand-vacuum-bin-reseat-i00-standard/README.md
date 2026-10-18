# dexhand-vacuum-bin-reseat-i00-standard

| | |
|---|---|
| Benchmark | DexHand |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `dexhand-vacuum-bin-reseat-i00-privileged` |
| Simulator / robot | `mujoco` / `sharpa-wave-floating-bimanual` |
| Family / instance | `vacuum_bin_reseat` |
| Oracle | `full` — solution/trajectory.npz: 1,331 two-hand Sharpa Wave control rows recorded from the closed-loop authoring controller (author.py; the left hand holds the vacuum by its handle, the right hand presses the release button, removes and reinstalls the bin); the replay ends at success after 1,181 controls (150 slack rows) in two fresh processes with identical state hashes, also with rows rounded to float32. The standard oracle submits the same rows as float64 through the public client. |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-dexhand:0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350` |

## Task
Remove the dust bin from the handheld vacuum on the counter and reinstall it. The bin is held by its two lower tabs on ledges at the bottom of the motor housing and by a spring latch at the top: the latch tooth on the red release button stops the bin's top catch from tilting out, and a fixed lip over the catch bridge stops it from being lifted straight out, so the top must tilt out from under the lip, which the tooth only allows while the button is pressed. Stages, in order: (1) release and remove: press the release button by at least 5.8 mm while the bin is still in its seat (bin origin within 5 mm of its seated pose), then take the bin away until its origin is more than 30 mm from its seated pose (both measured in the vacuum-body frame); (2) reinstall: put the bin back so that its origin is within 3 mm and its orientation within 0.05 rad of the seated pose (vacuum-body frame), the release button is back up (travel at most 1.5 mm, latch tooth raised) and the bin's catch is behind the tooth face (at most 0.5 mm in front of it); (3) let go: the stage-2 condition must hold with no hand contact on the bin, the vacuum body or the button, the bin and the vacuum body at rest (linear speed at most 0.01 m/s, bin angular speed at most 0.1 rad/s), for 50 consecutive controls (1 s). The episode ends with success at that moment; partial completion never counts. The episode ends immediately with failure, checked after every 1 ms physics substep, when the vacuum body moves more than 50 mm or tilts more than 0.35 rad from its start pose, when the bin falls (centre-of-mass downward speed above 0.99 m/s, i.e. a free fall from 5 cm, or above 0.55 m/s while nothing touches it), touches the floor or a table leg, its origin drops below the counter top (z < 0.65 m) or leaves the workspace box x in [0.2, 1.1] m, y in [-0.45, 0.45] m, z in [0.6, 1.2] m, when bin and vacuum geometry interpenetrate by more than 4 mm, or when the physics becomes unstable; later actions cannot undo a failure. Only robot actuator targets (the two wrist stages and the fingers of both hands) are allowed; no object teleports, welds or applied forces. The episode allows at most 3000 controls at 50 Hz.

## Difficulty
A two-hand task: one hand has to hold the free-standing vacuum by its handle while the other presses the release button
(nearly its full 6 mm) while the bin is still seated, takes the freed bin off its lower ledges, and reinstalls it with
millimetre alignment of the lower tabs and a closing rotation that forces the bin's catch over the spring-loaded latch
ramp (source plastic friction 0.55: the push is far larger than an unheld vacuum can take) until the tooth snaps behind
it. Every stage is checked in order from simulator state; a drop, a knock or a disturbed vacuum ends the
episode at once, and the hand must let go for a full second at the end.

## Reference solution
`solution/trajectory.npz` holds 1,331 two-hand Sharpa Wave control rows recorded from a closed-loop authoring
controller: the left hand takes a hook grip on the handle and holds the vacuum for the whole service; the right index
presses the release button (the freed bin tips onto the counter edge), an underhand power grasp takes the nozzle, the
tabs slide off the ledges and the bin is carried away, then it comes back tabs-first and is rotated closed about the
tabs until the latch snaps; the right hand opens and withdraws, then the left hand lets go. The replay ends at success
after 1,181 controls.
In standard mode the generator-owned oracle submits the same rows as float64 through the public client. The controller
only chose motor targets; it never drove an object pose or applied an object force, and it is not part of any task
environment.

## Verification
Standard mode. The trusted sim service judges the episode it ran (the last one after resets) with the task's predicate and
the selected hand, after the agent's container is stopped; its record (`final.json`, `graded_by = "live"`) is the
verdict, and nothing is replayed to grade it. The isolated verifier reads only the service's artifacts. The
service then renders `replay.mp4` from the recorded trajectory in one video-only pass, which never changes the
verdict. A missing or unfinished record, a give-up after crashes between the agent's calls and a frozen instance
that does not build at the episode's start are infrastructure errors.
The episode ends at the first success or the first failure.
Failures are fail-fast and permanent (checked every 1 ms physics substep): the vacuum body moved more than 50 mm or
tilted more than 0.35 rad; the bin falling (downward speed above 0.99 m/s, or above 0.55 m/s with no contact), touching
the floor or a table leg, below the counter top or out of the workspace; bin and vacuum geometry interpenetrating by more
than 4 mm; unstable physics; the 3,000-control budget. A no-op fails. Human review and full agent-trial calibration
remain pending; report this task as provisional.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 2 GB | 2 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: wave-2 integration smoke (Harbor 0.23, eai-dexhand:0.2.0, CPU-only, 2026-10-15; one privileged and one standard Sharpa oracle per family; docker cgroup memory.peak): privileged verifier <= 0.64 GiB with two concurrent replays, standard sim sidecar <= 0.96 GiB, agent containers < 0.05 GiB; one fresh replay process 0.26-0.39 GiB max RSS (os.wait4); x1.2 rounded up to a GB, raised to the 2 CPU / 2 GB design minimum (an agent's own simulator sessions take about 0.3-0.5 GiB each)
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 16 GiB memory. Limits measured: memory: 8 GiB lets an agent run more than a dozen 0.3-0.5 GiB simulator sessions next to its harness; measurements as in the [[rule]]; processes 512 and disk 10 GiB: design defaults, not yet measured; whole trial: + the sim service's 8 GiB cap (peaks <= 0.96 GiB).

## Details

### Notes
Source: `scripts/dexhand/families/vacuum_bin_reseat/`, generated by `scripts/dexhand/generate.py`. Scene geometry,
masses and materials come from the accepted T19 scene-expansion delivery (reduced Bosch UniversalVac18 geometry authored
for the benchmark, no manufacturer CAD), copied verbatim into `assets/` with a sha256 manifest checked at every build.
Wave 3 restores the source latch: latch tooth, catch and bridge keep the source friction 0.55 and the release button
its source 6 mm of travel (wave 2 used 0.15 and 7.5 mm); a second hand on its own wrist stage holds the vacuum, as a
person would. Physical adaptations, all in `task.json`: a fixed 2 mm lip over the bin's latch bridge (with the button up
the bin can neither tilt nor lift out); a 4 mm rubber base skid under the housing (the rounded housing hull rocked and
crept on the counter); the filter frame, pleats and cartridge and the lower-seat lips are visible but do not collide
(with them the authored geometry has no collision-free removal path); the button-guide contact pairs use a stable
soft-contact setting at the 1 ms step. The Sharpa Wave assets are pinned to
MuJoCo Menagerie commit `0059d4335f8156206f63a35662313385f7ad6d74` (Apache-2.0); the Wuji Hand 2.2 model (`hand2/hand2_2`)
to wuji-technology/wuji-description commit `829c9aa27cb12c3a49d5b8d63c9869dd8f656702` (MIT), mounted on the same wrist
stages (right and left). This is a feasibility task with two hands on floating wrist stages, not a full-arm or
zero-shot claim.

### Change Log
- 2026-10-14 (board 0109, before the first scored run): 20 resets in standard mode (owner; PROTOCOL §4.5, DexToolBench's value). `POST /reset` starts a new episode from the frozen start (the same state hash as a fresh process); only the last episode is graded, a success ends the trial; `reward.json` adds `resets` and `reset_budget`. Before, one trial was one episode.
- 2026-10-16 (board 0136, video only): the collect hook renders the replay video in its remaining time (timeout_sec minus 60 s, at most the video limit). The video films at most 300 steps (a longer episode at a larger stride; an OSMesa frame of an arm scene takes up to ~3.6 s on two cores), and the video, verifier and collect limits cover the longest archive the row limit allows. The verdict, the replays and `reward.json` are unchanged.
- 2026-10-17 (owner, board 0150/0151): standard mode graded by the live episode; no grading replay; video by one render pass from the trajectory after the verdict. `success` is the sim service's own verdict on the episode it ran (the same predicate a replay recomputed: the same rows through the same step, a success ending the episode); the collect hook no longer replays it twice in fresh processes, and `final.json` / `reward.json` drop `replay_success`, `deterministic` and `live_matches_replay` (`graded_by = "live"`, `replays = 0`). The service checks the frozen instance's files against the generator's record when an episode begins (`instance_mismatch`, an infrastructure error). A collect hook on `main` (`kill -9 -1`) stops whatever the agent left running before the service ends the episode. The agent's side (the instruction's grading sentence aside), the scene and the predicate are unchanged.
