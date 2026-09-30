# robocasa-gr1-posttrain-pn-p-novel-from-placemat-to-bowl-split-a-limited60min-v3-i00

limited task, protocol: `docs/prompts/metaworldplus_codex_luna_high_two_modes.md`. Historical source: `tasks/robocasa-gr1-posttrain-pn-p-novel-from-placemat-to-bowl-split-a-privileged-i00`.
Frozen instance SHA256: `6105aca7106c0e564c1af23a9438ea95870f6cfd915ab2d94d952f57b8999bac`.

## Difficulty
Same native instance and success predicate; 60 minute agent deadline.

## Reference solution
Trusted reference only; use `scripts/two_modes/run.py smoke`. No expert in the evaluated main container.

## Verification
Independent two-process replay. Limited additionally requires online/replay exact agreement.
Use the unified runner for lifecycle, isolation, timeout adjudication and evidence collection.
This task revision has no inherited model score. See suites/two-modes.json for validation status.
