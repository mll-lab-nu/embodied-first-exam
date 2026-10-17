# bicycle_pump_stroke (authoring notes)

DexHand family built from scene-expansion scene T50 "Inflate a tire with a portable bicycle pump" (a kinematic demo:
prescribed head insertion, 28 prescribed piston cycles, no hands). Here a dexterous hand on the right arm of a Tianji
Marvin robot connects the hose head to the valve (push on, close the thumb lock), pumps physically (28 strokes from
the source's 200.0 kPa) and disconnects the head again (open the lock, pull the head off), as in the source.

## Files
| file | role |
|---|---|
| `scene.py` | MJCF: the Marvin rig (`shared/arm_rig.py`; hand on the right flange under `wrist_stage`, left arm parked), bench/wheel/valve/head/hose (static, film pose), free pump with passive piston |
| `checker.py` | stroke counter, pressure, ordered stages, terminal hold, fail-fast (state only) |
| `runtime.py` | `Session` (FAMILY_PLUGIN section 4, plus `validate`, `snapshot`/`restore` for search) |
| `replay.py` | fresh-process replay CLI (section 5), optional `--video` |
| `task.json` | frozen instance: thresholds, pump parameters, cameras, per-hand start targets |
| `assets/` | `t50_scene.json` (geoms, colours, poses at film frame 50), meshes (smooth tire, rim, head shells), `manifest.json` (sha256) |
| `tools/extract_source.py` | one-off copy of the approved scene-v4 export into `assets/` |
| `tools/arm_port.py` | authoring: records the wave-2 floating-stage witness's hand poses, sets the arm start pose, repeats one stroke cycle to 28 strokes and tracks the hand path with the arm (`shared/arm_ik.py`); writes `solution/trajectory.npz` (no Wuji witness in this version) |
| `tools/film_export.py` | native pose export of a replay for the Blender film (`verify` re-checks every sample bit for bit) |
| `tools/studio_film.py` | Blender 4.5.3 studio film, copied from the approved T50 film renderer (materials, lights, camera) |
| `tests/test_bicycle_pump_stroke.py` | authoring tests (positive, nop, truncation, knock fail-fast, snapshot, forged/ambiguous members, width, NaN, range, hand label, Wuji) |

## Modelling choices
- Pump: free rigid body (source masses: barrel 65 g, housing 17 g, cap 5 g, foot 10 g; rod 10 g, T handle 18 g) on the
  source's 70 x 28 mm foot. Base contact over-damped (`solref 0.005 3`): a hard plastic foot does not ring on its
  soft-contact springs. The exposed piston rod and T handle are solid for the hand.
- Piston: slide `piston_extension` (0 = down, 0.20 m = up), linear air spring 200 N/m with reference 0.23 m (6 N at the
  top, 46 N at the bottom; the source's isothermal chamber reaches a 52 N plateau at 2.1 bar), damping 15 N s/m,
  seal friction 1 N (source value). The spring returns the handle; the inlet refill is not simulated.
- Pressure: checker quantity, 380 Pa per counted stroke (source: 200.0 -> 210.6 kPa in 28 strokes); start at the
  source's 200.0 kPa, so the source's 28 strokes reach 210.64 kPa and the 210.6 kPa target (27 do not).
- Robot (wave 3): the Tianji Marvin stand at the world origin of the T50 frame (the source scene was built for it),
  facing +x; two 7-DoF arms (pot_shelf_transfer's robot: kp 700, kv 48, no gravity compensation); the right flange
  carries the working hand under the fixed body `wrist_stage`, the left arm is parked with its hand open. Every
  robot body (both hands, arm links, stand) counts as the hand for the release condition. The wave-2 Sharpa tweaks
  (fingertip friction 1.5, finger velocity feedback -0.9) are applied before mounting, so both Waves carry them.
- Head (wave 3): starts disconnected as in the source's frame 0 (17.5 mm out along the stem axis = 8 mm gap + 9.5 mm
  core engagement; thumb lock up). Body `pump_head` on the passive slide `head_slide` along the stem axis (the hose
  guides it: no lateral play; 2 N friction with a stiff friction constraint so it does not creep; seat = end stop at
  -17.5 mm) carrying the source's head, collar and hose-neck geometry; the thumb lock `thumb_lock` on the passive hinge
  `lever_angle` (source axis: world y at the lever's foot; 0 = up/open, 1.65 rad = closed; 0.004 N m friction).
  Connected (latched) = seated within 0.5 mm and the lever within 0.15 rad of closed; strokes are armed and counted
  only while the head is seated and locked like this at that substep; until the pressure is reached a head pulled back
  > 2 mm or a lever opened below 1.2 rad is `head_disconnected`. Disconnected (latched, after the pressure) = lever
  opened to <= 0.5 rad and head pulled >= 12.5 mm back off its seat (beyond the 9.5 mm core engagement); pulling the
  head back > 2 mm while the lever is still >= 1.2 rad is `head_forced_off`. The final hold also requires no robot
  contact with the head.
  The cam's clamping force and the grommet/core seal are not simulated. Head and lever never collide with the static
  wheel/valve/hose (they move on their guided joints); the last four hose segments ride with the head (display
  only). Wheel, valve and hose are static world geometry at the approved film pose; hose segments 0-1 at the pump
  outlet are visual only so the free pump never leans on a static hose. Rim/tire contact uses hidden capsule rings; the visual rim
  and smooth tire are the film's meshes.
  The Sharpa fingertip pads use the vendor's very soft elastomer contact, so a pressing fingertip can engulf the 1 mm-radius wheel spokes (a contact-model property; the head and lock states come only from their own joints and contacts).

## Provenance
Source scene: `robot_coding_bench/scripts/scene_expansion/tasks/bicycle_pump/` (T50; Topeak MINI MORPH TMM-2B pump with
TRK-RP04 head, Schwalbe Big Apple 57-406 tire on a 406 x 25C rim, `parameters.json` for masses/stroke/gas estimates)
and its approved film export `scene-v4` of the scene-expansion evidence (copied by
`tools/extract_source.py`; hashes in `assets/t50_scene.json` and `assets/manifest.json`). The source was a kinematic
demo (prescribed head insertion and 28 prescribed piston cycles, no hands); this family keeps its objects, look and
goal and makes the pumping physical.

## Verdict notes (reviewer lessons L1-L3, 2026-10-14)
- L1: every fail-fast condition fires at the first physics substep it holds (no debounce window); the pump cannot be
  lifted more than 2 cm, so there is no drop-and-catch case.
- L2: `pump_speed_m_s` is `mj_objectVelocity(mjOBJ_BODY)`, i.e. the centre-of-mass velocity (checked against a finite
  difference of `xipos`: < 0.4 mm/s apart); nothing is added to it.
- L3: `state_sha` hashes the integration state, the predicate state, the hand and only the physics/predicate keys of
  `task.json` (`HASHED_CONFIG_KEYS` in runtime.py), never instruction prose, titles or cameras.

## Simplifications (disclosed in the instruction)
- The head starts disconnected, must be connected and locked, and must be unlocked and pulled off again at the end
  (the source's stages). The head is guided along the stem axis (no lateral misalignment).
- Air is not simulated: tire pressure is a checker quantity, 200.0 kPa + 380 Pa per counted stroke (the source's 28
  strokes). The piston's air is a linear spring (it returns the handle).
- Wheel, valve and hose are static props.

## Evidence
The authoring evidence (status, replays, Harbor trials, films) is kept outside the repository with the wave-2 worker
records.

```bash
export DEXHAND_ASSET_DIR=<robot_coding_bench>/images/dexhand/assets/hand WUJI_ASSET_DIR=<...>/assets/wuji_v2_2
python tools/arm_port.py poses --hand sharpa --old <wave-2 bicycle_pump_stroke folder> --out <dir>/poses_sharpa.npz
python tools/arm_port.py ready --hand sharpa --poses <dir>/poses_sharpa.npz     # initial_targets in task.json
python tools/arm_port.py author --hand sharpa --poses <dir>/poses_sharpa.npz --swing-over 0.3 --hold-extra 100 \
    --out solution/trajectory.npz
python replay.py --task bicycle_pump_stroke --traj solution/trajectory.npz --out <dir>/r.json   # twice: same state_sha
python -m pytest -q tests/test_bicycle_pump_stroke.py
# film (GPU): native pose export, exact re-check, Blender render + captions
python tools/film_export.py export --trajectory solution/trajectory.npz --export <film dir> \
    --source-scene <T50 scene-v4 export>/scene.json --stride 3
python tools/film_export.py verify --trajectory solution/trajectory.npz --export <film dir>
python tools/studio_film.py --export <film dir> --output <film dir>/bicycle_pump_stroke.mp4 --width 1280 --height 720 \
    --samples 16 --fps 25 --blender <blender 4.5.3>
```
