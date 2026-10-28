# Selective action repair campaign, 2026-10-21

The user authorized rerunning the explicit action-semantic mismatches with their
Klone account and existing **Azure `gpt-6-astra`** deployment. Original requests
used **Copilot/Magpie**. Every new run records this provider change; this is not
a controlled, provider-identical estimate of the parser fix's effect.

## Selection and destinations

| Cohort | Audited changed actions | Selected episodes | Original source variant |
|---|---:|---:|---|
| Codex r1 | 922 | 920 | 699 original-window + 221 imgwin50 |
| Codex r2 | 547 | 543 | native-actions-v2, medium, imgwin50 |
| Codex r3 | 468 | 468 | native-actions-v2, max, imgwin50 |

No Pi or Gemini episodes are selected. Multiple bad actions in one selected
attempt produce one rerun, and the original audit's selected attempt is retained.

New results live in the user's existing experiment hierarchy:

```
/gscratch/scrubbed/hengyil6/humanclaw-analysis/experiments/
  <corresponding-original-suite>/action-repair-azure-20261021/results/
    shard-NNNN/attempt-<unique-id>/rollout/
```

The coauthor's directories under `/gscratch/scrubbed/linjli/` remain read-only.
After the user's October 21 replacement instruction, completed and validated
episodes replace the corresponding shard in the **user-owned** original
`results/` tree. The previous owned shard is deleted, including its videos,
trajectories, raw logs and old shard summaries; no old-data backup is retained.
The r3 parent is created in the user's hierarchy because no restored r3 suite
was present there. The selected
original manifests and events are read to verify evidence and reconstruct the
episode. The run's `metadata.action_repair` links old and new attempts.

The user's subsequent October 21 instruction explicitly permits deleting the
audited invalid **owned copies before rerunning**, to reclaim shared storage.
`original_prune_receipt.json` records the selected old identity and deleted
size. Corrected results and unrelated episodes are retained. Rerun inputs still
come from the hash-verified read-only coauthor source, so deleting owned copies
does not remove the evidence or configuration needed for the reruns.

Control files and allocation logs are under:

```
/gscratch/scrubbed/hengyil6/humanclaw-analysis/experiments/
  action-repair-azure-20261021/control/
```

`prepared_plan.json` pins all 1,931 cohort–episode pairs, original run hashes,
source versions, effort and image-window settings. `sources/*/repair_source.json`
records the exact five-file backport. The source, action descriptions, native
runner, proxy, prompts and context behavior are reconstructed from each original
run's recorded hashes. Only parsing/condition validation, repair metadata, the
authorized provider connection, and the user's isolation/output paths change.
The underlying native binary remains Codex 0.145.0. The original GPU/machine and
provider behavior are not assumed deterministic.

## Execution and validation

The first four array tasks cover all source/effort combinations. Bulk arrays
depend on their corresponding pilot completing successfully as a *framework
validation*: benchmark `task_success: false` is a valid completed result.

| Stage | Slurm job | Index selection |
|---|---|---|
| Pilots | 42130264 | 0, 3, 920, 1463 |
| r1 bulk | 42130275 | 1–2, 4–919 |
| r2 bulk | 42130277 | 921–1462 |
| r3 bulk | 42130280 | 1464–1930 |

These are ordinary Slurm batch dependencies, not recurring automations. Each
original bulk cohort had four concurrent GPU slots (12 total, increased at the user's
request). Submission receipts and `concurrency_changes.json` in the control
directory, Slurm state and live logs are authoritative; a submitted job is not
proof of a completed rollout.

After shared-storage and Azure rate-limit failures, the pending portions of
these three arrays were cancelled and consolidated into **42138886**, containing
the remaining **1,924** selections with a global concurrency of **2 GPUs**.
The seven validated results are excluded. `recovery_submission_20261021.json`
records the exact indices, previous queue, capacity checks and submission.
Failed attempts remain identifiable; this does not reset experimental results
or change native harness behavior. The worker checks shared fileset headroom
including GPFS reservations, with a 20 GiB reserve, before model work.

Before model work, the worker checks source hashes, original run identity,
original mismatch spans, GPU availability and the **sata1-scrubbed** quota.
It restores the saved episode, profile, seed and asset identities, loads only
the user's existing Azure credential into the evaluator, and starts a fresh
native session. Native child processes receive the original environment
allowlist and cannot read benchmark data or the private credential file.

The coauthor's recorded absolute HSSD paths are not accessible to this account.
The launcher rebinds the scene configuration and scene instance to the user's
existing `/gscratch/stf/hengyil6/data/humanclaw-hssd-val41` copy, requiring each
file's SHA-256 to match the original replay manifest. Only these two path fields
change; all task, target and initial-state fields remain frozen. The mapping and
hashes are saved in `metadata.action_repair.asset_relocations`. Pilot attempts
that stopped at the inaccessible path are retained as infrastructure failures.

