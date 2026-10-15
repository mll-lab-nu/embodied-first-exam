# boot_sole_brush (authoring notes)

Physical DexHand version of scene T29 "Brush adhered debris from a shoe sole" (source, read-only:
`scripts/scene_expansion/repairs/shoe_brush_meta_delivery_trajectory_r1`, a kinematic demonstration in which no hand
acted and debris motion was prescribed). Here one dexterous hand (Sharpa Wave by default, Wuji Hand 2.2 selectable) on
the six-axis wrist stage picks up the brush and brushes six free clods off the boot sole into the tray, in physics.

## Files

| file | role |
|---|---|
| `scene.py` | MJCF builder (hand on the wrist stage, counter, tray, rack, boot, clods, brush, cameras) |
| `checker.py` | fail-fast + ordered stages + terminal hold, simulator state only |
| `runtime.py` | `Session` (FAMILY_PLUGIN section 4, plus `snapshot`/`restore`) |
| `replay.py` | fresh-process replay CLI (FAMILY_PLUGIN section 5), `--video` evidence |
| `task.json` | frozen instance: geometry, clod poses, predicate thresholds, start targets, cameras, task text |
| `assets/` | boot mesh/texture/292 contact hulls from scene T29 + `manifest.json` (sha256, checked at build) |
| `solution/trajectory.npz` | Sharpa Wave witness (1,329 rows; success at control 1,178) |
| `solution/wuji/trajectory.npz` | Wuji Hand 2.2 witness (1,336 rows; success at control 1,186); packaged by the generator as `solution/wuji/` (the oracle uses it when a run selects Wuji) |
| `tools/author_oracle.py` | authoring controller that recorded the witness (closed loop on Session state, IK by least squares) |
| `tools/author_layout.py`, `tools/probe_*.py` | clod placement by raycast on the sole hulls; geometry probes |
| `tests/test_boot_sole_brush.py` | oracle x2 identical + slack, float32, nop, truncations (stage 1, one row short of the hold), drop then resume, release-in-air-and-catch, hand-clod contact, forged members, wrong width, NaN / out-of-range rows, prose-independent state hash, Wuji composes + nop + deterministic, Wuji witness x2 |

## Task and predicate

The exact text is `task.json` `instruction`. Stages (in order): (1) bristle pad on the boot while the hand holds the
brush off the counter, >= 10 controls; (2) every clod touched by the bristle pad (not the wooden back) while still up on the
boot (centre at most 0.01 m below the sole plane) and every clod inside the tray walls below the wall top; (3) 50 consecutive controls with all clods in the tray at rest
(<= 0.05 m/s), the brush touching neither boot nor clods and withdrawn (pad >= 0.04 m above the sole plane or
>= 0.18 m horizontally from the sole centre) -> success (episode ends). Fail-fast after every 2 ms substep: boot moved
> 0.03 m or tilted > 0.35 rad; a clod touching counter/floor, below the counter top or outside the workspace box; any
hand geometry touching a clod; the brush touching floor/tray/rack, below the counter top or outside the box, or
released in the air (no contact except clods while its centre of mass sinks faster than 0.2 m/s: no drop-and-catch
window); unstable physics; 3,000-control budget. `state_sha` hashes the integration state, the predicate state, the
hand and the physics/predicate parameters of `task.json` (prose and camera keys excluded), so text edits never change
evidence hashes. Clod speeds use `mj_objectVelocity(..., mjOBJ_BODY, ...)` (COM velocity; checked against a finite
difference of `xipos`).

## Modelling choices (all passive; only robot actuator targets act)

- **Rig**: hamburger-style wrist stage (three slides kp 2500, three hinges kp 120), stage origin at world
  (0.55, -0.10, 1.10). The hand mount quaternion is rotated so that zero wrist angles give palm down, fingers +y, thumb
  on -x (the working orientation sits in the middle of the +-3.14 hinge ranges). Wuji is composed by
  `hands.replace_wave_hands` under the same stage; both hands start with the same wrist targets and open fingers.
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

## Reference witness (Sharpa Wave)

`tools/author_oracle.py --out X.npz` (needs `DEXHAND_ASSET_DIR`): top-down pinch of the brush back (thumb on the near
long face, index/middle/ring on the far face; IK keeps every hand geom >= 16 mm above the counter so no finger reaches
the clods), lift, then four centre-out strokes: forefoot +y, forefoot -y, heel +y, heel -y (lower until the pad
touches the boot, press 1 mm, sweep 6 cm, lift 3.5 cm), withdraw and hold. The recorded rows plus 150 copies of the
last row form `solution/trajectory.npz` (sha256 `db1d041f...`), replayed open loop: success at control 1,178, two
fresh processes identical, float32 rows succeed, 8/8 successes under 1e-4 m / 1e-3 rad Gaussian row noise.

## Wuji witness (optional evidence)

The same controller with Wuji Hand 2.2 (`--hand wuji --tipz -0.002 --thumbz 0.010 --squeeze 0.018 --grip-clear -1`,
multi-seed IK because the Wuji fingers start straight) succeeds at control 1,186 (1,336 rows with slack): two fresh
replays identical, float32 rows succeed, 6/6 under the same row noise. It is less tolerant of the grasp parameters
than Sharpa (1 of 8 grid settings succeeded): the Wuji thumb tip and finger distal links hang lower beside the brush
and touch clods (`hand_touched_debris`) unless the thumb pinches high on the back.

## Evidence commands

```bash
export DEXHAND_ASSET_DIR=<repo>/images/dexhand/assets/hand   # Wuji assets next to it
cd scripts/dexhand/families/boot_sole_brush
python replay.py --task boot_sole_brush --traj solution/trajectory.npz --out out/a.json        # success at 1178
python replay.py --task boot_sole_brush --traj solution/wuji/trajectory.npz --out out/w.json   # success at 1186
python -m pytest tests -q
python tools/author_oracle.py --out out/sharpa.npz            # regenerate the Sharpa witness (closed loop)
```
MuJoCo preview videos: `replay.py --video out.mp4 --camera overview|closeup|side`. The PR film is rendered with
Blender 4.5.3 from an exact pose export of the replay (`tools/film.py`).
