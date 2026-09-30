# robocasa-gr1-posttrain-pn-p-novel-from-plate-to-bowl-split-a-limited60min-v3-i00

limited task, protocol: `docs/prompts/metaworldplus_codex_luna_high_two_modes.md`. Historical source: `tasks/robocasa-gr1-posttrain-pn-p-novel-from-plate-to-bowl-split-a-privileged-i00`.
Frozen instance SHA256: `a1d9db27c54f5e870f3f538af3edf1fbd9395c981462ef86927f55e98612c222`.

## Difficulty
Same native instance and success predicate; 60 minute agent deadline.

## Reference solution
Trusted reference only; use `scripts/two_modes/run.py smoke`. No expert in the evaluated main container.

## Verification
Independent two-process replay. Limited additionally requires online/replay exact agreement.
Use the unified runner for lifecycle, isolation, timeout adjudication and evidence collection.
This task revision has no inherited model score. See suites/two-modes.json for validation status.
