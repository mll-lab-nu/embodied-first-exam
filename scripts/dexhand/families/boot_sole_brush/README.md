# boot_sole_brush (authoring notes)

Physical DexHand version of scene T29 "Brush adhered debris from a shoe sole" (source, read-only:
`scripts/scene_expansion/repairs/shoe_brush_meta_delivery_trajectory_r1`, a kinematic demonstration in which no hand
acted and debris motion was prescribed). Here the right arm of the Tianji Marvin two-arm robot (stand on the floor
beside the counter, left arm parked) with a dexterous hand (Sharpa Wave by default, Wuji Hand 2.2 selectable) picks up
the brush and brushes six free clods off the boot sole into the tray, in physics. Wave 3 moved the hand from the
wave-2 floating six-axis wrist stage onto the arm; the scene and the predicate are the wave-2 ones, plus the
`robot_collision` fail-fast.

## Files

| file | role |
|---|---|
| `scene.py` | MJCF builder (Marvin arm rig from the shared `arm_rig.py`, counter, tray, rack, boot, clods, brush, cameras) |
| `checker.py` | fail-fast + ordered stages + terminal hold, simulator state only |
| `runtime.py` | `Session` (FAMILY_PLUGIN section 4, plus `snapshot`/`restore`) |
| `replay.py` | fresh-process replay CLI (FAMILY_PLUGIN section 5), `--video` evidence |
| `task.json` | frozen instance: geometry, clod poses, predicate thresholds, start targets, cameras, task text |
| `assets/` | boot mesh/texture/292 contact hulls from scene T29 + `manifest.json` (sha256, checked at build) |
| `solution/trajectory.npz` | Sharpa Wave witness on the arm (1,688 rows of 58 targets; success at control 1,538) |
| `tools/arm_port.py` | authoring: records the wave-2 floating-hand episode's hand-root poses (`poses`, run on the wave-2 family code) and tracks them with the right arm (`author`, `arm_ik.track`); `replay` re-checks in a fresh process |
| `tools/author_oracle.py` | wave-2 authoring controller (floating wrist stage; runs only on the wave-2 family code, commit b686803d4) that recorded the episode `arm_port.py` tracks |
| `tools/author_layout.py`, `tools/probe_*.py` | clod placement by raycast on the sole hulls; geometry probes |
| `tests/test_boot_sole_brush.py` | oracle x2 identical + slack, float32, no robot contacts, nop, truncations (stage 1, one row short of the hold), drop then resume, release-in-air-and-catch, hand-clod contact (arm IK), arm folded into the torso (`robot_collision`), forged members, wrong width, NaN / out-of-range rows, prose-independent state hash, Wuji composes + nop + deterministic |

## Task and predicate

The exact text is `task.json` `instruction`. Stages (in order): (1) bristle pad on the boot while the hand holds the
brush off the counter, >= 10 controls; (2) every clod touched by the bristle pad (not the wooden back) while still up on the
boot (centre at most 0.01 m below the sole plane) and every clod inside the tray walls below the wall top; (3) 50 consecutive controls with all clods in the tray at rest
(<= 0.05 m/s), the brush touching neither boot nor clods and withdrawn (pad >= 0.04 m above the sole plane or
>= 0.18 m horizontally from the sole centre) -> success (episode ends). Fail-fast after every 2 ms substep: boot moved
> 0.03 m or tilted > 0.35 rad; a clod touching counter/floor, below the counter top or outside the workspace box; any
hand geometry touching a clod; the brush touching floor/tray/rack, below the counter top or outside the box, or
released in the air (no contact except clods while its centre of mass sinks faster than 0.2 m/s: no drop-and-catch
window); any contact of a robot part other than the right hand (stand, torso, arm links and flanges of either arm,
the parked left hand) with anything (`robot_collision`); unstable physics; 3,000-control budget. `state_sha` hashes the integration state, the predicate state, the
hand and the physics/predicate parameters of `task.json` (prose and camera keys excluded), so text edits never change
evidence hashes. Clod speeds use `mj_objectVelocity(..., mjOBJ_BODY, ...)` (COM velocity; checked against a finite
difference of `xipos`).

