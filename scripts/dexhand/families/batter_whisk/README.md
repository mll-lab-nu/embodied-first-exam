# batter_whisk (authoring notes)

DexHand plugin family built from scene-expansion T49 "Hold a bowl and whisk batter" (a kinematic demo: prescribed
whisk motion and advected batter). Here the whisk moves only through contact with a dexterous hand on the six-axis
wrist stage; the verdict is computed from simulator state by `checker.py`.

## Files

| file | role |
|---|---|
| `scene.py` | MJCF builder: counter, free bowl (+ lumped batter mass), free whisk, Sharpa Wave on the wrist stage; Wuji via `hands.replace_wave_hands` |
| `checker.py` | ordered stages, terminal hold and fail-fast list (numbers in `task.json` `predicate`) |
| `runtime.py` | `Session` (FAMILY_PLUGIN section 4) incl. `snapshot()` / `restore()` |
| `replay.py` | fresh-process replay CLI (section 5), optional `--video` |
| `task.json` | frozen instance: geometry, cameras, predicate, per-hand frozen reset (`reset_state`) |
| `assets/` | original T49 bowl / whisk-wire meshes (look only) + `manifest.json` (sha256) |
| `tools/make_reset.py` | authoring: settles the pre-held grasp and freezes it into `task.json` |
| `tools/author_oracle.py` | authoring: closed-loop scripted wrist controller, saves the executed rows |

## Modelling choices

- Geometry, masses and meshes from the T49 source (`scene_expansion/tasks/batter_mix`): counter top z = 0.68 m,
  Roesle 150672 bowl (233 g, inner profile 29-60 mm radius, 78 mm high), Roesle 950633 whisk (220 g, 8 wire loops,
  23 cm head, 25 mm x 115 mm handle).
- Contact proxies: bowl = 32 x 7 convex wall strips (2.5 mm thick), floor disc, 32 rolled-rim capsules; whisk = handle
  capsule (condim 6, rolling friction 1 mm: stable analytic contact when the whisk lies on the counter), ferrule
  capsule, 8 loops x 16 wire capsules (1.2 mm radius, condim 6). Steel-on-steel friction 0.2, steel/stone 0.4,
  finger pads 1.0-1.5 (Sharpa), vendor values for Wuji.
- Batter (252 g, 240 ml) is not simulated. Its mass is lumped rigidly into the bowl inertia; its surface is a visual
  mesh at the source fill height (35.7 mm above the bowl origin). Whisking is measured as the net unwrapped angle of the
  whisk-head point (20 mm above the wire tip) about the bowl axis while that point is inside the batter volume.
- Single hand: the source's second hand holding the bowl is omitted; the free bowl must not tip (10 deg), slide
  (30 mm) or lift (20 mm).
- Reset: each hand starts from a frozen grasp. `tools/make_reset.py` holds the whisk fixed only while the fingers close
  (authoring), then releases it and lets the hand hold it under gravity for 1.5 s; the resulting joint positions (zero
  velocities) are stored in `task.json` `reset_state[<hand>]`. Episodes start from that state; no welds, pins or state
  writes happen in an episode. The Sharpa grasp (and the Wuji one) were found by a random search + CEM over the handle
  offset and finger targets, scored by the slip under a whisk/lift/turn shake test.
- Verdict details (L1-L3 of the wave-2 lessons): a drop fails at the first control at which the whisk touches nothing,
  is not resting within 2 mm of the counter and its COM falls faster than 0.2 m/s (no drop-and-catch window);
  speeds come from `mj_objectVelocity(mjOBJ_BODY, ..., 0)` (COM velocity, checked against a finite difference of
  `xipos`); `state_sha` hashes the integration state, the verdict state, the hand and only the physics/predicate
  entries of `task.json` (`runtime.PHYSICS_KEYS`), never the instruction text or cameras.
- Authoring controller (`tools/author_oracle.py`): one script for both hands; it reads the whisk-head site and stage
  joints every control. Release: open the hand over 1.2 s, then slide it along the whisk axis off the handle
  (Sharpa toward the handle end, Wuji toward the head end, where its thumb does not hook the handle) and lift it.
- Wrist stage at the world origin: `wrist_x/y/z` are the world position of the grip point (on the handle axis inside
  the closed hand at reset), rotations are serial XYZ about it. Ranges x [0.15, 1.05], y [-0.45, 0.45], z [0.62, 1.50] m,
  rotations +-3.14 rad; gains as in `assemble_hamburger`.

## Provenance

Scene expansion T49 "Hold a bowl and whisk batter" (`scripts/scene_expansion/tasks/batter_mix`, approved kinematic
film `artifacts/scene-expansion-50/evidence/trajectory-r1/T49/root-review/approved-success.mp4`; composed hand+scene
model `scripts/hand_support/tasks/T49/model.xml`). Reused: counter height and extent, bowl pose, the Roesle bowl
profile/mass and whisk loop law/handle/mass (`meta_delivery/geometry.py`), the original authored OBJ meshes
(`assets/`, sha256 in `assets/manifest.json`; the trimesh export header comment was stripped) and, for the film, the
studio materials, lights, exposure and camera language of `trajectory_r1/studio_render.py`. Replaced: prescribed
whisk motion and advected batter by a dexterous hand that moves the free whisk through contact, and a state-only
verdict. Omitted: the second (bowl-holding) hand, SPH/advected batter and the draining strand.

## Evidence commands

```bash
cd scripts/dexhand/families/batter_whisk
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1; ulimit -c 0
# assets: DEXHAND_ASSET_DIR / WUJI_ASSET_DIR (or the prepared images/dexhand/assets of a checkout)
python -m unittest tests/test_batter_whisk.py -v                                  # 16 tests, about 80 s
python tools/make_reset.py --hand sharpa --grasp "$(cat grasp.json)" --write      # only when the scene changes
python tools/author_oracle.py --hand sharpa --out solution/trajectory.npz --slack 100
python tools/author_oracle.py --hand wuji --out solution/wuji/trajectory.npz --slack 100
python replay.py --task batter_whisk --traj solution/trajectory.npz --out out/r1.json   # twice, fresh processes
python replay.py --task batter_whisk --traj solution/trajectory.npz --video out/preview.mp4 --fps 25 --width 1280 --height 720
# PR film (Blender 4.5.3, OptiX): exact native poses every 4 controls (2x), then a 3.5 s camera move on the final state
python presentation.py export --trajectory solution/trajectory.npz --export out/whisk-export
python presentation.py verify --trajectory solution/trajectory.npz --export out/whisk-export
BLENDER=/path/to/blender python presentation.py render --export out/whisk-export --output out/batter_whisk.mp4
```

Grasps used by `make_reset.py` (native finger order): Sharpa `[1.8683, 0.0354, 1.2223, 0.349, 1.5388, 0.6632, 0,
1.1508, 0.7582, 0.6632, 0, 1.1508, 0.7582, 0.6632, 0, 1.1508, 0.7582, 0.1, 0.6632, 0, 1.1508, 0.7582]` with
`stage.grip_in_hand = [0.0421, 0, 0.0669]`; Wuji `[0.1822, 0.4028, 0.2444, 0.5616] + 4 x [1.552, 0, 1.7478, 0.9957]`
with `--offset [-0.0094, 0.0003]`.

Authoring-only files (never copied into a task): `tools/`, `tests/`, `presentation.py`, `studio_renderer.py`, this
README.
