# fan_guard_install (DexHand family, authoring notes)

Physical version of scene-expansion T26 "Install a desk fan front guard" (source, read-only:
`scripts/scene_expansion/repairs/fan_guard_meta_delivery_polish_r1_capture_trajectory_r1/`, a kinematic demo with
prescribed guard and clip motion; all four clips open at the start). Here a dexterous hand on a six-axis wrist stage
does the whole task in MuJoCo physics; only actuator targets are commanded.

## Files

| file | role |
|---|---|
| `geometry.py` | fan, rear cage, clips, free front guard (adapted from the source `geometry.py`) |
| `scene.py` | worktop, lights, cameras, hand on the wrist stage (`hands.replace_wave_hands` for Wuji) |
| `checker.py` | ordered stages, terminal hold, fail-fast invariants (state only) |
| `runtime.py` | `Session` (FAMILY_PLUGIN section 4, plus bit-exact `snapshot`/`restore` for search tooling); `state_sha` hashes the integration state, the predicate state, the hand and only the physics/predicate keys of `task.json` (`PHYSICS_KEYS`) |
| `replay.py` | fresh-process replay CLI (section 5); `--camera auto` switches overview/close-up for previews |
| `task.json` | frozen instance (thresholds, cameras, wrist stage, initial targets) |
| `assets/` | three blade STL lofts from the source + `manifest.json` (sha256) |
| `solution/trajectory.npz` | Sharpa Wave oracle rows (+ ignored `phases` labels for videos) |
| `tools/author.py`, `tools/fanplan.py` | authoring controller and IK helpers (never copied into a task) |

## Task and predicate

Stage 1 `guard_seated`: guard centre within 5 mm of the fan axis, axial seat error within 2.5 mm, guard axis within
5 deg of the fan axis. Stage 2 `clips_locked`: stage 1 and all four clip hinge angles <= 0.12 rad (closed stop at 0,
over-centre point at 0.70 rad, open stop at 1.40 rad); the guard rim inside every clip's U channel (rim point nearest
each clip, fan-fixed clip frame: x in [6.8, 9.9 / 8.6] mm, y in [-4.8, -2.2] mm); each upper clip locked at or after
the first seated control.
Stage 3 `released_hold`: stage 2 with no hand contact on guard/clips/fan, guard speed <= 0.02 m/s and <= 0.2 rad/s,
for 50 consecutive controls (1 s). Success ends the episode.

Fail-fast (every 2 ms substep, permanent): fan displaced > 3 cm or tilted > 0.10 rad; guard COM below the worktop
(z < 0.65) or outside x [0.20, 1.10], y [-0.55, 0.55], z [0.60, 1.40]; guard touching worktop/legs/floor after its COM
rose 5 cm above rest; guard touching nothing (no active contact) while its COM falls faster than 0.2 m/s (no
drop-and-catch window); guard touching the fan base/stem/neck/motor/feet/buttons/knob; unstable physics; 6000-control
budget.

## Modelling choices (all passive; no welds, mocap, equality constraints, object actuators or applied forces)

- Rigid free guard (185 g, source inertia) and rigid free fan (2.13 kg body + clips) standing on rubber feet.
- Clips: the source U channel (bridge + lip) on a passive hinge with damping, friction loss and armature; the source's
  45 mg articulated snap leaf (which needed a 0.25 ms step) is replaced by the source's own over-centre elastic tendon
  detent, made stiffer (2500 N/m: 0.036 N m holding torque, 14 mJ barrier) so a closed lower clip carries the guard.
  The snap leaf and bracket remain as visual-only shapes. A small thumb tab on the bridge gives a fingertip purchase.
- All four clips start open (1.40 rad), as in the source (wave 2 started the two lower clips closed as hanger
  channels; reverted in wave 3). With one hand the order is forced: the hand closes the two lower clips first (index
  fingertip reaching behind each open clip from beside the rim, hand outside the cage pointing down along the rim),
  hangs the guard in the two closed lower channels, lets go and closes the upper clips over the seated guard. The
  checker requires all four clips locked with the rim inside every channel, and the upper clips locked at or after the
  first seated control (an upper clip cannot be pre-closed: a closed channel at the top would block the rim).
