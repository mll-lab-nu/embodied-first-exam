### 3b. TopoGym native helper batches

Integration fragment for the official `SHARING_RUNS.md`. Keep that upstream file unchanged until this section is merged there. This file is not a replacement for the official manual.

The maintainer supplies an accessible helper release commit, frozen assignment, image build materials, batch name and HF destination. Clone that release; third-party helpers do not need access to the private development repository. The assignment fixes tasks, modes, reference seeds, repetitions and per-trial budgets. Use the supplied model and effort settings; choose others only when the assignment explicitly permits it, before starting the batch. Do not edit the assignment or regenerate the tasks.

The original `scripts/run_agent_batch.sh` command installs its pinned tools automatically and builds missing images from the frozen materials. Linux, Python 3/pip, Git, Docker/Compose, the NVIDIA runtime and network access are prerequisites. No separate `docker build` command is needed. If installing the tools separately:

```bash
bash scripts/setup_agent_batch.sh
export PATH="$PWD/.venv-agent-batch/bin:$PWD/.tools/agent-batch/node_modules/.bin:$PATH"
```

The installer uses a private Node 22.14.0 and Codex 0.157.0 installation; the host Node is unchanged. Save the separately supplied HF token using hidden terminal input, outside the checkout. An existing file is reused; the token must still be valid for the assigned dataset:

```bash
if [ ! -f "$HOME/.config/eai/helper-hf.token" ]; then
  python3 scripts/difficulty_hf_auth.py store --file "$HOME/.config/eai/helper-hf.token"
fi
```

The following wrapper is optional: the original manual's runner, scan, pack and upload commands remain supported. Set `ASSIGNMENT` to the supplied local JSON path and `WORK` to your results directory. Configure once, using your own model credentials. For this API-key batch, save `OPENAI_API_KEY` and `OPENAI_BASE_URL=https://api.openai.com/v1` in the private file `$HOME/rcb.env`, outside the checkout and readable only by you:

```bash
bash bash_scripts/run_helper_batch.sh --init-config \
  --config "$HOME/.config/eai/helper.local.json" \
  --assignment "$ASSIGNMENT" --jobs-dir "$WORK/jobs/agents" \
  --env-file "$HOME/rcb.env" --gpu 0 \
  --hf-token-file "$HOME/.config/eai/helper-hf.token"

bash bash_scripts/run_helper_batch.sh --config "$HOME/.config/eai/helper.local.json"
```

HF credentials are separate from model credentials; do not put `HF_TOKEN` or subscription-auth settings in `$HOME/rcb.env`. The wrapper checks authentication and image contents before background execution; its first invocation should run in the foreground.

The workflow runs `scripts/run_agent_batch.sh`, retains `agents/` and sibling `agents_mirror/`, checks every planned repetition and verdict, scans/redacts deliverables, writes MANIFEST, creates the standard archive/checksum and uploads exactly those three files. It prints a pinned HF URL and keeps local receipts under `$WORK/jobs/.helper-pipeline/<batch>/`. An HF account with read access is needed to open the private dataset in a browser.

```bash
bash bash_scripts/run_helper_batch.sh --config "$HOME/.config/eai/helper.local.json" --phase status
# Retry delivery only after fixing a transient upload failure; this does not rerun trials.
bash bash_scripts/run_helper_batch.sh --config "$HOME/.config/eai/helper.local.json" --phase upload
```

Never delete or move trial directories. Infrastructure failures remain in place; only a maintainer-issued `<batch>-rerun` assignment permits additional attempts. The receiver independently downloads and verifies results, then handles any website publication. The helper does not need website access.
