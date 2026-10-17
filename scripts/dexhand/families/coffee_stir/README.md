# coffee_stir (authoring notes)

Source scene: T11 "Mix coffee and milk" (scene-expansion kinematic demo, main checkout
`robot_coding_bench/scripts/scene_expansion/repairs/coffee_tripod/meta_delivery_polish_r1_gravity_trajectory_r1`; approved
film: the scene expansion's T11 root-review `approved-success.mp4`, outside the repository). The film starts with the
teaspoon held upright above the mug (`initial = (0.48, 0, 0.885)`), adds the milk from an offscreen supply, dips the spoon,
stirs six continuous turns, withdraws the spoon and lays it face-up on the worktop beside the mug. This family makes that
episode physical with a Sharpa Wave hand on the right arm of the Tianji Marvin dual-arm stand (wave 3: arm rig and source
start/count/end restored; wave 2 used a floating wrist stage, a spoon leaning in the mug, three turns and a spoon left in
the mug).

## Files
| file | role |
|---|---|
| `scene.py` | MJCF builder: Marvin stand (`arm_rig.mount_marvin`, right arm active, left parked; right hand mount named `wrist_stage`), worktop, mug, spoon |
| `checker.py` | ordered stages, terminal hold and fail-fast checks from simulator state only |
| `runtime.py` | `Session` (FAMILY_PLUGIN section 4, `snapshot`/`restore`); exact frozen reset from `task.json` `initial_qpos` |
| `replay.py` | fresh-process replay CLI; only archive-read errors become `bad_trajectory` (LESSONS L6) |
| `task.json` | frozen instance: poses, stand placement, per-hand start state, cameras, thresholds, task text |
| `tools/make_reset.py` | authoring: builds the Sharpa start state physically (see below) |
| `tools/make_reset_wuji.py` | authoring: the Wuji start state (spoon leaning in the mug, open hand above) |
| `tools/demo_arm.py` | authoring controller that produced `solution/trajectory.npz` |
| `tools/armctl.py`, `tools/rigtools.py` | authoring helpers: Cartesian arm control by IK (`shared/arm_ik.py`) with a joint integral; least-squares fingertip grasps |
| `tools/presentation.py`, `tools/studio_renderer.py` | Blender film (exact native poses; T11 kitchen look; Marvin meshes with the factory rgba) |
| `tests/test_coffee_stir.py` | authoring tests |

## Modelling choices
- Robot: Marvin stand at the world origin facing +x, plate on the floor (floor at z = -0.1, `base_z = floor_z + 0.1`);
  worktop front edge at x = 0.25 (the T11 counter extension behind the robot is set dressing in the film only). Arm servos
  as pot_shelf_transfer (kp 700, kv 48, no gravity compensation). 58 Sharpa / 54 Wuji targets per row.
- Coffee/milk is not simulated (visual surface 64 mm above the mug base); mixing = submerged bowl revolutions about the
  mug axis (six, the source's count). The milk is already poured at the start (the source pours it from an offscreen
  vessel before the spoon enters).
- Geometry and masses from the T11 native model (mug 300 g, spoon 35 g; contact proxies: mug floor disk + 32 wall boxes
  + 3 handle boxes; spoon shaft capsule r = 2.7 mm + two crossed bowl slabs).
- Start (Sharpa): the film's first frame, made physically by `tools/make_reset.py`: on the task model, with the spoon
  leaning in the mug, the right hand takes the wave-2 thumb-over/index-under pinch (wave-2 stage pose converted by arm
  IK, 3 cm further down the handle), raises the pinch over the mug axis so the spoon swings upright below it, places the
  bowl centre near the source point and holds 8 s; the settled `qpos` and the held targets are `initial_qpos` /
  `initial_targets`. No weld; the authoring rows are discarded.
- Start (Wuji): no Wuji pinch of the upright spoon exists yet; with Wuji selected the spoon starts leaning in the mug
  and the open Wuji hand hangs 0.25 m above it (stated in the task text). No Wuji reference solution.
- Picking the spoon up from the worktop (instead of the pre-held film start) was tried first and dropped: a 5.4 mm shaft
  lying flat on the worktop could not be pinched by the 16-19 mm Sharpa fingertip pads (frames
  `try2`, `try3` in the wave-3 authoring records, outside the repository).
- The bowl tip/neck reference sites lie 1.5 mm beyond the ends of the bowl's contact slab: the below-worktop margin for
  spoon reference points is 3 mm.

## Predicate (checker.py, numbers in task.json)
1. In hand, submerged: thumb + another finger on the spoon; bowl centre, tip and neck 4-64 mm above the mug base and
   within 50 mm of the axis.
2. Stirred: >= 6 net revolutions of the bowl centre about the mug axis (world frame), counted only while (1) holds and the
   bowl is >= 8 mm from the axis; > 0.785 rad per control ignored; restart when the bowl leaves the coffee.
3. Laid down: no hand contact, no mug contact, spoon on the worktop, bowl centre and handle end >= 0.10 m from the axis,
   axis within 15 degrees of horizontal, spoon/mug speeds <= 0.02 m/s and 0.5 rad/s, for 50 controls.
Fail-fast (every substep): mug tilt > 10 deg / slide > 20 mm / lift > 5 mm; spoon on the floor, or on the worktop before
stage 2; spoon touching neither hand, mug nor worktop while falling > 0.2 m/s; mug on the floor; spoon reference point
> 3 mm below the worktop or mug base > 5 mm below; bowl/handle end out of the workspace box; fingertip in the coffee;
arm link, stand or parked left hand touching mug, spoon or worktop; unstable physics; 3000-control budget.

## Authoring controller (tools/demo_arm.py, Sharpa)
Pinch-point commands (hand mount = pinch + fixed offset, fixed orientation, arm IK + joint integral): centre the hanging
bowl over the mug, lower it 32 mm above the mug base, circle the pinch on a 15 mm radius for 6.7 turns (110 controls per
turn, open loop; the hanging bowl follows), lift until the bowl clears the rim by 4 cm, carry 0.23 m beside the mug
(220 controls), lower until the bowl just touches, rotate the spoon down about its bowl (the pivot height follows the
tilted bowl slab), open thumb and index, slide the fingers off sideways, withdraw. Success at control 1,802; the solution
adds 80 slack rows (1,882).

## Evidence commands (from this folder; `DEXHAND_ASSET_DIR`, `WUJI_ASSET_DIR` set)
```sh
python tools/make_reset.py --hold 400 --squeeze 1.25 --grip-shift 0.03 --write   # Sharpa start state
python tools/make_reset_wuji.py                                                   # Wuji start state
python tools/demo_arm.py --out solution/trajectory.npz                            # 1,882 rows, success at 1,802
python replay.py --task coffee_stir --traj solution/trajectory.npz --out replay.json
python -m pytest -q tests
python tools/presentation.py export --trajectory solution/trajectory.npz --export <dir> --stride 6
BLENDER=<blender 4.5.3> python tools/presentation.py render --export <dir> --output coffee_stir.mp4 --samples 20
```
