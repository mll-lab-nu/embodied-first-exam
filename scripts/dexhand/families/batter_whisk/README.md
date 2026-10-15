# batter_whisk (authoring notes)

DexHand plugin family built from scene-expansion T49 "Hold a bowl and whisk batter" (a kinematic demo: prescribed
whisk motion and advected batter). Here the whisk moves only through contact with dexterous hands on the Tianji Marvin
two-arm rig (`scripts/dexhand/shared/arm_rig.py`, robot `marvin-bimanual-sharpa-wave`); the verdict is computed from
simulator state by `checker.py`. Wave 3 (2026-10-15): the whisk now starts at rest on the bowl rim (picked up in the
episode) and the second arm/hand is present and steadies the bowl during the pickup.

## Files

| file | role |
|---|---|
| `scene.py` | MJCF builder: counter, free bowl (+ lumped batter mass), free whisk, Marvin stand + two arms + two hands (`arm_rig.mount_marvin`, Wuji via `hands.replace_wave_hands`); legacy wrist stage when `task.json` has no `rig` |
| `checker.py` | ordered stages, terminal hold and fail-fast list (numbers in `task.json` `predicate`) |
| `runtime.py` | `Session` (FAMILY_PLUGIN section 4) incl. `snapshot()` / `restore()` |
| `replay.py` | fresh-process replay CLI (section 5), optional `--video` |
| `task.json` | frozen instance: geometry, cameras, predicate, rig (`rig`, `marvin.base_pos`, `floor_z`), per-hand frozen reset (`reset_state`) |
| `assets/` | original T49 bowl / whisk-wire meshes (look only) + `manifest.json` (sha256) |
| `tools/make_reset_arm.py` | authoring: arms in a ready pose (IK), whisk released from the source pose and settled; freezes it into `task.json` |
| `tools/author_arm.py`, `tools/armlib.py` | authoring: closed-loop two-arm controller (IK via `shared/arm_ik.py`), saves the executed float32 rows |
| `tools/sweep.py` | authoring: parameter sweeps of `author_arm.py` phases in one process |
| `tools/make_reset.py`, `tools/author_oracle.py` | wave-2 floating-stage tools (legacy rig only) |

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
- Start state (wave 3): the source starts with the whisk standing in the bowl (wire tip 9 mm above the bowl origin).
  Without a hand that pose is not statically stable (the handle side is heavier), so `tools/make_reset_arm.py` releases
  the whisk from it, tilted 3 deg toward azimuth -pi/2-0.35 (toward the robot's right), and lets the scene integrate
  3 s with both arms in a ready pose: the whisk comes to rest leaning on the bowl rim with its handle end on the counter.
  That settled state (zero velocities) is frozen per hand in `reset_state`; episodes start from it with no state writes.
- Stage 1 `picked_up` (new): robot contact, no counter/bowl contact, lowest point >= 30 mm above the counter for
  10 controls. Before it the whisk may be nudged (no drop rule, no "knocked" rule); counter/floor/workspace rules apply.
- Robot: Tianji Marvin stand at the origin facing +x (`base_z = floor_z + 0.1`, floor at z = -0.1), both arms and both
  hands active. The counter top keeps its source height (0.68 m) and position; the decorative cabinet under it starts
  behind the stand's base plate (x >= 0.77 m) so that no robot geom overlaps furniture. "Hand" contact in the checker
  means any robot body (hands, arm links, stand).
- Second hand: the source's bowl-holding hand is the left arm. The reference solution hooks the left fingertips over
  the near-left rim and steadies the bowl while the right hand lifts the whisk off the rim (without it the pickup
  drags the bowl > 30 mm), then lets go and withdraws before whisking: fingers over the rim of this 12 cm bowl sit
  inside the balloon whisk's volume (holding through the whisking was tried and the whisk struck the fingers in every
  variant). The predicate therefore does not require a hold.
- Verdict details (L1-L3 of the wave-2 lessons): a drop fails at the first control at which the whisk touches nothing,
  is not resting within 2 mm of the counter and its COM falls faster than 0.2 m/s (no drop-and-catch window);
  speeds come from `mj_objectVelocity(mjOBJ_BODY, ..., 0)` (COM velocity, checked against a finite difference of
  `xipos`); `state_sha` hashes the integration state, the verdict state, the hand and only the physics/predicate
  entries of `task.json` (`runtime.PHYSICS_KEYS`), never the instruction text or cameras.
- Authoring controller (`tools/author_arm.py`): every control the IK targets are computed from measured state (whisk
  pose, hand pose; damped least squares with a joint integral, `shared/arm_ik.py`), rows rounded to float32 before they
  are executed (a float32 round trip of the archive is lossless). Phases: left hook over the rim, right palm-down grasp
  of the handle (index toward the head), squeeze, lift, left lets go, turn the measured whisk axis upright beside the
  bowl, over the bowl, closed-loop head orbit (16 mm, 0.6 Hz) until five revolutions, lift and drain, carry and turn
  (whisk axis (-0.857, -0.514, -0.10)), lower until counter contact, open, withdraw.

## Provenance

Scene expansion T49 "Hold a bowl and whisk batter" (local authoring folder `scripts/scene_expansion/tasks/batter_mix`,
approved kinematic film of the scene review; composed hand+scene model `scripts/hand_support/tasks/T49/model.xml`). Reused: counter height and extent, bowl pose, the Roesle bowl
profile/mass and whisk loop law/handle/mass (`meta_delivery/geometry.py`), the original authored OBJ meshes
(`assets/`, sha256 in `assets/manifest.json`; the trimesh export header comment was stripped) and, for the film, the
studio materials, lights, exposure and camera language of `trajectory_r1/studio_render.py`. Replaced: prescribed
whisk motion and advected batter by a dexterous hand that moves the free whisk through contact, and a state-only
verdict. Omitted: the second (bowl-holding) hand, SPH/advected batter and the draining strand.

## Evidence commands

```bash
cd scripts/dexhand/families/batter_whisk
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1; ulimit -c 0
# assets: DEXHAND_ASSET_DIR / WUJI_ASSET_DIR / DEXHAND_TIANJI_DIR (or the prepared images/dexhand/assets of a checkout)
python -m unittest tests/test_batter_whisk.py -v
python tools/make_reset_arm.py --hand sharpa --write      # only when the scene changes (also --hand wuji)
python tools/author_arm.py --hand sharpa --out solution/trajectory.npz --slack 100
python replay.py --task batter_whisk --traj solution/trajectory.npz --out out/r1.json   # twice, fresh processes
```

Authoring-only files (never copied into a task): `tools/`, `tests/`, `presentation.py`, `studio_renderer.py`, this
README. Runtime shared file: `arm_rig.py` (`family.json` `runtime.shared`).
