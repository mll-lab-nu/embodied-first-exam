# usb_plug_insert (scene T24, "Connect a USB cable to a held device")

Authoring notes for the DexHand plugin family. Source scene (read-only): main checkout
`robot_coding_bench/scripts/scene_expansion/repairs/usb_cable_meta_delivery_trajectory_r1` (kinematic demo: object
motion prescribed, no hands). This family turns it into a physical task: one dexterous hand (Sharpa Wave default,
Wuji Hand 2.2 selectable) on the right arm of a Tianji Marvin robot (left arm parked) must pick up the USB-A plug, turn it polarity-up, insert it into
port 4 of the four-port hub and release it seated.

## Files
| file | role |
|---|---|
| `scene.py` | MJCF builder: Marvin stand + two 7-DoF arms (`arm_rig.mount_marvin`), Sharpa hands (or Wuji), desk, hub, plug, cable |
| `checker.py` | ordered stages, terminal hold and fail-fast checks, from simulator state only |
| `runtime.py` | `Session` (FAMILY_PLUGIN section 4, plus `snapshot`/`restore`) |
| `replay.py` | fresh-process replay CLI (FAMILY_PLUGIN section 5) |
| `task.json` | frozen instance: poses, Marvin base pose (`rig`, `marvin`), floor, desk legs, initial targets, cameras, checker thresholds, task text |
| `assets/usb_scene.json` | source-derived dimensions, masses and PBR materials; `assets/manifest.json` pins its sha256 |
| `tools/arm_author.py` | authoring only: re-authors the wave-2 floating-stage episode on the arm (pose tracking, planned IK-branch change, closed-loop insertion, release); `tools/reference/floating_oracle.npz` holds its inputs; `tools/peek.py` renders debug contact sheets |

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
- Robot (wave 3): the shared Marvin rig (`arm_rig.py`, pot_shelf_transfer's frozen robot: kp 700 / kv 48, no gravity
  compensation), right arm active, left arm parked (`arm_rig.PARK`). Base on the floor at (0.93, -0.52), yaw 135 deg,
  in front of the desk and right of the hub. Layout changes for the arm, disclosed in the instructions: (1) the floor
  (and the stand on it) is 0.10 m lower than in wave 2 (floor z -0.20, base z -0.10; desk top unchanged at 0.70, i.e. a
  0.90 m counter): the insertion pose (hand root 5 cm below the desk top, fingers pointing up-forward beyond the edge)
  needs J7 beyond its +-90 deg limit from any base on the old floor (best placement reached 54% of the old hand poses);
  (2) the desk's two front legs (visual only) stand back under the top at (0.32, 0.00) and (1.08, 0.46) so that no
  robot geom (stand plate, column, torso, arms, parked hand) overlaps a leg (exact check, see status). Objects, desk
  top, hub, plug, cable, checker thresholds and the predicate are unchanged.
- Arm collisions: any active contact of an arm link, the stand/torso or the parked left hand with anything fails the
  episode at once (`robot_collision`, checked after every substep); only the working right hand may touch the desk and
  the task objects.

## Predicate (checker.py, numbers in task.json `checker`)
1. Lifted: thumb + another finger on the rigid plug, the rigid plug touches nothing else, plug origin z >= 0.73 m.
2. Seated in port 4 (`target_port` 3, zero-based): tip depth >= 10.8 mm (90% of 12), |lateral| <= 0.6 mm,
   |vertical| <= 0.5 mm, plug/port axis angle < 5 deg, polarity (plug +z vs hub +z) within 20 deg.
3. Released hold: seated, no hand contact on plug, cable or hub, plug speed <= 0.01 m/s, 50 consecutive controls.
Fail-fast: hub displaced > 20 mm or tilted > 20 deg; plug below z = 0.685 m (counter top - 15 mm, the plug legitimately
works 5.6 mm above the top beyond the edge); plug or hub outside the workspace box; cable far end > 5 cm below the desk
top; arm link / stand / parked hand in contact with anything (`robot_collision`); plug dropped (after stage 1, the first control with no hand contact on plug or cable, not engaged >= 3 mm in a port, and COM vz < -0.2 m/s or resting on desk/floor; no debounce window); unstable
physics; 3000-control budget. A plug seated in another port reports `wrong_port` and never succeeds.

## Reference solution
`solution/trajectory.npz`: 1,595 Sharpa Wave rows of 58 targets (`hand` = `sharpa`); the replay ends at success after
1,475 controls (the last 120 rows are unexecuted hold slack). Produced by `tools/arm_author.py` from the wave-2
floating-stage oracle (`tools/reference/floating_oracle.npz`: its rows and its achieved hand-root poses): controls
0-279 track the old hand-root poses with damped-least-squares arm IK and a joint integral (`arm_ik.track` logic; pinch
and lift as before), 280-729 change the arm's IK branch in joint space through a sampled waypoint whose path keeps every
arm link, the stand and the parked hand out of contact (the pick and the under-the-edge insertion lie on different IK
branches), 730-1054 run the old closed loop on the measured plug pose (alignment 10 cm in front of port 4, approach,
insertion to ~11.9 mm), and from 1055 the old release (relax, index up, thumb down, open, move aside, withdraw) replays
at half speed relative to the reached pose, with the middle finger straightened off the hub case before the hand moves
aside. It computes motor targets only. Both modes use the same rows (the standard oracle submits them through
`rcb_client`). No Wuji solution is packaged (Wuji loads, nop scores 0).

## Evidence
Authoring evidence (kept outside the repository: status_arm.json, evidence_arm/*.json replays and negatives, harbor
trials on snapshot copies, film). Reproduce:

```bash
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 DEXHAND_ASSET_DIR=$PWD/images/dexhand/assets/hand; ulimit -c 0
F=scripts/dexhand/families/usb_plug_insert
python $F/tools/arm_author.py --base 0.93 -0.52 -0.1 --yaw 135 --plan --plan-margin 0.01 --n-joint 450 \
    --box-ymin -0.25 --box-zmax 0.95 --release-stretch 2 --straighten-middle-at 900 --out $OUT   # about 60 s
python $F/replay.py --task usb_plug_insert --traj $F/solution/trajectory.npz --out $OUT/r1.json   # about 60 s
python $F/replay.py --task usb_plug_insert --traj $F/solution/trajectory.npz --out $OUT/r2.json   # identical state_sha
python -m pytest -q $F/tests
python scripts/dexhand/generate.py --only-family usb_plug_insert
```

Results (2026-10-15, arm): two fresh replays succeed at control 1,475 with state_sha `c18aa345...`; float32 rows
succeed; zero contacts of arm links, stand or parked hand over the whole oracle (`robot_collision` would end it);
negatives (nop, truncation, one row short, drop, drop-then-resume, knock, arm collision, wrong width/label, forged
success) fail or are rejected; exact stand/furniture check: no overlap at reset or over the oracle. Harbor 0.23 on
snapshot copies: privileged oracle 1 / nop 0, standard oracle 1 / nop 0 (live = replay hash); wall: privileged oracle
1.8 min, standard oracle 11.9 min.

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
