# DexHand sources

The benchmark, its ten families, their predicates, hands and grading: [docs/benchmarks/dexhand.md](../../docs/benchmarks/dexhand.md).
Never edit the generated `tasks/dexhand-*` directories; edit the sources here and regenerate.

| Path | What it is |
|---|---|
| `generate.py` | renders both modes of every family into `tasks/` (`--release`, `--check`, `--list`, `--only-family`) and ends with `scripts/task_conventions.py` `normalize` |
| `sources.py` | the family files the generator copies unchanged into the tasks (runtime code, assets, oracle trajectories, essential `scene.py`) are committed only in the generated task directories; `sources.py` stages each family's source folder from its folder plus those copies (a file in the family folder wins), `--unpack [family ...]` writes the copies into the family folders for authoring tools and tests, `--clean` removes family-folder files equal to their task copy |
| `release.json` | the ten families of the release |
| `task_library/<family>/` | the six essential families: `task.json`, `assets/` (manifest with licenses, provenance), `render.json`, `README.md`, authoring scripts in `tools/`; `scene.py`, the packaged assets, `solution/` (optional `solution/wuji/`) and `wuji_reset.json` are in the family's generated privileged task (`sources.py`); registered in `task_library/index.json` |
| `library.py`, `sync_essential_catalog.py`, `essential_catalog.json` | registration check of the task library and the frozen catalog the generator renders (run `sync_essential_catalog.py` after editing a `task.json`) |
| `families/<family>/` | the plugin families: `family.json` registers the folder; texts, authoring notes, `tools/` and tests; the runtime files, assets and oracle (optional `solution/wuji/` for the Wuji hand) it declares are in the family's generated tasks (`sources.py`) |
| `shared/` | one source each, copied unchanged into every task: `rcb_dexhand.py`, `hands.py` (hand selection, Wuji composition, trajectory archives), the essential runtime (`runtime.py`, `scene.py`, `checker.py`, `essential*.py`, `replay.py`), the privileged grader `grade.py`, `standard/` (sim service, collect hook, standard grader), `solution/` (oracle runners, multi-part rows; `solve_*_by_hand.sh` for a task with a per-hand solution) and `arm_rig.py` (the Tianji Marvin arm rig, copied only into the families that list it in `family.json` `runtime.shared`); `arm_ik.py` (arm IK and closed-loop tracking for converting wrist-stage episodes into arm rows) is authoring only and never copied into a task |
| `verify_oracles.py` | binds the essential oracles to their recorded evidence (needs the authors' evidence directory, which is not in the repository) |
| `tests/` | `test_grading.py` (graders on stub replays; standard library only, run by `ci_checks/check-unit-tests.sh`), `test_essential.py`, `test_essential_strict.py` (the six essential families) and `test_family_plugin.py` (the generator; pytest, MuJoCo) |

```bash
python3 scripts/dexhand/generate.py --release && python3 scripts/dexhand/generate.py --check --release
python3 scripts/dexhand/tests/test_grading.py
python3 scripts/dexhand/sources.py --unpack    # before the MuJoCo suites and authoring tools; --clean afterwards
# MuJoCo suites (images/dexhand/requirements.txt + pytest; DEXHAND_ASSET_DIR, WUJI_ASSET_DIR, TIANJI_ASSET_DIR at the
# prepared images/dexhand/assets/{hand,wuji_v2_2,tianji}); run each suite in its own process:
python3 -m pytest scripts/dexhand/tests
python3 -m pytest scripts/dexhand/families/assemble_hamburger/test_task.py
python3 -m pytest scripts/dexhand/families/paper_half_fold/tests
python3 -m pytest scripts/dexhand/families/pot_shelf_transfer/tests
python3 -m pytest scripts/dexhand/families/sweep_dustpan/tests
```
