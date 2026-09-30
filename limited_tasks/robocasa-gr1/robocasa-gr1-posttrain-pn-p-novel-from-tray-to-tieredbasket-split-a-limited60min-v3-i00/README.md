# robocasa-gr1-posttrain-pn-p-novel-from-tray-to-tieredbasket-split-a-limited60min-v3-i00

limited task, protocol: `docs/prompts/metaworldplus_codex_luna_high_two_modes.md`. Historical source: `tasks/robocasa-gr1-posttrain-pn-p-novel-from-tray-to-tieredbasket-split-a-privileged-i00`.
Frozen instance SHA256: `e8832068367b24bbdcdb82b77a74025c89a538c88d7944f4e0dfeb1c7c1b1dbc`.

## Difficulty
Same native instance and success predicate; 60 minute agent deadline.

## Reference solution
Trusted reference only; use `scripts/two_modes/run.py smoke`. No expert in the evaluated main container.

## Verification
Independent two-process replay. Limited additionally requires online/replay exact agreement.
Use the unified runner for lifecycle, isolation, timeout adjudication and evidence collection.
This task revision has no inherited model score. See suites/two-modes.json for validation status.
