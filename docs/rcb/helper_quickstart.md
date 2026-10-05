# TopoGym helper delivery

Use the exact source release and `assignment.json` supplied by the maintainer. This implementation has CPU contract coverage; an independent GPU-host delivery rehearsal and the external review-site integration are still pending. The full Chinese guides cover [execution](helper_quickstart_zh.md) and [offline acceptance](helper_import_zh.md).

You need Linux x86_64, local Docker Engine/CLI with Buildx, NVIDIA drivers/Container Toolkit, disk space, and access to dependencies and the assigned model service. The assignment owns the batch, concrete instances, seeds, modes, budget, model/version/effort, CUDA recipe and upload target. Do not override them. One batch has one queue; duplicate invocations do not add lanes.

```bash
# Subscription login, if permitted by the assignment.
bash bash_scripts/run_difficulty_trials.sh auth login --device-auth

# First run. For an existing planned/run batch, add --resume.
bash bash_scripts/run_difficulty_trials.sh \
  --assignment /data/assignment.json --phase all \
  --auth subscription --gpu-device 0 --work-dir /data/helper-work

# Once execution stops, export complete evidence.
bash bash_scripts/run_difficulty_trials.sh helper export \
  --run-id BATCH --work-dir /data/helper-work
```

For API authentication use `--auth api-key --env-file /private/model.env` in the evaluation, and pass `--env-file /private/model.env` again to export. Keep those credentials private and available until scanning completes. Text is redacted in the delivery staging copy; binary credential hits, unreadable files, active writers, changing source evidence or missing required mirrors block export. Never upload `.preparing-*` directories.

The sealed directory is `work/outgoing/upload_BATCH/BUNDLE_ID/`. Transfer its three files together, in a separate folder for this bundle: `BATCH__HELPER__BUNDLE_ID.tar.gz`, the same filename with `.sha256`, and `MANIFEST.md`. Failed and interrupted records are preserved. A partial bundle is explicitly incomplete. Keep the original work directory and release.

For an assignment targeting a private HF dataset:

```bash
bash bash_scripts/run_difficulty_trials.sh helper upload \
  --archive /data/helper-work/outgoing/upload_BATCH/BUNDLE_ID/ARCHIVE.tar.gz \
  --work-dir /data/helper-work --hf-token-file /private/hf-token
```

Retry the same upload after a network interruption; it checks remote content and never reruns the model. `--hf-dry-run` requires no token. The final remote `UPLOAD_COMPLETE.json` is written only after all three files have been verified. Upload completion and evaluation completion are separate fields. The older `--results_to_hf` metrics export is not this full evidence delivery.

Resume continues unstarted trials and preserves existing attempts. Rerunning an incomplete attempt additionally requires a maintainer-issued `--retry-plan`, `--resume` and `--rerun-incomplete`. Canary retries must be explicitly authorized too. Do not create `BATCH-rerun` or rename job folders to fit an older importer.

The receiving machine downloads all three files and uses the maintainer's original assignment:

```bash
TOPOGYM_EVAL_PYTHON=python3 bash bash_scripts/run_difficulty_trials.sh helper import \
  --backend local --archive /data/received/BUNDLE_ID/ARCHIVE.tar.gz \
  --assignment /data/original-assignment.json \
  --require-complete --work-dir /data/acceptance
```

Python 3.10+ standard library is sufficient for offline verification/import. No GPU, model credentials, original helper paths, or execution of received agent code is needed. Read `imports/BATCH/BUNDLE_ID/receipt.json` and `reports/README.md`. Omit `--require-complete` only when receiving partial evidence deliberately. The importer rejects modified previously accepted terminal job files. It provides a review-site descriptor; registration with the actual external review site has not yet been implemented or tested there.
