# dexhand-essential-held-joystick-i00-standard

| | |
|---|---|
| Benchmark | DexHand |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `dexhand-essential-held-joystick-i00-privileged` |
| Simulator / robot | `mujoco` / `sharpa-wave-floating` |
| Family / instance | `essential_held_joystick` |
| Oracle | `full` — solution/trajectory.npz is the validated Sharpa Wave actuator trajectory of this frozen instance (415 controls at 50 Hz, physical contact only). The privileged oracle hands it in; the standard oracle submits the same rows as float64 through the client's request path (the service executes the validated targets bit for bit). Both replay to success in two fresh processes with identical final state hashes (scripts/dexhand/verify_oracles.py); float32-rounded copies of all six oracles also score 1. Human solvability review is pending; release status stays provisional. solution/wuji/trajectory.npz is a validated Wuji Hand 2.2 trajectory of this instance (146 controls, motor targets only, physical contact only); the oracle uses it when the run selects wuji (privileged: DEXHAND_HAND=wuji; standard: the sim service's hand), and it replays to success in two fresh processes with identical state hashes. |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350` |

## Task
With the wrist locked, keep the controller steady and move the joystick through left, front, right, back, then center, holding each checkpoint. Checkpoints are joint angles relative to the shell, not world tilt.

## Difficulty
hard: Stabilize a real Joy-Con mesh while independently steering and releasing its passive spring-centered two-axis thumbstick.
The scene uses free_controller_passive_gimbal and independently controlled fingers with the wrist locked; every ordered stage and
a terminal hold must be reached through contact alone.

## Reference solution
`solution/trajectory.npz` is the validated Sharpa Wave actuator trajectory of this frozen instance: 415 finger-target rows at 50 Hz (8.3 s) with the six wrist targets locked, executed through physical contact only. `solve.sh` submits the same rows as float64 through the agent's client request path (`hold`, dt 0.02 s), so the service executes the validated targets bit for bit; float32-rounded rows (the client's `submit`) also succeed. It was derived offline by authoring controllers (not part of the repository) and is bound to the validated evidence by `scripts/dexhand/verify_oracles.py` (byte-identical trajectory, model hash, two fresh-process replays with the validated final state hash). Wuji Hand 2.2: `solution/wuji/trajectory.npz` is a validated Wuji Hand 2.2 trajectory of this instance (146 rows of motor targets, physical contact only). When the sim service runs the Wuji Hand 2.2 (`DEXHAND_HAND=wuji`, `spec()["hand"]`), `solve.sh` submits these rows as float64 instead of the Sharpa Wave rows.

## Verification
The trusted sim service judges the episode it ran (the last one after resets) with the task's predicate and
the selected hand, after the agent's container is stopped; its record (`final.json`, `graded_by = "live"`) is the
verdict, and nothing is replayed to grade it. The isolated verifier reads only the service's artifacts. The
service then renders `replay.mp4` from the recorded trajectory in one video-only pass, which never changes the
verdict. A missing or unfinished record, a give-up after crashes between the agent's calls and a frozen instance
that does not build at the episode's start are infrastructure errors.
Reward 1 needs every ordered stage and the terminal hold with no invariant or guard violation. Invariants and guards are checked at every 2 ms
physics substep and fail the episode immediately (a dropped, slipped or knocked-away object ends it as a failure);
partial completion fails. Rows of the wrong width for the recorded hand, a forged or unknown hand label, non-finite
or out-of-range targets and wrist motion are rejected with reward 0. `scripts/dexhand/tests/test_essential_strict.py`
covers the oracle, no-op, truncated, dropped-object, forged-metadata and wrong-width cases for both hands.
Release status is provisional until independent solvability review.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 2 GB | 2 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: 30 Harbor 0.23 trials of the six essential families (12 oracle, 12 nop, 6 Wuji smoke; rcb_monitor samples every 5 s, efe:dexhand-0.2.0, CPU-only, 2026-10-14) plus the hamburger and paper oracle/nop trials: agent container peak <= 0.03 GiB; one fresh replay process 0.25-0.32 GiB max RSS (os.wait4; paper 0.31 GiB, hamburger 0.28 GiB), the privileged verifier runs two at once (<= 0.65 GiB); standard sim service peak 0.65 GiB (VmHWM, held_joystick oracle episode), paper 0.51 GiB; one core per replay process; x1.2 rounded up to a GB, raised to the 2 CPU / 2 GB design minimum (an agent's own simulator sessions take about 0.3 GiB each)
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 16 GiB memory. Limits measured: memory: 8 GiB lets an agent run about twenty 0.3 GiB simulator sessions (pot/sweep: three or four 2 GiB sessions) next to its harness; measurements as in the [[rule]]; processes 512 and disk 10 GiB: design defaults, not yet measured; whole trial: + the sim service's 8 GiB cap (peaks 0.65 GiB, dual-arm 2.53 GiB).

## Details

### Notes
Source: `scripts/dexhand/` (task folder `task_library/essential_held_joystick/`); the image recipe is `images/dexhand/`. Both
modes use the identical frozen `instance.json`. The Sharpa Wave model and meshes are pinned to MuJoCo Menagerie commit
`0059d4335f8156206f63a35662313385f7ad6d74` (Apache-2.0). Wuji Hand 2.2 is the manufacturer's `hand2/hand2_2` model
from `wuji-technology/wuji-description` commit `829c9aa27cb12c3a49d5b8d63c9869dd8f656702` (MIT), mounted unchanged in
the same wrist frame; its collision geoms are renamed to the predicate's finger/palm roles only. Object assets carry
their own licenses and checksums under `object_assets/`. Renderer output is evidence; it never determines the verdict.

### Change Log
- 2026-10-14 (board 0109, before the first scored run): 20 resets in standard mode (owner; PROTOCOL §4.5, DexToolBench's value). `POST /reset` starts a new episode from the frozen start (the same state hash as a fresh process); only the last episode is graded, a success ends the trial; `reward.json` adds `resets` and `reset_budget`. Before, one trial was one episode.
- 2026-10-14 (board 0109): two close-up cameras of the held object, `inhand_top` (above the palm) and `inhand_side` (thumb side), mounted on the locked hand like `palm`; the standard service returns `overview` and `inhand_top` by default. Before, the object was 40-60 px wide in the overview and the palm camera saw the back of the hand, so its in-hand pose could hardly be observed in standard mode.
- 2026-10-16 (board 0136, video only): the collect hook renders the replay video in its remaining time (timeout_sec minus 60 s) instead of a fixed 300 s, which cut the video of episodes longer than ~10k steps. The video films every 2nd step but at most 1500 frames (a 640x480 OSMesa frame takes ~0.3 s). The verdict, the replays and `reward.json` are unchanged; earlier results stay valid.
- 2026-10-17 (owner, board 0150/0151): standard mode graded by the live episode; no grading replay; video by one render pass from the trajectory after the verdict. `success` is the sim service's own verdict on the episode it ran (the same predicate a replay recomputed: the same rows through the same step, a success ending the episode); the collect hook no longer replays it twice in fresh processes, and `final.json` / `reward.json` drop `replay_success`, `deterministic` and `live_matches_replay` (`graded_by = "live"`, `replays = 0`). The service checks the frozen instance's files against the generator's record when an episode begins (`instance_mismatch`, an infrastructure error). A collect hook on `main` (`kill -9 -1`) stops whatever the agent left running before the service ends the episode. The agent's side (the instruction's grading sentence aside), the scene and the predicate are unchanged.
- 2026-10-14 (board 0109): the held object's rotation bound (invariant `body_rotation`) 0.24 -> 0.35 rad (20 degrees, both held-object families). The reference solution peaked at 0.2396 rad (joystick) and 0.218 rad (cube layer), within 0.0004 / 0.022 rad of the old bound, so the bound was effectively the reference's own peak; finger targets perturbed by +-0.001 rad peak at 0.25-0.30 rad. The task's intent (keep the held object steady) is unchanged.
