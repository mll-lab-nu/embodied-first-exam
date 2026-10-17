# binder_page_load (T37): authoring notes

Physical DexHand version of scene-expansion T37 "Load punched pages into a ring binder" (a kinematic demo with
prescribed page and ring motion). Here one hand on the six-axis wrist stage does everything through contact.

## Files
- `scene.py`: MJCF builder (binder hardware from the T37 source dimensions, rigid punched pages lying on the desk, desk,
  cameras) + hand composition through the shared `hands.py` (Wuji via `hands.replace_wave_hands`).
- `checker.py`: ordered stages, terminal hold and fail-fast checks (state only). `runtime.py`: `Session`.
  `replay.py`: fresh-process replay CLI (FAMILY_PLUGIN section 5). `task.json`: frozen instance and thresholds.
- Authoring only (not shipped): `ctl.py` (IK + recorded motion primitives), `demo.py` (closed-loop scripted
  controller that produced the oracle), `preview.py` (1280x720 MuJoCo preview with an inset ring view),
  `presentation.py` + `studio_renderer.py` (Blender 4.5.3 film on exact exported MuJoCo poses),
  `tests/test_binder_page_load.py` (authoring tests).
- `assets/`: sha256-pinned reference copies of the T37 sources the geometry is taken from (`manifest.json`); the
  scene itself is procedural, no meshes or textures are loaded at run time.

## Modelling choices (BRIEF "Allowed modelling")
- Binder: free body on the desk (`binder_free`), passive `spine_fold` / `cover_fold` hinges, two toggle plates
  (`left_toggle`, `right_toggle`, range 0..0.60 rad, damping 0.01 N m s/rad; the source used 0.001, raised so the
  over-centre snap does not fling the pages through the wire), the source's over-centre spatial-tendon housing spring
  per plate (stable at 0 and 0.60 rad, opening torque about 0.13 N m), and the source's internal joint couplings
  (`paired_toggle_plates`, `booster_link_*`): these are internal linkages of the mechanism, not attachments to the hand.
  The booster paddles open the rings when pressed down; pressing the raised inner edges of the toggle plates closes them.
- Pages: rigid stiff-cardstock plates (139.7 x 215.9 mm, 0.8 mm contact thickness, 6 g) whose collision geometry
  is a compound of boxes and corner prisms leaving three octagonal see-through holes (6.35 mm across flats) 9.525 mm
  from the binding edge, so a ring can only enter through a hole. The source used seven hinged paper panels; bending is
  not modelled here. Page contacts use `solmix=1000` so the stiff cardstock contact law wins over the soft fingertip
  elastomer (otherwise fingertips sank through the sheet).
- Pages on the desk (wave 3): as in the source (T37 `scene.py`: page origins (0.71, 0.22) and (0.71, -0.025), flat,
  printed face up, holes towards the binder), the two pages start loose and flat on the desk; the wave-2 page stands
  are gone. A page touching the desk is no longer a failure (only the floor is), and the page-origin floor of the
  workspace box is 2 mm below the desk top (a page pressed into the desk sits 0.1-0.4 mm lower). The oracle picks a
  page up the way a person would: index and middle fingertips press on its printed face and drag it +x until its
  far edge overhangs the desk edge (x = 0.98 m) by 4 cm, then the thumb goes under the overhang and the index and
  middle close on top (pinch 16 mm from the far edge), and the page is lifted and threaded as before.
