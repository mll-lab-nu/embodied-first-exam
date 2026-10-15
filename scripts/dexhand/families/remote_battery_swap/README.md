# remote_battery_swap (T07 "Remote battery replacement", physical DexHand version)

A single dexterous hand on the six-axis wrist stage (the `assemble_hamburger` rig, composed with the shared
`hands.py`; Sharpa Wave 28 controls, Wuji Hand 2.2 26 controls) slides a remote's battery door open, moves the old
gray AA into a tray, seats a new green AA with correct polarity and slides the door shut, then lets go for 1 s.
Objects move only through contact and passive joint dynamics; only actuator targets of the wrist stage and the
fingers are commanded.

## Provenance

Scene T07 of the scene expansion (`artifacts/scene-expansion-50`, catalog row T07, source
`robot_coding_bench/scripts/scene_expansion/repairs/battery_v3/trajectory_r1_presentation_r2`): an approved kinematic
film (object motion prescribed, no hand). `tools/export_assets.py` copied from its presentation export
(`presentation-r2/studio-v2`) the meshes of the molded remote shell, sliding battery door, flush thumb pad and OPEN
arrow (`geometry.npz` meshes 0-3, written as OBJ) and the two AA wrap textures; `assets/manifest.json` records the
sha256 of every copied file and of its source. `aa_cell.obj` (UV-mapped cell label) is original. The base collision
dimensions (remote 160 mm long, cavity 94 mm, AA r 7 mm x 49 mm, tray 80 x 70 mm, 18 mm walls) follow the source model
`artifacts/scene-expansion-50/evidence/battery/final08/model.xml`.

## Files

| file | role |
|---|---|
| `scene.py` | MJCF builder: table, remote (free body, collision boxes + presentation meshes), door (slide joint), slot (cradle ribs, terminal blocks, gold + / silver - contacts), two AA cells, tray, cameras, lights; hand rig |
| `checker.py` | fail-fast invariants (every 2 ms substep), four ordered latched stages, released hold |
| `runtime.py` | `Session` (FAMILY_PLUGIN section 4, plus exact `snapshot`/`restore` incl. solver warm start) |
| `replay.py` | fresh-process replay CLI (FAMILY_PLUGIN section 5); only archive-read / trajectory-validation errors become `bad_trajectory` (a scene-build error exits non-zero); `--video`, `--phases` for captions |
| `task.json` | frozen instance (geometry, thresholds in `checker`, initial targets per hand, task text) |
| `assets/` | T07 presentation meshes (OBJ) and AA wrap textures + `manifest.json` (sha256) |
| `solution/trajectory.npz` | the oracle rows (both modes); `solution/phases.npz` phase captions for films (not packaged) |
| `instruction/`, `README.task.md` | generator texts |
| `tests/test_remote_battery_swap.py` | authoring tests (oracle, negatives, fail-fast, predicate fixtures, trust boundary, Wuji) |
| `demo.py` | authoring controller, Sharpa (not copied into tasks); `python demo.py --out X.npz` reproduces the oracle byte for byte |
| `demo_wuji.py` | authoring controller port to Wuji (reaches stages 1-2 only; the table pick of the new cell is not robust) |
| `tools/` | `export_assets.py`, `check_oracle.py` (robustness/negatives), `check_predicate.py`, `render_preview.py` (MuJoCo mp4), `film.py` + `studio_renderer.py` (Blender PR film) |

## Modelling choices (all passive; no welds, mocap, equality constraints, object actuators or object forces)

- Remote: free rigid body, 0.35 kg (a weighted handset incl. ballast), four rubber feet (friction 1.4). Its shell is
  the approved presentation mesh (visual) **widened 1.25 times across** (80 mm, cavity 94 x 65 mm) so two fingertips
  fit beside one cell; collision = floor slab, side walls, rear wall, solid front block.
- Door: child body on a passive slide joint along the remote's -x, travel 0..0.085 m with end stops, damping 0.4,
  friction loss 0.25 N (a light friction hold that keeps it open or shut), and a 3 mm raised thumb ridge. **The
  source's latch tab (spring-loaded `tab_depth` joint) and its latch stop are not modelled**: the door is held by
  friction only.
