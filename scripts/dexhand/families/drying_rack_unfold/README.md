# drying_rack_unfold (authoring notes)

Physical DexHand version of scene-expansion T20 "Unfold a clothes drying rack" (previously a kinematic demo).

## Scene and modelling
- Rack: ported from the approved T20 source (`assets/source/rack.py`, sha256 in `assets/manifest.json`): legacy OXO
  folding sweater dryer, two 0.33 x 0.65 m frame halves (0.205 kg each) joined by one passive pole hinge
  (`fold_hinge`, range [0, pi], 0 = open flat, pi = folded, damping 0.001, friction loss 0.0005 N m), four passive
  offset legs (0.025 kg, range [0, 100 deg], stop 100 deg), capsule/box contact geometry with the source contact law,
  woven net visual only. Free body; storage pose = source (folded, underside up, legs folded, lower corner housings on
  the counter). No latch: an open leg stays open only past its over-centre (90 deg) under load, as in the source.
- Changes (all documented in `task.json` `modeling`): leg pivot damping 0.003 -> 0.03 N m s/rad (source friction loss
  0.003 N m kept; with the source damping jolts while the rack is turned over flutter legs off their stop); counter
  lengthened along x from 1.1 m to 1.5 m (same height and material) so the open rack can be turned over about a side
  rim and stay on the counter.
- Rig: one Sharpa Wave (default; Wuji Hand 2.2 via `hands.replace_wave_hands`) on a six-axis wrist stage whose origin
  is (0.62, 0, 0.75) m; mounted palm-down at zero wrist angles (fingers +x, thumb +y). 28 / 26 controls.

## Predicate (checker.py, from simulator state)
Ordered stages: unfolded (fold <= 0.1 pi, every leg >= 90 deg) -> standing (also tilt <= 10 deg, all four feet on the
counter, no other rack part on it) -> released hold (also no hand contact, rack speeds <= 0.02 m/s and 0.2 rad/s,
50 consecutive controls). Fail-fast every 2 ms substep: rack part below the counter top, off the counter footprint or
> 0.9 m above it; rack touching floor/cabinet; dropped (no counter and no hand contact while the rack COM falls faster
than 0.2 m/s, no debounce); after standing: tilt > 20 deg or any hinge leaving its open range; unstable physics;
6000-control budget.

## Authoring trajectory (tools/)
`tools/gen_oracle.py --params tools/oracle_params.json --out solution/trajectory.npz` regenerates the Sharpa rows
deterministically (rows quantized to float32 while generating, so a float32 client cannot change them):
1. thumb-index pinch on the top half's end-corner housing, 180 deg swing about the pole hinge (pinch acts as a pin);
2. for each leg a low thumb-index pinch (`pinch_low.json`, searched so that the fingertips reach a tube 11 mm above the
   counter with every other hand geom clear of it) rotates the leg about its pivot onto the 100 deg stop;
3. pin-pinch on the hinge collar in the middle of one side rim; the open rack is rotated about the opposite side rim
   over vertical (the wrist co-rotates late so the rims do not sweep into the hand), follows the pivot onto the near
   feet and is lowered level onto the far feet;
4. open, lift away, hold. The flip parameters (`oracle_params.json`) came from a physics-shooting search
   (snapshot/restore) over the flip waypoints with the strict checker as the objective.
`tools/negatives.py` builds nop / truncated / mid-flip drop / knock-off trajectories; `tools/preview.py` renders a
1280x720 preview (CPU Mesa EGL works: `MUJOCO_GL=egl __EGL_VENDOR_LIBRARY_FILENAMES=/usr/share/glvnd/egl_vendor.d/50_mesa.json`).

## Evidence commands (from this folder; outside the image set DEXHAND_ASSET_DIR / WUJI_ASSET_DIR)
```bash
python tools/gen_oracle.py --params tools/oracle_params.json --out solution/trajectory.npz   # regenerate the oracle
python replay.py --task drying_rack_unfold --traj solution/trajectory.npz --out out/r1.json  # twice: identical state_sha
python -m unittest tests/test_drying_rack_unfold.py                                          # 20 authoring tests
python tools/negatives.py --oracle solution/trajectory.npz --outdir out/neg                   # nop / truncated / drop / knock-off
python tools/presentation.py export --trajectory solution/trajectory.npz --export out/film   # exact poses, every 4 controls
blender -b -P tools/studio_renderer.py -- --export out/film --output out/film.mp4 --samples 16 --frame-step 2
python tools/presentation.py encode --export out/film --output out/film.mp4
```
Measured: one privileged replay of the oracle takes about 10 s of CPU (2,315 controls); `replay_sec`/`video_sec` in
`family.json` leave large margins for the image's software renderer.
