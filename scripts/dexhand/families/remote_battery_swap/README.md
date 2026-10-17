# remote_battery_swap (T07 "Remote battery replacement", physical DexHand version)

A dexterous hand on the right arm of the Tianji Marvin robot (shared `arm_rig.py`: stand, two 7-DoF arms, a hand on
each flange; the left arm is parked; robot id `marvin-bimanual-sharpa-wave`, Sharpa Wave 58 controls, Wuji Hand 2.2
54 controls) presses the remote's latch tab and slides the battery door open, moves the old gray AA into a tray,
seats a new green AA with correct polarity, slides the door shut until it latches, then lets go for 1 s. Objects move
only through contact and passive joint dynamics; only actuator targets of the arm joints and the fingers are
commanded. Wave 3 (2026-10-15): source-size remote, source latch tab + spring restored, floating stage replaced by the
arm (see "Wave-3 changes").

## Provenance

Scene T07 of the scene expansion (its evidence is kept outside the repository; catalog row T07, source
`robot_coding_bench/scripts/scene_expansion/repairs/battery_v3/trajectory_r1_presentation_r2`): an approved kinematic
film (object motion prescribed, no hand). `tools/export_assets.py` copied from its presentation export
(`presentation-r2/studio-v2`) the meshes of the molded remote shell, sliding battery door, flush thumb pad and OPEN
arrow (`geometry.npz` meshes 0-3, written as OBJ) and the two AA wrap textures; `assets/manifest.json` records the
sha256 of every copied file and of its source. `aa_cell.obj` (UV-mapped cell label) is original. The base collision
dimensions (remote 160 mm long, cavity 94 mm, AA r 7 mm x 49 mm, tray 80 x 70 mm, 18 mm walls) follow the source model
(the scene expansion's accepted `battery/final08/model.xml`, outside the repository).

## Files

| file | role |
|---|---|
| `scene.py` | MJCF builder: Marvin rig (`arm_rig.mount_marvin`; legacy floating stage for `"rig": "floating"`), table with legs, remote (free body, collision boxes + presentation meshes), door (slide joint), slot (cradle ribs, terminal blocks, gold + / silver - contacts), two AA cells, tray, cameras, lights; hand rig |
| `checker.py` | fail-fast invariants (every 2 ms substep), four ordered latched stages, released hold |
| `runtime.py` | `Session` (FAMILY_PLUGIN section 4, plus exact `snapshot`/`restore` incl. solver warm start) |
| `replay.py` | fresh-process replay CLI (FAMILY_PLUGIN section 5); only archive-read / trajectory-validation errors become `bad_trajectory` (a scene-build error exits non-zero); `--video`, `--phases` for captions |
| `task.json` | frozen instance (geometry, thresholds in `checker`, initial targets per hand, task text) |
| `assets/` | T07 presentation meshes (OBJ) and AA wrap textures + `manifest.json` (sha256) |
| `solution/trajectory.npz` | the oracle rows (both modes); `solution/phases.npz` phase captions for films (not packaged) |
| `instruction/`, `README.task.md` | generator texts |
| `tests/test_remote_battery_swap.py` | authoring tests (oracle, negatives, fail-fast, predicate fixtures, trust boundary, Wuji) |
| `demo.py` | authoring controller, Sharpa on the right arm (not copied into tasks); `python demo.py --out X.npz` reproduces the oracle byte for byte |
| `tools/` | `export_assets.py`, `check_oracle.py` (robustness/negatives), `negatives.py` (controller-made negatives: forced door, 3 cm release), `audit_arm.py` (arm/parked-hand contacts, peak unsupported fall), `check_predicate.py`, `render_preview.py` (MuJoCo mp4), `film.py` + `studio_renderer.py` (Blender PR film with the arm) |

## Modelling choices (all passive; no welds, mocap, equality constraints, object actuators or object forces)

- Robot: Tianji Marvin stand (pot_shelf_transfer's frozen robot via `scripts/dexhand/shared/arm_rig.py`), stand origin
  (-0.45, 0.15, -0.45), facing +x, both arms position servos kp 700 / kv 48, no gravity compensation; the right arm
  and hand work, the left arm is parked (`arm_rig.PARK`). The floor is at z = -0.55 (stand origin - 0.1); the table
  (top z 0.30, 0.72 x 0.68 m, front edge at x = -0.25) has four legs. Placement like the source scene's robot
  (battery_v2: robot at the origin, remote 0.51 m in front and 0.45 m above the robot origin).
- Remote: free rigid body, 0.35 kg (a weighted handset incl. ballast), four rubber feet (friction 1.4), at the
  **source size** (shell 160 x 64 mm, cavity 94 x 52 mm; the wave-2 1.25x widening is reverted); collision = floor
  slab, side walls, low rear wall between two ears (source `task_remote_end_-1` + ears), solid front block.
- Door (source mechanism): child body on a passive slide joint along the remote's -x, travel 0..0.085 m with end
  stops, source damping 0.1 and friction loss 0.08 N; **source latch restored**: a thumb tab (18 x 18 mm, 3 mm proud;
  slide joint `tab_depth` along -z, 0..5 mm, stiffness 120 N/m) carries a hook (source `task_cover_hook`) that sits in
  front of the fixed latch stop (source `task_latch_stop`) when the door is shut. The door opens only with the tab
  pressed 2.9..4.5 mm (hook under the stop and over the 2 mm-high rear wall); probe: pushing the tab's front edge
  without pressing it leaves the door shut (`tools/negatives.py force_door_without_tab`: 0.09 mm). The negative
  terminal block stops 6 mm short of the rear wall so the hook can pass (the source has no block there).
- **One-cell compartment**: two 1.5 mm cradle ribs (self-centring), fixed terminal blocks with 3 mm (- end) and
  4.4 mm (+ end incl. nub) play; gold + contact disc at +x, silver - contact with a visual coil at -x. **The source's
  compressible negative spring (`spring_compression` joint) is not modelled**; no electrical simulation.
- AA cells: free 23 g rigid cylinders (condim 6, mu 1.0; Sharpa fingertip pads mu 1.5). Tray: free rigid body 0.12 kg,
  inner 74 x 64 mm, 18 mm walls.
- Physics: 50 Hz control, 10 x 2 ms substeps, implicitfast, elliptic cones, impratio 10, multiccd.

## Predicate (task.json `checker`)

Stages latch in order: door >= 0.060 m open; gray cell resting on the tray floor inside the walls with no hand
contact; green cell within 5 / 3 / 2 mm (x / y / z, remote frame) of the slot centre, axis within 10 deg of the remote
+x with its + end at the gold contact, on both ribs, no hand contact; door shut and latched (slide <= 0.002 m and
tab pressed <= 0.0015 m, i.e. the hook is up in front of the stop). Success: all latched and
conditions 2-4 true with zero hand contact and every task object at rest (body-origin linear speed <= 0.02 m/s,
angular speed <= 0.5 rad/s; free-joint velocities) for 50 consecutive controls (1 s). Fail fast (every substep, no
grace window): task body below the table top or outside the workspace box, floor contact, remote or tray moved > 3 cm
or tilted > 15 deg, gray cell touching the table, green cell touching the table after it was lifted (lifted = the
first control it is clear of the table and > 1 cm above its start), a cell without hand contact moving down faster
than 0.886 m/s (free drop from 4 cm), a cell touching nothing at all moving down faster than 0.5 m/s (reviewer RB-1;
the oracle's own peak unsupported fall is 0.16 m/s), the parked left arm or left hand touching a task object (`left_arm_contact`), unstable physics, 6,000-control budget. `state_sha` hashes the integration state, the
predicate state, the hand and the physics/predicate parameters of `task.json` (never the prose keys), so text edits
do not change evidence hashes.

## Oracle (Sharpa on the right arm)

`demo.py`: least-squares IK of fingertip capsule/pad points over the seven right-arm joints and the finger joints
(collision margins via `mj_geomDistance`), hand-root straight-line motions between key postures (DLS arm IK every
control, bounded least squares as fallback), action = target + gravity/bias feed-forward on every actuated joint +
2x finger position-error boost (all plain motor targets), closed loop on simulator state while authoring, recorded
open loop. Phases: the index pad presses the latch tab (closed loop until 3.6 mm) and slides the door 80 mm (door open
at control 324); thumb/index pad pinch (natural palm-down posture, pitch 1.2 rad) lifts the gray cell out of the
52 mm cavity, carries it to the tray and releases it 4 mm above its resting height (943); the green cell is picked
off the table, turned 20 deg so + faces the gold contact, lowered onto the ribs and released by opening only the
thumb and index (arm still) (1729); the index presses the tab again and slides the door shut, lifts (latched at
2215); hand up, released hold, success at 2266; 150 hold rows of slack (2,416 rows). Audit (`tools/audit_arm.py`):
no arm-link, stand or parked-hand contact; peak downward speed of a cell touching nothing 0.16 m/s (gray) / 0.00
(green); remote displacement 0.01 mm. Rows rounded to float32 succeed.

## Wave-3 changes (realism + arm)

| item | wave 2 | wave 3 |
|---|---|---|
| remote size | widened 1.25x in y (cavity 65 mm) | source size (cavity 52 mm) |
| door latch | friction hold only (0.25 N), raised ridge | source thumb tab + spring (5 mm, 120 N/m) + hook/stop; source door damping/friction |
| cells in the compartment | one | one (= source: one gray AA in the compartment, one green AA on the table) |
| stage 4 | door <= 0.004 m | door <= 0.002 m and tab <= 1.5 mm (latched) |
| robot | floating six-axis wrist stage (28 / 26) | Marvin right arm + parked left arm (58 / 54) |
| not modelled | latch, negative spring | source compressible negative spring (fixed terminals, 3 mm play) |

## Evidence commands (authoring)

```bash
export DEXHAND_ASSET_DIR=<repo>/images/dexhand/assets/hand WUJI_ASSET_DIR=<repo>/images/dexhand/assets/wuji_v2_2
export MUJOCO_GL=egl OPENBLAS_NUM_THREADS=1; ulimit -c 0
python demo.py --out out/oracle.npz                                   # rows (+150 hold rows) + .live.json + .phases.npz
python replay.py --task remote_battery_swap --traj solution/trajectory.npz --out out/r1.json   # x2, fresh processes
python tools/check_oracle.py --traj solution/trajectory.npz --live out/oracle.live.json --out-dir out/v
python tools/check_predicate.py                                            # predicate fixtures (instance edits only)
python tools/negatives.py --out-dir out/neg                               # forced door, 3 cm release (controller-made)
python tools/audit_arm.py --traj solution/trajectory.npz --out out/audit.json
python -m unittest discover -s tests -v                                    # 20 authoring tests
python tools/render_preview.py --traj solution/trajectory.npz --phases solution/phases.npz --out out/preview.mp4
python tools/film.py export --trajectory solution/trajectory.npz --export out/film   # Blender film: export,
BLENDER=<blender 4.5.3> python tools/film.py render --export out/film --output out/remote_battery_swap.mp4  # render + encode
```
