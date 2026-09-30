# metaworldplus-pick-place-limited60min-v3-i02

limited task, protocol: `docs/prompts/metaworldplus_codex_luna_high_two_modes.md`. Historical source: `tasks/metaworldplus-pick-place-privileged-i02`.
Frozen instance SHA256: `de0f1dd248f6280432e5090dfe187e85cf76f2dac8f2bcb45c5d199d30835dc3`.

## Difficulty
Same native instance and success predicate; 60 minute agent deadline.

## Reference solution
Trusted reference only; use `scripts/two_modes/run.py smoke`. No expert in the evaluated main container.

## Verification
Independent two-process replay. Limited additionally requires online/replay exact agreement.
Use the unified runner for lifecycle, isolation, timeout adjudication and evidence collection.
This task revision has no inherited model score. See suites/two-modes.json for validation status.
