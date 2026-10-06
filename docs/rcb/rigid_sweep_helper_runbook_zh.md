# Running our tasks for us and sending back the logs

For a helper who runs a batch of our tasks on their own GPU host and cannot reach our review site or our machines. You run the batch with our runner, check it for secrets, pack the job directories without changing their layout or names, and upload one archive. Our receiver validates the results and builds a local review report from those files, so the layout is the contract.

> Release status: this frozen release is published in the private repository [LUIGIVAMPER/topogym-sweep-release-v1](https://github.com/LUIGIVAMPER/topogym-sweep-release-v1), at tag `rigid-v17-20261005-muse01-keyprompt01`. The helper needs access to this private repository and GitHub HTTPS authentication to use the clone command below. No SSH key setup is required; the HTTPS URL does not make the repository public. Review-site integration is deferred; section 8 covers the available receiver workflow.

> Version scope: this batch freezes `merged-v17` source and grading, including the privileged replay hold rule. At initial publication, all 24 instances were prepared; 6 passed preflight and full preflight was waived by the maintainer for the remaining 18. Additional maintainer preflight checks are separate from this frozen assignment and require no helper action. The online image rebuild and clean local Git clone were verified. These checks do not establish model success or completion of the formal 144-trial experiment.

## 1. What we send you first

| Item | Example | Why it matters |
| --- | --- | --- |
| Repository and release tag | [LUIGIVAMPER/topogym-sweep-release-v1](https://github.com/LUIGIVAMPER/topogym-sweep-release-v1), `rigid-v17-20261005-muse01-keyprompt01` | The tag pins the code, task directories and instructions for this release |
| Task list and modes | The 24 task bases below; privileged and standard; K=3 | One Harbor job per task and mode; three trials per job |
| Batch name | `topogym-rigid-solxh-jianwen-20261005-v17-keyprompt01` | Every job name starts with it; the receiver matches it to our assignment. Use it verbatim |
| Agent settings | `AGENT=codex MODEL=openai/gpt-6-sol EFFORT=xhigh`; helper-supplied API key | The actual model and effort are recorded and must stay the same across this batch |
| Upload target | Private dataset `eai-v2-internal/helper-uploads`, folder `helpers/jianwen/topogym-rigid-solxh-jianwen-20261005-v17-keyprompt01/`, write token from us | Where the archive goes |

Do not invent your own batch name, change budgets, edit task directories or modify the runner. If something forces a change, ask us first.

This assignment contains eight rigid/articulated-rigid tasks at easy, medium and hard, using fixed oracle seed 0: 24 instances x 2 modes x 3 repetitions = 144 trials, in 48 jobs. Each trial has a 12-hour agent budget, 150M input tokens and 10M output tokens; image setup and grading can take additional time. Token limits are checked after the run for scoring, not enforced as a live API spending cap. K=3 and both modes are already in the assignment.

`jianwen` is the helper ID assigned to this batch, not a requirement on your Linux, GitHub or HF username. Use it unchanged in the commands and upload path. This assignment permits choosing `MODEL` and `EFFORT` before the first start; the values below are the defaults. Keep `AGENT=codex`, and use the same chosen values for every lane. Changing them after the batch starts requires a new assignment.

## 2. What you need

- Linux x86_64 host with an NVIDIA GPU (driver >= 580), Docker with Compose v2 and the NVIDIA runtime, enough disk for the images (tens of GB) and all trial artifacts. Your user must be able to run Docker commands.
- git, python3 with pip and venv support, and network access. On a fresh Ubuntu host, install these OS prerequisites with `sudo apt update` and `sudo apt install -y git python3-pip python3-venv`. This runner then installs its pinned Harbor, Codex and HF tools automatically in its private environment; no manual venv activation is needed.
- On Windows/WSL 2, Docker Desktop must be running in Linux-container mode with **Settings > Resources > WSL Integration** enabled for this Ubuntu distribution. Installing Ubuntu alone does not install or expose Docker. Alternatively, use a configured remote Linux GPU host. See [Docker WSL integration](https://docs.docker.com/desktop/features/wsl/). The runner checks Docker access and Compose v2 before installing tools; it does not install a system daemon or change Windows settings.
- The benchmark images named in the task directories. This release builds missing images automatically from its frozen materials before running trials.
- Your own model credentials (an OpenAI API key for section 3, or an OpenRouter API key for section 3b). **Every time you run the configuration/start block, it prompts for a model API key with hidden input, even if the credential file already exists.** Section 3 writes the newly entered key to `$HOME/rcb.env` with `OPENAI_API_KEY` and `OPENAI_BASE_URL=https://api.openai.com/v1`; section 3b writes OpenRouter credentials to its separate file. These private files pass your current input to the background runner and the later secret scan. You do not need to edit them yourself. Tasks, seeds, repetitions and budgets come from the assignment. Do not put subscription-auth settings or `HF_TOKEN` in the model file.
- The HF write token we send you. The same configuration command prompts for it separately if missing and saves it in `$HOME/.config/eai/helper-hf.token`. Only the existing HF token is reused automatically. Both credentials stay outside the repository, with permissions restricted to their owner, and never go into the upload. Local configuration checks do not verify provider permissions or account credit.

## 3. Run the batch (e.g. Codex, gpt-6-sol)

Run these commands in **Bash on the Linux GPU host**, not in Windows PowerShell or CMD. If you use Windows to access a remote GPU host, connect to that Linux host first and run the commands there.

The command beginning with `AGENT=codex` and ending with `&` starts the actual experiment through `scripts/run_agent_batch.sh`. The backslashes join the lines into one command; the 24 task names are its arguments. It runs both modes and K=3 from the assignment, for 144 trials. `nohup` and the final `&` leave it running in the background, so the terminal prompt returning does not mean the experiment is finished. Cloning the repository and setting variables alone do not start trials.

```bash
git clone https://github.com/LUIGIVAMPER/topogym-sweep-release-v1.git && cd topogym-sweep-release-v1 && git checkout rigid-v17-20261005-muse01-keyprompt01
REPO=$PWD
export JOBS=$PWD/jobs/agents                 # keep the default layout: jobs/agents/<batch>-<mode>-<task>/
B=topogym-rigid-solxh-jianwen-20261005-v17-keyprompt01
export ENV_FILE="$HOME/rcb.env"
# Every launch: hidden model API-key prompt; HF-token prompt only if missing.
# Do not put this configuration command under nohup.
if python3 scripts/configure_agent_batch.py \
  --env-file "$ENV_FILE" --hf-token-file "$HOME/.config/eai/helper-hf.token"; then
# Start the formal 144-trial experiment only after configuration succeeds.
AGENT=codex MODEL=openai/gpt-6-sol EFFORT=xhigh ENV_FILE=$HOME/rcb.env \
CODEX_FORCE_AUTH_JSON=0 CODEX_AUTH_JSON_PATH= \
  nohup scripts/run_agent_batch.sh "$B" \
  topogym-interlocked-claws-easy-o00 \
  topogym-interlocked-claws-medium-o00 \
  topogym-interlocked-claws-hard-o00 \
  topogym-lock-picking-easy-o00 \
  topogym-lock-picking-medium-o00 \
  topogym-lock-picking-hard-o00 \
  topogym-hedgehog-in-cage-easy-o00 \
  topogym-hedgehog-in-cage-medium-o00 \
  topogym-hedgehog-in-cage-hard-o00 \
  topogym-fiber-bundling-easy-o00 \
  topogym-fiber-bundling-medium-o00 \
  topogym-fiber-bundling-hard-o00 \
  topogym-horseshoe-ring-easy-o00 \
  topogym-horseshoe-ring-medium-o00 \
  topogym-horseshoe-ring-hard-o00 \
  topogym-cast-coil-easy-o00 \
  topogym-cast-coil-medium-o00 \
  topogym-cast-coil-hard-o00 \
  topogym-cast-keyhole-easy-o00 \
  topogym-cast-keyhole-medium-o00 \
  topogym-cast-keyhole-hard-o00 \
  topogym-buzz-wire-3d-easy-o00 \
  topogym-buzz-wire-3d-medium-o00 \
  topogym-buzz-wire-3d-hard-o00 \
  >> "run_$B.out" 2>&1 &
fi
```

- Paste the model API key at `Model API key (hidden; not the HF token):`, and the separate upload token at `HF upload token (hidden):`. Characters are intentionally not displayed. If configuration is cancelled or fails, the experiment is not launched. For a different API provider, supply its compatible endpoint with `--api-base-url` to the configuration command before first use; existing endpoint settings are preserved.
- This release reads the published assignment automatically from the batch name. The 24 task bases above must match that assignment; no extra difficulty, seed, mode or K arguments are needed. Tool installation and image construction run automatically before trials; the helper does not run prepare or preflight.
- One runner is one lane (one trial at a time). Start the same command again to add a lane; every job is claimed by exactly one runner. The command defaults to GPU 0; coordinate GPU allocation before adding lanes.
- Progress: `$JOBS/$B.log`; the summary table: `$JOBS/$B.summary.md`. During initial setup, see `run_$B.out`. The summary is refreshed after each job, so it may be absent or out of date while that job runs. Appending to `run_$B.out` preserves earlier output when another lane starts.
- Never delete or move a job directory, including failed or interrupted ones. They are part of the record.
- A trial that crashed for an infrastructure reason (host OOM, GPU lost, network outage): leave it in place, note it in the manifest, and rerun it only if we ask. Reruns go into the batch `topogym-rigid-solxh-jianwen-20261005-v17-keyprompt01-rerun`, with a new assignment supplied by us; changing `B` alone is not sufficient.

**Check progress (optional; these commands do not start another lane).** Use the same terminal, with `REPO`, `JOBS` and `B` still set. In a new terminal, first enter your release checkout and set `REPO=$PWD`, `export JOBS=$REPO/jobs/agents` and `B=topogym-rigid-solxh-jianwen-20261005-v17-keyprompt01` again. Keep the batch name used at launch when inspecting an older run; do not substitute this batch name for a different experiment.

Follow setup, image construction and runner output:

```bash
tail -n 80 -f "$REPO/run_$B.out"
```

Press Ctrl+C to stop following this log and return to the prompt. This stops `tail`, not the background experiment. A quiet log alone does not prove that the runner has finished or is still running.

Inspect recent job events and the summary:

```bash
tail -n 50 "$JOBS/$B.log"
cat "$JOBS/$B.summary.md"
```

The batch log may not exist during initial setup. A line such as `start ... K=3` means the runner has claimed a task/mode job and is beginning its three trials. The summary is normally first written after a job returns; its absence during the first job is not itself an error. Check the per-trial status columns: the observed count can include unfinished trials, and is not a completed-trial count.

Check whether this batch still has a runner process:

```bash
pgrep -af -- "agent_batch_runtime.py.*$B"
```

After setup, this normally lists one process per active lane. During initial tool installation the bootstrap process runs instead, so no match at that point does not mean failure. No match after trials have started can mean success or failure; check `run_$B.out` and the final completion records below. Do not rerun the launch command merely to check progress: it can start another lane.

When the batch is done, every job has a verdict. This lists the ones that do not:

```bash
for d in "$JOBS"/"$B"-*/; do ls "$d"*/verifier/reward.json >/dev/null 2>&1 || echo "no verdict: $d"; done
```

Wait for all background lanes to finish before continuing. The loop only checks for at least one verdict in each existing job; it cannot prove that all 48 jobs or all three repetitions are present. For a complete delivery, the summary must report 144 observed trials, and the final `$JOBS/$B-MANIFEST.md` must report `Trials: 144/144; evaluation_complete=True; delivery_complete=True`, including the required mirrors. The runner also writes `$JOBS/$B-inventory.json` when it finishes sealing the files. If these are missing or incomplete, report the problem before packaging. Completion does not mean every task was solved or that it has been uploaded.

## 3b. Muse Spark through OpenRouter (Muse Code compatibility agent)

Choose this section instead of starting the Sol batch in section 3. Clone and check out the same release tag first. This route uses **`AGENT=muse-openrouter`**, retaining Meta's Muse Code CLI for planning, tools and sessions. It does not use Codex as the agent. The fixed Muse CLI is `1.4.3-R5018.1`; its official binary is downloaded once, verified by SHA-256 and copied into trial containers automatically. No extra helper command or task-image rebuild is needed.

The maintainer explicitly authorized an OpenRouter compatibility adapter for this batch. Results record `muse-openrouter-adapted-v1` and `native_d11=false`: these are adapted Muse Code results, not unmodified D11 native runs. The transport translates the model catalog and SSE event numbering, reversibly maps overlong tool names, and caps each response to the advertised limit (at most 16,384 output tokens). It preserves the conversation, tools, images and selected model; it does not switch models or silently discard reasoning history. A Meta API key is not required.

The full batch below uses the same 24 task bases, both modes, K=3 and per-trial budgets as section 3: **144 trials**. Only the experiment identity and agent/provider/model settings differ. Keep the complete model name `openrouter/meta/muse-spark-1.3-contributor`.

```bash
REPO=$PWD
export JOBS=$PWD/jobs/agents
B=topogym-rigid-muse-jianwen-20261005-keyprompt01
export ENV_FILE="$HOME/.config/eai/openrouter.env"
if python3 scripts/configure_agent_batch.py --provider openrouter \
  --env-file "$ENV_FILE" \
  --hf-token-file "$HOME/.config/eai/helper-hf.token"; then
AGENT=muse-openrouter MODEL=openrouter/meta/muse-spark-1.3-contributor EFFORT=default \
CODEX_FORCE_AUTH_JSON=0 CODEX_AUTH_JSON_PATH= \
  nohup scripts/run_agent_batch.sh "$B" \
  topogym-interlocked-claws-easy-o00 \
  topogym-interlocked-claws-medium-o00 \
  topogym-interlocked-claws-hard-o00 \
  topogym-lock-picking-easy-o00 \
  topogym-lock-picking-medium-o00 \
  topogym-lock-picking-hard-o00 \
  topogym-hedgehog-in-cage-easy-o00 \
  topogym-hedgehog-in-cage-medium-o00 \
  topogym-hedgehog-in-cage-hard-o00 \
  topogym-fiber-bundling-easy-o00 \
  topogym-fiber-bundling-medium-o00 \
  topogym-fiber-bundling-hard-o00 \
  topogym-horseshoe-ring-easy-o00 \
  topogym-horseshoe-ring-medium-o00 \
  topogym-horseshoe-ring-hard-o00 \
  topogym-cast-coil-easy-o00 \
  topogym-cast-coil-medium-o00 \
  topogym-cast-coil-hard-o00 \
  topogym-cast-keyhole-easy-o00 \
  topogym-cast-keyhole-medium-o00 \
  topogym-cast-keyhole-hard-o00 \
  topogym-buzz-wire-3d-easy-o00 \
  topogym-buzz-wire-3d-medium-o00 \
  topogym-buzz-wire-3d-hard-o00 \
  >> "run_$B.out" 2>&1 &
fi
```

Paste the OpenRouter key only at the hidden prompt. The model key is requested again on every configuration/start invocation; only the HF token is reused. Cancelling or entering an invalid key stops this block before `nohup`, without falling back to the old key. There is one prompt per launch, not per trial. Run the complete block: `nohup scripts/run_agent_batch.sh` alone cannot prompt in the background. For explicit automation only, `--api-key-env OPENROUTER_API_KEY_FOR_SMOKE` reads a fresh value from that named environment variable instead of prompting; it never reuses the saved model key. The separate `--check` option only validates saved files and does not start an experiment.

`EFFORT=default` leaves Muse's own effort default in effect; it does not disable reasoning. You may choose a supported effort before starting the batch, and must keep it unchanged across lanes. Unsupported model/effort combinations stop at the initial model check. That check uses the same Muse binary and compatibility transport, before claiming a trial; it is not proof of task solvability.

For a one-task smoke test, use the following **instead of** the full-batch launch above. It uses Claws easy, both modes and K=3 (**6 trials**), with the same per-trial budgets and production entrypoint:

```bash
REPO=$PWD
export JOBS=$PWD/jobs/agents
B=topogym-claws-muse-jianwen-smoke-20261005-keyprompt01
export ENV_FILE="$HOME/.config/eai/openrouter.env"
if python3 scripts/configure_agent_batch.py --provider openrouter \
  --env-file "$ENV_FILE" --hf-token-file "$HOME/.config/eai/helper-hf.token"; then
AGENT=muse-openrouter MODEL=openrouter/meta/muse-spark-1.3-contributor EFFORT=default \
CODEX_FORCE_AUTH_JSON=0 CODEX_AUTH_JSON_PATH= \
  nohup scripts/run_agent_batch.sh "$B" topogym-interlocked-claws-easy-o00 \
  >> "run_$B.out" 2>&1 &
fi
```

Use the progress commands in section 3 and the **unchanged commands in sections 4–8** with the selected `B` and exported `ENV_FILE`. Scanning reads that same credential file. The HF folder is `helpers/jianwen/$B`; the receiver uses the corresponding original assignment. The formal Muse batch expects 144 trials; the smoke batch expects 6. Do not overwrite or rename jobs from the earlier Codex/Muse experiment.

The maintainer tested this adapter offline, including the actual fixed Muse CLI against a local simulated provider. Real OpenRouter model access and physics rollout remain for the helper smoke run; no paid model call was made during development. Provider HTTP 401 denotes credentials, 402 account credit, and 429 rate/usage limits; these are separate from this experiment's 150M/10M token budget. The [Contributor model disclosure](https://openrouter.ai/meta/muse-spark-1.3-contributor) also applies.

**If the initial Muse model check fails.** The runner prints the failing stage, process exit code, provider/transport error codes and a path to retained redacted diagnostics. Each attempt has its own private directory with `summary.json`, `docker.log`, and any available Muse output and usage report. HTTP 400/403/404/5xx, container startup errors, timeouts and missing usage reports are no longer hidden behind a generic credentials message. These diagnostic files are kept outside the trial archive; never upload the private directory wholesale.

After tool installation and image construction have succeeded, this optional command retries **only the model check**. It can make a short paid model session, but does not build images, claim trials, seal a batch or upload results. Run it from the updated release checkout with the existing OpenRouter credential file:

```bash
B=topogym-rigid-muse-jianwen-20261005-keyprompt01
export JOBS=$PWD/jobs/agents
ENV_FILE="$HOME/.config/eai/openrouter.env" \
CODEX_FORCE_AUTH_JSON=0 CODEX_AUTH_JSON_PATH= \
  .venv-agent-batch/bin/python scripts/check_agent_batch_auth.py \
  --assignment "configs/helper_batches/$B.json" \
  --receipt "$JOBS/../.agent-batch-private/$B/manual-model-check.json"
```

Read the `summary.json` at the printed diagnostics path; it includes the redacted error details. Failed attempts retain their diagnostics even after the temporary container is removed. Use the new batch names in this release for subsequent experiments, preserving older failed batch directories, assignments and sealed inventories. Do not delete old records to bypass a batch-plan mismatch.

## 4. Check for secrets

The runner already scans and redacts each job. Scan once more over everything you will send:

```bash
"$REPO/.venv-agent-batch/bin/python" "$REPO/scripts/scan_secrets.py" "$JOBS" --env-file "$ENV_FILE" --codex-auth "$HOME/.codex/auth.json" --redact
"$REPO/.venv-agent-batch/bin/python" "$REPO/scripts/scan_secrets.py" "$JOBS" --env-file "$ENV_FILE" --codex-auth "$HOME/.codex/auth.json"   # must find none
```

Add --var NAME for any other credential variable you used. With a ChatGPT login, the agent logs may show your account id or email. We redact those before anything becomes public. Tell us if you mind them being in the private upload. For this API-key batch, `~/.codex/auth.json` may be absent; the scanner accepts that conventional missing path.

## 5. Pack the jobs without changing their layout

```bash
H=jianwen
cd "$(dirname "$JOBS")"                      # the directory that contains agents/
tar -czf "${B}__${H}.tar.gz" agents/"$B"-* agents/"$B".log agents/"$B".summary.md \
    $(ls -d agents_mirror/"$B"-* 2>/dev/null) &&
sha256sum "${B}__${H}.tar.gz" > "${B}__${H}.tar.gz.sha256"
```

- `agents/<batch>-*` also picks up `<batch>-rerun-*` jobs. Keep them.
- `agents_mirror/` contains the finalized, scanned copies of the protected agent records. This release makes those copies readable by the helper; `sudo tar` should not be needed. If they are missing or unreadable, report a finalization failure. This assignment requires the mirrors for complete acceptance. Do not package the raw `.agent-batch-private/` directory.
- Do not rename, flatten, re-encode or prune anything inside the jobs.

## 6. Write MANIFEST.md

```text
batch:            topogym-rigid-solxh-jianwen-20261005-v17-keyprompt01 (+ authorized rerun if any)
helper:           jianwen, contact supplied separately
repo:             LUIGIVAMPER/topogym-sweep-release-v1, tag rigid-v17-20261005-muse01-keyprompt01, <actual commit>
host:             <CPU>, <RAM GB>, <GPU model x N>, driver <version>, CUDA <version>
software:         docker <version>, harbor <version>
images:           <image> <RepoDigest or Id>        (one line per image used)
agent:            AGENT=<actual agent>, MODEL=<actual model>, EFFORT=<actual effort>, credentials: API key (no secrets)
lanes / GPUs:     <N runners>, GPUs <ids>
started/finished: <date time, timezone> / <date time, timezone>
unusual events:   crashes, OOM kills, outages, reruns, skipped jobs (job names + what happened)
```

These commands fill most of it:

```bash
git -C "$REPO" rev-parse HEAD
nvidia-smi --query-gpu=name,driver_version --format=csv
docker --version
"$REPO/.venv-agent-batch/bin/harbor" --version
docker image inspect --format '{{.Id}}' topogym-local/rcb-topogym-difficulty:ef700553e0ef3098a2d3-cu128
cp "$JOBS/$B-MANIFEST.md" MANIFEST.md
```

The runner supplies the generated MANIFEST copied above, including the actual model, image IDs and build verification. Locally built images may have no RepoDigest; the recorded image ID and build checks identify this build. The text block is a template for human notes, not a shell command. Use the generated copy unchanged, or write a separate human manifest with the fields above (including exact `batch:` and `helper:` values) to describe incidents. Retain the original sealed records inside `agents/` unchanged.

## 7. Send us the archive

Put the archive, its .sha256 and MANIFEST.md in one folder `upload_<batch>/`, then do one of:

- Hugging Face (private dataset, write token from us):

  ```bash
  mkdir -p "upload_$B"
  cp "${B}__${H}.tar.gz" "${B}__${H}.tar.gz.sha256" MANIFEST.md "upload_$B/" &&
  HF_TOKEN="$(cat "$HOME/.config/eai/helper-hf.token")" \
    "$REPO/.venv-agent-batch/bin/hf" upload eai-v2-internal/helper-uploads "upload_$B" "helpers/$H/$B" --repo-type dataset
  ```

  The runner already installed the pinned HF CLI. Do not run `pip install -U huggingface_hub` inside that environment.

- Shared folder: only if we separately arrange it, upload the three files to the link we sent. This assignment's default target is the HF dataset above.

Then message us the batch name, the archive name and its sha256.
Never upload credentials (~/.codex, .env, tokens), datasets, Docker images, or anything outside this batch's jobs.

## 8. What we do after receiving it

The commands below are for the receiver, after upload. The tool path is the existing installation on the maintainer's machine; the receiver uses its own HF read token. Keep `B` set to the exact batch being accepted (Sol, Muse formal, or Muse smoke), and set `REPO` to the matching release checkout. Use the trusted assignment supplied separately by the maintainer. The examples use the assignment in the fixed release checkout as that trusted original; do not use an assignment taken from the uploaded archive.

```bash
H=jianwen
HF_TOKEN="$(cat "$HOME/.config/eai/helper-hf.token")" \
  "$REPO/.venv-agent-batch/bin/hf" download \
  eai-v2-internal/helper-uploads --repo-type dataset \
  --include "helpers/$H/$B/*" --local-dir "$HOME/rcb_helper_downloads"
cd "$HOME/rcb_helper_downloads/helpers/$H/$B"
sha256sum -c "${B}__${H}.tar.gz.sha256" &&
mkdir -p "$HOME/rcb_helper_runs/$H/jobs" &&
tar -xzf "${B}__${H}.tar.gz" -C "$HOME/rcb_helper_runs/$H/jobs"
```

Checksum verification and extraction do not replace comparison against our saved original assignment. For full acceptance, use the following commands instead of the manual download/extract block above. This is a receiver operation, not an extra helper step.

```bash
TOPOGYM_RECEIVER_PYTHON="$REPO/.venv-agent-batch/bin/python" \
bash "$REPO/bash_scripts/import_helper_results.sh" \
  --assignment "$REPO/configs/helper_batches/$B.json" \
  --work-dir "$HOME/rcb_helper_acceptance/$B" \
  --require-complete \
  --hf-token-file "$HOME/.config/eai/helper-hf.token" &&
cat "$HOME/rcb_helper_acceptance/$B/accepted/$B/review/README.md"
```

The importer pins the HF revision, downloads the delivery files, checks their hashes, safely extracts the archive, and compares the results and evidence against our saved original assignment. For this batch without reruns, it must report `observed_trials: 144` and `delivery_complete: true` for a complete delivery. This does not require all trials to be solved; failures and pending human review remain visible in the report. If acceptance fails, keep the files and investigate the reported reason. For an archive containing authorized reruns, the receiver must also supply each saved rerun assignment with `--rerun-assignment`; the helper's packing layout stays the same.

On another receiver machine, provision the receiver tools, the maintainer's original assignment and a private HF read token first; do not substitute the assignment found inside the helper's archive as the sole source of truth. Run acceptance after the selected batch is uploaded. The formal assignments require 144 trials; the section 3b smoke assignment requires 6.

Review-site publication is a separate receiver operation and is not connected in this release. The importer produces a local review report; uploading to HF or accepting that report does not publish website pages. Site registration commands will be supplied once the site repository and benchmark are available. No additional website step is required from the helper.
