# dexhand-essential-cube-reorient-i00-privileged

| | |
|---|---|
| Benchmark | DexHand |
| Mode | privileged |
| Twin | `dexhand-essential-cube-reorient-i00-standard` |
| Simulator / robot | `mujoco` / `sharpa-wave-floating` |
| Family / instance | `essential_cube_reorient` / seed 0 |
| Oracle | `full` — solution/trajectory.npz is the validated Sharpa Wave actuator trajectory of this frozen instance (153 controls at 50 Hz, physical contact only). The privileged oracle hands it in; the standard oracle submits the same rows as float64 through the client's request path (the service executes the validated targets bit for bit). Both replay to success in two fresh processes with identical final state hashes; float32-rounded copies of all six oracles also score 1. Human solvability review is pending; release status stays provisional. solution/wuji/trajectory.npz is a validated Wuji Hand 2.2 trajectory of this instance (165 controls, motor targets only, physical contact only); the oracle uses it when the run selects wuji (privileged: DEXHAND_HAND=wuji; standard: the sim service's hand), and it replays to success in two fresh processes with identical state hashes. |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350` |

## Task
With the wrist fixed, rotate the free marked sphere +90 degrees around palm-local Y, then +90 degrees around palm-local X from that pose, then return to its exact initial orientation. Maintain hand contact and avoid any external support throughout; stabilize each ordered checkpoint with at least two fingertips.

Palm-local axes belong to a frame fixed to the palm; with the wrist locked it is aligned with the world axes: +X points from the wrist toward the fingertips (world +x), +Y points across the palm from the thumb side toward the little-finger side (world +y), and +Z points out of the palm, which faces up (world +z). In the simulator it has the orientation of the `wrist_stage` body (the identity quaternion while the wrist is locked), not that of the palm link `right_hand_C_MC`, whose own axes are rotated relative to it. A turn about a palm-local axis is about that palm-fixed axis (it does not turn with the object), and a positive angle follows the right-hand rule: counterclockwise when seen from the positive end of the axis looking back toward the palm. So +90 degrees about Y carries the side of the sphere that faces up toward the fingertips, and +90 degrees about X carries the side that faces up toward the thumb side.

## Difficulty
hard: Reorient a free spherical object with three asymmetric direction markers through two different axes and return.
The scene uses free_orientation_sphere and independently controlled fingers with the wrist locked; every ordered stage and
a terminal hold must be reached through contact alone.

## Reference solution
`solution/trajectory.npz` is the validated Sharpa Wave actuator trajectory of this frozen instance: 153 finger-target rows at 50 Hz (3.1 s) with the six wrist targets locked, executed through physical contact only. `solve.sh` hands it in unchanged as `/app/output/trajectory.npz`. It was derived offline by authoring controllers (not part of the repository) and is bound to the validated evidence (byte-identical trajectory, model hash, two fresh-process replays with the validated final state hash). Wuji Hand 2.2: `solution/wuji/trajectory.npz` is a validated Wuji Hand 2.2 trajectory of this instance (165 rows of motor targets, physical contact only). With `DEXHAND_HAND=wuji` set for the oracle, `solve.sh` hands it in instead of the Sharpa Wave rows; the verifier replays it with the Wuji Hand 2.2.

## Verification
The separate verifier replays the submitted numeric rows twice in fresh processes, with the hand recorded in the archive.
Reward 1 needs every ordered stage and the terminal hold with no invariant or guard violation, and identical final
state hashes. Invariants and guards are checked at every 2 ms
physics substep and fail the episode immediately (a dropped, slipped or knocked-away object ends it as a failure);
partial completion fails. Rows of the wrong width for the recorded hand, a forged or unknown hand label, non-finite
or out-of-range targets and wrist motion are rejected with reward 0. The verifier is tested
on the oracle, no-op, truncated, dropped-object, forged-metadata and wrong-width cases for both hands.
Release status is provisional until independent solvability review.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 2 | 4 GiB | 1024 | no GPU | 10 GiB |
| verifier (as `main`) | 2 | 4 GiB | no cap | no GPU | 10 GiB |

- GPU: not needed.

## Details

### Notes
Source: the DexHand essential task `essential_cube_reorient`; the image recipe is `images/dexhand/`. Both
modes use the identical frozen `instance.json`. The Sharpa Wave model and meshes are pinned to MuJoCo Menagerie commit
`0059d4335f8156206f63a35662313385f7ad6d74` (Apache-2.0). Wuji Hand 2.2 is the manufacturer's `hand2/hand2_2` model
from `wuji-technology/wuji-description` commit `829c9aa27cb12c3a49d5b8d63c9869dd8f656702` (MIT), mounted unchanged in
the same wrist frame; its collision geoms are renamed to the predicate's finger/palm roles only. Object assets carry
their own licenses and checksums under `object_assets/`. Renderer output is evidence; it never determines the verdict.
