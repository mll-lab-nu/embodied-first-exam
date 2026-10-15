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
- Robot (wave 3; wave 2 used two six-axis wrist stages): the shared `arm_rig.mount_marvin` Tianji Marvin stand (two
  7-joint arms, kp 700 / kv 48, force limits 108/108/66/66/18/18/18 N m, the accepted pot_shelf_transfer robot) at base
  (-0.085, 0, 0) facing +x behind the counter, both arms active: the stand stands on the floor (floor_z = -0.1 = base_z -
  0.1, the rig convention) and its 0.79 m base plate ends 1 cm before the counter's front legs (x = 0.318 m). The base was
  chosen by per-pose multi-seed IK over the old episode's hand poses (every pose reachable, < 1 mm); an earlier
  placement (-0.05, 0, -0.15) also worked but sank the plate 15 cm into the floor and touched the front legs (exact
  stand/furniture check). Sharpa:
  the genuine right Wave on the right flange and its declared y-mirror on the left (arm_rig, as before); Wuji:
  `hands.replace_wave_hands`. Flange mount bodies `right_wrist_stage` / `left_wrist_stage` (hand roots; checker
  lookups unchanged). Any contact of an arm/stand link with anything is the fail-fast `robot_collision`. Actuator order:
  left arm (7), right arm (7), left fingers, right fingers (58 / 54).
- Counterhold rotated for the arm: the wave-2 left grasp approached the cup from the far side (+x+y) and is out of the
  left arm's reach (150-230 mm); the arm oracle uses the same grasp rotated by 90 deg about the cup's vertical axis
  (`tools/author.py` `l_rot`; the cup is rotationally symmetric), i.e. from the robot's left side. The rotated grasp
  also succeeds on the old floating rig (authoring check).
- Grinding is summarised by the crank angle (no beans or grounds).

## Verdict (`checker.py`)

Stage 1: unwrapped crank hinge angle relative to the body >= 720 deg net clockwise (from above). Stage 2: with
stage 1 still true, no hand-grinder contact (either hand, any grinder geom), base touching the counter, tilt <= 10 deg,
linear speed <= 0.02 m/s, angular speed <= 0.2 rad/s, crank speed <= 0.5 rad/s for 50 consecutive controls. Fail-fast
after every substep: tilt > 10 deg, base slide > 2 cm, lift > 2 cm, base below the counter top - 5 mm, body yaw > 45 deg,
crank < -90 deg (net counter-clockwise), bad qpos/qvel/qacc; budget 3000 controls.

## Oracle (wave 3, arms)

`tools/arm_author.py` records `solution/trajectory.npz`: it runs the wave-2 closed-loop scripted controller
`tools/author.py` (reads simulator state only to choose targets; parameters `tools/oracle_params.json` from the wave-2
CEM searches `tools/search_pinch.py` / `tools/search_episode.py`) with the left grasp rotated by 90 deg (`l_rot`) through
`tools/arm_port.py` `StageProxy`: every old wrist-stage command becomes a hand-root pose by kinematics of the old
floating scene (`tools/floating_scene.py` + `tools/floating_task.json`, authoring-only copies), then Marvin damped-least-
squares IK with a gravity feed-forward gives the 14 arm joint targets; finger targets are copied by name. The left hand
preshapes, approaches the cup from the robot's left and wraps it; the right hand pinches the knob bulb from above and
its wrist follows the knob circle clockwise with a bounded lead; then the pinch opens, the right hand lifts, the left
fingers open, and the left hand withdraws. 100 hold rows are appended after success (slack). The wave-2 floating-stage
scripts (`tools/make_oracle.py`, `tools/negatives.py`, `tools/search_*.py`) are kept for provenance only; there is no
Wuji oracle on the arms (optional; the wave-2 `solution/wuji` was removed).

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
python tools/arm_author.py --init                   # IK start pose of both arms -> task.json initial_targets
python tools/arm_author.py --out solution/trajectory.npz   # the arm oracle: 1,096 rows, success at 996
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
