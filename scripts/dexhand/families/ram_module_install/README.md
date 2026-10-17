# ram_module_install (DexHand plugin family, wave 2, scene T28; socket throat from wave 3)

Physical version of scene-expansion scene T28 "Install a desktop RAM module" (accepted kinematic demo). A Sharpa Wave
(default) or Wuji Hand 2.2 on the shared six-axis wrist stage picks a Kingston DDR4 DIMM out of an anti-static foam
holder, carries it to the outer DIMM socket of a fixed ATX motherboard, inserts it fixed-end first, levels it so the
lower edge pushes the passive latch over centre, and lets go.

## Files
| file | role |
|---|---|
| `scene.py` | builds the MJCF: Sharpa `right_hand.xml` + wrist stage (`hands.replace_wave_hands` for Wuji) + the T28 source scene (`assets/t28_scene.xml`, verified against `assets/manifest.json`) with the physical socket changes below |
| `checker.py` | ordered stages, terminal released hold, fail-fast list (state only) |
| `runtime.py` | `Session` (FAMILY_PLUGIN section 4; adds `snapshot`/`restore`) |
| `replay.py` | fresh-process replay CLI (FAMILY_PLUGIN section 5) |
| `task.json` | frozen instance (all thresholds, cameras, initial targets) |
| `demo.py` | authoring controller (not shipped): closed-loop scripted pinch / carry / align / insert / release, recorded as float32-exact rows |
| `solution/trajectory.npz` | Sharpa oracle rows (both modes; the standard oracle submits them through the public client) |
| `tests/test_ram_module_install.py` | authoring tests (not shipped) |
| `presentation.py`, `studio_renderer.py` | authoring film (not shipped): exact native poses of the oracle replay rendered in Blender 4.5.3 with the T28 studio look |

## Modelling scope (all choices)
- Geometry, materials, label texture, module dimensions (133.35 x 31.25 x 1.27 mm), mass 14 g, inertia, keyed lower
  edge (off-centre notch), the four sockets and the board come from the source scene, copied verbatim.
- Target socket `socket_3`: the 30 copper contact sliders (0.25 g on 900 N/m springs; unstable at a 2 ms step, no
  electrical meaning) and both side catches are visual only; throat walls and end forks keep the source's 1.66 mm gap
  (wave 3; wave 2 had widened them to 2.10 mm) with 0.6 rad x 1.5 mm lead-in chamfers (exact visual copies keep the
  source look); floor raised 1 mm to the source's
  2 mm seating datum; key kept at its position/height, 0.70 mm wide with a rounded top (notch 1.50 mm); fixed-end post
  rigid (flexure not needed for a straight entry) with a chamfered top inner edge.
- Moving latch: source hinge (0..0.55 rad, damping 0.001, armature 1e-6). The source spring (0.012 N m/rad towards
  closed) relied on a 0.008 N m frictionloss to stay open, which creeps shut within a second in MuJoCo's soft-constraint
  solver; it is replaced by a passive over-centre toggle (spatial tendon, 600 N/m, from the spine to an anchor below the
  pivot, centre at 0.25 rad): the latch rests open and only the module's lower edge pushing the foot past centre closes it.
- Module starts upright in a slotted anti-static foam holder (static geoms, slit 1.32 mm) on the bench, oriented along
  the slot with the key towards +y (no pick-from-flat; a 1.27 mm flat PCB cannot be lifted off the bench by this rig).
- Physics: 2 ms step, 10 substeps per 50 Hz control, implicitfast, elliptic cone, impratio 10, multiccd; fingertip
  friction 1.5, module friction 0.8 (torsional 0.005, condim 4), latch foot friction 0.1.
- Wrist targets are the world position of the hand mount (stage base at the origin), ranges x [0.17, 1.07],
  y [-0.51, 0.39], z [0.70, 1.30] m, angles +-3.14 rad; mount quaternion `0 0 1 0` (fingers down at zero angles).

## Wave 3 (2026-10-15): realism review against the source scene

- Socket throat: back to the source's 1.66 mm (`socket_half_gap_m` 0.83 mm; wave 2 widened it to 2.10 mm). The same
  authoring controller inserts the module (success after 1,379 controls instead of 1,391); latch physics unchanged.
- Module start pose: still upright in the foam holder. In the source it lies flat on the workbench (DRAM packages up,
  resting on its rear package). Picking a flat 1.27 mm PCB was tried and is not feasible with these fingertips tonight:
  the fingertip spheres (r 8.1 / 9.4 mm) cannot get under an edge that the rear package can tilt up by at most 3.4 mm
  (the contact lies below the sphere centre and pushes the edge down); sliding / turning the board on the bench to an
  overhang at the bench edge fails because the soft finger servos give ~0.1 N of press force (with stiff contacts or
  joint-limit fingers a small hand turn slams one fingertip with 24-83 N and tips the board), and a palm press cannot
  transmit the turning torque through its single small contact patch. Scripts and logs: the wave-3 worker evidence
  (`flat_start_attempts/`, outside this repository).
- Marvin arm: a port onto the arm rig was attempted and is not shipped. Following the floating oracle's hand poses with
  arm IK drops the module during the carry; running this controller closed loop on the arm (its plans mirrored from
  the arm episode, arm IK + joint integral per control; tracking within 1 mm) carries it to the socket, but the
  two-pad pinch lets the 133 mm board pivot and slide during the alignment iterations, and with the source's 1.66 mm
  throat the fixed end then lands on the end-guide top (1-5 mm lateral error) instead of entering; a three-finger
  pinch (thumb against index + middle; an authoring variant, not shipped, that succeeds on the stage after 1,385
  controls) loses the middle finger when the arm lifts the module out of the holder. The task stays on the wave-2 wrist stage.

## Evidence (phase A)
Kept with the wave-2 worker records (status.json and evidence/, outside this repository): two fresh replays with
identical state hashes, float32 rows, negatives (nop, truncations, drops), a perturbation sweep, videos and frames.
The oracle never leaves the module unsupported while falling (8 unsupported substeps in the whole episode, peak
downward speed 0.002 m/s), so the 0.2 m/s unsupported-fall bound is tight.
Commands (from this folder, with `DEXHAND_ASSET_DIR` pointing at the Sharpa assets and `WUJI_ASSET_DIR` at Wuji's):

```bash
python demo.py --out solution/trajectory.npz                 # regenerate the oracle bit-exactly (~30 s)
python replay.py --task ram_module_install --traj solution/trajectory.npz --out out/r1.json   # success at 1379
python -m unittest tests/test_ram_module_install.py          # 24 authoring tests (~90 s)
python presentation.py export --trajectory <rows.npz> --export <dir>        # sampled native poses (every 4 controls)
BLENDER=<blender 4.5.3> python presentation.py render --export <dir> --output film.mp4 --engine eevee --samples 24
```

Harbor 0.23 (eai-dexhand:0.2.0, CPU only, `RCB_LIMITS_ENFORCE=0`, 2026-10-14): privileged oracle 1 / nop 0, standard
oracle 1 (live = replay, 1,391 controls, about 2.5 min) / nop 0, Wuji nop 0 in both modes (standard: `hand_wuji` 1).
No Wuji oracle: a short grasp search showed the Wuji pinch too weak to carry the module without it pivoting.
