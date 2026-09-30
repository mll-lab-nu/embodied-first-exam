# robocasa-gr1-cup-to-drawer-close-limited60min-v3-i02

limited task, protocol: `docs/prompts/metaworldplus_codex_luna_high_two_modes.md`. Historical source: `tasks/robocasa-gr1-cup-to-drawer-close-privileged-i02`.
Frozen instance SHA256: `87563f420ddc6f5b852ac0070f88bf9c88a867faf1060bb166412ba53d59e1b8`.

## Difficulty
Same native instance and success predicate; 60 minute agent deadline.

## Reference solution
Trusted reference only; use `scripts/two_modes/run.py smoke`. No expert in the evaluated main container.

## Verification
Independent two-process replay. Limited additionally requires online/replay exact agreement.
Use the unified runner for lifecycle, isolation, timeout adjudication and evidence collection.
This task revision has no inherited model score. See suites/two-modes.json for validation status.
