# Methods and interpretation contract

Analysis started 2026-10-19 and completed 2026-10-20 (America/Los_Angeles).

This analysis reads existing HumanCLAW experiment records on Klone. It does not
change experiment code, configurations, or recorded results; run inference;
simulate or rerun episodes; submit jobs; or implement an analysis skill.
Derived reports and tables are written locally.

## Scope

The nine analytical conditions are PSV r1; Codex and Pi Astra r1, r2, and r3;
and Codex and Pi Gemini. Astra r3 uses Codex `max` and Pi `xhigh`. They are
different delivered effort labels, not an assumed common compute budget.

The remote root is:

`/gscratch/scrubbed/linjli/humanclaw/experiments/`

Each native r1 condition combines the completed shards in the original
`astra-fullval-20261017` directory and its `-imgwin50` continuation. These
directories are complementary completion cohorts, not independent repetitions.
Their original/continuation membership is retained.

## Record selection and provenance

1. Use `done/shard-*.json` to identify the reported completed-shard population.
2. Read the corresponding final `metrics.json`.
3. Select a completed experiment run whose recorded
   `outcome.benchmark_metrics` equals that final metrics object.
4. Record missing or multiple matches as data-quality issues. Do not silently
   use the newest directory as proof that it is the final run.
5. Keep other runs and archived `superseded/*/results` runs in an attempt
   ledger, outside the final-episode quality comparison.

The run-level source commit, source-file hashes, effective settings, and
runtime identity take precedence over a suite-level label. Scene, episode,
target category, initial pose, instruction, profile, and effective seed are
checked separately. Matching task IDs alone is not proof of matching inputs.

A completed process is not necessarily a successful embodied task. Success is
`interact_sr` for interaction episodes and `nav_sr_20cm` for other episodes.
Failure markers are historical scheduler records and may coexist with a later
successful completion. Attempt coverage does not include unrecorded failures
before trace initialization.

## Counting and token conventions

The analysis distinguishes episodes, recorded attempts, model requests,
native dispatches, normalized action-tool executions, and physical motion.
Native `turn` counts are not directly compared across Codex and Pi.

Existing per-run `summary.json` leaf-model accounting provides normalized
request usage and capability counts. Selected raw event streams independently
check the request/action linkage and context composition. Native cumulative
usage notifications are not added to request usage. Nested module, tool, and
environment durations are not added together.

Input includes cached input. Output follows the recorded provider
normalization, including reasoning where applicable. Cached input and
reasoning are not counted a second time. Missing usage remains missing:
known subtotals and coverage are reported. Missing recorded prices prevent
a dollar-cost estimate; token volume is not a bill. Token counts from
different model families are not equivalent compute units.

The native HTTP boundary is the HumanCLAW-to-provider-route boundary.
Provider-internal processing and retries can remain opaque. PSV records
adapter calls, which do not expose every provider/SDK-internal HTTP attempt.

## Paired comparisons

Task pairing uses scene ID, episode ID, and target category, with provenance
checks reported separately. The four outcome cells are both successful,
Codex only, Pi only, and both unsuccessful.

Success-rate differences are Pi minus Codex unless a table explicitly names
another ordered comparison. Confidence intervals use 10,000 bootstrap
resamples of the 41 scenes, retaining paired episodes within each sampled
scene. The random seed is 20261019. These intervals describe variation over
the observed scene collection; they do not estimate variation over repeated
LLM runs at identical settings.

Exact two-sided McNemar tests are supplementary episode-level paired tests.
Their independence assumption is weaker than the scene-cluster analysis
requires, and unadjusted p-values are exploratory rather than a multiplicity-
controlled confirmatory claim.

Efficiency is reported both for the common-success subset and for all final
episodes. Common-success comparisons have selection bias and are not a
substitute for overall success/cost reporting. Matched-pair token statistics
identify the number of pairs with usable measurements.

## Trajectory measurements

Saved `trajectory_before.npz` supplies action identities. Saved
`trajectory_after.npz` supplies realized root positions, orientations, frame
counts, and timing. No physical replay or new scene rendering is performed.

Horizontal root path length uses axes 0 and 1 of the saved HalfPhysics
translation. The actual saved state is Z-up: the implementation's
`world_transformation` maps saved Z to Habitat Y. The replay manifest's
“Y-up SMPL-X” label is inconsistent with this conversion and observed saved
coordinates. The analysis follows the implemented conversion, not that label.
It is not target distance, body-surface clearance, or an optimal-path metric.
Generated action magnitude and realized displacement are separate quantities.

The saved motion archives omit the terminal zero-motion `stand` in both native
and PSV conditions. A derived terminal
row is added only when the metrics indicate an active stop and the stored
action count is exactly one below the decision count. The inferred row is
flagged and is not presented as an original NPZ record. Selected event streams
independently verify the terminal action and the normalized action sequence.

An identical action prefix is a diagnostic alignment. The first differing
action is not automatically the cause of failure. After trajectories diverge,
equal step indices do not imply equal observations or physical states.

## Context and case analysis

The diagnostic case sample contains five pairs from each outcome quadrant in
each of four paired conditions: 80 pairs total. Deterministic hash ordering,
scene diversity, and alternating navigation/interaction preference are used.
Additional length-extreme, median-length, PSV, and identical-chain examples
extend the raw-request audit. This sample is intentionally diagnostic; its
unweighted failure-label proportions do not estimate population prevalence.

The primary raw-request audit covers 209 runs and 10,259 requests. Six focused
audits separately examine native-tool exceptions and one r1/r2 interaction
example. Twenty-four paired cases receive visual inspection of 96 saved
observations, presented as 24 contact sheets. The image hashes and original
paths are recorded in [review_images.csv](tables/review_images.csv).

Raw requests are inspected after HumanCLAW transport normalization. Image
eviction, text truncation, native compaction, and provider caching are treated
as different mechanisms. Character counts measure serialized text burden,
not exact component-level tokenizer usage. Image-to-observation matching
uses recorded content hashes; identical images at multiple times can make
their temporal identity ambiguous.

Case cards distinguish:

- observed benchmark facts;
- trajectory and request evidence;
- heuristic diagnostic flags;
- candidate explanations requiring additional verification.

Ground-truth geometry and saved state may be used for analysis but are not
assumed to have been visible to the model. A model's own visible-state claim
is not independent proof that it recognized the correct object.

## Causal limits

These are historical conditions, not randomized component ablations. The
principal task-facing r1-to-r2 change is Sit/Stop tool wording. Comparing the
r1 image-cap continuation with r2, the transport difference is a docstring;
runtime changes primarily record binary identity and map higher Pi effort
levels. The delivered medium effort is unchanged. The original r1 cohort
also differs in image-window policy, so the composite r1 comparison is not
a perfectly isolated wording ablation.
The Gemini conditions also change model route, source version, image window,
and empty-response recovery settings. Within-condition paired comparisons
are useful, but cross-condition differences cannot be assigned to one
component without further controls.

Component recommendations in the final synthesis are evidence-ranked
hypotheses and engineering design conclusions. No causal component benefit,
universal model compatibility, or unobserved internal behavior is asserted.
