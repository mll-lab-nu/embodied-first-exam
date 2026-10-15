# picture_hang (T21 "Hang a large picture on two wall hooks") - authoring notes

A physical DexHand task built from the accepted T21 scene-expansion scene
(`scripts/scene_expansion/repairs/picture_sharpa/meta_delivery_trajectory_r1`, a meta-action demo there: the frame was
moved by bounded virtual point forces and no hand was shown). Here two dexterous hands do the whole task in MuJoCo
physics on the Tianji Marvin dual-arm robot (wave 3; wave 2 used two floating six-axis wrist stages); only arm-joint and
finger position targets are commanded and the frame moves only through contact, gravity and its passive ring hinges.

## Files
| file | in the task? | role |
|---|---|---|
| `scene.py` | yes | MJCF builder: room, console, frame with passive D-rings, hooks, Marvin robot (`arm_rig.mount_marvin`) with two hands |
| `checker.py` | yes | ordered stages, terminal released hold, fail-fast invariants (simulator state only) |
| `runtime.py` | yes | `Session` (reset/step/status/state_sha/hold_action/snapshot/restore/save_trajectory/replay/render_frame) |
| `replay.py` | yes | fresh-process replay CLI (`--task --traj --out [--trusted-service] [--hand] [--video]`) |
| `task.json` | yes | frozen instance: rates, robot base, arm start pose (`initial_targets`), cameras, start, predicate thresholds, task text |
| `assets/` | yes | `water-lilies.png` (CC0 Monet print, copied unchanged from the T21 source) + `manifest.json` (sha256) |
| `solution/trajectory.npz` | solution | Sharpa Wave oracle on the arms: 869 rows, success after 669 controls |
| `instruction/`, `README.task.md` | rendered | instruction bodies and task README (the exact predicate is task.json `instruction`) |
| `tests/test_picture_hang.py` | no | authoring tests (13): model invariants, oracle + slack + determinism, float32, nop, truncation, drop, knock-off, lip-resting ring, forged members, wrong width, NaN, out of range, CLI exit 0, Wuji nop + mount |
| `tools/controller.py` | no | closed-loop scripted controller of wave 2 (wrist-stage + finger commands; reads Session state) |
| `tools/arm_author.py`, `tools/arm_port.py` | no | wave 3: runs `controller.py` on the arm rig (`StageProxy`: old stage command -> hand-root pose by `floating_scene.py` kinematics -> Marvin IK + gravity feed-forward), records the arm rows + 200 hold rows; `--init` writes the IK start pose |
| `tools/floating_scene.py`, `tools/floating_task.json` | no | the wave-2 floating-stage scene/config, used only for that kinematic mapping |
| `tools/make_oracle.py` | no | wave-2 floating-stage oracle script (kept for provenance; not used for the arm oracle) |
| `tools/negatives.py` | no | negative / robustness cases with replay JSONs |
| `tools/presentation.py`, `tools/studio_renderer.py` | no | PR film: exact-pose export of the physical replay + the approved T21 film's Blender renderer |

## Provenance and modelling choices (all declared)
- Frame, D-rings, hooks, console, wall: geometry, masses, inertia, friction and contact parameters copied from the
  source `hardware.py`/`scene.py`: 52 x 52 x 6 cm frame (outer size of an IKEA SANNAHED 50 x 50 cm frame; the 2.0 kg
  package weight used as the frame mass), two 6 g 35 mm-class D-rings (2 mm wire, 18 x 20 mm loop) 3 mm behind the back
  of the side rails, two bent-sheet brass hooks (12 mm saddle, 10 mm lip) at z = 1.38 m, y = +-0.255 m on the wall face
  x = 0.74 m, a console top at z = 0.72 m. Project-authored primitives, not manufacturer CAD.
- D-ring hinge: the source range was +-1 rad. The ring is a child body of the frame, so MuJoCo filters ring-frame
  contacts, and an unloaded ring crept through the frame back under gravity. The lower stop is moved to 0 (the frame back
  a real ring cannot pass) and a weak return spring (0.005 N m/rad, springref 0) keeps an unloaded ring upright; damping,
  friction loss and the 1 rad upper limit are the source values. Under hanging load (~10 N) the spring is negligible.
- Wall widened to +-2.5 m (2.5 m tall) and floor enlarged (presentation only; no task contact changes).
- Robot (wave 3): the shared `arm_rig.mount_marvin` Tianji Marvin stand (two 7-joint arms, kp 700 / kv 48, force limits
  108/108/66/66/18/18/18 N m, the accepted pot_shelf_transfer robot) at base (0.18, 0, 0.20) facing the wall, raised on
  a 0.10 m plinth (its top is the stand's floor, base_z - 0.1) so that the hands reach the 1.38 m hooks with the fingers down; both arms work. Sharpa: the
  genuine right Wave on the right flange, its declared y-mirror on the left flange (positions S p, rotations S R S, hinge
  axes -S a, mesh scales reflected); Wuji: `hands.replace_wave_hands` mounts the genuine left/right Wuji Hand 2.2. The
  flange mount bodies are named `l_wrist_stage` / `r_wrist_stage` (hand roots). Start pose: IK of the controller's first
  hand pose (`tools/arm_author.py --init`). Grasp change for the arm: the Marvin wrist link is 28 mm proud of the palm
  surface, so a palm pressed on the side rail below the frame's top edge would put the wrist link into the rail (a
  `robot_collision`); the palms therefore squeeze the top 9 cm of the side rails (controller `z0` = +0.10 m) and the
  thumb is flexed further (`thumb_fe` 1.0) so that its base stays in front of the ring clips.
