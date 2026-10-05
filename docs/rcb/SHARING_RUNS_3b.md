### 3b. TopoGym native helper batches

Integration fragment for the official `SHARING_RUNS.md`. Keep that upstream file unchanged until this section is merged there. This file is not a replacement for the official manual.

The maintainer supplies an accessible helper release commit, frozen assignment, matching images, batch name and HF destination. Clone that release; third-party helpers do not need access to the private development repository. The assignment fixes tasks, modes, reference seeds, repetitions, model, effort and per-trial budgets. Do not edit it or regenerate the tasks.

On Linux with Docker/Compose and the NVIDIA runtime, install Python 3.12 and npm, then:

```bash
bash scripts/setup_agent_batch.sh
export PATH="$PWD/.venv-agent-batch/bin:$PWD/.tools/agent-batch/node_modules/.bin:$PATH"
```

The installer uses a private Node 22.14.0 and Codex 0.157.0 installation; the host Node is unchanged. Supply the maintainer's images before preparing the run. Save the separately supplied HF token using hidden terminal input, outside the checkout:

```bash
python scripts/difficulty_hf_auth.py store --file "$HOME/.config/eai/helper-hf.token"
```

Set `ASSIGNMENT` to the supplied local JSON path and `WORK` to your results directory. Configure once, using your own model credentials. The following uses the default Codex subscription login cache:

```bash
bash bash_scripts/run_helper_batch.sh --init-config \
  --config "$HOME/.config/eai/helper.local.json" \
  --assignment "$ASSIGNMENT" --jobs-dir "$WORK/jobs/agents" \
  --auth-file "$HOME/.codex/auth.json" --gpu 0 \
  --hf-token-file "$HOME/.config/eai/helper-hf.token"

bash bash_scripts/run_helper_batch.sh --config "$HOME/.config/eai/helper.local.json"
```

For API authentication, replace `--auth-file` with `--env-file /private/eai.env`. HF credentials are separate from model credentials. If using a fresh subscription cache, the first invocation requests device login in the foreground before background execution; do not wrap that invocation in `nohup`.

The workflow runs `scripts/run_agent_batch.sh`, retains `agents/` and sibling `agents_mirror/`, checks every planned repetition and verdict, scans/redacts deliverables, writes MANIFEST, creates the standard archive/checksum and uploads exactly those three files. It prints a pinned HF URL and keeps local receipts under `$WORK/jobs/.helper-pipeline/<batch>/`. An HF account with read access is needed to open the private dataset in a browser.

```bash
bash bash_scripts/run_helper_batch.sh --config "$HOME/.config/eai/helper.local.json" --phase status
# Retry delivery only after fixing a transient upload failure; this does not rerun trials.
bash bash_scripts/run_helper_batch.sh --config "$HOME/.config/eai/helper.local.json" --phase upload
```

Never delete or move trial directories. Infrastructure failures remain in place; only a maintainer-issued `<batch>-rerun` assignment permits additional attempts. The receiver independently downloads and verifies results, then handles any website publication. The helper does not need website access.
