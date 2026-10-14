# DexHand family `sweep_dustpan` (authoring notes)

Scene T13 of the scene-expansion set, "Sweep debris into a held dustpan", packaged as a DexHand plugin family
(`scripts/dexhand/generate.py --only-family sweep_dustpan` writes `tasks/dexhand-sweep-dustpan-i00-{privileged,standard}`).
Registration and the runtime/replay contracts: `artifacts/ready-10-2026-10-14/FAMILY_PLUGIN.md`; hand selection:
`HAND_INTERFACE.md` next to it (workspace paths).

## What is frozen

| file | content |
|---|---|
| `assets/sweep_sharpa.xml` | the accepted episode's MuJoCo model (`model.xml` sha256 `7679a0d2...`), byte-identical except mesh paths turned into `${DEXHAND_ASSET_DIR}` / `${TIANJI_ASSET_DIR}` tokens and four fixed cameras (overview, work, pan, side) added at the start of `<worldbody>` |
| `assets/reset.npz` | the accepted `initial_qpos` (168) and first control row (the pre-held hold targets), with the joint/actuator layout used to carry the reset over to the Wuji composition by name |
| `assets/external_assets.json` | the 144 meshes the model loads from the image (54 Sharpa Wave files under `/opt/dexhand/hand`, 90 Tianji Marvin STL files under `/opt/dexhand/tianji`), sha256 + size; `runtime.scene_xml()` verifies all of them before compiling |
| `assets/manifest.json` | sha256 of the three files above |
| `solution/trajectory.json` + `trajectory.part00..04.npz` | the accepted 132,521 x 58 float64 controls plus 16,000 copies of their last row (8 s lifted-pan hold), `hand = "sharpa"`, as parts below 2 MB (`scripts/dexhand/shared/solution/solution_parts.py`; `rows_sha256` 826f6e5b...) |
| `provenance.json` | where the accepted run and its reviews live (never copied into a task) |

`tools/build_assets.py` regenerates all of these from the accepted run (deterministic bytes). Provenance of the accepted
run: `artifacts/everyday-dexterity-2026-10-13/sweeping/strong-index-cleanup/native-trial/` (controller wrapper
`../run.py` on `scripts/everyday_dexterity/sweep_demo.py`), accepted in
`artifacts/scene-expansion-50/reports/T13-manager.json`; approved film
`artifacts/scene-expansion-50/evidence/trajectory-r1/T13/root-review/approved-success.mp4`.

## Control and predicate

One action row = the 58 (Sharpa) or 54 (Wuji) motor targets for one native 0.5 ms physics step (2000 Hz): the accepted
controls change at every physics step, so this is the only rate at which they replay bit for bit. `runtime.Session`
reproduces the accepted ordering exactly (`mj_resetData`, initial qpos, `mj_forward` with zero controls, then the hold
targets; per row: set `ctrl`, `mj_step`, evaluate). `checker.py` re-implements the accepted audit
(`scripts/everyday_dexterity/replay_sweep.py`, `NativeAudit`) vectorized over contacts and adds the release rules:

- success = 2000 consecutive physics steps (1.0 s) with all six pieces' collision shapes inside the moving pan
  (1 mm margins, 0.131 m half depth, 0.11 m height), all six touching the pan, pan lifted >= 0.05 m, debris speed
  < 0.03 m/s and spin < 0.8 rad/s, every piece brushed by the bristles at some time; success ends the episode;
- fail-fast (permanent, ends the episode): a piece outside the work area (x in [0.45, 1.00] m, y in [-0.50, 0.40] m,
  centre between 0.01 m below and 0.25 m above the floor), any robot-debris contact (>= 1 mN), after 1.2 s a tool held by
  fewer than two force-bearing (>= 10 mN) hand geoms, grip drift >= 25 mm or rotation >= 0.25 rad since 1.2 s, a tool
  pressed > 10 mN by a robot link other than its own hand, torso/arm/cross-hand self contact, unstable physics, and the
  160,000-row horizon;
