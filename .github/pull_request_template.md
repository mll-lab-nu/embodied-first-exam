## Kind
<!-- Pick one. A pull request that adds tasks and changes shared files will be split. -->
- [ ] New benchmark (proposal: #___)
- [ ] Tasks for an existing benchmark
- [ ] Task fix
- [ ] Shared files / protocol (protocol-change issue: #___)

## What and why
<!-- Written by you. For a fix: which agent behaviour it closes, with before/after runs. -->

## Contract
- Mode(s): privileged / standard — protocol (standard only): `eai-standard/2.__`
- Oracle: full / partial / none — evidence: ___
- Base image(s): `eai-<sim>:<ver>` (published / BUILD_ONLY)
- Agent time budget: ___ s (default 3600; reason if longer)

## Checklist
- [ ] `bash ci_checks/run_all.sh <tasks>` passes; no protocol warnings other than `legacy:` ones
- [ ] Generated tasks: re-running the generator leaves `git diff tasks/` empty
- [ ] Oracle and `nop` on a sample (≥ 2 tasks per mode), table below
- [ ] New simulator or family: two fresh replays give the same state hash
- [ ] Oracle `partial`/`none`: per-family table of positive examples (PROTOCOL §2.7)
- [ ] Runs with Harbor's native agents (no custom runner, gateway or adapter)
- [ ] Names `<base>-privileged` / `<base>-standard`; README in the standard layout; no `results/`
- [ ] No credentials, personal paths or files > 2 MB; `tasks/dataset.toml` refreshed

## Evidence
<!-- Oracle / nop table; optionally one strong-model run and why it failed. -->
