# robocasa-gr1-posttrain-pn-p-novel-from-plate-to-pan-split-a-limited60min-v3-i00

limited task, protocol: `docs/prompts/metaworldplus_codex_luna_high_two_modes.md`. Historical source: `tasks/robocasa-gr1-posttrain-pn-p-novel-from-plate-to-pan-split-a-privileged-i00`.
Frozen instance SHA256: `637958e138fa7e33e3d2a168029b768c0de512e59e4df0530e1bd33969884d66`.

## Difficulty
Same native instance and success predicate; 60 minute agent deadline.

## Reference solution
Trusted reference only; use `scripts/two_modes/run.py smoke`. No expert in the evaluated main container.

## Verification
Independent two-process replay. Limited additionally requires online/replay exact agreement.
Use the unified runner for lifecycle, isolation, timeout adjudication and evidence collection.
This task revision has no inherited model score. See suites/two-modes.json for validation status.
