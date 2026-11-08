# dexhand-pot-shelf-transfer-i00-privileged

| | |
|---|---|
| Benchmark | DexHand |
| Mode | privileged |
| Twin | `dexhand-pot-shelf-transfer-i00-standard` |
| Simulator / robot | `mujoco` / `marvin-bimanual-sharpa-wave` |
| Family / instance | `pot_shelf_transfer` / seed 0 |
| Oracle | `full` — solution/trajectory.npz: the 8,850 authoring rows of the accepted episode (bit-for-bit replay of the recorded states). Harbor 0.23 oracle reward 1 in both modes on 2026-10-14 (two fresh-process replays with identical state hashes; standard: live = replay). solution/wuji/trajectory.npz is a validated Wuji Hand 2.2 trajectory of this instance (8,266 controls, motor targets only, physical contact only); the oracle uses it when the run selects wuji (privileged: DEXHAND_HAND=wuji; standard: the sim service's hand), and it replays to success in two fresh processes with identical state hashes. |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350` |

## Task
A fixed dual-arm robot (two 7-joint arms, a dexterous hand on each wrist) stands at a kitchen worktop. A freely moving 1 kg two-handle stockpot (286 mm vessel diameter, 438 mm across its two loop handles) rests on the worktop; an open kitchen shelf is to the robot's left. Grasp the pot by its two handles, lift it with both hands, carry it into the shelf compartment and set it down upright on the shelf board at the target, then open both hands and withdraw them. The pot must never be dropped, tipped over, knocked against the furniture, the floor or a non-hand robot link, or leave its support while no hand carries it. Only the robot's position-controlled joint targets act on the world: there are no attachments, object actuators, scripted object motion or applied forces.

Mode `privileged`. A fixed Tianji Marvin dual-arm stand (two 7-joint arms) carries a dexterous hand on each wrist:
Sharpa Wave by default (58 targets per row), Wuji Hand 2.2 selectable (54 targets per row). One row is one 2 ms
physics step (500 Hz). The pot is a free 1 kg rigid body; only the robot's position servos act on the world.

## Difficulty
Hard. Both hands must hook the two thin (14 mm) loop handles of a 438 mm wide pot, lift it clear of the worktop, keep
it level while the two arms carry it 0.36 m sideways and 0.04 m up into an open shelf compartment, set it down at a
4 cm target, then release and withdraw without dragging it. The arm servos have no gravity compensation, the episode
fails on the first drop, tip, collision or furniture contact, and the 2 s released hold must be reached within 60 s
of simulated time.

## Reference solution
`solution/trajectory.npz` holds an authoring controller's 8,850 Sharpa rows (17.7 s at 500 Hz): supported approach,
both-handle grasp, loaded lift, levelling, carry into the compartment, placement, release and withdrawal. The
episode reaches the 2 s released hold at row 8,602, where it ends. The rows are replayed bit for bit by the packaged
scene (every physics state equals the authoring recording). Privileged: `solve.sh` re-saves the rows as the
deliverable. Standard: `solve.sh` submits them through the client with `dt = 0.002 s`. The solution is never copied
into the agent's environment or image.

Wuji Hand 2.2: `solution/wuji/trajectory.npz` is a validated Wuji Hand 2.2 trajectory of this instance (8,266 rows of motor targets, physical contact only). With `DEXHAND_HAND=wuji` set for the oracle, `solve.sh` hands it in instead of the Sharpa Wave rows; the verifier replays it with the Wuji Hand 2.2.

## Verification
Privileged: the isolated verifier rebuilds the frozen scene with the trajectory's `hand` (default `sharpa`) and replays
only the `actions` rows in one fresh process; reward 1 iff that replay succeeds.
Standard: the trusted service judges the live episode it ran; nothing is replayed. Rows of the wrong width for the recorded
hand, non-finite or out-of-range targets, a wrong `task` or `actuator_names` label and oversized archives are rejected
(reward 0, `bad_trajectory = 1`). The predicate is evaluated after every physics step from simulator state only
(contacts, contact forces, poses, velocities, geometric distances): two ordered stages (bimanual carry, released hold
on the shelf) and fail-fast invariants (drop, fall, tip, collision, furniture contact, penetration, joint overshoot,
unstable physics, step budget); nothing else fails early, so setting the pot back down on the worktop and regrasping
it is allowed. Partial completion fails. A `nop` agent scores 0 (no archive; in standard mode the
untouched pot never leaves the worktop).

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 2 | 9 GiB | 1024 | no GPU | 10 GiB |
| verifier (as `main`) | 2 | 9 GiB | no cap | no GPU | 10 GiB |

- GPU: not needed.

## Details

### Notes
Source: the DexHand family of this task. The frozen MJCF is
the manager-accepted scene-expansion model of this task (two-handle stockpot to shelf); freezing it rewrote
only its mesh paths and appended three static cameras, and the 8,850 authoring rows were checked to
replay to the accepted initial and final integration-state digests with every recorded qpos/qvel equal.

Assets: the pot is "Harvest Pot - Cookware" by Innerscene (CC0 1.0) at source scale, lid omitted; it is one 1 kg rigid
body (0.8 kg vessel + 0.2 kg dry payload), each hollow loop handle collides as 24 capsule chords, the vessel as 32 wall
boxes plus the source base mesh. Tianji Marvin arm geometry from DexForce's TianjiMarvin release (Apache-2.0) with
Genesis public inertia estimates (MIT); Sharpa Wave from MuJoCo Menagerie `0059d4335f8156206f63a35662313385f7ad6d74`
(Apache-2.0; the left hand is a declared mirror of the right model); Wuji Hand 2.2 from wuji-description
`829c9aa27cb12c3a49d5b8d63c9869dd8f656702` (MIT). Every mesh is checked against `assets/manifest.json` (sha256) before
the scene compiles; the arm and hand meshes come from the `efe:dexhand` image, the pot meshes from the task.

Modelling scope: estimated mass, inertia and contact compliance, no fluid, heat or deformation, internal hand
self-contact is not judged. Open kitchen shelf, not a narrow-cupboard challenge. The pot's 438 mm handles span the
board's depth direction, so at the target the front handle reaches about 32 mm past the board's open front edge; the
compartment test therefore admits at most 50 mm of overhang at the open front (all other faces are strict). Wuji Hand
2.2 composes on the same arm mounts with neutral fingers.