- **One-cell compartment**: two 1.5 mm cradle ribs (self-centring), fixed terminal blocks with 3 mm (- end) and
  4.4 mm (+ end incl. nub) play; gold + contact disc at +x, silver - contact with a visual coil at -x. **The source's
  compressible negative spring (`spring_compression` joint) is not modelled**; no electrical simulation.
- AA cells: free 23 g rigid cylinders (condim 6, mu 1.0; Sharpa fingertip pads mu 1.5). Tray: free rigid body 0.12 kg,
  inner 74 x 64 mm, 18 mm walls.
- Physics: 50 Hz control, 10 x 2 ms substeps, implicitfast, elliptic cones, impratio 10, multiccd.

## Predicate (task.json `checker`)

Stages latch in order: door >= 0.060 m open; gray cell resting on the tray floor inside the walls with no hand
contact; green cell within 5 / 3 / 2 mm (x / y / z, remote frame) of the slot centre, axis within 10 deg of the remote
+x with its + end at the gold contact, on both ribs, no hand contact; door <= 0.004 m. Success: all latched and
conditions 2-4 true with zero hand contact and every task object at rest (body-origin linear speed <= 0.02 m/s,
angular speed <= 0.5 rad/s; free-joint velocities) for 50 consecutive controls (1 s). Fail fast (every substep, no
grace window): task body below the table top or outside the workspace box, floor contact, remote or tray moved > 3 cm
or tilted > 15 deg, gray cell touching the table, green cell touching the table after it was lifted (lifted = the
first control it is clear of the table and > 1 cm above its start), a cell without hand contact moving down faster
than 0.886 m/s (free drop from 4 cm), a cell touching nothing at all moving down faster than 0.5 m/s (reviewer RB-1;
the oracle's own peak unsupported fall is 0.16 m/s), unstable physics, 6,000-control budget. `state_sha` hashes the integration state, the
predicate state, the hand and the physics/predicate parameters of `task.json` (never the prose keys), so text edits
do not change evidence hashes.

## Oracle (Sharpa)

`demo.py`: least-squares IK on fingertip capsule/pad points with collision margins (`mj_geomDistance`), smooth
joint-space interpolation, action = target + gravity-bias feedforward + 2x finger position-error boost (all plain
motor targets), closed loop on simulator state while authoring, recorded open loop. Phases: index fingertip pushes the
door ridge 80 mm (door open at control 273); thumb/index pad pinch lifts the gray cell 7 cm, carries it 20 cm and
releases it 4 mm above its resting height on the tray floor (851); thumb/index pad pinch picks the green cell off the
table, the hand turns 20 deg about the cell so + faces the gold contact, lowers it until it rests on the ribs and opens
(1607); the fingertip pushes the ridge back (2005); hand clear, released hold, success at 2100; 150 hold rows of slack.
Peak downward speed of a cell touching nothing: 0.16 m/s (gray, tray release), 0.02 m/s (green). Robustness: rows rounded to
float32 succeed; Gaussian noise on every row (sigma 1e-4, 5e-4, 1e-3 rad/m; 15 seeds) all succeed.

## Evidence commands (authoring)

```bash
export DEXHAND_ASSET_DIR=<repo>/images/dexhand/assets/hand WUJI_ASSET_DIR=<repo>/images/dexhand/assets/wuji_v2_2
export MUJOCO_GL=egl OPENBLAS_NUM_THREADS=1; ulimit -c 0
python demo.py --out out/oracle.npz                                   # rows (+150 hold rows) + .live.json + .phases.npz
python replay.py --task remote_battery_swap --traj solution/trajectory.npz --out out/r1.json   # x2, fresh processes
python tools/check_oracle.py --traj solution/trajectory.npz --live out/oracle.live.json --out-dir out/v
python tools/check_predicate.py                                            # predicate fixtures (instance edits only)
python -m unittest discover -s tests -v                                    # 19 authoring tests
python tools/render_preview.py --traj solution/trajectory.npz --phases solution/phases.npz --out out/preview.mp4
python tools/film.py export --trajectory solution/trajectory.npz --export out/film   # Blender film: export,
BLENDER=<blender 4.5.3> python tools/film.py render --export out/film --output out/remote_battery_swap.mp4  # render + encode
```
