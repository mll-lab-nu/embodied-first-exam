# Smoke-test references only

`scripts/two_modes/run.py smoke` drives the limited-mode oracle from each instance's frozen reference trajectory,
found at the instance's `source` path in `suites/two-modes.json`. Only those trajectory files are kept here, at their
original paths; they are byte-identical to the `solution/oracle.npz` of the matching unlimited task wherever both exist.
The full pre-unification task versions (`archive/task_versions/pre-unified-20260929/`) are not part of this branch.
