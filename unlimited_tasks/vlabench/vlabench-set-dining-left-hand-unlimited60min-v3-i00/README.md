# vlabench-set-dining-left-hand-unlimited60min-v3-i00

unlimited task, protocol: `docs/prompts/metaworldplus_codex_luna_high_two_modes.md`. Historical source: `staging/coverage/vlabench/vlabench-set-dining-left-hand-i00`.
Frozen instance SHA256: `ca2197b64e791c52f6b02adb622278c927e436b4b581915981376bafa1640002`.

## Difficulty
Same native instance and success predicate; 60 minute agent deadline.

## Reference solution
Trusted reference only; use `scripts/two_modes/run.py smoke`. No expert in the evaluated main container.

## Verification
Independent two-process replay. Limited additionally requires online/replay exact agreement.
Use the unified runner for lifecycle, isolation, timeout adjudication and evidence collection.
This task revision has no inherited model score. See suites/two-modes.json for validation status.
