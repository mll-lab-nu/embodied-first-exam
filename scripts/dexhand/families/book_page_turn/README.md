# book_page_turn: authoring notes

Physical DexHand version of scene T39 of the 50-scene expansion ("Turn a page in a real board book"). The source
scene was a kinematic demonstration (a prescribed leaf trace backed by a historical force-driven episode); here the
Tianji Marvin two-arm robot with dexterous hands turns the page through contact only (wave 3: Marvin arm rig, all
boards flat as in the source, source desk and book pose).

## Files

| file | role |
|---|---|
| `scene.py` | MJCF: T39 desk, free board book (8 leaves + 2 covers + spine), Marvin stand with two arms and Sharpa Waves (`arm_rig.mount_marvin`; Wuji via the rig) |
| `checker.py` | verdict from simulator state: ordered stages, terminal hold, fail-fast invariants |
| `runtime.py` | `Session` (reset/step/status/state_sha/hold_action/snapshot/restore/save_trajectory/replay/render_frame) |
| `replay.py` | fresh-process replay CLI (FAMILY_PLUGIN section 5) |
| `task.json` | frozen instance: physics, book parameters, thresholds, cameras, per-hand start targets |
| `assets/` | the T39 page prints, cover and licenses, copied unchanged; `manifest.json` holds sha256 + size (checked at build) |
| `author.py` | authoring controller (not shipped): closed-loop two-arm page turn (Marvin IK through `arm_ik`) recorded as open-loop rows |
| `tests/test_book_page_turn.py` | authoring tests (not shipped): oracles, nop, truncations, release, shove fail-fast, post-success rows, state-edit invariants, forged/shadowed/pickled members, wrong width/hand/task/names, NaN/inf/range/row limits, Wuji composition + nop |
| `presentation.py`, `studio_renderer.py`, `film.json` | authoring film (not shipped): exact native pose export + the T39 scene's Blender studio renderer (caption adapted) |
| `solution/trajectory.npz` | Sharpa oracle rows (`actions`, `hand`, `task`): 553 rows of 58 targets, success after 453 |

## Modelling choices

- Book: T39's 6 x 6 in board book (0.1524 m boards, 1.2 mm thick, 0.7 kg/m^2, 16 g per board), leaves 0-1 on the
  left, 2-7 on the right (leaf 2 on top, pages 5/6), covers below; same hinge-root heights as the source. One free
  spine body (`book_free`) on the desk; boards are children on a vertical binding compliance (slide, 200 N/m,
  +-6 mm; the source used 20 N/m, which let a lifted board sag 8 mm) and a binding hinge (damping 0.006 N m s/rad,
  friction 0.002 N m; source 0.001 / 0.0002). The higher damping/friction is a stiff new board-book binding: a page
  pushed past vertical settles onto the left stack in about a second instead of slamming down.
- Hinge ranges: right-hand boards (-0.25, pi + 0.25), left-hand boards (-pi - 0.25, 0.25) so any board can be turned in
  either direction (the source let left boards rise only 0.25 rad).
- All boards lie flat on their stacks (0.2 mm gaps), as in the T39 source; leaf 2 has the same hinge as every other
  right-hand board. (Wave 2 rested leaf 2 on a 4 degree springback stop so a fingertip could get under it; removed.)
- Desk and book in the T39 source pose: desk top z = 0.78 (centre (0.52, 0), 0.60 x 0.52 m), book spine at
  (0.51, 0, 0.7806), yaw -90 deg (spine along world x, right-hand stack toward -y). Robot: the Marvin stand at the
  world origin facing +x (`arm_rig.py`, robot id `marvin-bimanual-sharpa-wave`, the pot_shelf_transfer arm gains;
  floor at z = -0.1 = base_z - 0.1 under the stand's plate; the desk's front legs are set back from 0.29 to x = 0.43
  (`desk_legs_x`) so they stand clear of the stand's base plate; the robot never overlaps the desk: exact
  convex-hull check in the status record).
