# usb_plug_insert (scene T24, "Connect a USB cable to a held device")

Authoring notes for the DexHand plugin family. Source scene (read-only): main checkout
`robot_coding_bench/scripts/scene_expansion/repairs/usb_cable_meta_delivery_trajectory_r1` (kinematic demo: object
motion prescribed, no hands). This family turns it into a physical task: one dexterous hand (Sharpa Wave default,
Wuji Hand 2.2 selectable) on the six-axis wrist stage must pick up the USB-A plug, turn it polarity-up, insert it into
port 4 of the four-port hub and release it seated.

## Files
| file | role |
|---|---|
| `scene.py` | MJCF builder: Sharpa right hand (or Wuji via `hands.replace_wave_hands`) on the wrist stage, desk, hub, plug, cable |
| `checker.py` | ordered stages, terminal hold and fail-fast checks, from simulator state only |
| `runtime.py` | `Session` (FAMILY_PLUGIN section 4, plus `snapshot`/`restore`) |
| `replay.py` | fresh-process replay CLI (FAMILY_PLUGIN section 5) |
| `task.json` | frozen instance: poses, wrist stage, initial targets, cameras, checker thresholds, task text |
| `assets/usb_scene.json` | source-derived dimensions, masses and PBR materials; `assets/manifest.json` pins its sha256 |
| `demo.py` | authoring only: closed-loop scripted controller that records the Sharpa rows |

## Modelling choices (all physical; nothing attaches or drives an object)
- Geometry and materials follow the source (`mechanism.py`): hub case 103 x 30 x 10 mm, 21.8 g, four port apertures at
  hub-local x = -27, -7, 13, 33 mm; USB-A plug 7 g (12 x 4.5 x 12 mm metal shell, 15 x 20 x 8 mm housing, strain
  relief), 0.5 m cable 15 g with EI = 2e-5 N m^2 and a USB-B far end. The source has no meshes or textures.
- Layout change: the hub rests free on the desk with its port face flush with the desk's front edge (one hand; the
  "held device" is not held by a second hand). With the hub on the desk the port centre is only 5.6 mm above the
  desk, less than the radius of the Sharpa/Wuji fingertips (8-9 mm), so a fingertip grasp can only insert from beyond
  the desk edge. For the same reason the plug starts lying on its side (15 mm tall), so it can be pinched from the desk.
- Ports: open box cavities 12.5 x 4.8 x 12 mm for the 12.0 x 4.5 x 12 mm shell (0.25 mm clearance per side across,
  0.15 mm in height; the real connector has ~0.1 mm). The plug shell collides as one solid box; the receptacle tongue,
  the plug's polarized insert, the metal receptacle shell and the gold contacts are visual (polarity is checked by the
  predicate instead). Fit surfaces use a stiffer impedance (`solimp 0.99 0.999 0.0001`). Retention leaf springs are
  omitted (with a 21.8 g hub on the desk, a ~10 N retention would push the hub away); the seated plug is held by
  friction and its own weight, and the seat check requires >= 90% depth.
- The plug cable is a passive 20-link ball-joint rod lying on the desk; the hub's own upstream cable is a visual
  rigidly attached to the hub (lies on the desk; no physics).
- Grip surfaces of the plug housing use friction (1.0, 0.01, 0.0002): the torsional term is that of a ~1 cm soft pad
  patch; without it a two-point pinch spins the plug about the pinch axis under the cable's pull.
- Wrist stage: world-axis slides `wrist_x/y/z` (ranges x 0.2-1.1, y -0.45-0.55, z 0.55-1.30 m), then serial X-Y-Z hinges
  (+-3.14 rad) inside `wrist_gimbal`, whose fixed orientation (quat in `task.json`) keeps the task's hand orientations
  within about +-1 rad, away from the serial-XYZ singularity. Gains as `assemble_hamburger`.

## Predicate (checker.py, numbers in task.json `checker`)
1. Lifted: thumb + another finger on the rigid plug, the rigid plug touches nothing else, plug origin z >= 0.73 m.
2. Seated in port 4 (`target_port` 3, zero-based): tip depth >= 10.8 mm (90% of 12), |lateral| <= 0.6 mm,
   |vertical| <= 0.5 mm, plug/port axis angle < 5 deg, polarity (plug +z vs hub +z) within 20 deg.
