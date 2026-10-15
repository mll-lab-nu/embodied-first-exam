# book_page_turn: authoring notes

Physical DexHand version of scene T39 of the 50-scene expansion ("Turn a page in a real board book"). The source
scene was a kinematic demonstration (a prescribed leaf trace backed by a historical force-driven episode); here a
dexterous hand on a wrist stage turns the page through contact only.

## Files

| file | role |
|---|---|
| `scene.py` | MJCF: desk, free board book (8 leaves + 2 covers + spine), Sharpa Wave on the six-axis wrist stage; Wuji via `hands.replace_wave_hands` |
| `checker.py` | verdict from simulator state: ordered stages, terminal hold, fail-fast invariants |
| `runtime.py` | `Session` (reset/step/status/state_sha/hold_action/snapshot/restore/save_trajectory/replay/render_frame) |
| `replay.py` | fresh-process replay CLI (FAMILY_PLUGIN section 5) |
| `task.json` | frozen instance: physics, book parameters, thresholds, cameras, per-hand start targets |
| `assets/` | the T39 page prints, cover and licenses, copied unchanged; `manifest.json` holds sha256 + size (checked at build) |
| `author.py` | authoring controller (not shipped): closed-loop scripted page turn (both hands) recorded as open-loop rows |
| `tests/test_book_page_turn.py` | authoring tests (not shipped): oracles, nop, truncations, release, shove fail-fast, post-success rows, state-edit invariants, forged/shadowed/pickled members, wrong width/hand/task/names, NaN/inf/range/row limits, Wuji |
| `presentation.py`, `studio_renderer.py`, `film.json` | authoring film (not shipped): exact native pose export + the T39 scene's Blender studio renderer (caption adapted) |
| `solution/trajectory.npz` | Sharpa oracle rows (`actions`, `hand`, `task`): 650 rows, success after 391 |
| `solution/wuji/trajectory.npz` | Wuji oracle rows: 650 rows, success after 347 (per-hand oracle, packaged as `solution/wuji/`) |

## Modelling choices

- Book: T39's 6 x 6 in board book (0.1524 m boards, 1.2 mm thick, 0.7 kg/m^2, 16 g per board), leaves 0-1 on the
  left, 2-7 on the right (leaf 2 on top, pages 5/6), covers below; same hinge-root heights as the source. One free
  spine body (`book_free`) on the desk; boards are children on a vertical binding compliance (slide, 200 N/m,
  +-6 mm; the source used 20 N/m, which let a lifted board sag 8 mm) and a binding hinge (damping 0.006 N m s/rad,
  friction 0.002 N m; source 0.001 / 0.0002). The higher damping/friction is a stiff new board-book binding: a page
  pushed past vertical settles onto the left stack in about a second instead of slamming down.
- Hinge ranges: right-hand boards (-0.25, pi + 0.25), left-hand boards (-pi - 0.25, 0.25) so any board can be turned in
  either direction (the source let left boards rise only 0.25 rad).
- Springback: leaf 2, the right-hand board of the open spread, rests on its binding stop at 0.07 rad (4 deg; a joint
  limit), as a new board book's stiff glued binding holds the spread's boards slightly open. This leaves a 10.9 mm gap
  under its fore-edge, which a fingertip (8.1 mm capsule radius) can catch; with all boards flat (0.2 mm gaps) no
  fingertip contact can lift the top board without also dragging the one below.
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

Palm-up Sharpa hand, index straight, other fingers curled. The index fingertip sphere is placed 4.4 mm below and just
outside leaf 2's bottom fore-edge corner (1.5 mm preload), then the whole hand rotates rigidly about the spine axis
by 2.2 rad over 3 s, carrying the board past vertical; the hand backs off, parks palm-up and holds. The only feedback
is an integral correction of the fingertip position for the wrist stage's gravity sag during the approach. Rows are
recorded and replayed open loop; 100 extra hold rows give slack. Robustness: constant wrist offsets of +-3 mm in x and
-3/+1.5 mm in z and per-row noise (0.5 mm, 2 mrad, 0.01 rad fingers) still succeed; +3 mm in z misses the catch
(17/18 variants).

Wuji: the same controller with per-hand overrides (`HAND_DEFAULTS`: pitch 0.15 rad, catch 4 mm below the corner,
index PIP/DIP flexed 0.3/0.2 rad so the distal pad leads, and a slide under the raised board between 0.35 and 0.8 rad
of rotation), found by a small physics sweep; 15/18 perturbation variants succeed.

## Evidence

The authoring evidence (fresh-process replay JSONs, negatives, perturbation logs, Harbor trials, MuJoCo and Blender
films) was kept in the authoring workspace; the commands below regenerate it. Run them from this folder with
`DEXHAND_ASSET_DIR` pointing at the Sharpa assets:

```bash
python author.py --out solution/trajectory.npz                    # Sharpa oracle (650 rows, success after 391)
python author.py --hand wuji --out solution/wuji/trajectory.npz   # Wuji oracle (650 rows, success after 347)
python replay.py --task book_page_turn --traj solution/trajectory.npz --out r1.json   # twice: identical state_sha
python -m pytest -q tests                                        # authoring tests (about 1 minute)
python presentation.py export --export <export dir> --config film.json && python presentation.py verify --export <export dir>
BLENDER=<blender 4.5.3> python studio_renderer.py --export <export dir> --output film.mp4 --engine eevee --width 1280 --height 720 --samples 32 --fps 25
```

## Harbor (local, 2026-10-14)

Harbor 0.23, `eai-dexhand:0.2.0`, CPU only, `RCB_LIMITS_ENFORCE=0`, on snapshot copies of the generated pair:
privileged oracle 1 (success at control 391, deterministic) / nop 0 (missing trajectory); standard oracle 1 (live
success, live hash = replay hash, 391 controls, about 2 min per trial) / nop 0; Wuji (`DEXHAND_HAND=wuji`): oracle 1 in
both modes (per-hand `solution/wuji/`, success at control 347, `hand_wuji = 1`), standard nop 0, privileged nop 0.
