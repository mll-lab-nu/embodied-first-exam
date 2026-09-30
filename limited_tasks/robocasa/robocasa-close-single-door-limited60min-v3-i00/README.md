# robocasa-close-single-door-limited60min-v3-i00

limited task, protocol: `docs/prompts/metaworldplus_codex_luna_high_two_modes.md`. Historical source: `tasks/robocasa-close-single-door-privileged-i00`.
Frozen instance SHA256: `1d7df7d1e9b6cd2d3640e79857b7bdc1cb9232f57192e33feec11be3b3d924ea`.

## Difficulty
Same native instance and success predicate; 60 minute agent deadline.

## Reference solution
Trusted reference only; use `scripts/two_modes/run.py smoke`. No expert in the evaluated main container.

## Verification
Independent two-process replay. Limited additionally requires online/replay exact agreement.
Use the unified runner for lifecycle, isolation, timeout adjudication and evidence collection.
This task revision has no inherited model score. See suites/two-modes.json for validation status.