## Modelling choices (all passive; only robot actuator targets act)

- **Rig**: the Tianji Marvin robot of `pot_shelf_transfer` (shared `arm_rig.py`, robot id
  `marvin-bimanual-sharpa-wave`; stand, torso, two 7-DoF arms with position servos kp 700 / kv 48, no gravity
  compensation, a Sharpa Wave on each flange; `hand="wuji"` swaps both for Wuji Hand 2.2). Base origin at world
  (0.147, -0.591, 0.10), yaw +90 deg (facing +y), so the stand's plate rests on the floor (z = 0) beside the counter's
  -y edge and the right shoulder sits at (0.369, -0.591, 1.221). The working hand hangs under the fixed mount body
  `wrist_stage` on the right flange (the checker's hand root, unchanged); the left arm stays at `arm_rig.PARK`.
  Placement: from `arm/tools/place_base.py` (reach 1.0 for the wave-2 hand path), verified with an exact
  robot-vs-furniture check (`mj_geomDistance` on every robot collision geom and a vertex test of every robot visual
  mesh against the counter, tray, rack and floor at reset and every 5 controls of the oracle: no interpenetration; the
  counter is a slab without legs, the stand stays outside its footprint).
- **Boot**: free 0.65 kg rigid body with the source inertia; visual = the source OBJ + diffuse texture (source UVs, the same mapping as the approved T29 film); contact with hand, brush and clods = the source scene's 292 convex hulls of
  boot surface patches. It is slipped sole-up onto a fixed square boot-rack peg in the tray. The peg touches only an
  invisible interior proxy of the boot (a footbed pad at the inner sole, measured by raycast at local z = 0.062 m, and
  a square shaft sleeve with 0.5 mm clearance; contype/conaffinity bit 2), because the visual mesh has no lining.
- **Clods**: six free 1 g bodies with the source's seeded irregular aggregate meshes, friction 0.8 (condim 6) on the
  sole. They rest in the tread by gravity and friction. The source scene's cohesive Kelvin-Voigt bond law acted
  through `xfrc_applied` (forbidden object forces) and is not used. The clods sit on the flat forefoot and heel tread
  (|local x| = 0.025 m; the demo had two clods in the arch dip that a rigid brush cannot reach); `tools/author_layout.py`
  places them by raycast; the frozen reset lets everything settle for 250 physics steps (0.5 s, deterministic).
- **Brush**: source outline (14 cm beech back), 84 g, 32 tufts drawn with five fine fibres each. All bristle contact
  goes through one compliant box pad (solref 0.006) that covers the tuft field: the source's 1 mm tuft capsules leave
  12 mm channels that let clods pass between tufts; individual fibre bending is not simulated.
- **Tray**: the source tray footprint (0.34 x 0.58 m), centred under the boot, walls raised to 45 mm, a 12 mm
  rubber-lined floor with soft, well-damped contact (solref 0.006, dampratio 1.2, condim 6). A rigid floor made 1 g
  clods that drop 0.4 m bounce out or tunnel to the counter.
- **Physics**: dt 2 ms, implicitfast, elliptic cones, impratio 10, `multiccd` (stable resting contacts of the clod
  and peg polyhedra), 50 Hz control with 10 substeps.
- **Simplifications against the demo**: the hand does not lift, reorient and set down the boot (the rack holds it
  sole-up); the brush is not put back; the soil is loose rather than cohesively bonded; two clods moved out of the arch.

## Reference witness (Sharpa Wave on the arm)

`tools/arm_port.py` replays the accepted wave-2 floating-stage witness (below) on the wave-2 family code and records the
hand-root world pose and the finger targets after every control; the arm session then tracks those poses with
`arm_ik.track` (IK from the measured arm state, joint integral ki 0.25 against servo sag). Branch choice: the
multi-start IK solution at old control 221 (hand lifted above the counter) continued back to the reset pose by
warm-started IK, so the whole episode stays on one branch (the default multi-start at the reset pose flips branch when
the brush is lifted). The brush transfer (old controls 165-345, up to 0.54 m/s) is re-timed 3x slower, because the
arm's acceleration at the original speed let the pinched brush slip (`brush_dropped` at control 320; 2x slower still
dropped it, at control 1,310). Result: success at control 1,538 (tracking error mean 1.8 mm / max 10 mm, 0.002 / 0.03
rad), 150 copies of the last row appended; two fresh replays identical, float32 rows succeed, no arm, stand or parked
hand contact in any physics substep, no robot geom inside the counter, tray, rack or floor.
Harbor 0.23 on the generated task directories (2026-10-15): privileged oracle 1 / nop 0, standard oracle 1 / nop 0
(standard: live = replay, 1,538 steps). Negatives (authoring evidence): nop -> `episode_budget`; truncated at 1,000 rows
and one row short -> no success; fingers opened while carrying -> `brush_dropped` (released in the air, at once); the
hand pressed 6 cm into the sole -> `hand_touched_debris`; the parked left arm folded into the torso, and the right arm
driven down onto the counter (its wrist link meets the brush first) -> `robot_collision`; 28-wide, wrong-hand and forged archives -> `bad_trajectory` /
no success. Sideways and upward pushes of the open hand against the boot did not displace it (shift <= 2 mm, tilt
<= 0.012 rad): the rack peg holds it, so `boot_displaced` keeps its wave-2 validation.

