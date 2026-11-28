## Kind
<!-- Pick one. A pull request that adds tasks and changes shared files will be split. -->
- [ ] New benchmark (proposal: #___)
- [ ] Tasks for an existing benchmark
- [ ] Task fix
- [ ] Shared files / protocol (protocol-change issue: #___)

## What and why
<!-- Written by you. For a fix: which agent behaviour it closes, with before and after runs. -->

## Contract
- Mode(s): privileged / standard / realtime
- Oracle: full / partial / none. Evidence: ___
- Base image(s): `efe:<sim>-<version>` (published) / `efe-private:<sim>-<version>` (BUILD_ONLY)
- Agent time cutoff: ___ s per mode (`[agent] timeout_sec`; rules: docs/protocol/running.md "The agent's time"). The reason if not 3600. For a change of an existing task's cutoff: old → new, decided by ___
- Resources (caps per container, docs/protocol/resources.md):
  - main: ___ CPUs / ___ GiB memory / ___ processes / ___ GiB disk / ___ GiB GPU memory
  - each other service: ___ CPUs / ___ GiB memory / ___ processes / ___ GiB GPU memory
  - separate verifier (`[verifier.environment]`): ___ CPUs / ___ GiB memory, or "no cap"
  - GPU types (RTX-class only, or none): ___
  - measured from: ___

## Checklist
- [ ] `bash ci_checks/run_all.sh <tasks>` passes
- [ ] Tasks only: no task-generation code (generators, oracle searches, instance freezers). Shared code is in the image or `embodied_first_exam/benchmarks/<benchmark>/`
- [ ] Oracle and `nop` on a sample (at least 2 tasks per mode), table below
- [ ] New simulator or family: two fresh replays give the same state hash
- [ ] Oracle `partial` / `none`: a per-family table of positive examples
- [ ] Runs with Harbor's native agents (no custom runner, gateway or adapter)
- [ ] Names `<base>-privileged` / `<base>-standard` / `<base>-realtime`; every task in the normal form (`task_conventions.py --check`); no `results/`
- [ ] Standard / realtime: agent-ended episodes. `RCB_AGENT_END: "1"` in the `sim` service, `POST /finish` served, the success hidden, the end state judged, and the Finish line in `## Limits` (`ci_checks/check-agent-end.py`; docs/protocol/eai-standard.md "Agent-ended episodes")
- [ ] A new benchmark: its row is in `scripts/task_conventions.py` `BENCHMARK_TABLE` (shared-files pull request), with a prefix of its own
- [ ] The cutoff is each task's `[agent] timeout_sec`. The Time line of `## Limits` states it, and nothing else in the instruction does (`ci_checks/check-cutoffs.py`)
- [ ] The agent's egress is the allowlist (model APIs and package registries), and the oracle passes under it. The task downloads nothing at run time. No file the agent reads, in the task or its image, names or locates a solution, a demonstration or its dataset (H.2, H.6)
- [ ] The caps of every container (a `[[cap]]` rule in `scripts/task_resources.toml`) are set from measured peaks with a margin, and the oracle stays inside them. `normalize` renders the Resources line of `## Limits` and the README's resource section from them
- [ ] No credentials, personal paths or files > 2 MB. Each changed task's `DIGEST` is current (`normalize` writes it; `tasks/dataset.toml` is generated, not committed)

## Evidence
<!-- Oracle / nop table; optionally one strong-model run and why it failed. -->