- Arm-link contacts: any contact of a Marvin stand/torso/arm link with anything is the fail-fast `robot_collision`.
- Layout change for the stand (decor only): the console keeps its top, height and the frame's start, but stands on its
  two rear legs (moved from x = 0.60 to 0.615 m: 17 mm clearance to the plate); the source's front legs (x = 0.40 m)
  would pass through the stand's 0.79 m base plate.
  The plinth under the raised stand is exactly the plate's footprint. Exact check (every stand/torso/arm collision
  geom vs every static geom with `mj_geomDistance`, plus every visual-mesh vertex vs static boxes/planes, at reset and
  every 10 controls of the oracle): no interpenetration.
- Actuator order: left arm (7), right arm (7), left hand fingers, right hand fingers (Sharpa 58, Wuji 54).
- No welds, mocap, equality constraints, object actuators, applied forces or state writes after reset.
- Simplification: the frame is one rigid body (no moulding compliance), the rings and hooks are rigid wire/sheet
  primitives; the print, glazing and backboard are inside the frame body.

## Predicate (task.json `predicate`; evaluated from MuJoCo state)
Stages in order: (1) lifted (origin >= start z + 2 cm, no console contact); (2) both rings threaded on their own hook
and touching it; (3) 50 consecutive controls of released hanging: both threaded, each hook >= 20 % of the frame weight
(vertical ring-hook contact force), sum >= 85 %, no hand contact, no console/floor contact, |roll| <= 3 deg,
tilt <= 0.10 rad, COM speed <= 0.02 m/s, angular speed <= 0.15 rad/s. Stages and the hold are evaluated at the end of
each 50 Hz control.
"Threaded": the hook saddle centre expressed in the ring frame lies inside the D loop shrunk by wire radius and saddle
half-size (|y| <= 5 mm, above the pivot bar, inside the 7.5 mm inner arc; +0.5 mm tolerance), and the ring plane cuts
the saddle between the back of the lip and the wall (-5 mm <= local x <= 4 mm; +0.5 mm) - a ring resting on top of the
lip is not threaded.
Fail-fast after every 2 ms substep: floor contact; origin outside x [0.20, 0.76], y [-0.45, 0.45], z [0.60, 1.30];
tilt > 0.6 rad; origin more than 1 cm below the start height after lift-off; after stage 2, no hand contact while a
ring is not threaded (`fell_off_hook`); any arm/stand link contact (`robot_collision`); unstable physics; after lift-off, unsupported (no hand contact, no console
contact, not hanging threaded on both hooks with both rings touching) while the centre of mass moves down faster than
0.2 m/s (`picture_unsupported`). At the end of every control: unsupported at all after lift-off
(`picture_unsupported`, no drop-and-catch window; review PH-1); 3,000 controls. `speed_m_s` is the centre-of-mass
speed from `mj_objectVelocity(mjOBJ_BODY)` (review PH-2); `state_sha` hashes the integration state, the verdict state,
the step count, the hand and only the physics/predicate fields of task.json (review PH-3).

## Evidence commands
```bash
export DEXHAND_ASSET_DIR=<repo>/images/dexhand/assets/hand WUJI_ASSET_DIR=<repo>/images/dexhand/assets/wuji_v2_2
python tools/arm_author.py --init                                          # IK start pose -> task.json
python tools/arm_author.py --hand sharpa --out solution/trajectory.npz        # 869 rows, success at 669
python replay.py --task picture_hang --traj solution/trajectory.npz --out r1.json   # twice: identical state_sha
python -m pytest -q tests/test_picture_hang.py
python tools/presentation.py export --export <dir> && python tools/presentation.py verify --export <dir>
python tools/presentation.py render --export <dir> --output picture_hang.mp4    # Blender 4.5.3, Eevee, 1280x720
```
Blender films need `DEXHAND_BLENDER` (Blender 4.5.3) and, for Eevee on NVIDIA, `__EGL_VENDOR_LIBRARY_FILENAMES`.

## Evidence (wave 3, 2026-10-15)
Arm oracle: two fresh replays succeed at control 669 with identical state_sha `9f3ff2e9...` (also from the generated
task dir); float32 rows succeed; nop, truncations (300, 530, 668) fail; both arms returning to the start pose
mid-carry (or for only 5 controls) fail `picture_unsupported` at the next control (no drop-and-catch window); 13
authoring tests pass. Harbor 0.23: oracle 1 / nop 0 in both modes (standard: live = replay). PR film: Blender 4.5.3
Eevee of the exported native poses (a wide main view over the robot's right shoulder that shows the stand on its
plinth and the rear-leg console, then a closer final view; no hook close-up: with the top grip a hand sits in front of
each hook from every side a camera can take). `tools/negatives.py` is the wave-2 floating-stage negative script (kept for provenance).
