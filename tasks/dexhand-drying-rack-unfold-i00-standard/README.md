# dexhand-drying-rack-unfold-i00-standard

| | |
|---|---|
| Benchmark | DexHand |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `dexhand-drying-rack-unfold-i00-privileged` |
| Simulator / robot | `mujoco` / `sharpa-wave-floating` |
| Family / instance | `drying_rack_unfold` |
| Oracle | `full` — solution/trajectory.npz replays the recorded Sharpa Wave authoring episode (tools/gen_oracle.py, 2,415 controls, success after 2,315). The rows are float32-exact, so the standard oracle submits the same rows through the client. Two fresh-process replays succeed with identical state hashes. |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-dexhand:0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350` |

## Task
Set up the folding sweater dryer on the kitchen counter with the dexterous hand. It starts fully folded and stored underside up, its four legs folded between the two frame halves. Open the two halves flat about the pole hinge, open all four legs onto their stops, turn the open rack over and stand it on its four feet, then let go: success needs the fold angle at most 0.314 rad, every leg at least 1.571 rad, the rack upright within 10 degrees on all four feet and nothing else, untouched by the hand and still for 50 consecutive controls (1 s). Dropping the rack, pushing it off the counter, or letting it collapse or fall over after it stands ends the episode as a failure at once.

## Difficulty
Hard. One dexterous hand on a floating six-axis wrist stage has to open a large passive mechanism (0.66 m x 0.65 m,
0.51 kg) in three different manipulations: swing the folded frame half 180 degrees about the pole hinge, flip out four
thin legs that lie about 1 cm above the counter, and turn the whole open rack over so that it lands on its four feet
with every leg still past its over-centre position (the legs have no latch; only their 100 degree stop and the rack's
weight keep them open). Every stage is checked from simulator state, in order, with a 1 s released hold; dropping the
rack, pushing it off the counter, or letting it collapse or fall after it stands ends the episode at once.

## Reference solution
`solution/trajectory.npz` replays the recorded Sharpa Wave authoring episode (2,415 controls; the replay ends with
success after 2,315). In standard mode the same rows are submitted through `rcb_client` in 250-row chunks (they are
exactly representable in float32, so the client's rounding does not change them). The authoring controller that
produced them (`scripts/dexhand/families/drying_rack_unfold/tools/gen_oracle.py`) computes hand and wrist targets only:
a thumb-index pinch swings the top half open, a low pinch rotates each leg onto its stop, and a pinch on the hinge collar
turns the open rack over about the opposite side rim and lowers it onto its feet. It never drives an object pose or
applies an object force, and it is never copied into the agent's environment or image.

## Verification
standard mode. The verifier rebuilds the frozen scene with the recorded hand (`hand` member of the trajectory archive
in privileged mode; the hand of the trusted service episode in standard mode) and replays only numeric motor targets
twice in fresh processes. Both replays must succeed and have identical final integration state hashes; in standard
mode the replay hash must also equal the live final hash. A replay ends at the first success or the first failure.
Success needs, in order: fold angle at most 0.314 rad and all four legs at least 1.571 rad; then the rack upright within
10 degrees on its four feet and nothing else; then no hand contact and rack speeds at most 0.02 m/s and 0.2 rad/s for
50 consecutive controls. Failures are fail-fast and permanent, checked every 2 ms substep: a rack part below the counter
top, off the counter or more than 0.9 m above it, rack-floor or rack-cabinet contact, the rack unsupported (no counter
and no hand contact) while falling faster than 0.05 m/s, after standing a tilt above 20 degrees or any hinge leaving its
open range, unstable physics, or the 6,000-control budget. The frozen thresholds come from the task, never from an
agent archive. A no-op fails. Human review and full agent-trial calibration remain pending; report this task as
provisional.

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 2 GB | 2 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: wave-2 integration smoke (Harbor 0.23, eai-dexhand:0.2.0, CPU-only, 2026-10-15; one privileged and one standard Sharpa oracle per family; docker cgroup memory.peak): privileged verifier <= 0.64 GiB with two concurrent replays, standard sim sidecar <= 0.96 GiB, agent containers < 0.05 GiB; one fresh replay process 0.26-0.39 GiB max RSS (os.wait4); x1.2 rounded up to a GB, raised to the 2 CPU / 2 GB design minimum (an agent's own simulator sessions take about 0.3-0.5 GiB each)
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 16 GiB memory. Limits measured: memory: 8 GiB lets an agent run more than a dozen 0.3-0.5 GiB simulator sessions next to its harness; measurements as in the [[rule]]; processes 512 and disk 10 GiB: design defaults, not yet measured; whole trial: + the sim service's 8 GiB cap (peaks <= 0.96 GiB).

## Details

### Notes
Source: `scripts/dexhand/families/drying_rack_unfold/`, generated by `scripts/dexhand/generate.py`. The rack is the
approved scene-expansion T20 scene (a photo-dimensioned procedural reconstruction of the legacy OXO Good Grips folding
sweater dryer, original project geometry; no third-party visual asset): frame dimensions, masses, inertias, hinge
ranges, contact law and materials are unchanged, and the start is the scene's storage pose (folded, underside up). Two
modelling choices differ from that scene: the leg pivots have viscous damping 0.03 N m s/rad instead of 0.003 (dry
friction 0.003 N m unchanged), and the counter is 1.5 m instead of 1.1 m long so the open rack can be turned over on it.
The woven net is visual only, as in the scene; no laundry is simulated. The Sharpa Wave assets are pinned to MuJoCo
Menagerie commit `0059d4335f8156206f63a35662313385f7ad6d74` (Apache-2.0), derived from Sharpa Robotics commit
`6eea427eb24189519f32b9f21674cd534d3f973c`. The Wuji Hand 2.2 model (`hand2/hand2_2`) is pinned to
wuji-technology/wuji-description commit `829c9aa27cb12c3a49d5b8d63c9869dd8f656702` (MIT) and mounted on the same wrist
stage with its vendor joints, actuators and contact geometry unchanged. This is mechanism-handling feasibility on a
floating wrist stage, not a full-arm or zero-shot claim.

### Change Log
- 2026-10-14 (board 0109, before the first scored run): 20 resets in standard mode (owner; PROTOCOL §4.5, DexToolBench's value). `POST /reset` starts a new episode from the frozen start (the same state hash as a fresh process); only the last episode is graded, a success ends the trial; `reward.json` adds `resets` and `reset_budget`. Before, one trial was one episode.
- 2026-10-16 (board 0136, video only): the collect hook renders the replay video in its remaining time (timeout_sec minus 60 s, at most the video limit). The video films at most 300 steps (a longer episode at a larger stride; an OSMesa frame of an arm scene takes up to ~3.6 s on two cores), and the video, verifier and collect limits cover the longest archive the row limit allows. The verdict, the replays and `reward.json` are unchanged.
