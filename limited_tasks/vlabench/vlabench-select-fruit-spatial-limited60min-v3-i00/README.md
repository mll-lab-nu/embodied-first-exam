# vlabench-select-fruit-spatial-limited60min-v3-i00

limited task, protocol: `docs/prompts/metaworldplus_codex_luna_high_two_modes.md`. Historical source: `staging/coverage/vlabench/vlabench-select-fruit-spatial-i00`.
Frozen instance SHA256: `6a80604b02564f42bc77454d5489b83e90e62541a2ae06a44bf5af5c0e6d6a36`.

## Difficulty
Same native instance and success predicate; 60 minute agent deadline.

## Reference solution
Trusted reference only; use `scripts/two_modes/run.py smoke`. No expert in the evaluated main container.

## Verification
Independent two-process replay. Limited additionally requires online/replay exact agreement.
Use the unified runner for lifecycle, isolation, timeout adjudication and evidence collection.
This task revision has no inherited model score. See suites/two-modes.json for validation status.
