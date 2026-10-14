# DexHand sources

The benchmark, its ten families, their predicates, hands and grading: [docs/benchmarks/dexhand.md](../../docs/benchmarks/dexhand.md).
Never edit the generated `tasks/dexhand-*` directories; edit the sources here and regenerate.

| Path | What it is |
|---|---|
| `generate.py` | renders both modes of every family into `tasks/` (`--release`, `--check`, `--list`, `--only-family`) and ends with `scripts/task_conventions.py` `normalize` |
| `release.json` | the ten families of the release |
| `task_library/<family>/` | the six essential families: `task.json`, `scene.py`, `assets/` (manifest, credits), `render.json`, `README.md`, `solution/` (optional `solution/wuji/`: a Wuji reference solution, with its authoring script in `tools/`), optional `wuji_reset.json`; registered in `task_library/index.json` |
| `library.py`, `sync_essential_catalog.py`, `essential_catalog.json` | registration check of the task library and the frozen catalog the generator renders (run `sync_essential_catalog.py` after editing a `task.json`) |
| `families/<family>/` | the plugin families (`assemble_hamburger`, `paper_half_fold`, `sweep_dustpan`, `pot_shelf_transfer`): `family.json` registers the folder; runtime, replay, assets, texts, oracle (optional `solution/wuji/` for the Wuji hand), authoring notes, `tools/` and tests |
| `shared/` | one source each, copied unchanged into every task: `rcb_dexhand.py`, `hands.py` (hand selection, Wuji composition, trajectory archives), the essential runtime (`runtime.py`, `scene.py`, `checker.py`, `essential*.py`, `replay.py`), the privileged grader `grade.py`, `standard/` (sim service, collect hook, standard grader) and `solution/` (oracle runners, multi-part rows; `solve_*_by_hand.sh` for a task with a per-hand solution) |
| `verify_oracles.py` | binds the essential oracles to their recorded evidence (needs the authors' evidence directory, which is not in the repository) |
| `tests/` | `test_grading.py` (graders on stub replays; standard library only, run by `ci_checks/check-unit-tests.sh`), `test_essential.py`, `test_essential_strict.py` (the six essential families) and `test_family_plugin.py` (the generator; pytest, MuJoCo) |

```bash
python3 scripts/dexhand/generate.py --release && python3 scripts/dexhand/generate.py --check --release
python3 scripts/dexhand/tests/test_grading.py
# MuJoCo suites (images/dexhand/requirements.txt + pytest; DEXHAND_ASSET_DIR, WUJI_ASSET_DIR, TIANJI_ASSET_DIR at the
# prepared images/dexhand/assets/{hand,wuji_v2_2,tianji}); run each suite in its own process:
python3 -m pytest scripts/dexhand/tests
python3 -m pytest scripts/dexhand/families/assemble_hamburger/test_task.py
python3 -m pytest scripts/dexhand/families/paper_half_fold/tests
python3 -m pytest scripts/dexhand/families/pot_shelf_transfer/tests
python3 -m pytest scripts/dexhand/families/sweep_dustpan/tests
```