- Lower clip lips sit 1.3 mm deeper (0.65 mm axial play instead of 1.95 mm) so the hung guard (COM 18 mm in front of
  its rim plane) leans at most ~0.4 deg and the closing upper hooks clear the rim. Lips end 4.8 mm inside the clip
  (source 6.8 mm) so they do not land on the dish wires that rise steeply inside the rim.
- Centre badge: a 22 mm raised hub cap (source: 6 mm disc) so fingertips can grip its edge in front of the dish wires.
  Wave 3 tried the source badge (6 mm disc): it stands only ~1.9 mm proud of the inner spoke ends (3.4 mm at
  r = 50 mm), so an 8.1 mm fingertip capsule resting on the spokes can touch it only at its top corner. Corner-pinch
  grasps (several seed, offset, spin and release variants) did lift and seat the guard in some runs, but every such
  lift relied on the thumb and index fingertip capsules sinking 8+ mm into the 0.5 mm dish spokes (a soft-contact
  artifact: the wires end up inside the fingertip), and the jammed fingertips then dragged the seated guard off the fan
  on release. With legitimate contact the source badge cannot be gripped, so the 22 mm cap stays (the accepted
  oracle's hand-object penetration stays <= 3.4 mm; cap grasp <= 1.6 mm).
- Dish wires (spokes, hoops) collide with the hand, rims, clips, fan body and table but not with the other cage's dish
  wires (performance); rims, cap and clips collide with everything.
- Plug and cord are static visual decoration (source: a free plug body).
- Timestep 2 ms, implicitfast, elliptic cones, 10 substeps per 50 Hz control.

## Evidence (phase A; the evidence files stay outside the repository)

```bash
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1; ulimit -c 0
export DEXHAND_ASSET_DIR=<repo>/images/dexhand/assets/hand WUJI_ASSET_DIR=<repo>/images/dexhand/assets/wuji_v2_2
cd scripts/dexhand/families/fan_guard_install
python tools/author.py --out run.npz   # authoring; IK grasp seeds in tools/seeds/ (tools/seed_grasp.py)
python replay.py --task fan_guard_install --traj solution/trajectory.npz --out r1.json   # x2, fresh processes
python replay.py --task fan_guard_install --traj solution/trajectory.npz --video v.mp4 --camera auto --fps 25 \
    --width 1280 --height 720
```

Oracle robustness: identical `state_sha` in fresh processes; float32-rounded rows succeed; 180 rows of slack after
success; i.i.d. row noise of 0.5 mm / 0.5 mrad succeeded 4/4, 1 mm / 1 mrad 0/4 (the lower-channel window is 0.65 mm).

Wuji Hand 2.2: composes on the same wrist stage (26 controls), deterministic nop (identical `state_sha` in two fresh
processes). No Wuji success: with the vendor finger gains (MCP kp 0.37 N m/rad vs Sharpa 4.76) the hub-cap grip lifts
the guard but slips during the upright turn (`tools/seed_grasp.py --hand wuji`, `tools/author.py --hand wuji`).

## Packaging evidence (phase B)

```bash
python3 scripts/dexhand/generate.py --only-family fan_guard_install            # both task dirs
python3 scripts/dexhand/generate.py --check --only-family fan_guard_install    # clean-render comparison
python3 -m pytest scripts/dexhand/families/fan_guard_install/tests -q          # authoring tests
# PR film (presentation only; exact native body poses, no interpolation):
python tools/film.py export --trajectory solution/trajectory.npz --export out/fgi-film --stride 4
blender -b -P tools/film.py -- render --export out/fgi-film --frames out/fgi-film-frames --samples 32
python tools/film.py encode --export out/fgi-film --frames out/fgi-film-frames --output fan_guard_install.mp4
```

Measured: one fresh replay of the oracle 12 s wall and 0.30 GiB peak RSS (pinned venv, one core); the collect hook's
evidence video (`--trusted-service --video`, 5 fps, 960 x 544, coarse wire tessellation, no shadows) 151 s on the
host's software renderer, hence `video_sec = 1500`. The scene's `<visual>` tessellation (`numslices = 16`,
`numstacks = 8`) only affects drawing: about 1,700 thin wire capsules dominate software rendering (1.6 s per
640 x 480 frame with shadows in the service, 0.8 s without).

The oracle is an open-loop recording: deterministic, float32-safe and robust to 0.5 mm / 0.5 mrad i.i.d. row noise
(4/4), but not to 1 mm / 1 mrad (0/4): the guard rim must enter the lower clip channels within a 0.65 mm axial window.