- dropped from the accepted audit: its `t >= 16.2 s` gate on the terminal predicate (a time gate, not a physical
  criterion); every physical condition is kept and the audit's end-of-run checks became fail-fast rules.

The accepted run's extremes (all 132,521 steps): debris x 0.599-0.846 m, y -0.240-0.163 m, height <= 0.097 m above the
floor; minimum 7 hand contacts per shaft; grip drift 5.67 mm, rotation 0.2293 rad; terminal run 2,129 steps at the end.
Float32 rounding of the controls already breaks success (rotation 0.2575 rad > 0.25,
`artifacts/ready-10-2026-10-14/sweep/analysis/float32-rounded-replay.json`), which is why the standard oracle
submits float64 rows.

## Hands: Sharpa only (Wuji Hand 2.2 pending)

`family.json` declares `"hands": ["sharpa"]`; `runtime.Session` refuses any other hand (argument or `DEXHAND_HAND`)
and the replay rejects archives labelled with another hand (manager decision 2026-10-14, as for
`essential_two_object`). Why Wuji is pending: `hands.replace_wave_hands(root, "wuji")` composes the genuine
left/right Wuji Hand 2.2 at the same flanges (54 actuators: 14 arm + 20 + 20), but the broom and dustpan are pre-placed
where the Sharpa grip holds them. Of 48 Wuji closing-target candidates (`tools/search_wuji_grip.py`, 2.5 s each,
`artifacts/ready-10-2026-10-14/sweep/wuji/grip-search-v2.json`), 36 fail before 1.2 s because the tipping broom
touches another robot link and 12 fail at 1.2 s with at most one force-bearing right-hand contact on the broom (the
left hand reaches 2-6 contacts on the dustpan handle). A Wuji variant needs its own pre-grasp (tool poses or arm
targets for the Wuji hand), i.e. a new frozen instance. The composition stays available to authoring tools via
`Session(hand="wuji", allow_unsupported_hand=True)`.

## Oracle robustness

The 66 s episode is chaotic: any perturbation of the rows (even float32 rounding) gives a different rollout. With
the 8 s hold padding (`tools/perturbation_study.py --extra-hold 12000` on the 2 s-padded rows = the packaged 8 s
padding; `artifacts/ready-10-2026-10-14/sweep/robustness/`): float32 rounding 0/1, Gaussian noise on the finger
targets 1e-6 rad 8/10, 1e-4 rad 7/10 and 1e-3 rad 9/10 succeed (24/30; 20/30 with a 2 s padding). The binding quantities are the broom's rotation in the hand
(0.22-0.24 rad in every rollout against the 0.25 rad bound; >= 7 hand contacts and <= 5.8 mm drift, so not grip force;
firmer finger targets make it worse) and the pieces' spin in the lifted pan for the 1 s hold. Bounds unchanged.

## Commands

```bash
cd robot_coding_bench
export PYTHONPATH=scripts/dexhand/families/sweep_dustpan:scripts/dexhand/shared \
  DEXHAND_ASSET_DIR=$PWD/images/dexhand/assets/hand MUJOCO_GL=egl OPENBLAS_NUM_THREADS=1
python scripts/dexhand/families/sweep_dustpan/tools/build_assets.py           # frozen assets + oracle
python scripts/dexhand/families/sweep_dustpan/tools/bitexact.py --out $OUT/bitexact.json
python scripts/dexhand/families/sweep_dustpan/replay.py --task sweep_dustpan \
  --traj $OUT/oracle.npz --out $OUT/r1.json [--video $OUT/r1.mp4]   # $OUT/oracle.npz: see tools/make_negatives.py (oracle.npz)
python scripts/dexhand/families/sweep_dustpan/tools/make_negatives.py --out $OUT/sweep-negatives
python -m pytest -q scripts/dexhand/families/sweep_dustpan/tests
python3 scripts/dexhand/generate.py --only-family sweep_dustpan --refresh-manifest
```

Evidence of the packaging run (commands, JSON verdicts, videos, Harbor results):
`artifacts/ready-10-2026-10-14/reports/w-sweep.md`.
