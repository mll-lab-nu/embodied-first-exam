## What
<!-- New instance(s) of an existing family / new family / new simulator adapter / task repair -->

## Checklist
- [ ] `bash ci_checks/run_all.sh tasks/<my-task>` passes locally.
- [ ] `harbor run -p tasks/<my-task> -a oracle` gives reward 1 (paste the job summary below).
- [ ] `harbor run -p tasks/<my-task> -a nop` gives reward 0.
- [ ] Scene/verifier inputs under `environment/` and `tests/` are final (changing them later = new task).
- [ ] `instruction.md` states the deliverable and every convention the agent cannot infer (frames, quaternion order, paths).
- [ ] Fresh-process determinism evidence is included for a new simulator/family.
- [ ] If this touches `images/`: `images/VERSION` was bumped and dependent task Dockerfiles re-pinned.

## Evidence
<!-- oracle job summary; optional: one strong-model run and why it failed -->
