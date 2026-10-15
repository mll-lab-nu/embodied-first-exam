# bicycle_pump_stroke (authoring notes)

DexHand family built from scene-expansion scene T50 "Inflate a tire with a portable bicycle pump" (a kinematic demo:
prescribed head insertion, 28 prescribed piston cycles, no hands). Here a dexterous hand pumps the pump physically.

## Files
| file | role |
|---|---|
| `scene.py` | MJCF: hand on the six-axis wrist stage (palm-down mount), bench/wheel/valve/head/hose (static, film pose), free pump with passive piston |
| `checker.py` | stroke counter, pressure, ordered stages, terminal hold, fail-fast (state only) |
| `runtime.py` | `Session` (FAMILY_PLUGIN section 4, plus `validate`, `snapshot`/`restore` for search) |
| `replay.py` | fresh-process replay CLI (section 5), optional `--video` |
| `task.json` | frozen instance: thresholds, pump parameters, cameras, per-hand start targets |
| `assets/` | `t50_scene.json` (geoms, colours, poses at film frame 50), meshes (smooth tire, rim, head shells), `manifest.json` (sha256) |
| `tools/extract_source.py` | one-off copy of the approved scene-v4 export into `assets/` |
| `tools/controller.py` | authoring controller (closed loop on the pump pose, recorded as open-loop rows) |
| `tools/make_oracles.py` | deterministic regeneration of `solution/trajectory.npz` (Sharpa) and `solution/wuji/trajectory.npz` |
| `tools/negatives.py` | negative cases replayed in fresh processes |
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
- Pressure: checker quantity, 380 Pa per counted stroke (source: 200.0 -> 210.6 kPa in 28 strokes); start at
  207.8 kPa so 6 strokes reach the source's 210 kPa target (5 do not).
- Head pre-locked on the Schrader valve (the source's connection/locking stages are not part of this task); wheel,
  valve, head and hose are static world geometry at the approved film pose; hose segments 0-1 at the pump outlet are
  visual only so the free pump never leans on a static hose. Rim/tire contact uses hidden capsule rings; the visual rim
  and smooth tire are the film's meshes.

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
  `task.json` (`HASHED_CONFIG_KEYS` in runtime.py), never instruction prose, titles or cameras. Evidence hashes:
  Sharpa oracle `0c9d801c...`, Wuji oracle `5e5ed684...`.

## Simplifications (disclosed in the instruction)
- The head starts locked on the Schrader valve; connecting/unlocking are not part of the task.
- Air is not simulated: tire pressure is a checker quantity, 207.8 kPa + 380 Pa per counted stroke; 6 strokes instead of
  the source's 28 (partly inflated start). The piston's air is a linear spring (it returns the handle).
- Wheel, valve, head and hose are static props.

## Evidence
The authoring evidence (status, replays, Harbor trials, films) is kept outside the repository with the wave-2 worker
records.

```bash
export DEXHAND_ASSET_DIR=<robot_coding_bench>/images/dexhand/assets/hand WUJI_ASSET_DIR=<...>/assets/wuji_v2_2
python tools/make_oracles.py --out solution                       # deterministic; same sha256 as committed
python replay.py --task bicycle_pump_stroke --traj solution/trajectory.npz --out <dir>/r.json   # twice: same state_sha
python tools/negatives.py --oracle solution/trajectory.npz --params "$(python -c 'import sys,json; sys.path.insert(0,"tools"); import make_oracles as m; print(json.dumps(m.PARAMS["sharpa"]))')" --out <dir>/neg
python -m pytest -q tests/test_bicycle_pump_stroke.py
# film (GPU): native pose export, exact re-check, Blender render + captions
python tools/film_export.py export --trajectory solution/trajectory.npz --export <film dir> \
    --source-scene <T50 scene-v4 export>/scene.json --stride 3
python tools/film_export.py verify --trajectory solution/trajectory.npz --export <film dir>
python tools/studio_film.py --export <film dir> --output <film dir>/bicycle_pump_stroke.mp4 --width 1280 --height 720 \
    --samples 16 --fps 25 --blender <blender 4.5.3>
```
