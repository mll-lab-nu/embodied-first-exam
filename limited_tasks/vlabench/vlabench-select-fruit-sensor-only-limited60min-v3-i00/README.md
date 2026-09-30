# vlabench-select-fruit-sensor-only-limited60min-v3-i00

limited task, protocol: `docs/prompts/metaworldplus_codex_luna_high_two_modes.md`. Historical source: `staging/removed-duplicates/vlabench-select-fruit-sensor-only-i00`.
Frozen instance SHA256: `bbabe8e56d823ab512bcd0bd20481a24289c71857e0063c12950bd58ac7ac901`.

## Difficulty
Same native instance and success predicate; 60 minute agent deadline.

## Reference solution
Trusted reference only; use `scripts/two_modes/run.py smoke`. No expert in the evaluated main container.

## Verification
Independent two-process replay. Limited additionally requires online/replay exact agreement.
Use the unified runner for lifecycle, isolation, timeout adjudication and evidence collection.
This task revision has no inherited model score. See suites/two-modes.json for validation status.
