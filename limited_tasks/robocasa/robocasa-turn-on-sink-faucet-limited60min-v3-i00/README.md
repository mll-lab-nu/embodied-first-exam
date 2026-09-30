# robocasa-turn-on-sink-faucet-limited60min-v3-i00

limited task, protocol: `docs/prompts/metaworldplus_codex_luna_high_two_modes.md`. Historical source: `tasks/robocasa-turn-on-sink-faucet-privileged-i00`.
Frozen instance SHA256: `c260360d5b7589c6fa0816b1c9ddfe78aeab75a87c19820d891fa8bd9fd666ae`.

## Difficulty
Same native instance and success predicate; 60 minute agent deadline.

## Reference solution
Trusted reference only; use `scripts/two_modes/run.py smoke`. No expert in the evaluated main container.

## Verification
Independent two-process replay. Limited additionally requires online/replay exact agreement.
Use the unified runner for lifecycle, isolation, timeout adjudication and evidence collection.
This task revision has no inherited model score. See suites/two-modes.json for validation status.
