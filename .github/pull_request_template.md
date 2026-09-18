## What
<!-- New instance(s) of an existing family / new family / new simulator adapter / task repair -->

## Checklist
- [ ] `bash ci_checks/run_all.sh tasks/<my-task>` passes locally.
- [ ] `harbor run -p tasks/<my-task> -a oracle` gives reward 1 (paste the job summary below).
- [ ] `harbor run -p tasks/<my-task> -a nop` gives reward 0.
- [ ] `tests/instance.npz` was generated once and never regenerated (the sha in `task.toml` matches).
- [ ] `instruction.md` states the deliverable and every convention the agent cannot infer (frames, quaternion order, paths).
- [ ] If this adds a family: the adapter entry, oracle code, and `README.md` Difficulty section are filled in.
- [ ] If this touches `images/`: `images/VERSION` was bumped and every task Dockerfile re-pinned.

## Evidence
<!-- oracle job summary; optional: one strong-model run and why it failed -->