An observed startup stall in the shared environment's SciPy bytecode cache led
to a launcher-only change: subsequent workers read the identical Python source
files using a fresh local bytecode-cache prefix with cache writes disabled.
Dependencies and native decision behavior are unchanged; this startup policy
is recorded separately. Already-running allocations retain their loaded worker
version until they finish or are explicitly requeued.

The worker retains every interrupted or failed attempt. A requeued allocation
starts a new attempt, with a maximum of three allocations per selected episode;
it never repeats a valid completed benchmark failure to improve success rate.
`validated_result.json` is written only for a complete run with a valid trace,
real model calls, frozen episode/seed, matching normalized actions, benchmark
outcome and replay artifacts. Old provider prices are not reused: Azure dollar
cost stays unknown without an explicit rate card, while raw token usage is kept.

For a lightweight current count and an old-to-new mapping, run on the server:

```bash
control=/gscratch/scrubbed/hengyil6/humanclaw-analysis/experiments/action-repair-azure-20261021/control
/usr/bin/python3.12 "$control/action_repair.py" report "$control/prepared_plan.json"
```

The report has a fixed requested denominator and distinguishes validated
successes, validated task failures, infrastructure failures and unstarted work.
Detailed tokens, latency and raw events remain in each run's `summary.json`,
`run.json` and `events.jsonl`. The mapping records replacement explicitly and
retains the new run ID and the change from Copilot/Magpie to Azure.

## Replace completed owned episodes

For the explicitly authorized early cleanup, the policy additionally requires
`delete_confirmed_invalid_before_rerun: true`. Only exact audited owned shards
are eligible; symlinks, changed manifests and unrecognized additional runs are
rejected. Earlier original attempts of the same episode may be removed
with its shard only when their manifests also match the read-only source and
contain no repair metadata. Old copied `running` statuses are not treated as live
jobs; the scheduler is checked separately. Completed corrected episodes are
skipped. The command is:

```bash
/usr/bin/python3.12 "$control/action_repair_replace.py" "$control/prepared_plan.json" \
  --prune-invalid-originals --workers 4 --apply
```

Pruning and promotion share a per-shard lock. A small receipt is written before
deletion and supports interrupted cleanup without retaining an old-data backup.

`tools/action_repair_replace.py` verifies the old owned manifest against the
audited SHA-256, and verifies the new completed manifest, trace and artifacts.
An ordinary task failure is eligible; an infrastructure failure is not. It
rebuilds shard summaries from the new data, renames the new shard into
`<suite>/results/<shard>`, verifies the installed files and trace, then deletes
the exact old shard. The intermediate rename is recoverable if interrupted;
it is not a retained backup after successful replacement.

The repair attempt's former `rollout` path becomes a symlink to the canonical
shard. This preserves absolute references already recorded in the new logs
without storing a second copy. `replacement_receipt.json` contains only small
provenance metadata, hashes, paths and an estimate of deleted allocated bytes.
Original coauthor data and other episodes are excluded by path/identity guards.

The enabled `replacement_policy.json` in the server control directory records
the user's explicit authorization. Newly launched workers call the replacement
step after validation; it does not change native harness behavior. Existing
validated results can be processed idempotently with:

```bash
/usr/bin/python3.12 "$control/action_repair_replace.py" "$control/prepared_plan.json" --apply
```

Omit `--apply` for inspection. The operation skips unfinished episodes and never
reruns a valid benchmark failure to improve success rate. Already-running
workers retain their previous worker snapshot and require the same postprocess
step after they finish.

The campaign implementation is `tools/action_repair.py`, its batch entry is
`tools/action_repair.sbatch`, and the path-only native launcher adaptation is
`tools/action_repair_codex_isolated.py`. The local focused checks include 116
parser/prompt/campaign tests and 156 motion/integration/campaign checks in the
Torch-enabled test environment. These counts overlap and are not additive.

## First live verification

At approximately 17:35 PDT on 2026-10-21, all four restarted pilots had received
successful Azure responses and begun executing actions. Three used Quadro RTX
6000 GPUs on `g3030`, `g3036` and `g3037`; the max-effort pilot used an A40 on
`g3072`. The saved `verified_live_snapshot.json` records this check. It is an
intermediate snapshot, not a claim that an episode completed or the bulk gates
passed.

Recorded examples include `Turn right 90` becoming `Turn<right><90>` with
condition `-90.0`, and `Walk forward normal` becoming
`Walk<forward><normal>` with condition `[0.0, 0.4, 0.0]`. Provider usage was
present for completed calls, including the max-effort pilot. No failed model
calls appeared in that snapshot.

Initial startup was slowed by shared-filesystem reads during Python imports
and Habitat's registration of 14,537 object configuration files. An auxiliary
read-only cache warmup was run once on each allocated node; its receipts are
`cache-warm-<node>.json`. No asset contents were changed. Requeue receipts and
the first attempts' `scheduler_startup.log` preserve the startup investigation.
Each subsequent attempt snapshots its launcher as `worker.py` and records its
hash. The eight campaign-specific tests include SHA-verified dataset relocation.
