# P0 — Cohort and provenance audit

Snapshot analysis: October 19–20, 2026, America/Los_Angeles. Remote experiment root:
`/gscratch/scrubbed/linjli/humanclaw/experiments/`.

## Population and selection

The analysis covers **10,960 final episodes**, **12,997 recorded attempt directories**, **460,783 executed environment actions**, and **526,266 recorded model calls in the final episodes**. Every final metrics object has exactly one matching completed run in its selected rollout directory. All final trace summaries pass their recorded diagnostics. Overlapping records from two analysis extraction checkpoints were deduplicated by run/task identity.

There are nine analytical conditions and eleven physical suite directories. Native r1 combines complementary original and `imgwin50` completion cohorts; these are not two independent replicates.

| Condition | Final tasks | Recorded attempts | Archived attempts | Recorded status distribution |
| --- | --- | --- | --- | --- |
| PSV r1 | 1218 | 1386 | 4 | {"completed": 1223, "running": 127, "failed": 35, "None": 1} |
| Codex r1 | 1218 | 2105 | 9 | {"failed": 610, "completed": 1228, "interrupted": 137, "running": 124, "unknown": 6} |
| Pi r1 | 1218 | 1719 | 0 | {"failed": 398, "completed": 1220, "running": 97, "unknown": 2, "None": 2} |
| Codex r2 | 1218 | 1226 | 4 | {"completed": 1222, "running": 4} |
| Pi r2 | 1218 | 1221 | 0 | {"completed": 1218, "running": 3} |
| Codex r3 max | 1218 | 1260 | 4 | {"completed": 1225, "running": 28, "interrupted": 6, "failed": 1} |
| Pi r3 xhigh | 1218 | 1241 | 0 | {"completed": 1218, "running": 22, "failed": 1} |
| Codex Gemini | 1217 | 1342 | 114 | {"completed": 1329, "running": 9, "failed": 4} |
| Pi Gemini | 1217 | 1497 | 267 | {"completed": 1477, "running": 16, "failed": 4} |


“Completed” is a process status, not task success. A historical `running` manifest does not establish that a process is still running now. Extra attempts include failures, interruptions, incomplete records, and superseded completions. Their costs are retained separately in [attempt_summary.csv](tables/attempt_summary.csv); they are excluded from final-task success and efficiency comparisons. These records do not support a complete first-attempt failure rate: pre-trace failures and scheduler history are not fully observed.

Both Gemini suites lack the same completed task, **shard-0184**. It is excluded from the 1,217-task comparison, rather than assigned an outcome. All other conditions contain 1,218 tasks from 41 scenes.

## Pairing checks

Across all four within-condition Codex–Pi comparisons, task IDs, instructions, goals, initial pose metadata, profile, effective seed, and recorded base model configuration match exactly. Saved initial translations and orientations also match in all **4,871 pairs**. The r1→r2 and r2→r3 comparisons, and PSV→native-r1 comparisons, pass the same metadata checks.

This does **not** mean their entire model requests match. Native system prompts, tools, serialization, and native effort overrides differ. In particular, the base model configuration still says medium for r3, while actual HTTP requests deliver Codex **max** and Pi **xhigh**. The actual request is the authoritative evidence for delivered effort.

Full checks: [paired_input_audit.csv](tables/paired_input_audit.csv), [paired_trajectories.csv](tables/paired_trajectories.csv).

## Effective configurations

| Cohort | Final tasks | Recorded source | Delivered effort | Image cap |
|---|---:|---|---|---|
| PSV r1 | 1,218 | `d1fed52` | Adapter setting medium; raw HTTP effort not captured | Current image only |
| Codex r1 original | 905 | `d1fed52` | medium | No configured cap |
| Codex r1 continuation | 313 | `45fc836` | medium | 50 |
| Pi r1 original | 915 | `d1fed52` | medium | No configured cap |
| Pi r1 continuation | 303 | `45fc836` | medium | 50 |
| Codex/Pi r2 | 1,218 each | `d18b41d` | medium / medium | 50 |
| Codex/Pi r3 | 1,218 each | Same source-file fingerprint as r2 | max / xhigh | 50 |
| Codex/Pi Gemini | 1,217 each | `9693432` fingerprint | medium / medium | 10 |

The native context-window setting is 131,072; episode timeout 7,200 seconds; request and startup timeouts 180 seconds. Native raw requests omit explicit `temperature` and `max_output_tokens`: the configuration disables sending those fields. The nominal `temperature=0` and `max_tokens=4096` values therefore do not establish delivered controls at this boundary.

Nine final runs have blank commit fields: five Codex r3, one Pi r3, two Codex Gemini, and one Pi Gemini. Their source-file fingerprints equal those of their respective condition. They are retained, with the missing commit metadata visible in [configuration_variants.csv](tables/configuration_variants.csv) and [episode_registry.jsonl.gz](evidence/episode_registry.jsonl.gz).

Codex r2/r3/Gemini record the real Codex 0.145.0 binary identity; Pi records its 1.3.0 executable/package identity. Native r1 has weaker provenance: Codex's version comes from its wrapper, and Pi records its wrapper hash without the later package identity. Unchanged wrapper hashes alone cannot prove unchanged underlying executables. The suite manifest's older source label is also weaker evidence than the selected run's fingerprint.

## Source comparison and evidence strength

Fifteen inspected source-file/version combinations match the corresponding hashes stored in every applicable selected run. Earlier files were read as pinned Git blobs; r2/Gemini files were read from frozen source directories and checked against recorded hashes. See [source_hash_verification.json](evidence/source_hash_verification.json).

The complete recorded Python/JSON source-file manifests differ in only five paths between the r1 image-cap source and r2: the environment, runtime, and services files, the native harness configuration, and a Gemini model configuration. The Gemini model configuration is not selected by these Astra runs. The task-facing change is the Sit/Stop wording; the services change is a docstring; runtime changes add real executable/package identification and higher Pi effort mappings, leaving medium unchanged. Other recorded source hashes, including planner, PSV prompt, motion/physics code, and evaluator/metrics, are unchanged. The complete manifests also show zero source-file differences between r2 and r3. See [source_manifests.json](evidence/source_manifests.json).

## Archive normalization discovered during analysis

1. **Terminal Stop is absent from saved motion NPZs in every harness.** A flagged zero-motion terminal row was reconstructed from `active_stop` only when stored actions were exactly one below the decision count. All 10,960 action totals reconcile. All 209 sampled raw execution sequences match the normalized saved sequences exactly, including skill and condition.
2. **The saved-coordinate manifest has an inconsistent label.** The implementation converts saved Z to Habitat Y; saved root coordinates also show the third component as height. Path measurements therefore use saved axes 0/1. All 10,960 path summaries were calculated with that convention. No source correction was made.
3. **Capability accounting has boundaries.** Raw native events confirm 12 plan updates even though the generic summary records requests without execution spans. Codex rejected calls can also produce duplicated request counters. The analysis uses dispatch counts and executed-action spans, not an unqualified sum of every “requested” field.

The complete provenance and audit records are linked in [REPORT.md](REPORT.md). Original experiment files were not changed.
