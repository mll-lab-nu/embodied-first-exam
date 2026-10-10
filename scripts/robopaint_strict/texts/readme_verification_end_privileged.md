A file that is not a readable trajectory (not an npz, no `actions`, a wrong shape, NaN, more than 72,000 rows) scores 0 as
`bad_trajectory`; `grader_error` is left for the verifier's own failures (a replay process without a result or past its 1650 s).
The verifier has 3600 s: two replays of the 72,000 control steps a trajectory may have take up to 36 min at the measured
67-102 steps/s (docs/benchmarks/robopaint.md).