- Robot: still the floating six-axis wrist stage (wave 3 could not move this family onto the Marvin arm: replaying the
  oracle's hand-root poses through the arm IK, the right hand misses many of them by 0.12-0.66 m / 0.5-3.1 rad for
  every tested stand placement (origin facing +x, x 0.12-0.22, the desk's -y, +y and +x sides), because the threading
  and the far-edge pick need large wrist rolls beyond the Marvin wrist ranges (J6 +-60 deg, J7 +-90 deg) at 0.4-1.0 m
  from the stand; wave-3 authoring evidence `arm_reach.txt`, not in the repository).
- Hand: Sharpa Wave on the six-axis stage (28 controls) or Wuji Hand 2.2 (26). The stage base is at (0.62, 0, 0.70);
  the hand mount (quat 0 1 0 0) makes zero wrist rotation fingers-down, palm +x, which keeps every motion of this task
  far from the serial-XYZ wrist singularity. Fingertip pads use condim 6 with friction (1.5, 0.01, 0.004)
  (sliding, torsional, rolling resistance of a ~1 cm pad), as the hamburger sets fingertip friction.
- Physics: dt 2 ms, 10 substeps per 50 Hz control, implicitfast, elliptic cones, impratio 10.

## Predicate (task.json `checker`)
Stage 1 toggles >= 0.50 rad; stage 2 rings open, all six holes threaded by their own open right ring half (wire
centre line crosses the page plane once within 3.5 mm of the hole centre, left half not at all), no hand contact on
pages, pages touching binder or each other, page centres over the back cover (binder frame x 0.03..0.16, |y| < 0.03,
z -0.01..0.06 m); stage 3 toggles <= 0.05 rad, every hole linked once by its closed ring, pages over the cover;
stage 4 = stage 3 + no hand contact with pages or binder + pages resting + each page within 2 mm / 0.03 rad of its pose
at the window start, for 50 consecutive controls. Page stillness is a pose window, not an instantaneous speed:
pages resting on the closed rings show sub-0.1 mm contact chatter with brief 0.2 m/s velocity spikes.
Fail-fast per substep: page-floor contact; page with no contact falling faster than 0.2 m/s with no ring through
any of its holes (dropped, no catch window); page origin below z 0.698 or outside the workspace box; binder moved > 3 cm
or tilted > 0.35 rad; ring-page penetration > 1.2 mm; hand-page penetration > 3 mm; unstable physics; 6000 controls.
`state_sha` hashes the integration state, the predicate state, the hand and the non-prose `task.json` parameters.

## Commands
```bash
cd scripts/dexhand/families/binder_page_load        # DEXHAND_ASSET_DIR / WUJI_ASSET_DIR point at the hand assets
python demo.py --out oracle.npz                     # reproduces solution/trajectory.npz bit for bit
python replay.py --traj solution/trajectory.npz --out a.json   # twice, fresh processes: identical state_sha
python -m pytest -q tests                            # 7 tests: actuation, nop, widths, forged archives, oracle+float32, partial/drop/knock, holes
python preview.py --traj solution/trajectory.npz --video preview.mp4
python presentation.py export --export film/ --stride 4
blender -b -P studio_renderer.py -- --export film/ --output film.mp4      # Eevee, NVIDIA EGL
python presentation.py encode --export film/ --output film.mp4
```

## Oracle (Sharpa) and evidence
`python demo.py --out <file>` (phases open, page1, page0, close, flatten, finish; 150 slack rows appended) reproduces
`solution/trajectory.npz` bit for bit (sha256 cdc5856d...): 3,095 rows, success at control 2,940 (stages at 90 / 2605 /
2880 / 2940). Each page: fingertip drag (index and middle press the printed face, 0.8 mm hand steps, closed loop on
the far edge) until the far edge overhangs the desk by 4 cm, thumb under the overhang 6 mm outside the pinch line
(`thumb_dx`), index and middle on top 16 mm inside the far edge, 14 mm pre-gap and 6 mm squeeze, lift 2 cm + 7 cm,
then the wave-2 carry/thread/release servo. Evidence (wave 3, kept with the authoring records outside the repository):
two fresh replays and a generated-dir replay with identical state_sha c3d27bd5..., float32 success at 2,943,
negatives, Harbor, films. Harbor 0.23 (snapshot copies, eai-dexhand:0.2.0): privileged oracle 1 (2 replays
identical, 2,940 steps), privileged nop 0 (missing trajectory), standard oracle 1 (live = replay, 2,940 steps),
standard nop 0.

## Known limits
- Robustness: the oracle succeeds bit-exactly and with float32-rounded rows, but rows perturbed by 1e-5 rad Gaussian noise
  succeed in only one of three seeds (the release and ring-snap contacts are sensitive); agents need closed-loop control.
- Wuji Hand 2.2 composes and replays deterministically but has no successful trajectory: the ported controller
  (`demo.py --hand wuji`) opens the rings and threads one page, then the weak Wuji pinch loses the page while laying it down.
- The flat-desk pick (wave 3) is parameter sensitive: with the same plan, a 8 mm squeeze drops page 0 during the carry
  and a thumb 12 mm outside the pinch line drives a ring wire through page 1; the packaged parameters
  (`thumb_dx` 6 mm, squeeze 6 mm) succeed deterministically.
