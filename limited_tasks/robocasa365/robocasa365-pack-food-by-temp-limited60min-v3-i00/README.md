# robocasa365-pack-food-by-temp-limited60min-v3-i00

limited task, protocol: `docs/prompts/metaworldplus_codex_luna_high_two_modes.md`. Historical source: `tasks/robocasa365-pack-food-by-temp-privileged-i00`.
Frozen instance SHA256: `6cbd09d0f06aa838e5827d840f1a762e0ae7ee3e227b52731c4df2fc137d72fa`.

## Difficulty
Same native instance and success predicate; 60 minute agent deadline.

## Reference solution
Trusted reference only; use `scripts/two_modes/run.py smoke`. No expert in the evaluated main container.

## Verification
Independent two-process replay. Limited additionally requires online/replay exact agreement.
Use the unified runner for lifecycle, isolation, timeout adjudication and evidence collection.
This task revision has no inherited model score. See suites/two-modes.json for validation status.