```bash
python tools/arm_port.py poses --hand sharpa --old <wave-2 boot_sole_brush folder> --out poses_sharpa.npz
python tools/arm_port.py author --hand sharpa --poses poses_sharpa.npz --base 0.147 -0.591 0.1 --yaw 90 \
    --seg 165 345 3 --out out/
```

### Wave-2 floating-stage witness (tracked above)

`tools/author_oracle.py --out X.npz` (wave-2 family code only): top-down pinch of the brush back (thumb on the near
long face, index/middle/ring on the far face; IK keeps every hand geom >= 16 mm above the counter so no finger reaches
the clods), lift, then four centre-out strokes: forefoot +y, forefoot -y, heel +y, heel -y (lower until the pad
touches the boot, press 1 mm, sweep 6 cm, lift 3.5 cm), withdraw and hold. The recorded rows plus 150 copies of the
last row formed the wave-2 `solution/trajectory.npz` (sha256 `db1d041f...`): success at control 1,178 on the stage.

## Wuji Hand 2.2 (no arm witness)

Wuji stays selectable (both hands swap to Wuji Hand 2.2; 54 targets per row; it composes, a no-op fails, replays are
deterministic), but there is no Wuji witness on the arm. Tracking the wave-2 Wuji witness's hand poses the same way
(same base, same IK branch, same 3x re-timed transfer) fails with `hand_touched_debris`: a Wuji thumb or middle
fingertip touches a clod at control 780 (808 and 1,266 with every brushing pose lifted by 2 and 3.5 mm). The Wuji
fingertips hang lower beside the pinched brush; in wave 2 only 1 of 8 grasp settings avoided the clods on the stiff
stage, and the arm's few-millimetre compliance under brushing loads removes that margin. The wave-2 floating-stage
Wuji witness (success at control 1,186) is not valid for the arm rig and was removed.

## Evidence commands

```bash
export DEXHAND_ASSET_DIR=<repo>/images/dexhand/assets/hand   # Wuji assets next to it
cd scripts/dexhand/families/boot_sole_brush
python replay.py --task boot_sole_brush --traj solution/trajectory.npz --out out/a.json        # success at 1538
python -m pytest tests -q
```
MuJoCo preview videos: `replay.py --video out.mp4 --camera overview|closeup|side`. The PR film is rendered with
Blender 4.5.3 from an exact pose export of the replay (`tools/film.py`).
