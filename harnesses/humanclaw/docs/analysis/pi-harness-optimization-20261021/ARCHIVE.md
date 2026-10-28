# Full analysis archive

The repository retains the core reports, implementation plan, task index, source
excerpts and small evidence files. All nine CSV data tables, all 1,218 task cards,
and `evidence/native_transcripts.jsonl.gz` are excluded from Git. Local copies may
remain at their original paths, covered by the repository's `.gitignore`.

The complete original analysis package is preserved on Klone, including copies
of the reports before their links were adapted for this repository layout. Its
measurements are historical observations; the action parser fix documented in
[ACTION_PARSER_FIX.md](../../ACTION_PARSER_FIX.md) does not change those results.

The server snapshot is the original 2026-10-21 census. Later implementation
notes and [compact local trial results](LOCAL_IMPLEMENTATION_RESULTS.md) are
versioned separately in Git; their full local traces are not included in that
historical server archive.

## Server location

- SSH host: `hengyil6@klone.hyak.uw.edu`
- Directory: `/gscratch/stf/hengyil6/analysis-archives/pi-harness-optimization-20261021`
- File: `pi-harness-optimization-20261021.full.tar.gz`
- Compressed archive size: 118,075,549 bytes (about 112.6 MiB).
- Original contents: 1,245 files, 168,572,589 bytes (about 160.8 MiB).
- SHA-256: `88a9c79a994929f6974467060a1afcf91109f9196cad3af3e1f21ea157ddc3a9`

The archive is outside every Git checkout and has owner-only permissions. Read
access requires the owner's SSH access or a separately arranged authorized copy.
The same directory contains `SHA256SUMS` and `verification.json`. Verification
checks both the archive checksum and every file listed in its internal manifest.

## Retrieve and verify

Run these commands from the repository root with authorized Klone access. The
destination is under `outputs/`, which is already excluded from Git.

```bash
mkdir -p outputs/analysis-archives/pi-harness-optimization-20261021
cd outputs/analysis-archives/pi-harness-optimization-20261021
scp hengyil6@klone.hyak.uw.edu:/gscratch/stf/hengyil6/analysis-archives/pi-harness-optimization-20261021/pi-harness-optimization-20261021.full.tar.gz .
scp hengyil6@klone.hyak.uw.edu:/gscratch/stf/hengyil6/analysis-archives/pi-harness-optimization-20261021/SHA256SUMS .
shasum -a 256 -c SHA256SUMS
tar -xzf pi-harness-optimization-20261021.full.tar.gz
```

The extracted package retains the original relative paths and its original
`artifact_manifest.csv`. The [archive manifest](archive_manifest.csv) in Git is
an identical copy of that original manifest: it inventories the server snapshot,
not the edited repository documents. The repository's separate
[artifact manifest](artifact_manifest.csv) hashes the files actually retained in
Git, excluding itself.

The archived reports also reference the earlier `harness-comparison-20261019`
package. To follow those links, place that existing repository package beside
the extracted `pi-harness-optimization-20261021` directory. No prior analysis is
deleted or moved by this publication.

## Task cards

All 1,218 detailed reports are in `tasks/shard-0000.md` through
`tasks/shard-1217.md` inside the archive. The repository's
[task index](TASK_INDEX.md) keeps outcome summaries and task IDs. Its task links
lead here; use the displayed shard ID to locate the corresponding archived file.
Selected examples in the main report also retain their exact archive paths.

To read one card on the server without extracting the archive:

```bash
tar -xOzf /gscratch/stf/hengyil6/analysis-archives/pi-harness-optimization-20261021/pi-harness-optimization-20261021.full.tar.gz pi-harness-optimization-20261021/tasks/shard-0317.md
```

## Data tables

All CSV tables are stored under `tables/` in the archive:

| File | Purpose |
| --- | --- |
| `action_contract_mismatches.csv` | Explicit requested/applied action substitutions |
| `episode_diagnostics.csv` | Full per-episode diagnostic data |
| `first_action_intent_comparison.csv` | Paired first-action intent and execution |
| `native_call_accounting.csv` | Accepted, rejected and unexecuted call accounting |
| `paired_diagnostics.csv` | Paired outcomes, behavior and resource use |
| `pi_image_cap_boundaries.csv` | Image-cap boundary observations |
| `recommendation_coverage.csv` | Recommendation eligibility counts |
| `task_index.csv` | Filterable task index |
| `tool_counts.csv` | Accepted environment action counts |

## Native transcripts

`evidence/native_transcripts.jsonl.gz` is retained only in the full archive and
ignored local copies. It is 110,005,139 bytes (about 104.9 MiB). The small evidence
files kept in Git preserve summary statistics, selected contact/request records,
source provenance and the original package's validation results.

`evidence/package_validation.json` describes validation of the complete original
package before relocation, including its original link counts. It does not
assert that all of those attachments are distributed through Git. Consult the
archive manifest for their sizes and SHA-256 digests.
