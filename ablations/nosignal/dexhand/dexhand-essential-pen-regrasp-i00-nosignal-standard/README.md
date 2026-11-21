# dexhand-essential-pen-regrasp-i00-standard

| | |
|---|---|
| Benchmark | DexHand |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `dexhand-essential-pen-regrasp-i00-privileged` |
| Simulator / robot | `mujoco` / `sharpa-wave-floating` |
| Family / instance | `essential_pen_regrasp` / seed 0 |
| Oracle | `full` — solution/trajectory.npz is the validated Sharpa Wave actuator trajectory of this frozen instance (385 controls at 50 Hz, physical contact only). The privileged oracle hands it in; the standard oracle submits the same rows as float64 through the client's request path (the service executes the validated targets bit for bit). Both replay to success in two fresh processes with identical final state hashes; float32-rounded copies of all six oracles also score 1. Human solvability review is pending; release status stays provisional. solution/wuji/trajectory.npz is a validated Wuji Hand 2.2 trajectory of this instance (1,571 controls, motor targets only, physical contact only); the oracle uses it when the run selects wuji (privileged: DEXHAND_HAND=wuji; standard: the sim service's hand), and it replays to success in two fresh processes with identical state hashes. |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350` |

## Task
With the wrist fixed, move the unsupported pen 30 mm along its initial longitudinal axis relative to the palm, then turn its axis by 45 degrees and hold its marked grip band with thumb, index and middle fingertips. The initial pen rests against the central palm surfaces; the final pen must clear those central palm surfaces. All three named fingertips must contact the marked band. Other finger links may also contribute contact; an exclusive fingertip-only grasp is not required. No table support, other hand or whole-object release is allowed.

## Difficulty
hard: Advance and reorient a real pen mesh with a fitted shaft, physical writing tip and tail into a marked three-finger grip.
The scene uses free_pen and independently controlled fingers with the wrist locked; every ordered stage and
a terminal hold must be reached through contact alone.

## Reference solution
`solution/trajectory.npz` is the validated Sharpa Wave actuator trajectory of this frozen instance: 385 finger-target rows at 50 Hz (7.7 s) with the six wrist targets locked, executed through physical contact only. `solve.sh` submits the same rows as float64 through the agent's client request path (`hold`, dt 0.02 s), so the service executes the validated targets bit for bit; float32-rounded rows (the client's `submit`) also succeed. It was derived offline by authoring controllers (not part of the repository) and is bound to the validated evidence (byte-identical trajectory, model hash, two fresh-process replays with the validated final state hash). Wuji Hand 2.2: `solution/wuji/trajectory.npz` is a validated Wuji Hand 2.2 trajectory of this instance (1,571 rows of motor targets, physical contact only). When the sim service runs the Wuji Hand 2.2 (`DEXHAND_HAND=wuji`, `spec()["hand"]`), `solve.sh` submits these rows as float64 instead of the Sharpa Wave rows.

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
or out-of-range targets and wrist motion are rejected with reward 0. The verifier is tested
on the oracle, no-op, truncated, dropped-object, forged-metadata and wrong-width cases for both hands.
Release status is provisional until independent solvability review.

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
Source: the DexHand essential task `essential_pen_regrasp`; the image recipe is `images/dexhand/`. Both
modes use the identical frozen `instance.json`. The Sharpa Wave model and meshes are pinned to MuJoCo Menagerie commit
`0059d4335f8156206f63a35662313385f7ad6d74` (Apache-2.0). Wuji Hand 2.2 is the manufacturer's `hand2/hand2_2` model
from `wuji-technology/wuji-description` commit `829c9aa27cb12c3a49d5b8d63c9869dd8f656702` (MIT), mounted unchanged in
the same wrist frame; its collision geoms are renamed to the predicate's finger/palm roles only. Object assets carry
their own licenses and checksums under `object_assets/`. Renderer output is evidence; it never determines the verdict.
