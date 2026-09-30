## What
<!-- New instance(s) / task repair / runner or lifecycle change; name the benchmark(s) and mode(s) -->

## Checklist
- [ ] `bash ci_checks/run_all.sh` passes locally (per-task contract checks and `scripts/two_modes/check.py`).
- [ ] `run.py smoke --benchmark <b> --task <task> --output jobs/<new-dir>` passes oracle and nop in both modes
      (paste `summary.json` below).
- [ ] Changed task content is a new task version: its registry fingerprints and dataset digest were refreshed on purpose
      (`scripts/two_modes/check.py --freeze`), not to silence a check.
- [ ] `instruction.md` states the deliverable and every convention the agent cannot infer (frames, quaternion order, paths).
- [ ] If this touches `images/`: `images/VERSION` was bumped and dependent task Dockerfiles re-pinned.

## Evidence
<!-- smoke summary.json; optional: one model run and why it failed -->
