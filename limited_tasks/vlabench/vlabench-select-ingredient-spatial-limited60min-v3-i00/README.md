# vlabench-select-ingredient-spatial-limited60min-v3-i00

limited task, protocol: `docs/prompts/metaworldplus_codex_luna_high_two_modes.md`. Historical source: `staging/coverage/vlabench/vlabench-select-ingredient-spatial-i00`.
Frozen instance SHA256: `8171d254380853e5756f7cdee93a53d6ad0a8f24c8495595e496ae89a99c6c9e`.

## Difficulty
Same native instance and success predicate; 60 minute agent deadline.

## Reference solution
Trusted reference only; use `scripts/two_modes/run.py smoke`. No expert in the evaluated main container.

## Verification
Independent two-process replay. Limited additionally requires online/replay exact agreement.
Use the unified runner for lifecycle, isolation, timeout adjudication and evidence collection.
This task revision has no inherited model score. See suites/two-modes.json for validation status.