- Covers are glued to the spine wrap (hinge stiffness 0.5 N m/rad); a flat 16 mm "binding base" contact box under the
  gutter keeps the free spine level (with the source's tall thin wrap the spine tipped ~1.5 deg while settling). The
  teal wrap is visual only.
- Contact: thin boxes with the board footprint, starting 4 mm from the hinge line (boards of opposite stacks met
  board-to-board at the hinge line otherwise); the 5 mm corner rounding stays in the visual mesh. Board friction 0.35,
  desk 0.65, Sharpa fingertips 1.2.
- Reset: hand at its declared targets, then a fixed 0.5 s (250 substeps) passive settle; the verdict references
  (start angles, spine pose) are taken after it. Deterministic in fresh processes.
- Verso prints reverse u and all prints flip v so pages read normally in MuJoCo (T39's export applied the same
  reversal for Blender).

`state_sha` hashes the integration state, the predicate state, the hand and only the physics/predicate keys of
`task.json` (`runtime.HASHED_KEYS`), so editing texts or cameras never changes evidence hashes.

## Verdict (checker.py)

Stage angle = `leaf_2_binding` (0 = flat right, pi = flat left). Stages in order: lifted > 30 deg, past vertical
> 90 deg, laid (> 170 deg AND leaf 2 contacts leaf 0/leaf 1/left cover AND |leaf-2 hinge speed| <= 0.2 rad/s AND every
other board and cover within 5 deg of its start AND no hand-book contact), held: laid for 50 consecutive controls.
Fail-fast after every 2 ms substep: spine moved > 3 cm or rotated > 10 deg; any other leaf moved > 30 deg
(`second_leaf_turned`); a cover moved > 30 deg (`book_closing`); a book body's centre of mass > 2 mm below the desk top;
non-finite state / MuJoCo instability warnings; 3000-control budget.

## Authoring controller (author.py)

The plan is written in the canonical book frame of wave 2 (spine along +y, right stack toward +x) and mapped to the
world through the book's start pose. Right hand palm up, index straight, other fingers curled. The left arm first
moves (joint space via a waypoint beside the stand, outside the desk, and one above the desk, then IK) its index fingertip, pointing down, against the left
stack's fore-edge (sphere centre 8.5 mm above the desk): a stop that keeps the free book from sliding. The right index
fingertip sphere comes to 1 mm outside leaf 2's fore-edge face, 1.5 mm above leaf 2's top face, settles there, then presses in by
4.5 mm (it mainly loads leaf 2's fore-edge; it also brushes the fore-edges of leaves 3-5, at most 1.4 mm deep, which
move less than 0.003 deg); the hand then turns about the measured leaf-2 hinge (the fingertip
target keeps its place in the board frame, the hand itself turns only 0.45 x the board angle to stay inside the
wrist's range): fingertip friction on the edge face lifts the board and carries it to 126 deg. The left hand lets go
at 100 deg (board angle of the plan) and moves 0.12 m outward and 0.15 m up, clear of the right hand's retreat, the board settles on the left stack under its binding damping, the right hand
backs away and parks. Each control: right-arm IK (`arm_ik.ArmIK`) to the planned hand-root pose, a joint integral for
servo sag that adapts only in free space (frozen while touching the book, so a preloaded contact target cannot wind
it up), and a velocity feed-forward `(kv / kp) qdot` against servo lag. Rows are recorded and replayed open loop;
100 extra hold rows give slack. Variants with a 3.5 / 4.5 / 5.5 mm press all succeed; 1.5-2.5 mm presses lose the
edge (arm tracking error ~5 mm), and without the left-hand stop any press above ~2 mm shoves the book. Open-loop robustness of the recorded rows to i.i.d. per-row target noise (arm joints / fingers): 0.5 mrad / 0.005 rad 3 of 3 succeed, 1 mrad / 0.01 rad 2 of 3 (one shoved book), 2 mrad / 0.01 rad 1 of 3.

No Wuji reference solution. The Wuji settings in `HAND_DEFAULTS` (pitch 0.4 rad, 6.5 mm press, hand turn 0.6 rising to
0.85-0.9 x the board angle) turn the page, but late in the turn the right-arm IK target leaves the reachable set and
the right arm brushes the left arm (robot self-contact), so no Wuji episode is packaged; Wuji composes on the rig with a
deterministic nop.

## Evidence

The authoring evidence (fresh-process replay JSONs, negatives, perturbation logs, Harbor trials, MuJoCo and Blender
films) was kept in the authoring workspace; the commands below regenerate it. Run them from this folder with
`DEXHAND_ASSET_DIR` pointing at the Sharpa assets:

```bash
python author.py --out solution/trajectory.npz                    # Sharpa oracle (553 rows, success after 453)
python replay.py --task book_page_turn --traj solution/trajectory.npz --out r1.json   # twice: identical state_sha
python -m pytest -q tests                                        # authoring tests (a few minutes)
python presentation.py export --export <export dir> --config film.json && python presentation.py verify --export <export dir>
BLENDER=<blender 4.5.3> python studio_renderer.py --export <export dir> --output film.mp4 --engine eevee --width 1280 --height 720 --samples 32 --fps 25
```

## Harbor

Wave 3 (Harbor 0.23, eai-dexhand:0.2.0, snapshot copies of the generated pair, 2026-10-15): privileged oracle 1 (553
rows, success at 453, deterministic) / nop 0; standard oracle 1 (live success, live hash = replay hash) / nop 0; Wuji
standard nop 0. Robot checks (exact convex-hull stand/arm vs desk check, every-substep contact audit: zero robot
self-contacts, zero arm/stand contacts with the world) are recorded in the family's status record.