3. Released hold: seated, no hand contact on plug, cable or hub, plug speed <= 0.01 m/s, 50 consecutive controls.
Fail-fast: hub displaced > 20 mm or tilted > 20 deg; plug below z = 0.685 m (counter top - 15 mm, the plug legitimately
works 5.6 mm above the top beyond the edge); plug or hub outside the workspace box; cable far end > 5 cm below the desk
top; plug dropped (after stage 1, the first control with no hand contact on plug or cable, not engaged >= 3 mm in a port, and COM vz < -0.2 m/s or resting on desk/floor; no debounce window); unstable
physics; 3000-control budget. A plug seated in another port reports `wrong_port` and never succeeds.

## Reference solution
`solution/trajectory.npz`: 1,134 Sharpa Wave rows (`hand` = `sharpa`, sha256 `081cc971...`); the replay ends at success
after 1,014 controls (the last 120 rows are unexecuted hold slack). Produced by `demo.py` (closed-loop scripted
controller on the simulator state: least-squares fingertip IK for a thumb vs index+middle pinch of the plug lying on its
side, joint-space wrist rotation to polarity-up, rate-limited closed-loop alignment in front of port 4 using the
measured plug-in-hand pose, insertion to 11.8 mm, staged release: relax, index up, wrist 4 mm down so the thumb leaves
the housing along its normal, open, move aside, withdraw). It computes motor targets only. Both modes use the same rows
(the standard oracle submits them through `rcb_client`). No Wuji solution is packaged (Wuji loads, nop scores 0);
`demo.py --params '{"hand": "wuji"}'` has an untuned Wuji port (mesh-fingertip IK) that does not succeed yet.
`demo.py` with default parameters reproduces the Sharpa rows bit for bit (checked 2026-10-15).

## Evidence
Authoring evidence (kept outside the repository: status.json, evidence/*.json replays and
negatives, harbor/ trials on snapshot copies, videos/, frames/, film/). Reproduce:

```bash
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 DEXHAND_ASSET_DIR=$PWD/images/dexhand/assets/hand; ulimit -c 0
F=scripts/dexhand/families/usb_plug_insert
python $F/demo.py --out $OUT/oracle.npz                         # rows up to success + 60 hold rows (about 70 s)
python $F/replay.py --task usb_plug_insert --traj $F/solution/trajectory.npz --out $OUT/r1.json   # about 35 s
python $F/replay.py --task usb_plug_insert --traj $F/solution/trajectory.npz --out $OUT/r2.json   # identical state_sha
python $F/replay.py --task usb_plug_insert --traj $F/solution/trajectory.npz --video $OUT/replay.mp4 --camera closeup
python -m pytest -q $F/tests                                     # 13 tests, about 4 minutes
python scripts/dexhand/generate.py --only-family usb_plug_insert
```

Results (2026-10-14): two fresh replays succeed at control 1,014 with state_sha `5d0414a6...`; float32 rows succeed;
nop, truncation (stage 1 / stage 2), one row short of the hold, drop (fail-fast `plug_dropped` 2 controls after the
fingers open), drop-then-resume, hub knock (`hub_displaced`), wrong width/hand label/task, NaN, out-of-range targets
and a raw `actions` member are rejected or fail; a forged `success` member is ignored. Harbor 0.23 on snapshot copies
(eai-dexhand:0.2.0): privileged oracle 1 / nop 0, standard oracle 1 / nop 0 (live = replay hash), Wuji nop 0 in both
modes. Measured wall: privileged oracle trial 1.3 min, standard oracle trial 5.7 min.

## Studio film (authoring only)
`presentation.py` exports every visible native geom transform (every 4th control) from a passing replay, `verify`
re-runs the physics and checks every sample and the final hash, `render` runs `studio_renderer.py` in Blender 4.5.3
(materials, AgX exposure and soft area lights of the approved T24 scene film; hand surfaces of the hamburger film; a
wide shot, then a cut to the port close-up when the plug is carried in front of the desk edge), `encode` adds the
caption (task, hand, "physics replay, 2x") and writes H.264. No pose is synthesized or interpolated.

```bash
BLENDER=/path/to/blender-4.5.3/blender python $F/presentation.py export --trajectory $F/solution/trajectory.npz --export $OUT/film
python $F/presentation.py verify --trajectory $F/solution/trajectory.npz --export $OUT/film
BLENDER=... python $F/presentation.py render --export $OUT/film --output $OUT/usb_plug_insert.mp4 --engine eevee
```
