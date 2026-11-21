# dexhand-drying-rack-unfold-i00-standard

| | |
|---|---|
| Benchmark | DexHand |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `dexhand-drying-rack-unfold-i00-privileged` |
| Simulator / robot | `mujoco` / `sharpa-wave-floating` |
| Family / instance | `drying_rack_unfold` / seed 0 |
| Oracle | `full` — solution/trajectory.npz replays the recorded Sharpa Wave authoring episode (2,415 controls, success after 2,315). The rows are float32-exact, so the standard oracle submits the same rows through the client. Two fresh-process replays succeed with identical state hashes. |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350` |

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
produced them computes hand and wrist targets only:
a thumb-index pinch swings the top half open, a low pinch rotates each leg onto its stop, and a pinch on the hinge collar
turns the open rack over about the opposite side rim and lowers it onto its feet. It never drives an object pose or
applies an object force, and it is never copied into the agent's environment or image.

## Verification
Standard mode. The trusted sim service judges the episode it ran (the last one after resets) with the task's predicate and
the selected hand, after the agent's container is stopped; its record (`final.json`, `graded_by = "live"`) is the
verdict, and nothing is replayed to grade it. The isolated verifier reads only the service's artifacts. The
service then renders `replay.mp4` from the recorded trajectory in one video-only pass, which never changes the
verdict. A missing or unfinished record, a give-up after crashes between the agent's calls and a frozen instance
that does not build at the episode's start are infrastructure errors.
The episode ends at the first success or the first failure.
Success needs, in order: fold angle at most 0.314 rad and all four legs at least 1.571 rad; then the rack upright within
10 degrees on its four feet and nothing else; then no hand contact and rack speeds at most 0.02 m/s and 0.2 rad/s for
50 consecutive controls. Failures are fail-fast and permanent, checked every 2 ms substep: a rack part below the counter
top, off the counter or more than 0.9 m above it, rack-floor or rack-cabinet contact, the rack unsupported (no counter
and no hand contact) while falling faster than 0.05 m/s, after standing a tilt above 20 degrees or any hinge leaving its
open range, unstable physics, or the 6,000-control budget. The frozen thresholds come from the task, never from an
agent archive. A no-op fails. Human review and full agent-trial calibration remain pending; report this task as
provisional.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 2 | 10 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 2 | 5 GiB | 1024 | no GPU | — |
| verifier (as `main`) | 2 | 10 GiB | no cap | no GPU | 10 GiB |

- GPU: not needed.

## Details

### Notes
Source: the DexHand family of this task. The rack is the
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
