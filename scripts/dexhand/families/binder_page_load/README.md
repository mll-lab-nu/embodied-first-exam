# binder_page_load (T37): authoring notes

Physical DexHand version of scene-expansion T37 "Load punched pages into a ring binder" (a kinematic demo with
prescribed page and ring motion). Here one hand on the six-axis wrist stage does everything through contact.

## Files
- `scene.py`: MJCF builder (binder hardware from the T37 source dimensions, rigid punched pages, page stands, desk,
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
- Page stands: the source starts with two loose sheets flat on the desk, which a single rigid hand cannot pick up;
  two wooden stands hold the pages leaning 12 degrees, holes down, so the top edge can be pinched (like the hamburger's
  preparation supports). Same objects, look and goal.
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
Fail-fast per substep: page-desk/floor contact; page with no contact falling faster than 0.2 m/s with no ring through
any of its holes (dropped, no catch window); page origin below z 0.70 or outside the workspace box; binder moved > 3 cm
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
`solution/trajectory.npz` bit for bit: 2,192 rows, success at control 2,042 (stages at 90 / 1486 / 1826 / 2042).
Evidence (fresh replays, float32, negatives, previews) was recorded with `replay.py`, `preview.py` and
`tests/test_binder_page_load.py`.
Harbor 0.23 (snapshot copies, eai-dexhand:0.2.0): privileged oracle 1 (2 replays identical, 2,042 steps, verifier 39 s),
privileged nop 0 (missing trajectory), standard oracle 1 (live = replay, 2,042 steps), standard nop 0, standard Wuji
nop 0 (`hand_wuji` 1). The standard oracle submits the privileged rows as float64 through the public client.
Margins along the oracle: binder tilt 0.136 rad (limit 0.35), shift 15.7 mm (30), ring-page penetration 0.43 mm (1.2),
hand-page penetration 0.77 mm (3).

## Known limits
- Robustness: the oracle succeeds bit-exactly and with float32-rounded rows, but rows perturbed by 1e-5 rad Gaussian noise
  succeed in only one of three seeds (the release and ring-snap contacts are sensitive); agents need closed-loop control.
- Wuji Hand 2.2 composes and replays deterministically but has no successful trajectory: the ported controller
  (`demo.py --hand wuji`) opens the rings and threads one page, then the weak Wuji pinch loses the page while laying it down.
