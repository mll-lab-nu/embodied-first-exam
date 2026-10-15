# grinder_crank (authoring notes)

DexHand family for scene T15 "Operate a manual coffee grinder". The source scene
(`scripts/scene_expansion/repairs/sharpa_grinder/meta_delivery_trajectory_r1`) is a kinematic demo: the grinder pose
and crank angle were prescribed. This family makes it a physical two-hand task.

## Scene and modelling choices

- Grinder: the unchanged source `mechanism.py` (copied byte-identical to `assets/source/hario_mechanism.py`, sha256 in
  `assets/manifest.json`, checked at import) builds the HARIO MSS-1DTB-style mill: free body (0.325 kg body + 0.050 kg
  crank + 0.025 kg knob = 0.40 kg), lathe-mesh visuals, hidden contact cylinders, passive `crank_rotation` hinge
  (frictionloss 0.08 N m, damping 0.012 N m s/rad) and passive `knob_spin` bearing. Position as in the source scene:
  base centre (0.45, 0, 0.70) on the counter (box top z = 0.70, friction 0.35, four legs).
- Task overrides (all in `task.json` / `scene.py`, documented in the instruction): crank armature 2e-4 and knob
  armature 1e-5 (numerical stability at 2 ms); knob friction 1.0 (rubber-like resin, condim 4); internal steel shaft
  and inner burr excluded from contact (they sit inside the closed body); `multiccd` so the base disk rests on the
  counter with several contact points (without it the base had one contact point and the mill spun on it); decorative
  visual-only steel band and lid ring (no mass/contact). The source's 384-piece convex cup refinement is not used
  (the cup keeps the source's single contact cylinder).
- Why two hands: with the source load the free-standing 0.40 kg mill tips over when the knob is pushed with 0.5 N
  (measured with an authoring probe script, not kept in the repository), and the base friction torque
  cannot resist the 0.08 N m crank friction. A person counterholds the body with the other hand; so does this task.
- Rig: two hands of the selected model on two six-axis wrist stages (same joints/gains/ranges as `assemble_hamburger`,
  slide ranges x [0, 0.9], y [-0.5, 0.5], z [0.70, 1.40] m, so slide targets are world coordinates of the wrist root).
  Sharpa: the genuine right Wave and the declared y-reflection of it as the left hand (the convention of the accepted
  bimanual families). Wuji: `hands.replace_wave_hands` swaps both for the genuine right and left Wuji Hand 2.2 (mount
  checked: flexing an index MCP moves the fingertip the same way as the Wave's, both sides). Actuator order: right
  wrist (6), left wrist (6), right fingers, left fingers. Widths 56 / 52.
- Grinding is summarised by the crank angle (no beans or grounds).

## Verdict (`checker.py`)

Stage 1: unwrapped crank hinge angle relative to the body >= 720 deg net clockwise (from above). Stage 2: with
stage 1 still true, no hand-grinder contact (either hand, any grinder geom), base touching the counter, tilt <= 10 deg,
linear speed <= 0.02 m/s, angular speed <= 0.2 rad/s, crank speed <= 0.5 rad/s for 50 consecutive controls. Fail-fast
after every substep: tilt > 10 deg, base slide > 2 cm, lift > 2 cm, base below the counter top - 5 mm, body yaw > 45 deg,
crank < -90 deg (net counter-clockwise), bad qpos/qvel/qacc; budget 3000 controls.

## Oracle (phase A)

`tools/make_oracle.py` regenerates `solution/trajectory.npz` deterministically: `tools/author.py` is a closed-loop
scripted controller (reads simulator state only to choose motor targets): left hand preshapes, approaches the cup from
+x+y and wraps it (thumb on the +x side, fingers around -x/-y); right hand pinches the knob bulb from above (thumb vs
index/middle) and its wrist follows the knob circle clockwise with a bounded lead; then the pinch opens, the right hand
lifts, the left fingers open, and the left hand withdraws along +x then +y. Parameters (`tools/oracle_params.json`)
came from CEM searches (`tools/search_pinch.py`: pinch geometry scored by crank progress; `tools/search_episode.py`:
left grasp + crank rate scored on the full episode). 100 hold rows are appended after success (slack).
`tools/negatives.py` builds the negative/robustness variants.

Wuji Hand 2.2: `solution/wuji/trajectory.npz` (1,005 rows, success after 905) comes from the same controller with Wuji
parameters (`tools/oracle_params_wuji.json`, from `tools/search_wuji.py` run in the modes left -> pinch -> full;
`tools/rig.py` aliases the Sharpa-style finger keys to the Wuji actuators); regenerate with
`tools/make_oracle.py --hand wuji --out solution/wuji/trajectory.npz`. Both trajectories replay deterministically in
fresh processes and succeed with float32-rounded rows.

`state_sha` hashes the integration state, the verdict state, the step count, the hand and only the physics/predicate
keys of `task.json` (`runtime.PHYSICS_KEYS`), so text edits never change evidence hashes. Speeds in the hold
predicate are `mj_objectVelocity(mjOBJ_BODY)`, i.e. at the grinder's centre of mass.

## Evidence

Evidence lives in the authoring workspace, outside the repository (status.json, replay JSONs, negatives, videos, frames).

## Evidence commands

From this folder, with `DEXHAND_ASSET_DIR` pointing at the Sharpa Wave assets (`images/dexhand/assets/hand`; the Wuji
assets are found next to it) and MuJoCo 3.4.0:

```bash
python replay.py --task grinder_crank --traj solution/trajectory.npz --out r1.json        # twice: identical state_sha
python replay.py --task grinder_crank --traj solution/wuji/trajectory.npz --out w1.json   # Wuji Hand 2.2
python tools/make_oracle.py                         # regenerates solution/trajectory.npz byte for byte
python tools/make_oracle.py --hand wuji --out solution/wuji/trajectory.npz
python tools/negatives.py OUT_DIR                   # nop, truncations, knock-over, counterhold release, reversed, 1.5 turns
python -m pytest -q tests/test_grinder_crank.py     # authoring tests
python presentation.py export --trajectory solution/trajectory.npz --export FILM --stride 4
python presentation.py verify --trajectory solution/trajectory.npz --export FILM
blender -b --factory-startup -P studio_renderer.py -- --export FILM --output film.mp4 --samples 16 \
    --camera 0.92 -0.62 1.20 --target 0.43 -0.02 0.92 --lens 38
python presentation.py encode --export FILM --output film.mp4
```

The PR film is a Blender 4.5.3 Cycles render of the exported native poses (every 4th control, played at 2x), with the
T15 film's grinder finishes, background and exposure; poses are never interpolated.

## Disclosures

- The left Sharpa Wave is the declared y-reflection of the genuine right model (as in the accepted bimanual
  families), not a separate manufacturer asset; the Wuji rig uses the manufacturer's left and right models.
- Grinding is summarised by the crank angle (2 turns); no beans, fracture or grounds are simulated. The grinding load
  is the source scene's passive hinge friction (0.08 N m dry friction, 0.012 N m s/rad damping).
- Two hands are required by the physics of the free-standing 0.40 kg mill (see "Why two hands").
