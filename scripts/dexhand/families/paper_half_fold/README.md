# DexHand family `paper_half_fold` (scene T06)

Self-owned DexHand family (`family.json`, FAMILY_PLUGIN contract). `scripts/dexhand/generate.py --only-family
paper_half_fold` writes `tasks/dexhand-paper-half-fold-i00-{privileged,standard}` from this folder; never edit the
generated directories.

| file | reaches a task | role |
|---|---|---|
| `task.json` | yes (as `instance.json`) | frozen instance: original T06 `config` (unchanged), support/workspace limits, Wuji reset, model hash |
| `scene_sharpa.xml` | yes | the accepted episode's compiled-model XML (`trial-01/model.xml`, meshdir replaced by a placeholder) |
| `shell.py` | yes | the unchanged passive elastic/plastic paper shell (sha256 `1a7a9278...`) |
| `runtime.py` | yes | `Session`: build, step, predicate, fail-fast, status, hashes, snapshot/restore, trajectories |
| `replay.py` | yes | fresh-process replay CLI used by both graders |
| `instruction/*.md`, `README.task.md` | rendered | task texts |
| `solution/trajectory.npz` | `solution/` only | the accepted episode's 1,108 Sharpa rows + 250 copies of the last row (`actions`, `hand`, `task`, `actuator_names`); float32-rounded rows succeed at row 1,109 |
| `tests/`, `tools/`, this README | no | authoring checks and evidence |

`hands.py` and `rcb_dexhand.py` come from `scripts/dexhand/shared/` (the generator copies them in).

## Provenance and physics identity

Source scene: `scripts/scene_expansion/repairs/paper_recovery/` (accepted T06 delivery, `artifacts/scene-expansion-50/
reports/T06-manager.json`), episode `artifacts/scene-expansion-50/evidence/paper-recovery-v3/trial-01`. That folder,
`scripts/dexhand/paper_folding/` and `artifacts/sharpa-paper-folding/` are read-only sources; nothing there is edited.

- `scene_sharpa.xml` + the original post-compile settings (flex edge `solref/solimp`, vertex damping) compile to a
  binary model byte-identical to the accepted `model.mjb` (sha256 `665706cd6ef8a63dddba743a9d715e7ca289ccc16f9f0514c4cbcd72693afd51`).
  `Session` recomputes this hash at start and refuses a different model (for example changed image assets).
  The XML already contains the accepted task-local contact geometry (distal shell colliders, middle-fingertip source
  elastomer/DP colliders) produced by `paper_recovery/{physical_adapter,contact_model}.py`; those builders and the
  `sharpa_surfaces` package are therefore not needed at run time.
- `runtime.step` keeps the original order (`shell.apply`, `mj_step` x 40, `mj_forward`, features, predicate). The
  added checks only read state. `tools/verify_oracle.py` proves the identity: every control-boundary state and paper
  material array equals the accepted `saved-states.npz` exactly, and the accepted runtime's own hash rule gives the
  accepted initial/final hashes `a29f0701...`/`8e47b346...`.

## Predicate (strict)

Released goal (all at once): fold angle > 2.6 rad, mean central plastic crease > 2.2 rad, crease coverage >= 0.9,
edge alignment < 18 mm, strain < 0.08, no hand-paper contact, and every paper vertex over the table top
(x in [-0.345, 0.135] m, |y| <= 0.30 m, z >= 0.298 m). Success = 100 consecutive released-goal samples; it ends the
episode. Fail-fast, permanent, checked after every 0.5 ms substep: any vertex below z = 0.29 m (10 mm under the
table top; the free overhang's own sag is 5.1 mm in the no-op), any vertex outside x in [-0.03, 0.19], |y| <= 0.09,
z <= 0.45, strain > 0.08, unstable physics; and 1,500 controls without success. Stages for diagnostics: folded,
creased, released on the table, held.

## Hands

Sharpa Wave is the accepted scene. Wuji Hand 2.2: `hands.replace_wave_hands` swaps the hand subtree on the same wrist
stage and mount frame; unreferenced Sharpa mesh assets are then dropped so the compiled Wuji model (and its hash) does
not depend on MuJoCo's process-wide mesh cache. Wuji reset: the same six wrist targets, fingers curled
(`wuji_initial_fingers`) so nothing touches the table or paper at reset (straight fingers would start 19 mm inside
the table). A Wuji success is packaged: `solution/wuji/trajectory.npz` (see Wuji reference solution).

## Wuji reference solution

`solution/wuji/trajectory.npz` (620 x 26 rows, `hand` = `wuji`, sha256 `5e470618...`) folds and creases the sheet
with the Wuji Hand 2.2; success at control 554 (all four stages, then the 100-sample released hold), so 66 rows of
slack remain. Rows are wrist-stage and finger position targets only. The script `tools/wuji_gen.py` writes it:
roll the hand palm up below the table edge and slide the four fingertip pads under the 25 mm overhang, rotate the
hand rigidly about the fold line by 2.95 rad (the free half turns with the pads and the fold-line hinges yield),
press lightly on the folded stack, then lift 6 cm and hold still. The generator packages the file as
`solution/wuji/` of both task directories, and the oracle uses it when the run selects the Wuji hand. 15 of 16
one-parameter variants of the script also succeed, and float32-rounded rows succeed.

```bash
PYTHONPATH=tasks/dexhand-paper-half-fold-i00-privileged/environment \
  python3 scripts/dexhand/families/paper_half_fold/tools/wuji_gen.py --out $OUT/wuji.npz   # the identical archive
```

Evidence (2026-10-14): `artifacts/ready-10-2026-10-14/wuji-success/paper_half_fold/`.

## Checks and evidence

```bash
cd robot_coding_bench
export DEXHAND_ASSET_DIR=$PWD/images/dexhand/assets/hand OPENBLAS_NUM_THREADS=1
python3 -m pytest -q scripts/dexhand/families/paper_half_fold/tests       # ~4 min
python3 scripts/dexhand/families/paper_half_fold/tools/verify_oracle.py \
  --trial ../artifacts/scene-expansion-50/evidence/paper-recovery-v3/trial-01 --out $OUT/paper-oracle.json
python3 scripts/dexhand/families/paper_half_fold/tools/make_controls.py --out $OUT/paper-controls
bash scripts/dexhand/families/paper_half_fold/tools/run_evidence.sh $OUT/paper-controls $OUT/paper-evidence
```

`make_controls.py` writes the positive and the negative controls (no-op, fold without the crease press, early stop,
pull over the table edge, forged success flags, wrong widths, Wuji hold and motion); `run_evidence.sh` replays each
twice in fresh processes and records an mp4 of each physical one. The 2026-10-14 results are in
`artifacts/ready-10-2026-10-14/paper/` and `artifacts/ready-10-2026-10-14/reports/w-paper.md`.

## Modelling scope

9 x 5 triangular MuJoCo flex shell, 160 x 100 mm, 1.28 g, uncalibrated elastic/plastic bending memory with weakening;
the left half is adhered to a visible backing (pinned vertices); 0.35 mm contact radius (0.7 mm effective thickness);
finite contact compliance (a 0.17 mm rigid/table overlap occurs in the accepted fold). A reduced passive-paper model,
not a fibre or adhesive-peel model. Single right hand on a six-DoF wrist stage, not an arm.
