# robocasa-turn-off-stove-unlimited60min-v3-i00

unlimited task, protocol: `docs/prompts/metaworldplus_codex_luna_high_two_modes.md`. Historical source: `tasks/robocasa-turn-off-stove-privileged-i00`.
Frozen instance SHA256: `350b328f84e28c5420c0ef43a2074fab15bba475e9d79b02fcfed692215f51d0`.

## Difficulty
Same native instance and success predicate; 60 minute agent deadline.

## Reference solution
Trusted reference only; use `scripts/two_modes/run.py smoke`. No expert in the evaluated main container.

## Verification
Independent two-process replay. Limited additionally requires online/replay exact agreement.
Use the unified runner for lifecycle, isolation, timeout adjudication and evidence collection.
This task revision has no inherited model score. See suites/two-modes.json for validation status.
